"""Recipes: turn (game, detected info, user settings) into a plan, apply it, undo it.

Everything uplift writes is recorded in a state file so it can be undone exactly:
  ~/.local/share/uplift/state.json        per-game record (original launch options, files, ini keys)
  ~/.local/share/uplift/backups/<appid>/  copies of any game file we replaced
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import detect, steam, system

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "uplift"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "uplift"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "uplift"
STATE = DATA / "state.json"

QUALITY = {  # render scale per axis — AMD's FSR ratios (1.3 / 1.5 / 1.7 / 2.0)
    "native": 1.0, "ultra": 1 / 1.3, "quality": 1 / 1.5, "balanced": 1 / 1.7, "performance": 1 / 2.0,
}
METHODS = ("auto", "off", "unreal", "optiscaler", "gamescope-fsr", "gamescope-nis", "wine-fsr")
LSFG = {"off": None, "x2": ("uplift-x2", 2), "x2-perf": ("uplift-x2-perf", 2), "x3": ("uplift-x3", 3)}

# env vars uplift manages; stripped from the user's own options when we set them
MANAGED_ENV = ("WINE_FULLSCREEN_FSR", "WINE_FULLSCREEN_FSR_STRENGTH", "WINE_FULLSCREEN_FSR_MODE",
               "WINE_FULLSCREEN_FSR_CUSTOM_MODE", "ENABLE_VKBASALT", "VKBASALT_CONFIG_FILE",
               "LSFGVK_PROFILE", "DXVK_FRAME_RATE", "VKD3D_FRAME_RATE", "MANGOHUD", "ENABLE_GAMESCOPE_WSI")


@dataclass
class Settings:
    method: str = "auto"
    quality: str = "quality"
    sharpness: float = 0.4            # 0 = soft … 1 = sharpest (mapped per method)
    monitor: str = ""                 # output monitor name ('' = biggest)
    cas: bool = False                 # vkBasalt CAS on top
    lsfg: str = "off"
    fps_cap: int = -1                 # -1 auto (refresh / multiplier when lsfg is on), 0 off
    gamemode: bool = True
    mangohud: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "Settings":
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class Step:
    kind: str                     # files | ini | launch | lsfg | vkbasalt | warn
    text: str                     # message id (see i18n) — args in .args
    args: dict = field(default_factory=dict)


@dataclass
class Plan:
    appid: str
    name: str
    method: str                   # resolved method
    settings: Settings
    env: dict = field(default_factory=dict)
    wrappers: list = field(default_factory=list)        # list[list[str]]
    dll_overrides: dict = field(default_factory=dict)  # name -> "n,b"
    ini: dict | None = None        # {"path": Path, "section": str, "keys": {k: v}}
    optiscaler: dict | None = None
    vkbasalt_conf: str | None = None
    steps: list[Step] = field(default_factory=list)
    blocked: str | None = None     # reason the main method can't run
    launch_options: str = ""       # final string (filled by compose)

    def warn(self, text, **args):
        self.steps.append(Step("warn", text, args))


# ---------------------------------------------------------------- state

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False))
    os.replace(tmp, STATE)


# ---------------------------------------------------------------- recommendations

def recommend(info: detect.Info, tools: system.Tools, compat: str = "") -> str:
    if info.platform == "windows" and info.has_upscaler_inputs and not info.anticheat:
        return "optiscaler"
    if info.unreal:
        return "unreal"
    if tools.gamescope:
        return "gamescope-fsr"
    if "ge-proton" in compat.lower() or "proton-ge" in compat.lower():
        return "wine-fsr"
    return "off"


def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


def _monitor(settings: Settings) -> system.Monitor:
    for m in system.monitors():
        if m.name == settings.monitor:
            return m
    return system.best_monitor()


# ---------------------------------------------------------------- Unreal Engine.ini

UE_SKIP_DIRS = {"microsoft", "temp", "unrealengine", "nvidia corporation", "nvidia", "d3dscache",
                "crashdumps", "cef", "packages", "programs", "amd", "intel"}


def unreal_config_dir(game: steam.Game, info: detect.Info) -> Path | None:
    """<…>/Saved/Config/<Windows|WindowsNoEditor|Linux> for this game, if the game has created it."""
    cands: list[Path] = []
    if info.platform == "linux":
        base = Path.home() / ".config" / "Epic"
        if base.is_dir():
            cands = [p for p in base.iterdir() if p.is_dir()]
        sub = ("Linux", "LinuxNoEditor")
    else:
        base = game.prefix / "drive_c" / "users" / "steamuser" / "AppData" / "Local"
        if base.is_dir():
            cands = [p for p in base.iterdir() if p.is_dir() and p.name.lower() not in UE_SKIP_DIRS]
        sub = ("Windows", "WindowsNoEditor")
    proj = (info.ue_project or "").lower()
    cands.sort(key=lambda p: (p.name.lower() != proj, -p.stat().st_mtime))
    for c in cands:
        for s in sub:
            d = c / "Saved" / "Config" / s
            if d.is_dir():
                if c.name.lower() == proj or len(cands) == 1 or (d / "GameUserSettings.ini").exists():
                    return d
    return None


def unreal_keys(info: detect.Info, settings: Settings) -> dict:
    pct = int(round(QUALITY.get(settings.quality, 0.67) * 100))
    sharpen = round(max(0.0, min(1.0, settings.sharpness)) * 1.0, 2)
    if info.engine == "unreal5":
        return {"r.AntiAliasingMethod": "4", "r.ScreenPercentage": str(pct), "r.TSR.History.ScreenPercentage": "200",
                "r.Tonemapper.Sharpen": str(sharpen)}
    return {"r.DefaultFeature.AntiAliasing": "2", "r.PostProcessAAQuality": "4", "r.TemporalAA.Upsampling": "1",
            "r.TemporalAA.Algorithm": "1", "r.TemporalAA.UpsampleFiltered": "1",
            "r.ScreenPercentage": str(pct), "r.Tonemapper.Sharpen": str(sharpen)}


def _ini_read(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="surrogateescape").splitlines()
    except OSError:
        return []


def ini_set(path: Path, section: str, keys: dict) -> dict:
    """Set keys in [section]; returns previous values (None = absent). Keeps everything else."""
    lines = _ini_read(path)
    prev: dict = {k: None for k in keys}
    out, i, in_sec, found_sec, done = [], 0, False, False, set()
    for line in lines:
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            if in_sec:
                for k, v in keys.items():
                    if k not in done:
                        out.append(f"{k}={v}")
                        done.add(k)
            in_sec = st[1:-1].strip().lower() == section.lower()
            found_sec = found_sec or in_sec
            out.append(line)
            continue
        if in_sec and "=" in st and not st.startswith(";"):
            k = st.split("=", 1)[0].strip()
            for kk in keys:
                if kk.lower() == k.lower():
                    if prev[kk] is None:
                        prev[kk] = st.split("=", 1)[1]
                    if kk not in done:
                        out.append(f"{kk}={keys[kk]}")
                        done.add(kk)
                    break
            else:
                out.append(line)
            continue
        out.append(line)
    if in_sec:
        for k, v in keys.items():
            if k not in done:
                out.append(f"{k}={v}")
                done.add(k)
    if not found_sec:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[{section}]")
        out += [f"{k}={v}" for k, v in keys.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(out) + "\r\n", encoding="utf-8", errors="surrogateescape")
    return prev


def ini_restore(path: Path, section: str, prev: dict) -> None:
    lines = _ini_read(path)
    out, in_sec = [], False
    for line in lines:
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            in_sec = st[1:-1].strip().lower() == section.lower()
            out.append(line)
            continue
        if in_sec and "=" in st:
            k = st.split("=", 1)[0].strip()
            match = next((kk for kk in prev if kk.lower() == k.lower()), None)
            if match is not None:
                if prev[match] is not None:
                    out.append(f"{match}={prev[match]}")
                continue
        out.append(line)
    # drop an empty [section] we may have created
    clean = []
    for idx, line in enumerate(out):
        if line.strip().lower() == f"[{section.lower()}]":
            rest = [l for l in out[idx + 1:] if l.strip()]
            if not rest or rest[0].strip().startswith("["):
                continue
        clean.append(line)
    path.write_text("\r\n".join(clean) + ("\r\n" if clean else ""), encoding="utf-8", errors="surrogateescape")


# ---------------------------------------------------------------- OptiScaler

OPTI_REPO = "optiscaler/OptiScaler"


def optiscaler_release(log=print) -> Path:
    """Download + extract the latest OptiScaler release (cached). Returns the extracted folder."""
    import urllib.request
    CACHE.mkdir(parents=True, exist_ok=True)
    base = CACHE / "optiscaler"
    base.mkdir(exist_ok=True)
    meta_p = base / "latest.json"
    meta = None
    try:
        if not meta_p.exists() or time.time() - meta_p.stat().st_mtime > 86400:
            req = urllib.request.Request(f"https://api.github.com/repos/{OPTI_REPO}/releases/latest",
                                         headers={"User-Agent": "uplift"})
            with urllib.request.urlopen(req, timeout=20) as r:
                meta = json.loads(r.read())
            meta_p.write_text(json.dumps({"tag": meta["tag_name"], "assets": [
                {"name": a["name"], "url": a["browser_download_url"]} for a in meta["assets"]]}))
        meta = json.loads(meta_p.read_text())
    except Exception:  # noqa: BLE001 — offline: use whatever is cached
        cached = sorted((d for d in base.iterdir() if d.is_dir() and (d / "OptiScaler.dll").exists()),
                        key=lambda d: d.stat().st_mtime)
        if cached:
            return cached[-1]
        raise
    tag = meta["tag"]
    dest = base / tag
    if (dest / "OptiScaler.dll").exists():
        return dest
    asset = next(a for a in meta["assets"] if a["name"].endswith((".7z", ".zip")))
    arc = base / asset["name"]
    if not arc.exists():
        log(f"Downloading OptiScaler {tag}…")
        req = urllib.request.Request(asset["url"], headers={"User-Agent": "uplift"})
        with urllib.request.urlopen(req, timeout=120) as r, open(str(arc) + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(str(arc) + ".part", arc)
    tmp = base / (tag + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    tool = shutil.which("bsdtar") or shutil.which("7z") or shutil.which("7za")
    if not tool:
        raise RuntimeError("need bsdtar (libarchive) or 7z to extract OptiScaler")
    cmd = [tool, "-xf", str(arc), "-C", str(tmp)] if "bsdtar" in tool else [tool, "x", "-y", f"-o{tmp}", str(arc)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    inner = next((p.parent for p in tmp.rglob("OptiScaler.dll")), None)
    if not inner:
        raise RuntimeError("OptiScaler.dll not found in the release archive")
    shutil.move(str(inner), dest) if inner != tmp else os.replace(tmp, dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return dest


def optiscaler_ini(info: detect.Info, settings: Settings, tools: system.Tools) -> dict:
    """{section: {key: value}} overrides for OptiScaler.ini."""
    ratio = 1.0 / max(0.34, QUALITY.get(settings.quality, 0.67))
    only_dlss = set(info.upscalers) & {"DLSS"} and not (set(info.upscalers) & {"XeSS", "FSR2", "FSR3.1", "FSR4"})
    o = {
        "Upscalers": {"Dx11Upscaler": "fsr31", "Dx12Upscaler": "fsr31", "VulkanUpscaler": "fsr31"},
        "Sharpness": {"OverrideSharpness": "true", "Sharpness": f"{max(0.0, min(1.0, settings.sharpness)):.2f}"},
        "UpscaleRatio": {"UpscaleRatioOverrideEnabled": "true", "UpscaleRatioOverrideValue": f"{ratio:.3f}"},
    }
    if tools.nvidia and only_dlss:
        # GTX cards don't expose DLSS: spoof an RTX and use fakenvapi so the game offers its DLSS option
        o["Spoofing"] = {"Dxgi": "true"}
        o["NvApi"] = {"OverrideNvapiDll": "true"}
    elif not only_dlss:
        o["Spoofing"] = {"Dxgi": "false"}
    return o


# ---------------------------------------------------------------- lsfg-vk profiles

LSFG_CONF = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lsfg-vk" / "conf.toml"
LSFG_PROFILES = {
    "uplift-x2": dict(multiplier=2, flow_scale=1.0, performance_mode=False),
    "uplift-x2-perf": dict(multiplier=2, flow_scale=1.0, performance_mode=True),
    "uplift-x3": dict(multiplier=3, flow_scale=0.85, performance_mode=True),
}


def ensure_lsfg_profiles(tools: system.Tools) -> list[str]:
    """Append uplift's profiles to lsfg-vk's conf.toml if missing (never rewrites the user's ones)."""
    added = []
    LSFG_CONF.parent.mkdir(parents=True, exist_ok=True)
    text = LSFG_CONF.read_text() if LSFG_CONF.exists() else "version = 2\n\n[global]\nlog_level = \"info\"\n"
    if "[global]" not in text:
        text = text.rstrip() + "\n\n[global]\n"
    if tools.lsfg_dll and not re.search(r"(?m)^\s*dll\s*=", text):
        text = text.replace("[global]", f'[global]\ndll = "{tools.lsfg_dll}"', 1)
    if tools.nvidia and not re.search(r"(?m)^\s*allow_fp16\s*=", text):
        text = text.replace("[global]", "[global]\nallow_fp16 = false", 1)   # Pascal/Turing: FP16 no faster
    for name, p in LSFG_PROFILES.items():
        if re.search(rf'(?m)^\s*name\s*=\s*"{re.escape(name)}"', text):
            continue
        text = text.rstrip() + (
            f'\n\n[[profile]]\nname = "{name}"\nactive_in = []\nmultiplier = {p["multiplier"]}\n'
            f'flow_scale = {p["flow_scale"]}\nperformance_mode = {str(p["performance_mode"]).lower()}\n'
            f'pacing_mode = "vsync"\noverride_present_mode = true\npreserve_swapchain_image_count = false\n')
        added.append(name)
    LSFG_CONF.write_text(text if text.endswith("\n") else text + "\n")
    return added


# ---------------------------------------------------------------- planning

def defaults_for(info: detect.Info, tools: system.Tools, current_opts: str, saved: dict | None = None) -> Settings:
    """Initial settings: what uplift applied before, else derived from the current launch options."""
    if saved:
        return Settings.from_dict(saved)
    s = Settings()
    o = current_opts or ""
    s.mangohud = bool(re.search(r"(^|\s)(MANGOHUD=1|mangohud)(\s|$)", o))
    s.gamemode = tools.gamemode and (not o or "gamemode" in o)
    return s


def build_plan(game: steam.Game, info: detect.Info, tools: system.Tools, settings: Settings,
               compat: str = "") -> Plan:
    method = settings.method if settings.method != "auto" else recommend(info, tools, compat)
    p = Plan(game.appid, game.name, method, settings)
    mon = _monitor(settings)
    scale = QUALITY.get(settings.quality, 0.67)

    if info.anticheat and method == "optiscaler":
        p.blocked = "anticheat"
        p.method = method = "off"
    if info.anticheat:
        p.warn("warn_anticheat", names=", ".join(info.anticheat))
    if "opengl" in info.notes:
        p.warn("warn_opengl")

    if method == "unreal":
        cfg = unreal_config_dir(game, info)
        if not cfg:
            p.blocked = "unreal_run_once"
        else:
            p.ini = {"path": cfg / "Engine.ini", "section": "SystemSettings", "keys": unreal_keys(info, settings)}
            p.steps.append(Step("ini", "step_unreal", {"pct": int(scale * 100), "path": str(cfg / "Engine.ini"),
                                                      "algo": "TSR" if info.engine == "unreal5" else "TAAU"}))
    elif method == "optiscaler":
        if not info.exe_dir:
            p.blocked = "no_exe"
        else:
            taken = set(info.proxies)
            name = next((n for n in ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "winhttp.dll")
                         if n not in taken), None)
            if not name:
                p.blocked = "proxy_taken"
            else:
                p.optiscaler = {"dir": str(info.exe_dir), "dll": name, "ini": optiscaler_ini(info, settings, tools)}
                p.dll_overrides[name.removesuffix(".dll")] = "n,b"
                if p.optiscaler["ini"].get("NvApi", {}).get("OverrideNvapiDll") == "true":
                    p.warn("warn_dlss_gtx")
                p.steps.append(Step("files", "step_optiscaler", {"dll": name, "dir": str(info.exe_dir),
                                                                 "inputs": ", ".join(sorted(info.upscalers))}))
    elif method in ("gamescope-fsr", "gamescope-nis"):
        if not tools.gamescope:
            p.blocked = "need_gamescope"
        else:
            w, h = _even(mon.width * scale), _even(mon.height * scale)
            filt = "fsr" if method == "gamescope-fsr" else "nis"
            gs = ["gamescope", "-W", str(mon.width), "-H", str(mon.height), "-w", str(w), "-h", str(h),
                  "-r", str(round(mon.refresh)), "-f", "-F", filt]
            # gamescope: 0 = sharpest … 20 = softest
            gs += ["--fsr-sharpness" if filt == "fsr" else "--sharpness", str(int(round((1 - settings.sharpness) * 10)))]
            if settings.mangohud and tools.mangohud:
                gs.append("--mangoapp")
            gs.append("--")
            p.wrappers.append(gs)
            if tools.nvidia:
                # gamescope's WSI layer crashes with any upscaling filter on the proprietary NVIDIA driver
                # (SyncobjFdToHandle → vkImportSemaphoreFdKHR fails → segfault). Without the layer it works.
                p.env["ENABLE_GAMESCOPE_WSI"] = "0"
            p.steps.append(Step("launch", "step_gamescope", {"filter": filt.upper(), "w": w, "h": h,
                                                             "W": mon.width, "H": mon.height}))
    elif method == "wine-fsr":
        p.env["WINE_FULLSCREEN_FSR"] = "1"
        p.env["WINE_FULLSCREEN_FSR_STRENGTH"] = str(int(round((1 - settings.sharpness) * 5)))
        p.steps.append(Step("launch", "step_winefsr", {"w": _even(mon.width * scale), "h": _even(mon.height * scale)}))
        if "ge-proton" not in compat.lower():
            p.warn("warn_winefsr_ge")

    if settings.cas:
        if not tools.vkbasalt:
            p.warn("warn_need_vkbasalt")
        else:
            conf = CONFIG / "vkbasalt" / f"{game.appid}.conf"
            p.vkbasalt_conf = (f"effects = cas\ncasSharpness = {max(0.0, min(1.0, settings.sharpness)):.2f}\n"
                               "toggleKey = Home\nenableOnLaunch = True\n")
            p.env["ENABLE_VKBASALT"] = "1"
            p.env["VKBASALT_CONFIG_FILE"] = str(conf)
            p.steps.append(Step("vkbasalt", "step_cas", {"s": settings.sharpness}))

    lsfg = LSFG.get(settings.lsfg)
    if lsfg:
        if not tools.lsfg:
            p.warn("warn_need_lsfg")
        elif not tools.lsfg_dll:
            p.warn("warn_lsfg_branch" if tools.lossless_dll_only else "warn_need_lossless")
        else:
            prof, mult = lsfg
            p.env["LSFGVK_PROFILE"] = prof
            cap = settings.fps_cap if settings.fps_cap >= 0 else int(round(mon.refresh)) // mult
            if cap > 0:
                p.env["DXVK_FRAME_RATE"] = str(cap)
                p.env["VKD3D_FRAME_RATE"] = str(cap)
            p.steps.append(Step("lsfg", "step_lsfg", {"mult": mult, "cap": cap, "out": cap * mult if cap else 0,
                                                      "perf": settings.lsfg != "x2"}))

    if settings.mangohud and tools.mangohud and not any(w and w[0] == "gamescope" for w in p.wrappers):
        p.wrappers.insert(0, ["mangohud"])
    if settings.gamemode and tools.gamemode:
        p.wrappers.insert(0, ["gamemoderun"])
    return p


# ---------------------------------------------------------------- launch options

_ENV_TOKEN = re.compile(r'''^([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|'[^']*'|\S*)''')
_CMD_TYPO = re.compile(r"%+\s*command\s*%*", re.I)


def normalize(opts: str) -> tuple[str, list[str]]:
    """Fix common mistakes ('%%command', 'gamemode %command%'). Returns (fixed, list of fixes)."""
    fixes = []
    s = opts.strip()
    if s and "%command%" not in s and _CMD_TYPO.search(s):
        s = _CMD_TYPO.sub("%command%", s, count=1)
        fixes.append("fix_command_typo")
    if re.search(r"(^|\s)gamemode(\s+%command%)", s):
        s = re.sub(r"(^|\s)gamemode(\s+%command%)", r"\1gamemoderun\2", s)
        fixes.append("fix_gamemode")
    return s, fixes


def _split_pre(pre: str) -> tuple[list[tuple[str, str]], str]:
    """Leading KEY=VALUE assignments and the rest (user wrappers)."""
    env, rest = [], pre.strip()
    while True:
        m = _ENV_TOKEN.match(rest)
        if not m:
            break
        env.append((m.group(1), m.group(2)))
        rest = rest[m.end():].lstrip()
    return env, rest


def _q(v: str) -> str:
    return v if re.fullmatch(r"[A-Za-z0-9_./,:=+@%-]*", v) else '"' + v.replace('"', '\\"') + '"'


def compose(base: str, plan: Plan) -> str:
    base, _ = normalize(base)
    if "%command%" in base:
        pre, post = base.split("%command%", 1)
    elif base:
        pre, post = "", " " + base       # plain game arguments
    else:
        pre, post = "", ""
    user_env, user_wrap = _split_pre(pre)

    ours = dict(plan.env)
    drop = {k for k in MANAGED_ENV if k in ours or (plan.method != "off" and k.startswith("WINE_FULLSCREEN_FSR"))}
    drop.add("MANGOHUD")          # MangoHud is always driven by the toggle (wrapper or --mangoapp)
    words = user_wrap.split()
    if not plan.settings.gamemode:
        words = [w for w in words if w != "gamemoderun"]
    if not plan.settings.mangohud:
        words = [w for w in words if w != "mangohud"]
    user_wrap = " ".join(words)
    # merge DLL overrides with the user's
    dll = {}
    for k, v in user_env:
        if k == "WINEDLLOVERRIDES":
            for part in v.strip("\"'").split(";"):
                if "=" in part:
                    a, b = part.split("=", 1)
                    dll[a] = b
    dll.update(plan.dll_overrides)
    env_out = [(k, v) for k, v in user_env if k not in drop and k != "WINEDLLOVERRIDES"]
    env_out += [(k, _q(v)) for k, v in ours.items()]
    if dll:
        env_out.append(("WINEDLLOVERRIDES", _q(";".join(f"{a}={b}" for a, b in dll.items()))))

    wrap_words = user_wrap.split()
    our_wraps = []
    for w in plan.wrappers:
        if len(w) == 1 and w[0] in wrap_words:
            continue        # user already has gamemoderun / mangohud
        if w[0] == "gamescope" and "gamescope" in wrap_words:
            continue
        our_wraps.append(" ".join(_q(x) for x in w))
    parts = [f"{k}={v}" for k, v in env_out] + ([user_wrap] if user_wrap else []) + our_wraps + ["%command%"]
    out = " ".join(parts) + post
    out = re.sub(r"\s+", " ", out).strip()
    return "" if out == "%command%" else out


# ---------------------------------------------------------------- apply / undo

def _backup_dir(appid: str) -> Path:
    d = DATA / "backups" / appid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _undo_files(rec: dict, log) -> None:
    for f in reversed(rec.get("files", [])):
        p = Path(f["path"])
        try:
            if f.get("backup"):
                shutil.copy2(f["backup"], p)
            elif p.is_dir():
                shutil.rmtree(p)
            elif p.exists() or p.is_symlink():
                p.unlink()
        except OSError as e:
            log(f"! {p}: {e}")
    ini = rec.get("ini")
    if ini and Path(ini["path"]).exists():
        try:
            ini_restore(Path(ini["path"]), ini["section"], ini["prev"])
        except OSError as e:
            log(f"! {ini['path']}: {e}")


def _apply_files(plan: Plan, rec: dict, log) -> None:
    files = rec.setdefault("files", [])
    if plan.ini:
        path = Path(plan.ini["path"])
        prev = ini_set(path, plan.ini["section"], plan.ini["keys"])
        rec["ini"] = {"path": str(path), "section": plan.ini["section"], "prev": prev}
        log(f"✓ {path}")
    if plan.optiscaler:
        src = optiscaler_release(log)
        dst = Path(plan.optiscaler["dir"])
        bdir = _backup_dir(plan.appid)
        for item in sorted(src.iterdir()):
            if item.name.lower().endswith((".bat", ".sh", ".txt")) or item.name == "Licenses":
                continue
            target = dst / (plan.optiscaler["dll"] if item.name == "OptiScaler.dll" else item.name)
            entry = {"path": str(target), "backup": None}
            if target.exists() and target.is_file():
                b = bdir / target.name
                shutil.copy2(target, b)
                entry["backup"] = str(b)
            elif target.exists():
                log(f"! {target} exists, skipped")
                continue
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
            files.append(entry)
        ini = dst / "OptiScaler.ini"
        for sec, kv in plan.optiscaler["ini"].items():
            ini_set(ini, sec, kv)
        log(f"✓ OptiScaler → {dst} ({plan.optiscaler['dll']})")
    if plan.vkbasalt_conf:
        conf = Path(plan.env["VKBASALT_CONFIG_FILE"])
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(plan.vkbasalt_conf)
        files.append({"path": str(conf), "backup": None})
    if "LSFGVK_PROFILE" in plan.env:
        root = steam.find_steam()
        ensure_lsfg_profiles(system.tools(steam.libraries(root) if root else []))


def apply(root: steam.SteamRoot, plans: list[Plan], restart: bool = True, log=print) -> dict:
    """Apply plans (files first, then launch options with a Steam restart). Returns {appid: options}."""
    st = load_state()
    new_opts: dict[str, str] = {}
    for plan in plans:
        cur = steam.get_launch_options(root, plan.appid)
        rec = st.get(plan.appid)
        if rec and cur == rec.get("written"):
            base = rec["original"]
            _undo_files(rec, log)        # re-apply from a clean slate
        else:
            base = cur
        rec = {"original": base, "settings": asdict(plan.settings), "method": plan.method, "time": int(time.time())}
        try:
            _apply_files(plan, rec, log)
        except Exception as e:  # noqa: BLE001
            _undo_files(rec, log)
            raise RuntimeError(f"{plan.name}: {e}") from e
        opts = compose(base, plan)
        plan.launch_options = opts
        rec["written"] = opts
        new_opts[plan.appid] = opts
        st[plan.appid] = rec
        save_state(st)
    _write_launch(root, new_opts, restart, log)
    return new_opts


def undo(root: steam.SteamRoot, appids: list[str], restart: bool = True, log=print) -> dict:
    st = load_state()
    new_opts = {}
    for appid in appids:
        rec = st.get(appid)
        if not rec:
            continue
        _undo_files(rec, log)
        cur = steam.get_launch_options(root, appid)
        if cur == rec.get("written"):
            new_opts[appid] = rec.get("original", "")
        else:
            log(f"! {appid}: launch options were changed by hand; left as they are")
        del st[appid]
        save_state(st)
        shutil.rmtree(DATA / "backups" / appid, ignore_errors=True)
    _write_launch(root, new_opts, restart, log)
    return new_opts


def _write_launch(root: steam.SteamRoot, opts: dict, restart: bool, log) -> None:
    if not opts:
        return
    cur = {a: steam.get_launch_options(root, a) for a in opts}
    if all(cur[a] == o for a, o in opts.items()):
        return
    was_running = steam.steam_running()
    if was_running:
        if steam.game_running():
            raise RuntimeError("a game is running — close it first")
        if not steam.shutdown(root, log=log):
            raise RuntimeError("could not close Steam")
    steam.set_launch_options(root, opts)
    log("✓ launch options saved")
    if was_running and restart:
        steam.start(root)
        log("✓ Steam restarted")


def applied(appid: str) -> dict | None:
    return load_state().get(appid)

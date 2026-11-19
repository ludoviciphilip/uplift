"""Steam discovery: libraries, installed games, artwork, launch options, restart."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import vdf

STEAM_ID64_BASE = 76561197960265728

# Things in steamapps/common that are not games.
TOOL_PREFIXES = ("Proton", "Steam Linux Runtime", "Steamworks Common", "SteamVR", "Steam Audio")
TOOL_APPIDS = {"228980", "1070560", "1391110", "1628350", "1493710", "2180100", "3658110", "4183110",
               "961940", "993090", "1580130", "1887720", "2348590", "250820"}


@dataclass
class SteamRoot:
    path: Path
    flatpak: bool = False

    @property
    def steamapps(self) -> Path:
        return self.path / "steamapps"


@dataclass
class Game:
    appid: str
    name: str
    installdir: str
    library: Path            # .../steamapps
    size_on_disk: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.library / "common" / self.installdir

    @property
    def compatdata(self) -> Path:
        return self.library / "compatdata" / self.appid

    @property
    def prefix(self) -> Path:
        return self.compatdata / "pfx"


def find_steam() -> SteamRoot | None:
    home = Path.home()
    cands = [
        (home / ".local/share/Steam", False),
        (home / ".steam/steam", False),
        (home / ".steam/root", False),
        (home / ".var/app/com.valvesoftware.Steam/.local/share/Steam", True),
        (home / "snap/steam/common/.local/share/Steam", False),
    ]
    env = os.environ.get("UPLIFT_STEAM_ROOT")
    if env:
        cands.insert(0, (Path(env), False))
    seen = set()
    for p, flat in cands:
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if (rp / "steamapps").is_dir():
            return SteamRoot(rp, flat)
    return None


def libraries(root: SteamRoot) -> list[Path]:
    libs = [root.steamapps]
    lf = root.steamapps / "libraryfolders.vdf"
    if lf.is_file():
        try:
            d = vdf.iget(vdf.load(lf), "libraryfolders") or {}
        except (OSError, vdf.VDFError):
            d = {}
        for v in d.values():
            p = v.get("path") if isinstance(v, dict) else v if isinstance(v, str) else None
            if p:
                sa = Path(p) / "steamapps"
                if sa.is_dir() and sa.resolve() not in [l.resolve() for l in libs]:
                    libs.append(sa)
    return libs


def is_tool(appid: str, name: str) -> bool:
    return appid in TOOL_APPIDS or name.startswith(TOOL_PREFIXES)


def games(root: SteamRoot, include_tools: bool = False) -> list[Game]:
    out: dict[str, Game] = {}
    for lib in libraries(root):
        for acf in sorted(lib.glob("appmanifest_*.acf")):
            try:
                st = vdf.iget(vdf.load(acf), "AppState") or {}
            except (OSError, vdf.VDFError):
                continue
            appid, name = st.get("appid", ""), st.get("name", "")
            if not appid or (not include_tools and is_tool(appid, name)):
                continue
            g = Game(appid, name, st.get("installdir", ""), lib, int(st.get("SizeOnDisk", 0) or 0))
            if g.path.is_dir():
                out[appid] = g
    return sorted(out.values(), key=lambda g: g.name.lower())


ART_NAMES = {
    "cover": ("library_600x900", "library_capsule"),
    "hero": ("library_hero",),
    "header": ("header", "library_header"),
    "logo": ("logo",),
}


def artwork(root: SteamRoot, appid: str, kind: str = "cover") -> Path | None:
    """Local cached artwork. Handles the old flat layout and the newer hashed sub-folders."""
    base = root.path / "appcache" / "librarycache"
    names = ART_NAMES.get(kind, (kind,))
    d = base / appid
    for n in names:
        for p in (d / f"{n}.jpg", d / f"{n}.png", base / f"{appid}_{n}.jpg", base / f"{appid}_{n}.png"):
            if p.is_file():
                return p
        if d.is_dir():
            for ext in ("jpg", "png"):
                for p in d.glob(f"*/{n}.{ext}"):
                    return p
    return None


def artwork_url(appid: str, kind: str = "cover") -> str:
    n = ART_NAMES.get(kind, (kind,))[0]
    return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/{n}.jpg"


def compat_tool(root: SteamRoot, appid: str) -> str:
    """Proton forced for this game ('' = Steam default / native)."""
    try:
        d = vdf.load(root.path / "config" / "config.vdf")
    except (OSError, vdf.VDFError):
        return ""
    m = vdf.iget(d, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping") or {}
    return str(vdf.iget(m, appid, "name", default="") or "")


# ---------------------------------------------------------------- users / launch options

def current_user(root: SteamRoot) -> str | None:
    """accountid (userdata folder name) of the most recent login."""
    users = sorted(p.name for p in (root.path / "userdata").glob("*") if p.name.isdigit() and p.name != "0")
    lu = root.path / "config" / "loginusers.vdf"
    if lu.is_file():
        try:
            d = vdf.iget(vdf.load(lu), "users") or {}
            best = None
            for sid, info in d.items():
                if not sid.isdigit():
                    continue
                acc = str(int(sid) - STEAM_ID64_BASE)
                if acc not in users:
                    continue
                if str(vdf.iget(info, "MostRecent", default="0")) == "1":
                    return acc
                ts = int(vdf.iget(info, "Timestamp", default="0") or 0)
                if best is None or ts > best[0]:
                    best = (ts, acc)
            if best:
                return best[1]
        except (OSError, vdf.VDFError, ValueError):
            pass
    if users:   # fall back to the most recently modified userdata
        return max(users, key=lambda u: (root.path / "userdata" / u).stat().st_mtime)
    return None


def localconfig_path(root: SteamRoot, user: str | None = None) -> Path | None:
    user = user or current_user(root)
    if not user:
        return None
    return root.path / "userdata" / user / "config" / "localconfig.vdf"


def _apps_node(cfg: dict, create: bool = False):
    path = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
    cur = cfg
    for k in path:
        nxt = vdf.iget(cur, k)
        if nxt is None:
            if not create:
                return None
            nxt = vdf.isetdefault(cur, k, {})
        cur = nxt
    return cur


def get_launch_options(root: SteamRoot, appid: str) -> str:
    p = localconfig_path(root)
    if not p or not p.is_file():
        return ""
    apps = _apps_node(vdf.load(p))
    return str(vdf.iget(apps or {}, appid, "LaunchOptions", default="") or "")


def set_launch_options(root: SteamRoot, changes: dict[str, str]) -> Path:
    """Write LaunchOptions for several apps at once. Steam must NOT be running."""
    p = localconfig_path(root)
    if not p or not p.is_file():
        raise FileNotFoundError("localconfig.vdf not found — log into Steam once first")
    cfg = vdf.load(p)
    apps = _apps_node(cfg, create=True)
    for appid, opts in changes.items():
        node = vdf.isetdefault(apps, appid, {})
        if opts:
            for k in list(node):
                if k.lower() == "launchoptions":
                    del node[k]
            node["LaunchOptions"] = opts
        else:
            for k in list(node):
                if k.lower() == "launchoptions":
                    del node[k]
    bak = p.with_suffix(".vdf.uplift-bak")
    shutil.copy2(p, bak)
    tmp = p.with_suffix(".vdf.uplift-tmp")
    vdf.dump(cfg, tmp)
    vdf.load(tmp)  # sanity: must parse back
    os.replace(tmp, p)
    return bak


# ---------------------------------------------------------------- running / restart

def _steam_pids() -> list[int]:
    pids = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            comm = (d / "comm").read_text().strip()
        except OSError:
            continue
        if comm in ("steam", "steamwebhelper"):
            try:
                if (d / "exe").resolve().name in ("steam", "steamwebhelper"):
                    pids.append(int(d.name))
            except OSError:
                pids.append(int(d.name))
    return pids


def steam_running() -> bool:
    if os.environ.get("UPLIFT_TEST"):
        return False
    return any(_pid_comm(p) == "steam" for p in _steam_pids())


def _pid_comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def game_running() -> str | None:
    """appid of a running Steam game (reaper / SteamAppId env), if any."""
    if os.environ.get("UPLIFT_TEST"):
        return None
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            env = (d / "environ").read_bytes()
        except OSError:
            continue
        for item in env.split(b"\0"):
            if item.startswith(b"SteamAppId="):
                v = item.split(b"=", 1)[1].decode(errors="ignore")
                if v and v != "0" and not is_tool(v, ""):
                    return v
    return None


def _steam_cmd(root: SteamRoot) -> list[str]:
    if root.flatpak:
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    return [shutil.which("steam") or "steam"]


def shutdown(root: SteamRoot, timeout: float = 45.0, log=print) -> bool:
    if not steam_running():
        return True
    log("Closing Steam…")
    try:
        subprocess.Popen(_steam_cmd(root) + ["-shutdown"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not steam_running():
            time.sleep(1.0)   # let it finish flushing its files
            return True
        time.sleep(0.5)
    log("Steam did not close in time; sending SIGTERM")
    for pid in _steam_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(3)
    return not steam_running()


def start(root: SteamRoot) -> None:
    subprocess.Popen(_steam_cmd(root) + ["-silent"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

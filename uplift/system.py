"""What the host has: monitors, gamescope, vkBasalt, lsfg-vk, MangoHud, GameMode, GPU."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Monitor:
    name: str
    width: int
    height: int
    refresh: float
    primary: bool = False

    @property
    def label(self) -> str:
        return f"{self.name} — {self.width}×{self.height} @ {round(self.refresh)} Hz"


def _run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _hypr_env() -> dict:
    env = dict(os.environ)
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        run = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        dirs = sorted(glob.glob(f"{run}/hypr/*/.socket.sock"), key=os.path.getmtime, reverse=True)
        if dirs:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = Path(dirs[0]).parent.name
    return env


@lru_cache(maxsize=1)
def monitors() -> tuple[Monitor, ...]:
    out: list[Monitor] = []
    if shutil.which("hyprctl"):
        try:
            data = json.loads(subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True,
                                             timeout=3, env=_hypr_env()).stdout or "[]")
            for m in data:
                if not m.get("disabled"):
                    out.append(Monitor(m["name"], m["width"], m["height"], float(m.get("refreshRate", 60)),
                                       bool(m.get("focused"))))
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
            pass
    if not out and shutil.which("wlr-randr"):
        cur = None
        for line in _run(["wlr-randr"]).splitlines():
            if line and not line.startswith(" "):
                cur = line.split()[0]
            mt = re.search(r"(\d+)x(\d+) px, ([\d.]+) Hz.*current", line)
            if cur and mt:
                out.append(Monitor(cur, int(mt.group(1)), int(mt.group(2)), float(mt.group(3))))
    if not out and shutil.which("xrandr"):
        cur, prim = None, False
        for line in _run(["xrandr", "--current"]).splitlines():
            mt = re.match(r"(\S+) connected( primary)?", line)
            if mt:
                cur, prim = mt.group(1), bool(mt.group(2))
                continue
            mt = re.match(r"\s+(\d+)x(\d+)\s+(.*)", line)
            if cur and mt and "*" in mt.group(3):
                hz = re.search(r"([\d.]+)\*", mt.group(3))
                out.append(Monitor(cur, int(mt.group(1)), int(mt.group(2)), float(hz.group(1)) if hz else 60.0, prim))
                cur = None
    if not out:
        out.append(Monitor("default", 1920, 1080, 60.0, True))
    return tuple(out)


def best_monitor() -> Monitor:
    ms = monitors()
    return max(ms, key=lambda m: (m.width * m.height, m.refresh))


# ---------------------------------------------------------------- tools

def _layer_installed(pattern: str) -> bool:
    dirs = ["/usr/share/vulkan/implicit_layer.d", "/usr/share/vulkan/explicit_layer.d",
            "/etc/vulkan/implicit_layer.d", "/etc/vulkan/explicit_layer.d",
            os.path.expanduser("~/.local/share/vulkan/implicit_layer.d"),
            os.path.expanduser("~/.local/share/vulkan/explicit_layer.d")]
    return any(glob.glob(f"{d}/{pattern}") for d in dirs)


def lsfg_dll(steam_libs: list[Path]) -> Path | None:
    for lib in steam_libs:
        p = lib / "common" / "Lossless Scaling" / "lsfg-vk.dll"
        if p.is_file():
            return p
    return None


@dataclass
class Tools:
    gamescope: bool
    vkbasalt: bool
    lsfg: bool
    lsfg_dll: Path | None
    lossless_dll_only: bool      # Lossless Scaling installed but not on the lsfg-vk beta branch
    mangohud: bool
    gamemode: bool
    nvidia: bool
    gpu: str

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["lsfg_dll"] = str(self.lsfg_dll) if self.lsfg_dll else None
        return d


def gpu_name() -> str:
    out = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if out.strip():
        return out.strip().splitlines()[0]
    for line in _run(["lspci"]).splitlines():
        if re.search(r"VGA|3D|Display", line):
            return line.split(": ", 1)[-1]
    return "unknown"


def tools(steam_libs: list[Path]) -> Tools:
    dll = lsfg_dll(steam_libs)
    ls_plain = any((lib / "common" / "Lossless Scaling" / "Lossless.dll").is_file() for lib in steam_libs)
    gpu = gpu_name()
    return Tools(
        gamescope=bool(shutil.which("gamescope")),
        vkbasalt=_layer_installed("vkBasalt*.json"),
        lsfg=_layer_installed("VkLayer_LSFGVK*.json") or _layer_installed("VkLayer_LS_frame_generation*.json"),
        lsfg_dll=dll,
        lossless_dll_only=ls_plain and dll is None,
        mangohud=bool(shutil.which("mangohud")),
        gamemode=bool(shutil.which("gamemoderun")),
        nvidia="nvidia" in gpu.lower() or "geforce" in gpu.lower() or os.path.exists("/proc/driver/nvidia"),
        gpu=gpu,
    )

"""Inspect an installed game: engine, graphics API, bundled upscalers, anti-cheat."""
from __future__ import annotations

import mmap
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .steam import Game

SKIP_EXE = re.compile(
    r"(unins|setup|install|redist|vc_?redist|dxsetup|dotnet|crash|report|launcher_?helper|"
    r"easyanticheat|eac_|battleye|be(service|launcher)|start_protected|cefprocess|webhelper|"
    r"ue4prereq|ueprereq|prereq|helper|updater|uploader|unitycrashhandler|touchup|7z|dxwebsetup)", re.I)

UPSCALER_FILES = {
    "nvngx_dlss.dll": "DLSS",
    "nvngx_dlssg.dll": "DLSS-FG",
    "nvngx_dlssd.dll": "DLSS-RR",
    "libxess.dll": "XeSS",
    "libxess_dx11.dll": "XeSS",
    "libxess_fg.dll": "XeSS-FG",
    "ffx_fsr2_api_x64.dll": "FSR2",
    "ffx_fsr2_api_dx12_x64.dll": "FSR2",
    "ffx_fsr2_api_vk_x64.dll": "FSR2",
    "ffx_fsr2_api_dx11_x64.dll": "FSR2",
    "amd_fidelityfx_dx12.dll": "FSR3.1",
    "amd_fidelityfx_vk.dll": "FSR3.1",
    "amd_fidelityfx_upscaler_dx12.dll": "FSR4",
    "amd_fidelityfx_loader_dx12.dll": "FSR4",
}
# DLLs a proxy loader (OptiScaler, ReShade) may already occupy.
PROXY_NAMES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "d3d12.dll", "wininet.dll", "winhttp.dll")
ANTICHEAT_DIRS = {"easyanticheat": "EasyAntiCheat", "battleye": "BattlEye", "eaanticheat": "EA AntiCheat",
                  "vanguard": "Vanguard", "nprotect": "nProtect", "xigncode": "XIGNCODE3", "gameguard": "GameGuard"}
ANTICHEAT_FILES = {"easyanticheat_eos_setup.exe": "EasyAntiCheat", "start_protected_game.exe": "EasyAntiCheat",
                   "beservice_x64.exe": "BattlEye", "eaanticheat.gameservicelauncher.exe": "EA AntiCheat"}
API_DLLS = {"d3d12.dll": "DX12", "d3d11.dll": "DX11", "d3d10.dll": "DX10", "d3d10_1.dll": "DX10",
            "d3d9.dll": "DX9", "d3d8.dll": "DX8", "vulkan-1.dll": "Vulkan", "opengl32.dll": "OpenGL",
            "ddraw.dll": "DirectDraw"}

MAX_FILES = 40000


@dataclass
class Info:
    platform: str = "windows"            # windows | linux
    exe: Path | None = None              # main executable
    exe_dir: Path | None = None
    engine: str = "unknown"              # unreal4 | unreal5 | unity | source | ...
    ue_project: str | None = None        # Unreal project name (for config paths)
    apis: list[str] = field(default_factory=list)
    upscalers: dict[str, list[Path]] = field(default_factory=dict)
    anticheat: list[str] = field(default_factory=list)
    proxies: list[str] = field(default_factory=list)   # proxy DLL names already next to the exe
    notes: list[str] = field(default_factory=list)

    @property
    def has_upscaler_inputs(self) -> bool:
        return any(k in self.upscalers for k in ("DLSS", "XeSS", "FSR2", "FSR3.1", "FSR4"))

    @property
    def unreal(self) -> bool:
        return self.engine.startswith("unreal")

    def summary(self) -> dict:
        return {
            "platform": self.platform, "exe": str(self.exe) if self.exe else None, "engine": self.engine,
            "ue_project": self.ue_project, "apis": self.apis, "upscalers": sorted(self.upscalers),
            "anticheat": self.anticheat, "proxies": self.proxies, "notes": self.notes,
        }


def _walk(root: Path, max_depth: int = 6, dirs_seen: set | None = None):
    n = 0
    root_depth = len(root.parts)
    for dp, dns, fns in os.walk(root):
        depth = len(Path(dp).parts) - root_depth
        if depth >= max_depth:
            dns[:] = []
        dns[:] = [d for d in dns if not d.startswith(".") and d.lower() not in ("__installer", "_commonredist", "redist")]
        if dirs_seen is not None:
            dirs_seen.update(d.lower() for d in dns)
        for f in fns:
            n += 1
            if n > MAX_FILES:
                return
            yield Path(dp), f


# ---------------------------------------------------------------- PE import table

def pe_imports(path: Path) -> list[str]:
    """Names of DLLs imported by a PE file (lower-case). Minimal parser, no deps."""
    try:
        with open(path, "rb") as f:
            data = f.read(64)
            if data[:2] != b"MZ":
                return []
            pe_off = struct.unpack_from("<I", data, 0x3C)[0]
            f.seek(pe_off)
            hdr = f.read(24)
            if hdr[:4] != b"PE\0\0":
                return []
            nsec = struct.unpack_from("<H", hdr, 6)[0]
            opt_size = struct.unpack_from("<H", hdr, 20)[0]
            opt = f.read(opt_size)
            magic = struct.unpack_from("<H", opt, 0)[0]
            dd_off = 96 if magic == 0x10B else 112
            imp_rva, _ = struct.unpack_from("<II", opt, dd_off + 8)
            delay_rva = struct.unpack_from("<I", opt, dd_off + 13 * 8)[0] if len(opt) >= dd_off + 14 * 8 else 0
            secs = []
            for _ in range(nsec):
                s = f.read(40)
                vsize, va, rsize, rptr = struct.unpack_from("<IIII", s, 8)
                secs.append((va, max(vsize, rsize), rptr))

            def off(rva):
                for va, sz, ptr in secs:
                    if va <= rva < va + sz:
                        return rva - va + ptr
                return None

            def cstr(o):
                f.seek(o)
                return f.read(256).split(b"\0", 1)[0].decode("ascii", "ignore").lower()

            names = []
            o = off(imp_rva) if imp_rva else None
            while o is not None and len(names) < 512:
                f.seek(o)
                ent = f.read(20)
                if len(ent) < 20 or ent == b"\0" * 20:
                    break
                no = off(struct.unpack_from("<I", ent, 12)[0])
                if no:
                    names.append(cstr(no))
                o += 20
            o = off(delay_rva) if delay_rva else None
            while o is not None and len(names) < 1024:
                f.seek(o)
                ent = f.read(32)
                if len(ent) < 32 or ent == b"\0" * 32:
                    break
                no = off(struct.unpack_from("<I", ent, 4)[0])
                if no:
                    names.append(cstr(no))
                o += 32
            return names
    except (OSError, struct.error):
        return []


_UE_RE = [re.compile(rb"\+\+UE([45])\+Release-([0-9]+\.[0-9]+)"),
          re.compile(rb"\+\0\+\0U\0E\0([45])\0\+\0R\0e\0l\0e\0a\0s\0e\0-\0([0-9])\0\.\0([0-9])\0([0-9]?)\0?")]


def ue_version(path: Path) -> str | None:
    """'4.27', '5.3'… from the branch string Unreal embeds in every build (ASCII or UTF-16)."""
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            mt = _UE_RE[1].search(m)
            if mt:
                return f"{mt.group(2).decode()}.{mt.group(3).decode()}{mt.group(4).decode()}"
            mt = _UE_RE[0].search(m)
            if mt:
                return mt.group(2).decode()
    except (OSError, ValueError):
        pass
    return None


def _contains(path: Path, needles: list[bytes]) -> set[bytes]:
    found = set()
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            for nd in needles:
                if m.find(nd) >= 0:
                    found.add(nd)
    except (OSError, ValueError):
        pass
    return found


def _is_elf(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


# ---------------------------------------------------------------- main

def inspect(game: Game) -> Info:
    info = Info()
    root = game.path
    exes: list[Path] = []
    elfs: list[Path] = []
    dirs_seen: set[str] = set()
    has_unity = has_ue_engine = False

    for dp, f in _walk(root, dirs_seen=dirs_seen):
        fl = f.lower()
        p = dp / f
        for part in dp.relative_to(root).parts:
            dirs_seen.add(part.lower())
        if fl in UPSCALER_FILES:
            info.upscalers.setdefault(UPSCALER_FILES[fl], []).append(p)
        if fl in ANTICHEAT_FILES and ANTICHEAT_FILES[fl] not in info.anticheat:
            info.anticheat.append(ANTICHEAT_FILES[fl])
        if fl == "unityplayer.dll" or fl == "globalgamemanagers":
            has_unity = True
        if fl.endswith(".exe") and not SKIP_EXE.search(fl):
            exes.append(p)
        elif "." not in f or fl.endswith((".x86_64", ".x86", ".sh")):
            try:
                if p.is_file() and os.access(p, os.X_OK) and p.stat().st_size > 512 * 1024 and _is_elf(p):
                    elfs.append(p)
            except OSError:
                pass

    for d, name in ANTICHEAT_DIRS.items():
        if d in dirs_seen and name not in info.anticheat:
            info.anticheat.append(name)
    has_ue_engine = "engine" in dirs_seen and "binaries" in dirs_seen

    shipping = [e for e in exes if e.name.lower().endswith("-shipping.exe")]
    if shipping:
        info.exe = max(shipping, key=lambda p: p.stat().st_size)
    elif exes:
        info.exe = max(exes, key=lambda p: p.stat().st_size)
    elif elfs:
        info.exe = max(elfs, key=lambda p: p.stat().st_size)
        info.platform = "linux"
    if exes and elfs and not game.prefix.exists():
        info.platform = "linux"
        info.exe = max(elfs, key=lambda p: p.stat().st_size)
    info.exe_dir = info.exe.parent if info.exe else root

    # engine
    if shipping or has_ue_engine:
        exe = shipping[0] if shipping else info.exe
        info.engine = "unreal4"
        if exe:
            m = re.match(r"(.+?)-win64-shipping\.exe$", exe.name, re.I)
            # <root>/<Project>/Binaries/Win64/<x>-Win64-Shipping.exe
            if len(exe.parents) >= 3 and exe.parent.name.lower() == "win64":
                info.ue_project = exe.parents[2].name
            elif m:
                info.ue_project = m.group(1)
            ver = ue_version(exe)
            if ver:
                info.engine = "unreal5" if ver.startswith("5") else "unreal4"
                info.notes.append(f"ue-{ver}")
            elif (root / "Engine" / "Binaries" / "ThirdParty" / "DbgHelp").is_dir():
                info.engine = "unreal5"
    elif has_unity:
        info.engine = "unity"
    elif any(root.glob("*/gameinfo.txt")):
        info.engine = "source"

    # graphics APIs
    if info.exe and info.platform == "windows":
        imps = set(pe_imports(info.exe))
        for dll, api in API_DLLS.items():
            if dll in imps and api not in info.apis:
                info.apis.append(api)
        if info.unreal:
            # UE links every RHI it was built with; the one used comes from the game's config
            info.apis = [a for a in ("DX12", "DX11") if a in info.apis] or ["DX11/DX12"]
        if info.engine == "unity" and not info.apis:
            info.apis = ["DX11"]
        if not info.apis and "dxgi.dll" in imps:
            info.apis = ["DX10/11"]
        if info.exe_dir:
            info.proxies = [n for n in PROXY_NAMES if (info.exe_dir / n).exists()]
    elif info.exe and info.platform == "linux":
        found = _contains(info.exe, [b"libvulkan.so", b"libGL.so", b"libEGL.so"])
        if b"libvulkan.so" in found:
            info.apis.append("Vulkan")
        if b"libGL.so" in found or b"libEGL.so" in found:
            info.apis.append("OpenGL")

    if "OpenGL" in info.apis and "Vulkan" not in info.apis and not any(a.startswith("DX") for a in info.apis):
        info.notes.append("opengl")
    return info

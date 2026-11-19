"""End-to-end test on a fake Steam tree: apply → check files/launch options → undo → identical.

Run:  python3 -m unittest discover -s tests -v
Uses the real OptiScaler release (downloaded once into ~/.cache/uplift).
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="uplift-test-"))
os.environ.update({
    "UPLIFT_TEST": "1",
    "UPLIFT_STEAM_ROOT": str(TMP / "Steam"),
    "XDG_DATA_HOME": str(TMP / "data"),
    "XDG_CONFIG_HOME": str(TMP / "config"),
    "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")),
    "UPLIFT_LANG": "en",
})

from uplift import core, detect, steam, system, vdf  # noqa: E402
from uplift.library import Library  # noqa: E402


def pe_exe(path: Path, imports: list[str], extra: bytes = b""):
    """Smallest PE32+ that our import parser understands."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sec_rva, sec_raw = 0x1000, 0x200
    names_off = 20 * (len(imports) + 1)
    blob = bytearray()
    strings = bytearray()
    for i, n in enumerate(imports):
        blob += struct.pack("<IIIII", 0, 0, 0, sec_rva + names_off + len(strings), 0)
        strings += n.encode() + b"\0"
    blob += b"\0" * 20 + strings
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)                  # PE32+
    struct.pack_into("<II", opt, 112 + 8, sec_rva, len(blob))  # import directory
    hdr = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, len(opt), 0x22)
    sec = b".idata\0\0" + struct.pack("<IIIIIIHHI", len(blob), sec_rva, len(blob), sec_raw, 0, 0, 0, 0, 0)
    mz = bytearray(0x40)
    mz[:2] = b"MZ"
    struct.pack_into("<I", mz, 0x3C, 0x40)
    head = bytes(mz) + hdr + bytes(opt) + sec
    data = head + b"\0" * (sec_raw - len(head)) + bytes(blob) + extra
    path.write_bytes(data)


def acf(lib: Path, appid: str, name: str, installdir: str):
    (lib / f"appmanifest_{appid}.acf").write_text(vdf.dumps({"AppState": {
        "appid": appid, "name": name, "installdir": installdir, "SizeOnDisk": "1"}}))


def tree_hash(p: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        h.update(str(f.relative_to(p)).encode())
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = TMP / "Steam"
        sa = s / "steamapps"
        (sa / "common").mkdir(parents=True)
        (s / "config").mkdir()
        (s / "userdata" / "12345" / "config").mkdir(parents=True)
        (s / "config" / "loginusers.vdf").write_text(vdf.dumps({"users": {str(76561197960265728 + 12345): {
            "AccountName": "t", "MostRecent": "1", "Timestamp": "1"}}}))
        (sa / "libraryfolders.vdf").write_text(vdf.dumps({"libraryfolders": {"0": {"path": str(s)}}}))
        # Unreal 4 game, already run once (config exists)
        acf(sa, "100", "Unreal Game", "UnrealGame")
        pe_exe(sa / "common/UnrealGame/MyProj/Binaries/Win64/MyProj-Win64-Shipping.exe", ["kernel32.dll", "d3d12.dll"],
               "++UE4+Release-4.27".encode("utf-16-le"))
        (sa / "common/UnrealGame/Engine/Binaries").mkdir(parents=True)
        cfg = sa / "compatdata/100/pfx/drive_c/users/steamuser/AppData/Local/MyProj/Saved/Config/WindowsNoEditor"
        cfg.mkdir(parents=True)
        (cfg / "Engine.ini").write_text("[Core.System]\r\nPaths=../../../Engine/Content\r\n\r\n[SystemSettings]\r\nr.ScreenPercentage=100\r\nfoo=1\r\n")
        # DX12 game with DLSS + FSR2
        acf(sa, "200", "Upscaler Game", "UpGame")
        pe_exe(sa / "common/UpGame/bin/UpGame.exe", ["d3d12.dll", "dxgi.dll"])
        (sa / "common/UpGame/bin/nvngx_dlss.dll").write_bytes(b"x")
        (sa / "common/UpGame/bin/ffx_fsr2_api_x64.dll").write_bytes(b"y")
        (sa / "compatdata/200/pfx").mkdir(parents=True)
        # Plain DX11 game with a broken launch option
        acf(sa, "300", "Plain Game", "Plain")
        pe_exe(sa / "common/Plain/Plain.exe", ["d3d11.dll"])
        # Anti-cheat game with DLSS
        acf(sa, "400", "Protected Game", "Prot")
        pe_exe(sa / "common/Prot/Prot.exe", ["d3d12.dll"])
        (sa / "common/Prot/nvngx_dlss.dll").write_bytes(b"x")
        (sa / "common/Prot/EasyAntiCheat").mkdir()
        # a tool that must be hidden
        acf(sa, "1493710", "Proton Experimental", "Proton - Experimental")
        (sa / "common/Proton - Experimental").mkdir()

        (s / "userdata/12345/config/localconfig.vdf").write_text(vdf.dumps({"UserLocalConfigStore": {"Software": {"Valve": {"Steam": {"apps": {"999": {"LastPlayed": "1"}}}}}}}))
        steam.set_launch_options(steam.find_steam(), {"300": "gamemode %%command", "100": "MANGOHUD=1 %command% -dx12"})
        cls.root = steam.find_steam()
        cls.before = {d: tree_hash(sa / "common" / d) for d in ("UnrealGame", "UpGame", "Plain")}
        cls.ini_before = (cfg / "Engine.ini").read_bytes()
        cls.cfg = cfg

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_1_detect(self):
        lib = Library()
        lib.load()
        names = {e.appid: e for e in lib.entries}
        self.assertNotIn("1493710", names)
        u = names["100"]
        self.assertEqual(u.info.engine, "unreal4")
        self.assertEqual(u.info.ue_project, "MyProj")
        self.assertEqual(u.recommended, "unreal")
        up = names["200"]
        self.assertEqual(set(up.info.upscalers), {"DLSS", "FSR2"})
        self.assertIn("DX12", up.info.apis)
        self.assertEqual(up.recommended, "optiscaler")
        self.assertEqual(names["300"].info.apis, ["DX11"])
        self.assertEqual(names["400"].info.anticheat, ["EasyAntiCheat"])
        self.assertNotEqual(names["400"].recommended, "optiscaler")

    def test_2_compose(self):
        p = core.Plan("1", "x", "off", core.Settings(gamemode=True, mangohud=False))
        p.env = {"LSFGVK_PROFILE": "uplift-x2"}
        p.wrappers = [["gamemoderun"]]
        p.dll_overrides = {"dxgi": "n,b"}
        self.assertEqual(core.compose('WINEDLLOVERRIDES="d3d9=n,b" FOO=1 mangohud %command% -fs', p),
                         "FOO=1 LSFGVK_PROFILE=uplift-x2 WINEDLLOVERRIDES=d3d9=n,b;dxgi=n,b gamemoderun %command% -fs"
                         .replace("d3d9=n,b;dxgi=n,b", '"d3d9=n,b;dxgi=n,b"'))
        self.assertEqual(core.compose("-novid", p),
                         "LSFGVK_PROFILE=uplift-x2 WINEDLLOVERRIDES=dxgi=n,b gamemoderun %command% -novid")
        self.assertEqual(core.normalize("gamemode %%command")[0], "gamemoderun %command%")

    def test_3_apply_undo(self):
        lib = Library()
        lib.load()
        lib.tools.lsfg = True
        lib.tools.lsfg_dll = TMP / "lsfg-vk.dll"
        plans = []
        for appid, extra in (("100", {}), ("200", {"quality": "balanced"}), ("300", {"lsfg": "x2-perf", "method": "off"})):
            e = lib.get(appid)
            s = e.settings(lib.tools)
            for k, v in extra.items():
                setattr(s, k, v)
            plans.append(lib.plan(e, s))
        core.apply(self.root, plans, log=lambda *_: None)

        ini = (self.cfg / "Engine.ini").read_text()
        self.assertIn("r.ScreenPercentage=67", ini)
        self.assertIn("r.TemporalAA.Upsampling=1", ini)
        self.assertIn("foo=1", ini)
        self.assertEqual(ini.count("r.ScreenPercentage"), 1)
        bin_ = self.root.steamapps / "common/UpGame/bin"
        self.assertTrue((bin_ / "dxgi.dll").exists())
        self.assertTrue((bin_ / "OptiScaler.ini").exists())
        oi = (bin_ / "OptiScaler.ini").read_text()
        self.assertIn("Dx12Upscaler=fsr31", oi)
        self.assertIn("Dxgi=false", oi)            # has FSR2 inputs → no spoofing needed
        self.assertIn("UpscaleRatioOverrideValue=1.700", oi)
        lo = {a: steam.get_launch_options(self.root, a) for a in ("100", "200", "300")}
        self.assertEqual(lo["100"], "mangohud %command% -dx12")
        self.assertIn("WINEDLLOVERRIDES=dxgi=n,b", lo["200"])
        self.assertTrue(lo["300"].startswith("LSFGVK_PROFILE=uplift-x2-perf DXVK_FRAME_RATE="))
        self.assertIn("gamemoderun %command%", lo["300"])
        conf = (TMP / "config/lsfg-vk/conf.toml").read_text()
        self.assertIn('name = "uplift-x2-perf"', conf)

        # applying again must not stack anything
        core.apply(self.root, plans, log=lambda *_: None)
        self.assertEqual(steam.get_launch_options(self.root, "100"), lo["100"])
        self.assertEqual((self.cfg / "Engine.ini").read_text().count("r.ScreenPercentage"), 1)

        core.undo(self.root, ["100", "200", "300"], log=lambda *_: None)
        self.assertEqual((self.cfg / "Engine.ini").read_bytes(), self.ini_before)
        for d, h in self.before.items():
            self.assertEqual(tree_hash(self.root.steamapps / "common" / d), h, d)
        self.assertEqual(steam.get_launch_options(self.root, "100"), "MANGOHUD=1 %command% -dx12")
        self.assertEqual(steam.get_launch_options(self.root, "300"), "gamemode %%command")
        self.assertEqual(core.load_state(), {})

    def test_3b_gamescope_nvidia(self):
        lib = Library()
        lib.load()
        lib.tools.gamescope = True
        lib.tools.nvidia = True
        e = lib.get("300")
        s = e.settings(lib.tools)
        s.method, s.quality, s.monitor = "gamescope-fsr", "quality", ""
        from uplift import system as sysm
        sysm.monitors.cache_clear()
        sysm.monitors.__wrapped__  # noqa: B018
        p = lib.plan(e, s)
        self.assertEqual(p.env.get("ENABLE_GAMESCOPE_WSI"), "0")
        self.assertIn("ENABLE_GAMESCOPE_WSI=0", p.launch_options)
        gs = p.wrappers[-1]
        W, H = int(gs[gs.index("-W") + 1]), int(gs[gs.index("-H") + 1])
        w, h = int(gs[gs.index("-w") + 1]), int(gs[gs.index("-h") + 1])
        self.assertEqual((w, h), (round(W / 1.5 / 2) * 2, round(H / 1.5 / 2) * 2))
        lib.tools.nvidia = False
        self.assertNotIn("ENABLE_GAMESCOPE_WSI", lib.plan(e, s).env)

    def test_4_pe_parser_real_dll(self):
        # sanity on a real Windows binary if Proton is around
        for p in Path.home().glob(".local/share/Steam/steamapps/common/Proton*/files/lib/wine/x86_64-windows/dxgi.dll"):
            self.assertIsInstance(detect.pe_imports(p), list)
            break


if __name__ == "__main__":
    unittest.main(verbosity=2)

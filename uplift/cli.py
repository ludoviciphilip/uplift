"""Command line: uplift list | show | apply | undo | doctor  (no args → GUI, --tui → terminal UI)."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, core
from .i18n import t
from .library import Library


def _fmt_info(e) -> list[str]:
    i = e.info
    return [
        f"  {t('platform')}: {t('native_linux') if i.platform == 'linux' else t('windows_proton')}"
        + (f"  [{e.compat}]" if e.compat else ""),
        f"  {t('engine')}: {i.engine}" + (f" ({i.ue_project})" if i.ue_project else ""),
        f"  {t('api')}: {', '.join(i.apis) or t('unknown')}",
        f"  {t('upscalers')}: {', '.join(sorted(i.upscalers)) or t('none')}",
        f"  {t('anticheat')}: {', '.join(i.anticheat) or t('none')}",
    ]


def _settings_from_args(e, lib, a) -> core.Settings:
    s = e.settings(lib.tools)
    for k in ("method", "quality", "sharpness", "monitor", "lsfg", "fps_cap"):
        v = getattr(a, k, None)
        if v is not None:
            setattr(s, k, v)
    for k in ("cas", "gamemode", "mangohud"):
        v = getattr(a, k, None)
        if v is not None:
            setattr(s, k, v)
    return s


def _print_plan(p, e):
    print(f"{e.game.name}  →  {t('m_' + p.method)}")
    if p.blocked:
        print(f"  ✗ {t('blocked_' + p.blocked)}")
    for st in p.steps:
        mark = "!" if st.kind == "warn" else "•"
        print(f"  {mark} {t(st.text, **st.args)}")
    _, fixes = core.normalize(e.launch)
    for f in fixes:
        print(f"  ✎ {t(f)}")
    print(f"  {t('launch_preview')}: {p.launch_options or '(—)'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="uplift", description=t("app_subtitle"))
    ap.add_argument("--version", action="version", version=f"uplift {__version__}")
    ap.add_argument("--tui", action="store_true", help="terminal interface")
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("list", help="installed games and what Uplift recommends")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("show", help="details + plan for one game")
    sp.add_argument("game", help="appid or part of the name")
    for name in ("apply", "plan"):
        sp = sub.add_parser(name, help="apply settings to games" if name == "apply" else "dry run")
        sp.add_argument("games", nargs="+")
        sp.add_argument("--method", choices=core.METHODS)
        sp.add_argument("--quality", choices=list(core.QUALITY))
        sp.add_argument("--sharpness", type=float)
        sp.add_argument("--monitor")
        sp.add_argument("--lsfg", choices=list(core.LSFG))
        sp.add_argument("--fps-cap", dest="fps_cap", type=int)
        sp.add_argument("--cas", action=argparse.BooleanOptionalAction, default=None)
        sp.add_argument("--gamemode", action=argparse.BooleanOptionalAction, default=None)
        sp.add_argument("--mangohud", action=argparse.BooleanOptionalAction, default=None)
        sp.add_argument("--no-restart", action="store_true", help="don't reopen Steam afterwards")
        sp.add_argument("-y", "--yes", action="store_true", help="don't ask before restarting Steam")
    sp = sub.add_parser("undo", help="restore games to how they were")
    sp.add_argument("games", nargs="+")
    sp.add_argument("--no-restart", action="store_true")
    sp.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("doctor", help="check tools, monitors and Steam")
    a = ap.parse_args(argv)

    if a.cmd is None:
        if a.tui:
            from .tui import run
        else:
            try:
                from .gui import run
            except Exception as ex:  # noqa: BLE001 — no GTK: fall back to the TUI
                print(f"GUI unavailable ({ex}); starting the terminal UI", file=sys.stderr)
                from .tui import run
        return run()

    lib = Library()
    if not lib.root:
        print(t("no_steam"), file=sys.stderr)
        return 1
    lib.load()

    if a.cmd == "doctor":
        from . import system
        print(f"Steam: {lib.root.path}" + (" (flatpak)" if lib.root.flatpak else ""))
        print("Libraries: " + ", ".join(str(p) for p in lib.libs))
        print(f"GPU: {lib.tools.gpu}")
        for m in system.monitors():
            print(f"{t('monitor')}: {m.label}")
        for k, v in lib.tools.as_dict().items():
            if k != "gpu":
                print(f"  {k}: {v}")
        miss = lib.missing_tools()
        if miss:
            print(t("missing_tools", names=", ".join(miss)))
            for n, cmd in miss.items():
                print(f"  {n}: {cmd}")
        return 0

    if a.cmd == "list":
        if a.json:
            print(json.dumps([{"appid": e.appid, "name": e.game.name, "recommended": e.recommended,
                               "applied": bool(e.applied), **e.info.summary()} for e in lib.entries],
                             indent=2, ensure_ascii=False))
            return 0
        for e in lib.entries:
            flag = "✓" if e.applied else " "
            ups = ",".join(sorted(e.info.upscalers)) or "-"
            print(f"{flag} {e.appid:>8}  {e.game.name[:38]:38}  {e.info.engine:9} {ups:12} → {t('m_' + e.recommended)}")
        return 0

    def pick(keys):
        out = []
        for k in keys:
            e = lib.get(k)
            if not e:
                print(f"? {k}", file=sys.stderr)
                sys.exit(2)
            out.append(e)
        return out

    if a.cmd == "show":
        e = pick([a.game])[0]
        print(e.game.name, f"({e.appid})")
        print("\n".join(_fmt_info(e)))
        print(f"  {t('launch_preview')}: {e.launch or '(—)'}")
        p = lib.plan(e, e.settings(lib.tools))
        print()
        _print_plan(p, e)
        return 0

    if a.cmd in ("plan", "apply"):
        plans = []
        for e in pick(a.games):
            p = lib.plan(e, _settings_from_args(e, lib, a))
            _print_plan(p, e)
            plans.append(p)
        if a.cmd == "plan":
            return 0
        from . import steam
        if steam.steam_running() and not a.yes:
            if input(f"\n{t('restart_body')} [y/N] ").strip().lower() not in ("y", "s", "yes", "sim"):
                return 1
        core.apply(lib.root, plans, restart=not a.no_restart)
        print(t("done"))
        return 0

    if a.cmd == "undo":
        from . import steam
        es = pick(a.games)
        if steam.steam_running() and not a.yes:
            if input(f"{t('restart_body')} [y/N] ").strip().lower() not in ("y", "s", "yes", "sim"):
                return 1
        core.undo(lib.root, [e.appid for e in es], restart=not a.no_restart)
        print(t("undone"))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

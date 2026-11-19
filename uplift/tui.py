"""Terminal UI (Textual). `uplift --tui`"""
from __future__ import annotations

import sys

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Select, Static, Switch
except ImportError:  # pragma: no cover
    App = None

from . import core, steam, system
from .i18n import t
from .library import Library

QUALITIES = list(core.QUALITY)
LSFG_KEYS = list(core.LSFG)


if App is not None:
    class Confirm(ModalScreen[bool]):
        DEFAULT_CSS = """
        Confirm { align: center middle; }
        #box { width: 64; height: auto; padding: 1 2; border: thick $accent; background: $surface; }
        #btns { height: auto; margin-top: 1; align-horizontal: right; }
        Button { margin-left: 1; }
        """

        def compose(self) -> ComposeResult:
            with Vertical(id="box"):
                yield Label(f"[b]{t('restart_title')}[/b]")
                yield Label(t("restart_body"))
                with Horizontal(id="btns"):
                    yield Button(t("cancel"), id="no")
                    yield Button(t("continue"), id="yes", variant="primary")

        @on(Button.Pressed)
        def _btn(self, ev: Button.Pressed) -> None:
            self.dismiss(ev.button.id == "yes")

    class UpliftTUI(App):
        TITLE = "Uplift"
        SUB_TITLE = t("app_subtitle")
        CSS = """
        #games { width: 42; border-right: tall $panel; }
        #detail { padding: 0 2; }
        .h { margin-top: 1; text-style: bold; color: $accent; }
        .row { height: 3; }
        .row Label { width: 30; padding-top: 1; }
        .row Select { width: 1fr; }
        #launch { border: round $panel; padding: 0 1; margin-top: 1; }
        #plan { margin-top: 1; }
        #search { margin: 0 1; }
        """
        BINDINGS = [
            Binding("a", "apply", t("apply")),
            Binding("u", "undo", t("undo")),
            Binding("r", "reload", "Reload"),
            Binding("/", "focus_search", t("search")),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(self):
            super().__init__()
            self.lib = Library()
            self.entry = None
            self._building = False

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                with Vertical(id="games"):
                    yield Input(placeholder=t("search"), id="search")
                    yield ListView(id="list")
                with VerticalScroll(id="detail"):
                    yield Static(t("app_subtitle"), id="title")
                    yield Static("", id="info")
                    yield Label(t("upscaling"), classes="h")
                    with Horizontal(classes="row"):
                        yield Label(t("method"))
                        yield Select([(t("m_" + m), m) for m in core.METHODS], id="method", allow_blank=False, value="auto")
                    with Horizontal(classes="row"):
                        yield Label(t("quality"))
                        yield Select([(t("q_" + q), q) for q in QUALITIES], id="quality", allow_blank=False,
                                     value="quality")
                    with Horizontal(classes="row"):
                        yield Label(t("sharpness"))
                        yield Select([(f"{v/20:.2f}", v / 20) for v in range(0, 21)], id="sharpness",
                                     allow_blank=False, value=0.4)
                    with Horizontal(classes="row"):
                        yield Label(t("monitor"))
                        yield Select([(m.label, m.name) for m in system.monitors()], id="monitor",
                                     allow_blank=False, value=system.best_monitor().name)
                    yield Label(t("extras"), classes="h")
                    with Horizontal(classes="row"):
                        yield Label(t("framegen"))
                        yield Select([(t("fg_" + k), k) for k in LSFG_KEYS], id="lsfg", allow_blank=False, value="off")
                    for sid, key in (("cas", "cas"), ("gamemode", "gamemode"), ("mangohud", "mangohud")):
                        with Horizontal(classes="row"):
                            yield Label(t(key))
                            yield Switch(id=sid)
                    yield Static("", id="launch")
                    yield Static("", id="plan")
            yield Footer()

        def on_mount(self) -> None:
            self.action_reload()

        @work(thread=True, exclusive=True)
        def action_reload(self) -> None:
            entries = self.lib.load()
            self.call_from_thread(self._fill, entries)

        def _fill(self, entries) -> None:
            lv = self.query_one("#list", ListView)
            lv.clear()
            if not self.lib.root:
                self.query_one("#title", Static).update(t("no_steam"))
                return
            q = self.query_one("#search", Input).value.lower().strip()
            for e in entries:
                if q and q not in e.game.name.lower():
                    continue
                mark = "[green]●[/] " if e.applied else "  "
                item = ListItem(Label(f"{mark}{e.game.name}\n   [dim]{t('m_' + ((e.applied or {}).get('method') or e.recommended))}[/]"))
                item.entry = e
                lv.append(item)
            miss = self.lib.missing_tools()
            if miss:
                self.notify(t("missing_tools", names=", ".join(miss)), severity="warning", timeout=8)
            if entries and self.entry is None:
                lv.index = 0
                self._show(lv.children[0].entry if lv.children else entries[0])

        @on(Input.Changed, "#search")
        def _search(self, _ev) -> None:
            self._fill(self.lib.entries)

        def action_focus_search(self) -> None:
            self.query_one("#search", Input).focus()

        @on(ListView.Highlighted, "#list")
        def _hl(self, ev: ListView.Highlighted) -> None:
            if ev.item is not None and getattr(ev.item, "entry", None):
                self._show(ev.item.entry)

        def _show(self, e) -> None:
            self.entry = e
            self._building = True
            s = e.settings(self.lib.tools)
            i = e.info
            self.query_one("#title", Static).update(f"[b]{e.game.name}[/b]  [dim]AppID {e.appid}"
                                                    + (f" · {e.compat}" if e.compat else "") + "[/]")
            self.query_one("#info", Static).update(
                f"{t('engine')}: {i.engine}   {t('api')}: {', '.join(i.apis) or '?'}   "
                f"{t('upscalers')}: {', '.join(sorted(i.upscalers)) or t('none')}   "
                f"{t('anticheat')}: {', '.join(i.anticheat) or t('none')}")
            meth = self.query_one("#method", Select)
            meth.set_options([(t("m_" + m) + (f" → {t('m_' + e.recommended)}" if m == "auto" else ""), m)
                              for m in core.METHODS])
            meth.value = s.method
            self.query_one("#quality", Select).value = s.quality
            self.query_one("#sharpness", Select).value = round(round(s.sharpness * 20) / 20, 2)
            mons = [m.name for m in system.monitors()]
            self.query_one("#monitor", Select).value = s.monitor if s.monitor in mons else system.best_monitor().name
            self.query_one("#lsfg", Select).value = s.lsfg
            self.query_one("#cas", Switch).value = s.cas
            self.query_one("#gamemode", Switch).value = s.gamemode
            self.query_one("#mangohud", Switch).value = s.mangohud
            self._building = False
            self._update_plan()

        def _settings(self) -> core.Settings:
            s = core.Settings()
            s.method = self.query_one("#method", Select).value
            s.quality = self.query_one("#quality", Select).value
            s.sharpness = float(self.query_one("#sharpness", Select).value)
            s.monitor = self.query_one("#monitor", Select).value
            s.lsfg = self.query_one("#lsfg", Select).value
            s.cas = self.query_one("#cas", Switch).value
            s.gamemode = self.query_one("#gamemode", Switch).value
            s.mangohud = self.query_one("#mangohud", Switch).value
            return s

        @on(Select.Changed)
        @on(Switch.Changed)
        def _changed(self, _ev) -> None:
            if not self._building and self.entry:
                self._update_plan()

        def _update_plan(self) -> None:
            p = self.lib.plan(self.entry, self._settings())
            self.plan = p
            self.query_one("#launch", Static).update(f"[b]{t('launch_preview')}[/b]\n{p.launch_options or '—'}")
            lines = []
            if p.blocked:
                lines.append(f"[red]✗ {t('blocked_' + p.blocked)}[/]")
            for st in p.steps:
                lines.append(f"[yellow]! {t(st.text, **st.args)}[/]" if st.kind == "warn"
                             else f"[green]✓[/] {t(st.text, **st.args)}")
            for f in core.normalize(self.entry.launch)[1]:
                lines.append(f"[cyan]✎ {t(f)}[/]")
            self.query_one("#plan", Static).update("\n".join(lines))

        def _confirm_then(self, fn) -> None:
            if steam.steam_running():
                self.push_screen(Confirm(), lambda ok: fn() if ok else None)
            else:
                fn()

        def action_apply(self) -> None:
            if self.entry:
                self._confirm_then(lambda: self._do("apply"))

        def action_undo(self) -> None:
            if self.entry and self.entry.applied:
                self._confirm_then(lambda: self._do("undo"))

        @work(thread=True, exclusive=True, group="apply")
        def _do(self, what: str) -> None:
            e = self.entry
            self.call_from_thread(self.notify, t("working"))
            try:
                if what == "apply":
                    core.apply(self.lib.root, [self.lib.plan(e, self._settings())], log=lambda *_: None)
                    msg = t("done")
                else:
                    core.undo(self.lib.root, [e.appid], log=lambda *_: None)
                    msg = t("undone")
                self.lib.refresh(e.appid)
                self.call_from_thread(self.notify, f"{msg} — {e.game.name}")
            except Exception as ex:  # noqa: BLE001
                self.call_from_thread(self.notify, f"{t('error')}: {ex}", severity="error", timeout=10)
            self.call_from_thread(self._fill, self.lib.entries)
            self.call_from_thread(self._show, e)


def run():
    if App is None:
        print("The terminal UI needs Textual:  sudo pacman -S python-textual   (or: pip install textual)\n"
              "Meanwhile the command line works:  uplift list | show | apply | undo", file=sys.stderr)
        return 1
    return UpliftTUI().run() or 0

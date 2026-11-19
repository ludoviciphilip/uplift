"""GTK4 / libadwaita interface."""
from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import __version__, core, steam, system  # noqa: E402
from .i18n import t  # noqa: E402
from .library import Entry, Library  # noqa: E402

APP_ID = "io.github.ludoviciphilip.Uplift"
QUALITIES = list(core.QUALITY)
LSFG_KEYS = list(core.LSFG)

CSS = b"""
.hero-title { font-size: 26px; font-weight: 800; color: white; text-shadow: 0 2px 8px rgba(0,0,0,.8); }
.hero-sub { color: rgba(255,255,255,.85); text-shadow: 0 1px 6px rgba(0,0,0,.8); }
.hero { border-radius: 12px; }
.cover { border-radius: 6px; }
.launch { font-family: monospace; padding: 12px; }
.badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 99px;
         background: alpha(@accent_bg_color, .25); color: @accent_color; }
.warn-row { color: @warning_color; }
"""


def _texture(path, w: int = 0, h: int = 0):
    """Texture from a file; with w/h it's pre-scaled (keeps list rows small and fast)."""
    if not path:
        return None
    try:
        if w and h:
            from gi.repository import GdkPixbuf
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), w, h, False)
            return Gdk.Texture.new_for_pixbuf(pb)
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error:
        return None


class GameRow(Gtk.ListBoxRow):
    def __init__(self, lib: Library, e: Entry):
        super().__init__()
        self.entry = e
        box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, valign=Gtk.Align.CENTER)
        pic.set_size_request(44, 66)
        pic.add_css_class("cover")
        tex = _texture(lib.cover(e.appid), 52, 78)
        if tex:
            pic.set_paintable(tex)
        else:
            pic = Gtk.Image(icon_name="applications-games-symbolic", pixel_size=32, width_request=44)
        box.append(pic)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        title = Gtk.Label(label=e.game.name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        title.add_css_class("heading")
        self.sub = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.sub.add_css_class("dim-label")
        self.sub.add_css_class("caption")
        txt.append(title)
        txt.append(self.sub)
        box.append(txt)
        self.badge = Gtk.Label(label=t("applied_badge"), valign=Gtk.Align.CENTER)
        self.badge.add_css_class("badge")
        box.append(self.badge)
        self.set_child(box)
        self.update()

    def update(self):
        e = self.entry
        eng = {"unreal4": "Unreal 4", "unreal5": "Unreal 5", "unity": "Unity", "source": "Source"}.get(e.info.engine, "")
        bits = [b for b in (eng, ", ".join(sorted(e.info.upscalers))) if b]
        meth = (e.applied or {}).get("method") or e.recommended
        self.sub.set_label(" · ".join(bits + [t("m_" + meth)]))
        self.badge.set_visible(bool(e.applied))


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Uplift", default_width=1180, default_height=820)
        self.lib = Library()
        self.entry: Entry | None = None
        self.rows: dict[str, GameRow] = {}
        self._loading_settings = False

        self.toasts = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(min_sidebar_width=300, max_sidebar_width=380, sidebar_width_fraction=0.32)
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        # sidebar
        sb = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        menu = Gio.Menu()
        menu.append(t("tools"), "app.tools")
        menu.append("About Uplift", "app.about")
        hb.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh.connect("clicked", lambda *_: self.load())
        hb.pack_start(refresh)
        sb.add_top_bar(hb)
        self.search = Gtk.SearchEntry(placeholder_text=t("search"), margin_start=8, margin_end=8, margin_bottom=6)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        sb.add_top_bar(self.search)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.set_filter_func(self._filter)
        self.listbox.connect("row-selected", self._on_row)
        sb.set_content(Gtk.ScrolledWindow(child=self.listbox, vexpand=True))
        self.split.set_sidebar(Adw.NavigationPage(title="Uplift", child=sb))

        # content
        self.content_view = Adw.ToolbarView()
        chb = Adw.HeaderBar()
        self.undo_btn = Gtk.Button(label=t("undo"))
        self.undo_btn.add_css_class("destructive-action")
        self.undo_btn.connect("clicked", lambda *_: self.confirm(self.do_undo))
        self.apply_btn = Gtk.Button(label=t("apply"))
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", lambda *_: self.confirm(self.do_apply))
        chb.pack_end(self.apply_btn)
        chb.pack_end(self.undo_btn)
        self.content_view.add_top_bar(chb)
        self.banner = Adw.Banner(revealed=False)
        self.content_view.add_top_bar(self.banner)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(Adw.StatusPage(icon_name="applications-games-symbolic", title="Uplift",
                                            description=t("app_subtitle")), "empty")
        spin = Adw.StatusPage(title=t("working"))
        spin.set_child(Adw.Spinner(width_request=48, height_request=48))
        self.stack.add_named(spin, "loading")
        self.detail = Gtk.ScrolledWindow(vexpand=True)
        self.stack.add_named(self.detail, "detail")
        self.content_view.set_content(self.stack)
        self.page = Adw.NavigationPage(title="Uplift", child=self.content_view)
        self.split.set_content(self.page)
        self.apply_btn.set_sensitive(False)
        self.undo_btn.set_visible(False)

        self.load()

    # ------------------------------------------------------------ library
    def load(self):
        self.stack.set_visible_child_name("loading")
        while (r := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(r)

        def work():
            try:
                entries = self.lib.load()
                err = None
            except Exception as ex:  # noqa: BLE001
                entries, err = [], str(ex)
            GLib.idle_add(self._loaded, entries, err)

        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, entries, err):
        self.rows = {}
        if err or not self.lib.root:
            self.stack.add_named(Adw.StatusPage(icon_name="dialog-error-symbolic", title=t("no_steam"),
                                                description=err or ""), "err")
            self.stack.set_visible_child_name("err")
            return
        for e in entries:
            r = GameRow(self.lib, e)
            self.rows[e.appid] = r
            self.listbox.append(r)
        miss = self.lib.missing_tools()
        if miss:
            self.banner.set_title(t("missing_tools", names=", ".join(miss)))
            self.banner.set_button_label(t("tools"))
            self.banner.connect("button-clicked", lambda *_: self.show_tools())
            self.banner.set_revealed(True)
        self.stack.set_visible_child_name("empty" if entries else "empty")
        if entries:
            self.listbox.select_row(self.listbox.get_row_at_index(0))

    def _filter(self, row):
        q = self.search.get_text().strip().lower()
        return not q or q in row.entry.game.name.lower()

    def _on_row(self, _lb, row):
        if row is None:
            return
        self.entry = row.entry
        self.build_detail(row.entry)

    # ------------------------------------------------------------ detail page
    def build_detail(self, e: Entry):
        self._loading_settings = True
        self.settings = e.settings(self.lib.tools)
        self.page.set_title(e.game.name)
        clamp = Adw.Clamp(maximum_size=860, margin_top=12, margin_bottom=24, margin_start=12, margin_end=12)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(box)

        # hero
        ov = Gtk.Overlay()
        hero = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, height_request=200, can_shrink=True)
        hero.add_css_class("hero")
        tex = _texture(self.lib.hero(e.appid)) or _texture(self.lib.cover(e.appid))
        if tex:
            hero.set_paintable(tex)
            ov.set_child(hero)
        else:
            ov.set_child(Gtk.Box(height_request=120))
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.END, halign=Gtk.Align.START,
                     margin_start=18, margin_bottom=14)
        tl = Gtk.Label(label=e.game.name, xalign=0, wrap=True)
        tl.add_css_class("hero-title" if tex else "title-1")
        sub = Gtk.Label(label=f"AppID {e.appid}" + (f" · {e.compat}" if e.compat else ""), xalign=0)
        sub.add_css_class("hero-sub" if tex else "dim-label")
        tb.append(tl)
        tb.append(sub)
        ov.add_overlay(tb)
        box.append(ov)

        # detected
        g = Adw.PreferencesGroup(title=t("detected"))
        i = e.info
        eng = i.engine + (f" ({', '.join(n for n in i.notes if n.startswith('ue-'))})" if i.unreal else "")
        for k, v in ((t("platform"), t("native_linux") if i.platform == "linux" else t("windows_proton")),
                     (t("engine"), eng if i.engine != "unknown" else t("unknown")),
                     (t("api"), ", ".join(i.apis) or t("unknown")),
                     (t("upscalers"), ", ".join(sorted(i.upscalers)) or t("none")),
                     (t("anticheat"), ", ".join(i.anticheat) or t("none"))):
            row = Adw.ActionRow(title=k, subtitle=v, subtitle_selectable=True)
            row.add_css_class("property")
            g.add(row)
        box.append(g)

        # upscaling
        g = Adw.PreferencesGroup(title=t("upscaling"))
        labels = []
        for m in core.METHODS:
            lab = t("m_" + m)
            if m == "auto":
                lab += f" → {t('m_' + e.recommended)}"
            labels.append(lab)
        self.method_row = Adw.ComboRow(title=t("method"), model=Gtk.StringList.new(labels))
        self.method_row.set_selected(core.METHODS.index(self.settings.method) if self.settings.method in core.METHODS else 0)
        self.quality_row = Adw.ComboRow(title=t("quality"), model=Gtk.StringList.new([t("q_" + q) for q in QUALITIES]))
        self.quality_row.set_selected(QUALITIES.index(self.settings.quality) if self.settings.quality in QUALITIES else 2)
        adj = Gtk.Adjustment(lower=0, upper=1, step_increment=0.05, page_increment=0.1, value=self.settings.sharpness)
        self.sharp_row = Adw.SpinRow(title=t("sharpness"), adjustment=adj, digits=2)
        mons = system.monitors()
        self.mon_names = [m.name for m in mons]
        self.mon_row = Adw.ComboRow(title=t("monitor"), model=Gtk.StringList.new([m.label for m in mons]))
        cur_mon = self.settings.monitor or system.best_monitor().name
        if cur_mon in self.mon_names:
            self.mon_row.set_selected(self.mon_names.index(cur_mon))
        for r in (self.method_row, self.quality_row, self.sharp_row, self.mon_row):
            g.add(r)
        box.append(g)

        # frame gen + extras
        g = Adw.PreferencesGroup(title=t("extras"))
        self.lsfg_row = Adw.ComboRow(title=t("framegen"), subtitle=t("framegen_sub"),
                                     model=Gtk.StringList.new([t("fg_" + k) for k in LSFG_KEYS]))
        self.lsfg_row.set_selected(LSFG_KEYS.index(self.settings.lsfg) if self.settings.lsfg in LSFG_KEYS else 0)
        self.cas_row = Adw.SwitchRow(title=t("cas"), subtitle=t("cas_sub"), active=self.settings.cas)
        self.gm_row = Adw.SwitchRow(title=t("gamemode"), subtitle=t("gamemode_sub"), active=self.settings.gamemode)
        self.mh_row = Adw.SwitchRow(title=t("mangohud"), subtitle=t("mangohud_sub"), active=self.settings.mangohud)
        for r in (self.lsfg_row, self.cas_row, self.gm_row, self.mh_row):
            g.add(r)
        box.append(g)

        # plan + launch options
        self.plan_group = Adw.PreferencesGroup(title=t("launch_preview"))
        self.launch_label = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.CHAR, selectable=True)
        self.launch_label.add_css_class("launch")
        frame = Gtk.Frame(child=self.launch_label)
        frame.add_css_class("card")
        self.plan_group.add(frame)
        self.plan_rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_top=8)
        self.plan_rows.add_css_class("boxed-list")
        self.plan_group.add(self.plan_rows)
        box.append(self.plan_group)

        for r, sig in ((self.method_row, "notify::selected"), (self.quality_row, "notify::selected"),
                       (self.mon_row, "notify::selected"), (self.lsfg_row, "notify::selected"),
                       (self.sharp_row, "notify::value"), (self.cas_row, "notify::active"),
                       (self.gm_row, "notify::active"), (self.mh_row, "notify::active")):
            r.connect(sig, self._changed)
        self.gm_row.set_sensitive(self.lib.tools.gamemode)
        self.mh_row.set_sensitive(self.lib.tools.mangohud)

        self.detail.set_child(clamp)
        if GLib.getenv("UPLIFT_DEBUG_SCROLL"):   # screenshots of the lower part during development
            v = float(GLib.getenv("UPLIFT_DEBUG_SCROLL"))
            GLib.timeout_add(400, lambda: self.detail.get_vadjustment().set_value(v) or False)
        self.stack.set_visible_child_name("detail")
        self.undo_btn.set_visible(bool(e.applied))
        self._loading_settings = False
        self._changed()
        self.split.set_show_content(True)

    def _read_settings(self) -> core.Settings:
        s = core.Settings()
        s.method = core.METHODS[self.method_row.get_selected()]
        s.quality = QUALITIES[self.quality_row.get_selected()]
        s.sharpness = round(self.sharp_row.get_value(), 2)
        s.monitor = self.mon_names[self.mon_row.get_selected()] if self.mon_names else ""
        s.lsfg = LSFG_KEYS[self.lsfg_row.get_selected()]
        s.cas = self.cas_row.get_active()
        s.gamemode = self.gm_row.get_active()
        s.mangohud = self.mh_row.get_active()
        return s

    def _changed(self, *_):
        if self._loading_settings or not self.entry:
            return
        self.settings = self._read_settings()
        meth = self.settings.method if self.settings.method != "auto" else self.entry.recommended
        self.quality_row.set_sensitive(meth not in ("off",))
        self.mon_row.set_sensitive(meth.startswith("gamescope") or meth == "wine-fsr" or self.settings.lsfg != "off")
        self.plan = self.lib.plan(self.entry, self.settings)
        self.launch_label.set_label(self.plan.launch_options or "—")
        while (r := self.plan_rows.get_row_at_index(0)) is not None:
            self.plan_rows.remove(r)
        items = []
        if self.plan.blocked:
            items.append(("dialog-error-symbolic", t("blocked_" + self.plan.blocked), True))
        for st in self.plan.steps:
            items.append(("dialog-warning-symbolic" if st.kind == "warn" else "emblem-ok-symbolic",
                          t(st.text, **st.args), st.kind == "warn"))
        for f in core.normalize(self.entry.launch)[1]:
            items.append(("document-edit-symbolic", t(f), False))
        for icon, text, warn in items:
            row = Adw.ActionRow(title=GLib.markup_escape_text(text), title_lines=3)
            img = Gtk.Image(icon_name=icon)
            if warn:
                img.add_css_class("warning")
            row.add_prefix(img)
            self.plan_rows.append(row)
        self.plan_rows.set_visible(bool(items))
        self.apply_btn.set_sensitive(not self.plan.blocked or bool(self.plan.env or self.plan.wrappers))

    # ------------------------------------------------------------ actions
    def confirm(self, fn):
        if not steam.steam_running():
            fn()
            return
        d = Adw.AlertDialog(heading=t("restart_title"), body=t("restart_body"))
        d.add_response("cancel", t("cancel"))
        d.add_response("ok", t("continue"))
        d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("ok")
        d.connect("response", lambda _d, r: fn() if r == "ok" else None)
        d.present(self)

    def _busy(self, on: bool):
        self.apply_btn.set_sensitive(not on)
        self.undo_btn.set_sensitive(not on)
        self.listbox.set_sensitive(not on)

    def _run(self, work, ok_msg):
        e = self.entry
        self._busy(True)
        toast = Adw.Toast(title=t("working"), timeout=0)
        self.toasts.add_toast(toast)

        def thread():
            try:
                work()
                err = None
            except Exception as ex:  # noqa: BLE001
                err = str(ex)
            GLib.idle_add(done, err)

        def done(err):
            toast.dismiss()
            self._busy(False)
            self.toasts.add_toast(Adw.Toast(title=f"{t('error')}: {err}" if err else f"{ok_msg} — {e.game.name}",
                                            timeout=6 if err else 3))
            self.lib.refresh(e.appid)
            if e.appid in self.rows:
                self.rows[e.appid].update()
            if self.entry is e:
                self.build_detail(e)

        threading.Thread(target=thread, daemon=True).start()

    def do_apply(self):
        plan = self.lib.plan(self.entry, self._read_settings())
        self._run(lambda: core.apply(self.lib.root, [plan], log=lambda *_: None), t("done"))

    def do_undo(self):
        appid = self.entry.appid
        self._run(lambda: core.undo(self.lib.root, [appid], log=lambda *_: None), t("undone"))

    def show_tools(self):
        d = Adw.Dialog(title=t("tools"), content_width=560)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(description=f"GPU: {self.lib.tools.gpu}")
        tl = self.lib.tools
        status = {"gamescope": tl.gamescope, "vkBasalt": tl.vkbasalt, "lsfg-vk": tl.lsfg,
                  "Lossless Scaling (lsfg-vk)": bool(tl.lsfg_dll), "MangoHud": tl.mangohud, "GameMode": tl.gamemode}
        miss = self.lib.missing_tools()
        for name, ok in status.items():
            row = Adw.ActionRow(title=name, subtitle="" if ok else t("install_hint", cmd=miss.get(name, "—")),
                                subtitle_selectable=True)
            row.add_suffix(Gtk.Image(icon_name="emblem-ok-symbolic" if ok else "dialog-warning-symbolic"))
            g.add(row)
        if tl.lossless_dll_only:
            g.add(Adw.ActionRow(title=t("warn_lsfg_branch")))
        page.add(g)
        tv.set_content(page)
        d.set_child(tv)
        d.present(self)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win = None

    def do_activate(self):
        if not self.win:
            prov = Gtk.CssProvider()
            prov.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.win = Window(self)
            for name, cb in (("about", self.about), ("tools", lambda *_: self.win.show_tools())):
                a = Gio.SimpleAction.new(name, None)
                a.connect("activate", cb)
                self.add_action(a)
        self.win.present()

    def about(self, *_):
        Adw.AboutDialog(application_name="Uplift", version=__version__, developer_name="Luis Felipe",
                        application_icon=APP_ID, license_type=Gtk.License.MIT_X11,
                        website="https://github.com/ludoviciphilip/uplift",
                        comments=t("app_subtitle")).present(self.win)


def run():
    return App().run(sys.argv[:1])

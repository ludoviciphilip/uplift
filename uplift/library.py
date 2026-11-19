"""Shared model for the GUI / TUI / CLI: the Steam library with detection results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import core, detect, steam, system


@dataclass
class Entry:
    game: steam.Game
    info: detect.Info
    compat: str
    launch: str                  # current launch options
    applied: dict | None         # uplift state record
    recommended: str

    @property
    def appid(self) -> str:
        return self.game.appid

    def settings(self, tools: system.Tools) -> core.Settings:
        return core.defaults_for(self.info, tools, self.launch, (self.applied or {}).get("settings"))


class Library:
    def __init__(self):
        self.root = steam.find_steam()
        self.libs = steam.libraries(self.root) if self.root else []
        self.tools = system.tools(self.libs)
        self.entries: list[Entry] = []

    def load(self, progress=None) -> list[Entry]:
        self.entries = []
        if not self.root:
            return []
        st = core.load_state()
        games = steam.games(self.root)
        for i, g in enumerate(games):
            if progress:
                progress(i, len(games), g.name)
            info = detect.inspect(g)
            compat = steam.compat_tool(self.root, g.appid)
            self.entries.append(Entry(g, info, compat, steam.get_launch_options(self.root, g.appid),
                                      st.get(g.appid), core.recommend(info, self.tools, compat)))
        return self.entries

    def refresh(self, appid: str) -> Entry | None:
        st = core.load_state()
        for e in self.entries:
            if e.appid == appid:
                e.launch = steam.get_launch_options(self.root, appid)
                e.applied = st.get(appid)
                return e
        return None

    def get(self, key: str) -> Entry | None:
        key_l = key.lower()
        for e in self.entries:
            if e.appid == key:
                return e
        matches = [e for e in self.entries if key_l in e.game.name.lower()]
        return matches[0] if len(matches) == 1 else None

    def plan(self, e: Entry, settings: core.Settings) -> core.Plan:
        p = core.build_plan(e.game, e.info, self.tools, settings, e.compat)
        base = e.applied["original"] if e.applied and e.launch == e.applied.get("written") else e.launch
        p.launch_options = core.compose(base, p)
        return p

    def cover(self, appid: str) -> Path | None:
        return steam.artwork(self.root, appid, "cover") if self.root else None

    def hero(self, appid: str) -> Path | None:
        return steam.artwork(self.root, appid, "hero") if self.root else None

    def missing_tools(self) -> dict[str, str]:
        t = self.tools
        miss = {}
        if not t.gamescope:
            miss["gamescope"] = "sudo pacman -S gamescope"
        if not t.vkbasalt:
            miss["vkBasalt"] = "paru -S vkbasalt lib32-vkbasalt"
        if not t.lsfg:
            miss["lsfg-vk"] = "paru -S lsfg-vk"
        if not t.mangohud:
            miss["MangoHud"] = "sudo pacman -S mangohud lib32-mangohud"
        if not t.gamemode:
            miss["GameMode"] = "sudo pacman -S gamemode lib32-gamemode"
        return miss

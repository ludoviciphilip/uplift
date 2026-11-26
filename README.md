# Uplift

**Open-source upscaling and frame generation manager for Steam games on Linux — picked per game, applied in one click, undone in one click.**

[![License: MIT](https://img.shields.io/github/license/ludoviciphilip/uplift)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-linux-informational)](#install)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

[Português](README.pt-BR.md) · [Features](#features) · [Install](#install) · [Usage](#use) · [Alternatives](#alternatives--comparison)

![Uplift window](docs/screenshot-gui.png)

Uplift reads your Steam library, inspects every installed game (engine, graphics API, bundled upscalers, anti-cheat) and sets up the best upscaling path that game supports — DLSS/FSR/XeSS swaps via OptiScaler, Unreal Engine's own TSR/TAAU, or gamescope's FSR/NIS, plus optional lsfg-vk frame generation, on any distro with Proton:

## Features

| The game has… | Uplift does | Quality |
|---|---|---|
| DLSS, XeSS or FSR 2/3 | Installs **[OptiScaler](https://github.com/optiscaler/OptiScaler)** and swaps it for **FSR 3.1** (works on any GPU) | Real temporal upscaling |
| Unreal Engine 4/5, no upscaler in the menu | Enables the engine's own **TAAU (UE4) / TSR (UE5)** via `Engine.ini` | Temporal — close to FSR 2 |
| Nothing | **gamescope + FSR 1 or NIS** at the resolution you pick, with tuned sharpness | Spatial |
| Any of the above | Optional **vkBasalt CAS** sharpening, **lsfg-vk** frame generation (Lossless Scaling), GameMode, MangoHud | |

It also writes the Steam **launch options** for you: Steam keeps them in a file it rewrites while running, so Uplift closes Steam, saves them and reopens it. Your own launch options are kept (env vars, wrappers, game arguments) and common mistakes are fixed (`%%command`, `gamemode` instead of `gamemoderun`).

Everything is recorded and **reversible**: files Uplift adds are removed, files it replaces are backed up, `Engine.ini` keys get their previous values back, and the launch options return to exactly what they were.

## Install

```bash
git clone https://github.com/ludoviciphilip/uplift
cd uplift && ./install.sh
```

Needs Python 3.10+.

`./install.sh` offers to install the tools Uplift drives (gamescope, MangoHud, GameMode, vkBasalt, lsfg-vk, GTK/Textual) with your distro's package manager — Arch (+AUR via paru/yay), Debian/Ubuntu, Fedora, openSUSE. `--deps` installs without asking, `--no-deps` skips. **Lossless Scaling** (needed by lsfg-vk) is a paid Steam app: install it and pick the `lsfg-vk` beta branch.

## Use

- `uplift` — window: pick a game, adjust, **Apply** / **Undo**
- `uplift --tui` — the same in the terminal (`a` apply, `u` undo, `/` search)
- Command line, for scripts:

```bash
uplift list                                   # library + recommendation per game
uplift show "escape the backrooms"            # detection + plan
uplift plan 374320 --method gamescope-fsr --quality quality --lsfg x2-perf   # dry run
uplift apply 374320 --lsfg x2-perf -y         # apply (restarts Steam if it's open)
uplift undo 374320 -y
uplift doctor                                 # tools, monitors, GPU
```

## Notes

- **OptiScaler path is experimental**: tested end-to-end on a synthetic library (install → re-apply → byte-identical undo), not yet on many real DLSS/FSR2 games. Reports welcome!
- **Anti-cheat** (EasyAntiCheat, BattlEye…): Uplift never drops DLLs into those games.
- **OptiScaler on NVIDIA GTX** with DLSS-only games is experimental (GPU spoofing + fakenvapi). Games with FSR 2/XeSS inputs work without it.
- **Unreal**: run the game once so it creates its config folder.
- **lsfg-vk**: Uplift caps the game at refresh ÷ multiplier (`DXVK_FRAME_RATE`/`VKD3D_FRAME_RATE`) so generated frames land on the display's refresh.
- Uplift doesn't redistribute OptiScaler; it downloads the official release from GitHub.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Builds a fake Steam library (Unreal game, DLSS+FSR2 game, DX11 game, anti-cheat game), applies, re-applies and undoes, and checks every file is byte-identical afterwards.

## Alternatives / comparison

- **vs. installing [OptiScaler](https://github.com/optiscaler/OptiScaler) by hand**: Uplift detects per game whether it can swap DLSS/FSR2/XeSS for FSR 3.1 and does the file copy + config for you, with one-click undo (OptiScaler itself does the actual upscaling work; Uplift automates setting it up).
- **vs. [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/)'s own frame generation**: Uplift drives [lsfg-vk](https://github.com/PancakeTAS/lsfg-vk), an open-source Vulkan layer that brings Lossless Scaling's frame generation to native Linux/Proton games, and caps the game's frame rate so generated frames land on your display's refresh rate. Lossless Scaling itself is still required (it ships the frame-generation DLL that lsfg-vk loads).
- **vs. manually editing `Engine.ini` or Steam launch options**: Uplift finds the right keys/flags for Unreal TSR/TAAU and gamescope, writes them safely (Steam's launch-options file gets rewritten while Steam runs, so Uplift closes/saves/reopens it for you), and reverts everything with `uplift undo`.

### Trademark notice

NVIDIA DLSS, AMD FSR and Intel XeSS are trademarks of their respective owners. Lossless Scaling is a trademark of its developer/publisher, THS. Unreal Engine is a trademark of Epic Games. Uplift is an independent, open-source project and is not affiliated with, sponsored by, or endorsed by NVIDIA, AMD, Intel, THS, Epic Games, or Valve.

## License

MIT

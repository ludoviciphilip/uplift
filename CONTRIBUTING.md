# Contributing to Uplift

Thanks for considering a contribution! Uplift is a small Python project (GUI + TUI + CLI) for upscaling and
frame generation on Linux Steam games.

## Setup

```bash
git clone https://github.com/ludoviciphilip/uplift
cd uplift
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,tui]"
```

Needs Python 3.10+. The GUI extra needs PyGObject/GTK4/libadwaita available on your system (see `scripts/deps.sh`
for the per-distro package names); the TUI extra is pure Python (`textual`).

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

The test suite builds a fake Steam library (Unreal game, DLSS+FSR2 game, DX11 game, anti-cheat game), applies,
re-applies and undoes changes, and checks that every file is byte-identical afterwards. Any change that touches
`uplift/core.py`, `uplift/detect.py` or `uplift/steam.py` should keep this suite green — the apply/undo
reversibility guarantee is the core promise of the project.

## Making changes

- Keep PRs focused: one feature or fix per PR.
- Match the existing code style (standard library first, minimal dependencies).
- If you add a new detection case (new engine, upscaler or anti-cheat), add a corresponding test fixture.
- Update `README.md` (and `README.pt-BR.md` if the change is user-facing) when behavior changes.
- Describe what you tested (real game, synthetic library, which distro) in the PR description — Uplift edits
  users' live Steam configuration, so real-world testing notes matter a lot for review.

## Reporting bugs

Open an issue with the bug report template — please include `uplift doctor` output, your distro, and the
AppID of the game involved when relevant.

## Security issues

See [SECURITY.md](SECURITY.md) — please do not open a public issue for security vulnerabilities.

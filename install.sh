#!/usr/bin/env bash
# Uplift installer — per-user, no root needed for Uplift itself.
#   ./install.sh              install / update (asks to install the optional tools)
#   ./install.sh --deps       … and install the tools without asking
#   ./install.sh --no-deps    only Uplift
#   ./install.sh --uninstall
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/uplift/app"
BIN="$HOME/.local/bin"
ID=io.github.ludoviciphilip.Uplift

if [[ ${1:-} == --uninstall ]]; then
  rm -rf "$APP" "$BIN/uplift" "$DATA/applications/$ID.desktop" "$DATA/icons/hicolor/scalable/apps/$ID.svg"
  echo "Uplift removed. Your games keep their current settings — run 'uplift undo <game>' BEFORE uninstalling to revert them."
  echo "(State/backups in $DATA/uplift were kept.)"
  exit 0
fi

DEPS=ask
for a in "$@"; do case $a in --deps) DEPS=yes;; --no-deps) DEPS=no;; esac; done

# Tools first: on a minimal system this also brings Python and GTK.
case $DEPS in
  yes) "$HERE/scripts/deps.sh" --yes ;;
  ask) "$HERE/scripts/deps.sh" ;;
esac
echo

PY=/usr/bin/python3
[[ -x $PY ]] || PY=$(command -v python3 || true)
if [[ -z $PY ]] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "✗ Uplift needs Python 3.10 or newer (python3). Install it, or run: ./install.sh --deps" >&2
  exit 1
fi

mkdir -p "$APP" "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
rm -rf "$APP/uplift"
cp -r "$HERE/uplift" "$APP/"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
cat > "$BIN/uplift" <<SH
#!/bin/sh
PYTHONPATH="$APP\${PYTHONPATH:+:\$PYTHONPATH}" exec $PY -m uplift "\$@"
SH
chmod +x "$BIN/uplift"
install -m644 "$HERE/data/$ID.svg" "$DATA/icons/hicolor/scalable/apps/$ID.svg"
sed "s|@BIN@|$BIN|" "$HERE/data/$ID.desktop" > "$DATA/applications/$ID.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true

echo "✓ Uplift installed:  uplift  (window)  ·  uplift --tui  ·  uplift --help"
"$PY" -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); from gi.repository import Adw' 2>/dev/null \
  || echo "! The window needs GTK4 + libadwaita + PyGObject (run: ./install.sh --deps)"
"$PY" -c 'import textual' 2>/dev/null || echo "· The terminal UI needs Textual (run: ./install.sh --deps, or pip install textual)"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "! $BIN is not in your PATH";; esac

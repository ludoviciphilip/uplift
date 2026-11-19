#!/usr/bin/env bash
# Install the tools Uplift drives (all optional — Uplift works with whatever is present).
#   scripts/deps.sh            ask, then install
#   scripts/deps.sh --yes      install without asking
#   scripts/deps.sh --dry-run  only show what would be installed
set -uo pipefail
YES=0 DRY=0
for a in "$@"; do case $a in --yes|-y) YES=1;; --dry-run|-n) DRY=1;; esac; done

say()  { printf '\e[1;36m==>\e[0m %s\n' "$*"; }
warn() { printf '\e[1;33m!\e[0m  %s\n' "$*"; }
run()  { [[ $1 == sudo && $EUID -eq 0 ]] && shift; echo "    \$ $*"; ((DRY)) || "$@"; }

. /etc/os-release 2>/dev/null || true
ids=" ${ID:-} ${ID_LIKE:-} "
want=() repo=() aur=() missing=() have=()

pick() {   # pick <check-installed-cmd> <check-available-cmd> pkgs...  → fills have/repo/missing
  local inst=$1 avail=$2; shift 2
  for p in "$@"; do
    if eval "$inst \"\$p\"" >/dev/null 2>&1; then have+=("$p")
    elif eval "$avail \"\$p\"" >/dev/null 2>&1; then repo+=("$p")
    else missing+=("$p"); fi
  done
}

if command -v pacman >/dev/null; then
  DISTRO=arch
  helper=$(command -v paru || command -v yay || true)
  pkgs=(python gamescope mangohud gamemode python-gobject gtk4 libadwaita python-textual libarchive lsfg-vk vkbasalt)
  grep -q '^\[multilib\]' /etc/pacman.conf && pkgs+=(lib32-mangohud lib32-gamemode lib32-vkbasalt lib32-lsfg-vk) \
    || warn "multilib is off: 32-bit games won't get MangoHud/vkBasalt/lsfg (enable [multilib] in /etc/pacman.conf)"
  for p in "${pkgs[@]}"; do
    if pacman -Qq "$p" >/dev/null 2>&1; then have+=("$p")
    elif pacman -Si "$p" >/dev/null 2>&1; then repo+=("$p")
    elif [[ -n $helper ]]; then aur+=("$p")
    else missing+=("$p"); fi
  done
elif command -v apt-get >/dev/null; then
  DISTRO=debian
  deb_avail() { local c; c=$(apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/{print $2}'); [[ -n $c && $c != "(none)" ]]; }
  deb_inst() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "ok installed"; }
  pick deb_inst deb_avail python3 gamescope mangohud gamemode vkbasalt python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-textual libarchive-tools
elif command -v dnf >/dev/null; then
  DISTRO=fedora
  pick "rpm -q" "dnf -q info" python3 gamescope mangohud gamemode vkBasalt python3-gobject gtk4 libadwaita python3-textual bsdtar
elif command -v zypper >/dev/null; then
  DISTRO=suse
  pick "rpm -q" "zypper -q info" python3 gamescope mangohud gamemoded vkbasalt python3-gobject typelib-1_0-Adw-1 python3-textual bsdtar
else
  warn "Unknown package manager — install gamescope, MangoHud, GameMode, vkBasalt and lsfg-vk yourself."
  exit 0
fi

say "Uplift's tools on ${PRETTY_NAME:-$DISTRO}"
((${#have[@]}))    && echo "    already installed: ${have[*]}"
((${#repo[@]}))    && echo "    to install:        ${repo[*]}"
((${#aur[@]}))     && echo "    from the AUR:      ${aur[*]}  (via $(basename "${helper:-?}"))"
((${#missing[@]})) && echo "    not available:     ${missing[*]}"
if [[ $DISTRO == arch && -z ${helper:-} ]]; then
  warn "No AUR helper (paru/yay): vkBasalt (and lsfg-vk outside CachyOS) come from the AUR."
fi
if [[ $DISTRO != arch ]] && ! command -v lsfg-vk-cli >/dev/null; then
  warn "lsfg-vk isn't packaged here: see https://lsfg-vk.dev/docs/installation/"
fi
if [[ -d $HOME/.var/app/com.valvesoftware.Steam ]] && ! command -v steam >/dev/null; then
  warn "Flatpak Steam: games only see Vulkan layers installed as Flatpak extensions, e.g."
  echo "    flatpak install flathub org.freedesktop.Platform.VulkanLayer.MangoHud org.freedesktop.Platform.VulkanLayer.vkBasalt com.valvesoftware.Steam.Utility.gamescope"
fi

if ((${#repo[@]} + ${#aur[@]} == 0)); then
  say "Nothing to install."
else
  if ((!YES && !DRY)) && [[ -t 0 ]]; then
    read -rp "Install them now? (asks for your password) [Y/n] " ok
    [[ ${ok,,} =~ ^(n|no|nao|não)$ ]] && { echo "Skipped."; exit 0; }
  fi
  case $DISTRO in
    arch)   inst=(sudo pacman -S --needed --noconfirm) ;;
    debian) inst=(sudo apt-get install -y) ;;
    fedora) inst=(sudo dnf install -y) ;;
    suse)   inst=(sudo zypper -n install) ;;
  esac
  failed=()
  if ((${#repo[@]})) && ! run "${inst[@]}" "${repo[@]}"; then
    ((DRY)) || { warn "Batch install failed — trying one package at a time"
      for p in "${repo[@]}"; do run "${inst[@]}" "$p" >/dev/null 2>&1 || failed+=("$p"); done; }
  fi
  if ((${#aur[@]})) && ! run "$helper" -S --needed --noconfirm "${aur[@]}"; then
    ((DRY)) || for p in "${aur[@]}"; do run "$helper" -S --needed --noconfirm "$p" || failed+=("$p"); done
  fi
  ((${#failed[@]})) && warn "Could not install: ${failed[*]} (Uplift will just not offer what needs them)"
fi

cat <<'TXT'

Frame generation (lsfg-vk) also needs Lossless Scaling from Steam (paid, not installable by scripts):
  1. Buy/install "Lossless Scaling" in Steam (Properties → Compatibility → force Proton).
  2. Properties → Betas → choose the "lsfg-vk" branch.
Uplift finds it automatically after that.
TXT

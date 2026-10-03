#!/usr/bin/env bash
# SocialCluster by /MNT Node installer.
#
# Usage (paste into a terminal):
#   curl -fsSL https://raw.githubusercontent.com/MaanavNagda/SocialCluster-by-MNT-Node/main/install.sh | bash
#
# Clones/updates the app into ~/.local/share/SocialCluster, creates an
# isolated Python virtualenv there, installs a `social-cluster` launcher
# into ~/.local/bin, and registers a desktop entry so it shows up in the
# KDE Plasma application menu.
#
# This script deliberately does NOT use sudo / install system packages. If
# a required system dependency (e.g. the python3-venv package on Debian/
# Ubuntu-based distros) is missing, it prints what to install manually and
# stops instead of silently escalating privileges.

set -euo pipefail

REPO_URL="https://github.com/MaanavNagda/SocialCluster-by-MNT-Node.git"
INSTALL_DIR="${SOCIAL_CLUSTER_INSTALL_DIR:-$HOME/.local/share/SocialCluster}"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
LAUNCHER="$BIN_DIR/social-cluster"

log() { printf '==> %s\n' "$1"; }
die() { printf 'error: %s\n' "$1" >&2; exit 1; }

log "SocialCluster by /MNT Node installer"

command -v git >/dev/null 2>&1 || die "git is required but was not found on PATH."
command -v python3 >/dev/null 2>&1 || die "python3 is required but was not found on PATH."

if [ -d "$INSTALL_DIR/.git" ]; then
    log "Existing install found at $INSTALL_DIR, updating..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    log "Cloning into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

log "Setting up Python virtual environment"
if ! python3 -m venv "$INSTALL_DIR/venv" 2>/tmp/social-cluster-venv-error.log; then
    cat /tmp/social-cluster-venv-error.log >&2
    rm -f /tmp/social-cluster-venv-error.log
    die "Failed to create a Python virtualenv. Your distro may need a separate venv package, e.g.:
    Debian/Ubuntu: sudo apt install python3-venv
    Fedora:        sudo dnf install python3-virtualenv
Then re-run this installer."
fi
rm -f /tmp/social-cluster-venv-error.log

"$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# --- Media codec check -----------------------------------------------------
# The pip-bundled Qt WebEngine is built without proprietary codecs
# (H.264/AAC), which many services need for video playback. Distro-provided
# Qt6 WebEngine builds usually DO include them, so if the system python can
# import PySide6/QtWebEngine bindings and they probe codec-capable, the
# launcher prefers that interpreter. Nothing distro-specific is invoked --
# we simply use what is already installed. The venv remains the fallback.
APP_PYTHON="$INSTALL_DIR/venv/bin/python"
PROBE="$INSTALL_DIR/tools/webengine_codec_probe.py"

codec_probe() {  # $1 = python interpreter
    [ -f "$PROBE" ] || return 1
    "$1" "$PROBE" >/dev/null 2>&1
}

log "Checking Qt WebEngine media codec support"
if codec_probe "$APP_PYTHON"; then
    :
elif command -v python3 >/dev/null 2>&1 \
     && python3 -c "import PySide6.QtWebEngineCore" >/dev/null 2>&1 \
     && codec_probe python3; then
    APP_PYTHON="$(command -v python3)"
    log "Using system Python -- its Qt WebEngine has proprietary codecs"
else
    cat <<'WARN'
==> NOTE: no codec-capable Qt WebEngine found. The app works, but video
    playback inside services (WhatsApp, Instagram, ...) may fail: the
    pip-bundled Qt lacks H.264/AAC for licensing reasons.
    To enable video, install your distro's Qt6 PySide6 bindings and re-run
    this installer (it will auto-detect them). Examples:
      openSUSE:      sudo zypper install python313-pyside6
      Arch:          sudo pacman -S pyside6
      Debian/Ubuntu: sudo apt install python3-pyside6.qtwebengine*
      Fedora:        enable RPM Fusion, then 'dnf install python3-pyside6'
WARN
fi

log "Installing launcher to $LAUNCHER"
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "\${SOCIAL_CLUSTER_PYTHON:-$APP_PYTHON}" "$INSTALL_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"

log "Registering desktop entry"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/social-cluster.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SocialCluster by /MNT Node
Comment=Unified social media and messaging aggregator
Exec=$LAUNCHER
Icon=$INSTALL_DIR/social_cluster/assets/icon.png
Terminal=false
Categories=Network;InstantMessaging;
StartupWMClass=SocialCluster
EOF

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        log "NOTE: $BIN_DIR is not on your PATH yet."
        echo "    Add this line to your ~/.bashrc (or ~/.zshrc) and restart your terminal:"
        echo "        export PATH=\"$BIN_DIR:\$PATH\""
        ;;
esac

log "Done. Launch SocialCluster from your application menu, or run: social-cluster"

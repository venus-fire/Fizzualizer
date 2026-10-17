#!/usr/bin/env bash
# Install the desktop entry and icon for the current user.
#
# The repo copy of fizzualizer.desktop carries @EXEC@ / @PATH@ placeholders;
# this script fills them with the checkout's real path, so the entry keeps
# working from wherever the repo lives.
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"

APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$APPS" "$ICONS"

sed "s|@EXEC@|$REPO/run.sh|; s|@PATH@|$REPO|" fizzualizer.desktop > "$APPS/fizzualizer.desktop"
install -m644 icons/fizzualizer.svg "$ICONS/fizzualizer.svg"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true

echo "Installed $APPS/fizzualizer.desktop -> $REPO/run.sh"
echo "Icon: $ICONS/fizzualizer.svg"

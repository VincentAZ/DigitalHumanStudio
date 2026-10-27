#!/usr/bin/env bash
# Install (or refresh) a desktop launcher for the Digital Human Studio control center.
# Writes a freedesktop .desktop entry to ~/.local/share/applications and, when a Desktop folder
# exists, a copy there. Paths are resolved from this script's location, so the entry follows the
# checkout. Re-run after moving the repository. Pass --uninstall to remove both entries.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
entry="$app_dir/digital-human-studio.desktop"
desktop_dir=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
desktop_copy="$desktop_dir/digital-human-studio.desktop"
if [[ "${1:-}" == --uninstall ]]; then
    rm -f "$entry" "$desktop_copy"
    update-desktop-database "$app_dir" 2>/dev/null || true
    echo "Removed $entry and $desktop_copy"
    exit 0
fi
mkdir -p "$app_dir"
cat > "$entry" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Digital Human Studio
GenericName=Control center
Comment=Train, evaluate and direct the physically simulated character
Exec=$project_root/scripts/studio.sh
Path=$project_root
Icon=$project_root/scripts/studio_app/icon.svg
Terminal=false
Categories=Development;
Keywords=isaac;humanoid;simulation;studio;
StartupNotify=true
StartupWMClass=digital-human-studio
EOF
chmod +x "$entry"
if [[ -d "$desktop_dir" ]]; then
    cp "$entry" "$desktop_copy"
    chmod +x "$desktop_copy"
    # GNOME marks desktop-folder launchers trusted only after this metadata is set.
    gio set "$desktop_copy" metadata::trusted true 2>/dev/null || true
fi
update-desktop-database "$app_dir" 2>/dev/null || true
desktop-file-validate "$entry" 2>/dev/null && echo "Entry validated." || true
echo "Installed $entry${desktop_copy:+ and $desktop_copy}"
echo "Find 'Digital Human Studio' in the application grid, or double-click the Desktop icon."

#!/usr/bin/env bash
# compile-macos.sh - compiles jira-timesheet-qt into a standalone macOS app with Nuitka.
#
# Produces a --standalone .app bundle (no Python install needed on the target
# machine). Output: dist/jira-timesheet-qt.app and
# dist/jira-timesheet-qt-vX.Y.Z-macos.tar.gz.
#
# --standalone/App-Bundle, NICHT --onefile: nur der Ordner-Build erfuellt die
# LGPL-Weitergabepflicht von PySide6 (Qt-Frameworks als eigene Dateien daneben).
#
# HINWEIS: nicht code-signiert/notarisiert. Beim ersten Start meldet Gatekeeper
# einen unbekannten Entwickler - der Nutzer oeffnet die App per Rechtsklick ->
# Oeffnen oder gibt sie in den Systemeinstellungen frei.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
entry="$root/src/jira_timesheet_qt/__main__.py"
init_py="$root/src/jira_timesheet_qt/__init__.py"
icon="$root/assets/app-icon.png"
out_dir="$root/dist"
app_bundle="$out_dir/jira-timesheet-qt.app"

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
else
    python="python3"
fi

if command -v uv >/dev/null 2>&1; then
    echo "Syncing venv to lockfile (uv sync --inexact)..."
    uv sync --inexact --project "$root"
else
    echo "uv nicht gefunden - venv-Sync uebersprungen" >&2
fi

version="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' "$init_py")"
if [ -z "$version" ]; then
    echo "Konnte __version__ nicht aus $init_py lesen" >&2
    exit 1
fi

echo "Compiling jira-timesheet-qt v$version with Nuitka (macOS app bundle)..."

rm -rf "$app_bundle"
started=$(date +%s)

if ! "$python" -m nuitka --version >/dev/null 2>&1; then
    echo "Nuitka fehlt im venv - installiere..."
    uv pip install nuitka || { echo "Nuitka-Installation fehlgeschlagen" >&2; exit 1; }
fi

# Nuitka wandelt das PNG-App-Icon nur mit imageio ins native macOS-.icns
# ("FATAL: Need to install 'imageio' ..."). Ins venv legen, bevor der Build laeuft.
uv pip install imageio || "$python" -m pip install imageio || {
    echo "imageio-Installation fehlgeschlagen" >&2; exit 1; }

# --macos-create-app-bundle : .app statt nackter Binary (macOS-uebliche Form)
# --enable-plugin=pyside6    : Qt-Binding samt Plugins buendeln
"$python" -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --assume-yes-for-downloads \
    --remove-output \
    --enable-plugin=pyside6 \
    --include-package=jira_timesheet_qt \
    --include-package-data=jira_timesheet_qt \
    --include-package-data=qtawesome \
    --include-package=holidays \
    --macos-app-icon="$icon" \
    --macos-app-name="jira-timesheet-qt" \
    --macos-app-version="$version" \
    --output-dir="$out_dir" \
    --output-filename=jira-timesheet-qt \
    "$entry"

# Nuitka benennt das Bundle nach dem Hauptmodul (__main__.app) - umbenennen
if [ -d "$out_dir/__main__.app" ]; then
    mv "$out_dir/__main__.app" "$app_bundle"
fi

elapsed=$(( $(date +%s) - started ))
size_mb=$(du -sm "$app_bundle" | cut -f1)

# tar.gz statt zip - bewahrt Bundle-Struktur und Ausfuehrungs-Flags
tarball="$out_dir/jira-timesheet-qt-v$version-macos.tar.gz"
rm -f "$tarball"
tar -czf "$tarball" -C "$out_dir" jira-timesheet-qt.app
tar_mb=$(du -sm "$tarball" | cut -f1)

echo ""
echo "Done in ${elapsed}s"
echo "  app bundle : $app_bundle  (${size_mb} MB)"
echo "  tarball    : $tarball  (${tar_mb} MB)"

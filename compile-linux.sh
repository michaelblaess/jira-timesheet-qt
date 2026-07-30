#!/usr/bin/env bash
# compile-linux.sh - compiles jira-timesheet-qt into a standalone Linux binary with Nuitka.
#
# Produces a self-contained --standalone build (no Python install needed on the
# target machine). Output: dist/jira-timesheet-qt/jira-timesheet-qt plus its
# shared libraries, and dist/jira-timesheet-qt-vX.Y.Z-linux-x86_64.tar.gz.
#
# --standalone (Ordner), NICHT --onefile: nur der Ordner-Build erfuellt die
# LGPL-Weitergabepflicht von PySide6 (Qt-Libs als eigene Dateien daneben).
#
# Build-Maschine braucht: gcc, patchelf, python3-dev sowie die Qt-xcb-Systemlibs.
#   Debian/Ubuntu:  sudo apt install gcc patchelf python3-dev libxcb-cursor0
#
# HINWEIS (unverifiziert, siehe qt-specialist-Skill): ob die Binary auf einem
# nackten Linux ohne X-Bibliotheken startet, ist offen. Fehlt zur Laufzeit eine
# .so, meldet Qt "Could not load the Qt platform plugin xcb" - dann die fehlende
# Lib hier vor dem Packen mit ins dist kopieren.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
entry="$root/src/jira_timesheet_qt/__main__.py"
init_py="$root/src/jira_timesheet_qt/__init__.py"
icon="$root/assets/app-icon.png"
out_dir="$root/dist"
dist_dir="$out_dir/jira-timesheet-qt"

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
else
    python="python3"
fi

for tool in gcc patchelf; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Fehlt: $tool - bitte installieren (z.B. sudo apt install gcc patchelf python3-dev)" >&2
        exit 1
    fi
done

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

echo "Compiling jira-timesheet-qt v$version with Nuitka..."

rm -rf "$dist_dir"
started=$(date +%s)

if ! "$python" -m nuitka --version >/dev/null 2>&1; then
    echo "Nuitka fehlt im venv - installiere..."
    uv pip install nuitka || { echo "Nuitka-Installation fehlgeschlagen" >&2; exit 1; }
fi

# --enable-plugin=pyside6          : Qt-Binding samt Plugins buendeln
# --include-package-data=qtawesome : Material-Design-Icon-Fonts (Paketdaten)
# --include-package=holidays       : holidays laedt Laender-Module dynamisch
"$python" -m nuitka \
    --standalone \
    --assume-yes-for-downloads \
    --remove-output \
    --enable-plugin=pyside6 \
    --include-package=jira_timesheet_qt \
    --include-package-data=jira_timesheet_qt \
    --include-package-data=qtawesome \
    --include-package=holidays \
    --linux-icon="$icon" \
    --output-dir="$out_dir" \
    --output-filename=jira-timesheet-qt \
    "$entry"

if [ -d "$out_dir/__main__.dist" ]; then
    mv "$out_dir/__main__.dist" "$dist_dir"
fi

elapsed=$(( $(date +%s) - started ))
exe="$dist_dir/jira-timesheet-qt"
size_mb=$(du -sm "$dist_dir" | cut -f1)

# tar.gz statt zip - tar bewahrt das Ausfuehrungs-Flag der Binary
tarball="$out_dir/jira-timesheet-qt-v$version-linux-x86_64.tar.gz"
rm -f "$tarball"
tar -czf "$tarball" -C "$out_dir" jira-timesheet-qt
tar_mb=$(du -sm "$tarball" | cut -f1)

echo ""
echo "Done in ${elapsed}s"
echo "  dist folder : $dist_dir  (${size_mb} MB)"
echo "  tarball     : $tarball  (${tar_mb} MB)"
echo "  run         : $exe"

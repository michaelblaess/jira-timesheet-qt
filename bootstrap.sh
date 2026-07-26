#!/usr/bin/env bash
# Richtet die Entwicklungsumgebung ein (venv, Abhaengigkeiten, Nuitka).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"

echo "Abhaengigkeiten synchronisieren..."
uv sync --extra dev

echo "Nuitka bereitstellen..."
uv pip install nuitka

echo
echo "Fertig. Starten mit:  ./run.sh"
echo "Mit Beispieldaten:    ./run.sh --demo"

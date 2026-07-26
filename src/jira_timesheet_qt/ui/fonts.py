"""Schriftauswahl fuer die Oberflaeche.

Ziel ist ein Schriftbild, das nicht nach Standard-Toolkit aussieht. Bevorzugt
werden die mitgelieferten Schriften des PRECISION-Systems (Manrope und JetBrains
Mono). Liegen sie nicht vor, greift eine Kette moderner Systemschriften - die
Anwendung startet in jedem Fall.

Hinweis: In den GitHub-Pages liegen die Schriften als woff2 vor, was Qt NICHT
laden kann. Fuer resources/fonts/ werden TTF oder OTF gebraucht.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

# Verzeichnis mit mitgelieferten Schriften (TTF/OTF).
FONT_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"

# Wunschschrift zuerst, danach moderne Systemschriften je Plattform.
_SANS_CANDIDATES = (
    "Manrope",
    "Segoe UI Variable Text",  # Windows 11
    "Segoe UI",  # Windows 10
    "SF Pro Text",  # macOS
    "Inter",
    "Ubuntu",
    "Noto Sans",
    "DejaVu Sans",
)

_MONO_CANDIDATES = (
    "JetBrains Mono",
    "Cascadia Code",  # Windows 11
    "SF Mono",  # macOS
    "Consolas",
    "Ubuntu Mono",
    "DejaVu Sans Mono",
)


@dataclass(frozen=True)
class Fonts:
    """Die tatsaechlich verwendeten Schriftfamilien."""

    sans: str
    mono: str


def load_fonts() -> Fonts:
    """Laedt mitgelieferte Schriften und waehlt die beste verfuegbare Familie.

    Returns:
        Die gewaehlten Familien fuer Oberflaeche und dicktengleiche Anzeige.
    """
    _register_bundled_fonts()
    available = set(QFontDatabase.families())
    return Fonts(
        sans=_first_available(_SANS_CANDIDATES, available),
        mono=_first_available(_MONO_CANDIDATES, available),
    )


def _register_bundled_fonts() -> None:
    """Meldet alle Schriften aus resources/fonts bei Qt an."""
    if not FONT_DIR.is_dir():
        return
    for path in sorted(FONT_DIR.glob("*")):
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            logger.warning("Schrift konnte nicht geladen werden: %s", path.name)


def _first_available(candidates: tuple[str, ...], available: set[str]) -> str:
    """Liefert den ersten Kandidaten, den Qt tatsaechlich kennt.

    Kennt Qt keinen davon, kommt eine leere Zeichenkette zurueck. Das
    Stylesheet laesst die Angabe dann weg, sodass Qt seine eigene
    Standardschrift verwendet. Ein erfundener Name wie "sans-serif" ist keine
    Qt-Schriftfamilie und fuehrt zu leeren Kaestchen statt Text.
    """
    return next((name for name in candidates if name in available), "")

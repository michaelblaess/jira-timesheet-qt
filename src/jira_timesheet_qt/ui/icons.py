"""Zugriff auf die Oberflaechensymbole - Material Design Icons via QtAwesome.

QtAwesome (MIT) buendelt die Material Design Icons (mdi6.*, Apache 2.0) als
Icon-Font und faerbt sie zur Laufzeit in einer beliebigen Farbe. Das loest das
fehlende currentColor von QSS OHNE je Erscheinungsbild eine eigene Datei zu
pflegen - und skaliert direkt auf weitere Themenfarben.

Die App spricht die Symbole weiter unter ihren eigenen, sprechenden Namen an
(load_icon("refresh", mode)); die Abbildung auf die mdi6-Glyphen liegt hier.
"""

from __future__ import annotations

import contextlib

import qtawesome as qta
from PySide6.QtGui import QIcon

from jira_timesheet_qt.ui.theme import Mode, palette_for

# App-Symbolname -> Material-Design-Icon (mdi6). Alle Namen sind gegen QtAwesome
# 1.4 geprueft.
GLYPHS: dict[str, str] = {
    "chevron-left": "mdi6.chevron-left",
    "chevron-right": "mdi6.chevron-right",
    "chevron-up": "mdi6.chevron-up",
    "chevron-down": "mdi6.chevron-down",
    "info": "mdi6.information-outline",
    "settings": "mdi6.tune-variant",
    "sun": "mdi6.weather-sunny",
    "moon": "mdi6.weather-night",
    "search": "mdi6.magnify",
    "plus": "mdi6.plus",
    "log": "mdi6.text-box-outline",
    "refresh": "mdi6.refresh",
    "group": "mdi6.format-list-group",
}


def load_icon(name: str, mode: Mode) -> QIcon:
    """Laedt ein Symbol in der Strichfarbe des Erscheinungsbilds.

    Args:
        name:
            Sprechender App-Symbolname (siehe GLYPHS).
        mode:
            Erscheinungsbild - bestimmt die Fuellfarbe.

    Returns:
        Ein QIcon. Ist der Name unbekannt oder scheitert das Rendern, kommt ein
        leeres QIcon zurueck - die Schaltflaeche bleibt bedienbar, sieht nur
        nackt aus (statt eines Absturzes).
    """
    glyph = GLYPHS.get(name)
    if glyph is None:
        return QIcon()
    color = palette_for(mode).text_secondary
    with contextlib.suppress(Exception):
        icon = qta.icon(glyph, color=color)
        if isinstance(icon, QIcon):
            return icon
    return QIcon()

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
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap

from jira_timesheet_qt.ui.theme import Mode, palette_for

# Markenfarbe des App-Icons - fester Orange-Verlauf, gut lesbar auf hellen wie
# dunklen Taskleisten (unabhaengig vom gewaehlten Erscheinungsbild).
_APP_ICON_TOP = "#fb923c"
_APP_ICON_BOTTOM = "#ea580c"
_APP_ICON_GLYPH = "mdi6.timetable"
# Anteil der Kachel, den das freigeschnittene Symbol fuellt.
_APP_ICON_FILL = 0.78


def _glyph_ink(glyph: str, color: str) -> QPixmap | None:
    """Rendert ein Symbol und schneidet den sichtbaren Tintenbereich frei.

    So laesst sich das Symbol spaeter optisch zentrieren - die mdi-Glyphen haben
    je eigene, asymmetrische Innenraender. QtAwesome liefert die Pixmap zudem mit
    dem Device-Pixel-Ratio des Bildschirms (Windows-Skalierung > 1); ohne
    Ruecksetzen driften reale Pixel und logische Breite auseinander und der
    Zuschnitt landet daneben.

    Args:
        glyph:
            Name des mdi-Symbols.
        color:
            Fuellfarbe des Symbols.

    Returns:
        Die freigeschnittene Pixmap, oder None wenn das Rendern scheitert.
    """
    try:
        source = qta.icon(glyph, color=color).pixmap(256, 256)
    except Exception:
        return None
    source.setDevicePixelRatio(1.0)
    image = source.toImage()
    width, height = image.width(), image.height()
    x0, y0, x1, y1 = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 16:
                x0 = min(x0, x)
                y0 = min(y0, y)
                x1 = max(x1, x)
                y1 = max(y1, y)
    if x1 < 0:
        return QPixmap(source)
    return QPixmap(source.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1))


def _compose_icon(size: int, ink: QPixmap | None) -> QPixmap:
    """Setzt eine Icon-Pixmap zusammen: Verlaufskachel plus zentriertes Symbol."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, QColor(_APP_ICON_TOP))
    gradient.setColorAt(1.0, QColor(_APP_ICON_BOTTOM))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    radius = size * 0.22
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    if ink is not None and ink.width() > 0 and ink.height() > 0:
        target = size * _APP_ICON_FILL
        factor = target / max(ink.width(), ink.height())
        scaled = ink.scaled(
            max(1, round(ink.width() * factor)),
            max(1, round(ink.height() * factor)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(
            round((size - scaled.width()) / 2),
            round((size - scaled.height()) / 2),
            scaled,
        )
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """Baut das Fenster-/Taskleisten-Icon der Anwendung.

    Gerundetes Quadrat mit Orange-Verlauf und einem weissen Stundenplan-Symbol,
    optisch zentriert. Zur Laufzeit in mehreren Groessen komponiert - ohne
    Asset-Datei. Das Symbol wird nur einmal freigeschnitten und je Groesse neu
    skaliert.

    Returns:
        Ein QIcon mit Pixmaps von 16 bis 256 Pixeln.
    """
    icon = QIcon()
    ink = None
    with contextlib.suppress(Exception):
        ink = _glyph_ink(_APP_ICON_GLYPH, "#ffffff")
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_compose_icon(size, ink))
    return icon

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

"""Ladeanzeige der Statusleiste in vier waehlbaren Darstellungen.

Bis v0.19 stand hier ein unbestimmter QProgressBar. Fusion zeichnet ihn als
schmalen Streifen, der in der Statusleiste kaum auffaellt. Die drei neuen
Darstellungen zeichnen selbst und greifen den Verlauf des Wochenbands auf,
der alte Balken bleibt als "classic" waehlbar.

Alle Darstellungen sagen nur "laeuft", nie "wie weit" - die Dauer eines
Abrufs ist unbekannt, eine Prozentzahl waere erfunden.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QRadialGradient,
    QShowEvent,
)
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QWidget

from jira_timesheet_qt.models.settings import (
    BUSY_CLASSIC,
    BUSY_COMET,
    BUSY_INDICATORS,
    BUSY_SEGMENTS,
    BUSY_SHIMMER,
    DEFAULT_BUSY_INDICATOR,
)
from jira_timesheet_qt.ui.theme import Mode, Palette, palette_for

# Beschriftungen fuer die Auswahl in den Einstellungen, in Anzeigereihenfolge.
BUSY_LABELS: dict[str, str] = {
    BUSY_SEGMENTS: "Lauflicht",
    BUSY_COMET: "Komet",
    BUSY_SHIMMER: "Schimmer",
    BUSY_CLASSIC: "Klassischer Balken",
}

WIDTH = 120
HEIGHT = 14
# Bildwiederholung nur, solange die Anzeige sichtbar ist.
FRAME_MS = 16

COMET_PERIOD = 1.6
SHIMMER_PERIOD = 1.8
SEGMENT_COUNT = 12
# Segmente je Sekunde, und wie viele Segmente lang ein Segment nachglueht.
SEGMENT_SPEED = 11.0
SEGMENT_AFTERGLOW = 5.0


def _alpha(color: str, alpha: int) -> QColor:
    result = QColor(color)
    result.setAlpha(alpha)
    return result


def pingpong(seconds: float, period: float) -> tuple[float, int]:
    """Position 0..1 mit weichem Abbremsen an beiden Enden.

    Args:
        seconds:
            Laufzeit der Anzeige.
        period:
            Dauer fuer einmal hin und zurueck.

    Returns:
        Position und Laufrichtung (1 nach rechts, -1 nach links).
    """
    phase = (seconds % period) / period
    forward = phase < 0.5
    u = phase * 2 if forward else (1 - phase) * 2
    return (1 - math.cos(u * math.pi)) / 2, 1 if forward else -1


def segment_glow(seconds: float, index: int) -> float:
    """Helligkeit 0..1 eines Lauflicht-Segments.

    Der Kopf laeuft ueber alle Segmente und vier unsichtbare Plaetze dahinter,
    damit zwischen zwei Durchlaeufen kurz Ruhe ist.
    """
    head = (seconds * SEGMENT_SPEED) % (SEGMENT_COUNT + 4)
    behind = head - index
    return max(0.0, 1 - behind / SEGMENT_AFTERGLOW) if behind >= 0 else 0.0


class BusyIndicator(QWidget):
    """Unbestimmte Ladeanzeige fuer die Statusleiste.

    Args:
        mode:
            Erscheinungsbild, aus dem die Farben kommen.
        style:
            Einer der Werte aus BUSY_INDICATORS.
    """

    def __init__(self, mode: Mode, style: str = DEFAULT_BUSY_INDICATOR, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BusyBar")
        self.setFixedSize(WIDTH, HEIGHT)
        self._palette: Palette = palette_for(mode)
        self._clock: Callable[[], float] = time.monotonic
        self._start = self._clock()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self.update)
        # Der alte Balken bleibt ein echter QProgressBar - so sieht er genau
        # aus wie bisher, samt Fusion-Animation.
        self.classic_bar = QProgressBar(self)
        self.classic_bar.setRange(0, 0)
        self.classic_bar.setTextVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.classic_bar)
        self._style = ""
        self.set_style(style)

    @property
    def style_name(self) -> str:
        """Die aktive Darstellung."""
        return self._style

    def set_style(self, style: str) -> None:
        """Wechselt die Darstellung, unbekannte Werte fallen auf die Vorgabe."""
        self._style = style if style in BUSY_INDICATORS else DEFAULT_BUSY_INDICATOR
        self.classic_bar.setVisible(self._style == BUSY_CLASSIC)
        self._sync_timer()
        self.update()

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt die Farben eines neuen Erscheinungsbilds."""
        self._palette = palette_for(mode)
        self.update()

    @property
    def animating(self) -> bool:
        """Ob der eigene Bildtakt laeuft (nur sichtbar und selbstgezeichnet)."""
        return self._timer.isActive()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        super().showEvent(event)
        self._start = self._clock()
        self._sync_timer()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        super().hideEvent(event)
        self._sync_timer()

    def _sync_timer(self) -> None:
        # Unsichtbar oder klassisch: kein Takt, sonst zeichnet die Statusleiste
        # die ganze Zeit fuer nichts.
        if self.isVisible() and self._style != BUSY_CLASSIC:
            self._timer.start()
        else:
            self._timer.stop()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        if self._style == BUSY_CLASSIC:
            super().paintEvent(event)
            return
        seconds = self._clock() - self._start
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._style == BUSY_COMET:
            self._paint_comet(painter, seconds)
        elif self._style == BUSY_SHIMMER:
            self._paint_shimmer(painter, seconds)
        else:
            self._paint_segments(painter, seconds)
        painter.end()

    def _track(self) -> QRectF:
        return QRectF(self.rect()).adjusted(0.5, 3.5, -0.5, -3.5)

    def _paint_comet(self, painter: QPainter, seconds: float) -> None:
        p = self._palette
        track = self._track()
        radius = track.height() / 2
        painter.setBrush(_alpha(p.accent, 40))
        painter.drawRoundedRect(track, radius, radius)
        pos, direction = pingpong(seconds, COMET_PERIOD)
        head = track.left() + radius + pos * (track.width() - 2 * radius)
        end = head - direction * track.width() * 0.55
        tail = QLinearGradient(QPointF(end, 0), QPointF(head, 0))
        tail.setColorAt(0.0, _alpha(p.accent, 0))
        tail.setColorAt(0.7, _alpha(p.accent, 150))
        tail.setColorAt(1.0, _alpha(p.accent, 255))
        painter.save()
        painter.setClipRect(track)
        painter.setBrush(tail)
        left, right = min(end, head), max(end, head)
        painter.drawRoundedRect(QRectF(left, track.top(), right - left, track.height()), radius, radius)
        painter.restore()
        center = QPointF(head, track.center().y())
        glow = QRadialGradient(center, 7)
        glow.setColorAt(0.0, QColor(255, 255, 255, 230))
        glow.setColorAt(0.35, _alpha(p.accent_hover, 200))
        glow.setColorAt(1.0, _alpha(p.accent, 0))
        painter.setBrush(glow)
        painter.drawEllipse(center, 7, 7)

    def _paint_shimmer(self, painter: QPainter, seconds: float) -> None:
        p = self._palette
        track = self._track()
        radius = track.height() / 2
        base = QLinearGradient(track.topLeft(), track.topRight())
        base.setColorAt(0.0, _alpha(p.accent, 70))
        base.setColorAt(1.0, _alpha(p.accent, 210))
        painter.setBrush(base)
        painter.drawRoundedRect(track, radius, radius)
        phase = (seconds % SHIMMER_PERIOD) / SHIMMER_PERIOD
        width = 46.0
        x = track.left() - width + phase * (track.width() + 2 * width)
        shine = QLinearGradient(QPointF(x, 0), QPointF(x + width, 0))
        shine.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine.setColorAt(0.5, QColor(255, 255, 255, 170))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setClipRect(track)
        painter.setBrush(shine)
        painter.drawRoundedRect(track, radius, radius)

    def _paint_segments(self, painter: QPainter, seconds: float) -> None:
        p = self._palette
        track = self._track().adjusted(0, -1, 0, 1)
        gap = 3.0
        width = (track.width() - gap * (SEGMENT_COUNT - 1)) / SEGMENT_COUNT
        for index in range(SEGMENT_COUNT):
            glow = segment_glow(seconds, index)
            segment = QRectF(track.left() + index * (width + gap), track.top(), width, track.height())
            painter.setBrush(_alpha(p.accent, int(35 + 220 * glow)))
            painter.drawRoundedRect(segment, 2, 2)
            if glow > 0.85:
                # Der Kopf bekommt einen hellen Kern, damit er leuchtet statt nur satter zu sein.
                painter.setBrush(QColor(255, 255, 255, int(160 * (glow - 0.85) / 0.15)))
                painter.drawRoundedRect(segment.adjusted(1, 1, -1, -1), 1.5, 1.5)

"""Vollflaechiges Hintergrundbild fuer den Leerzustand.

Zeichnet ein Bild formatfuellend (cover: zentriert zugeschnitten, nie verzerrt)
hinter dem Inhalt - das Seitenverhaeltnis bleibt erhalten, ueberstehende Raender
werden beschnitten. Das Bild wird nur geladen, solange das Widget sichtbar ist:
sobald Daten da sind und der Leerzustand verschwindet, gibt hideEvent den
Speicher wieder frei (ein 1440x720-Bild sonst dauerhaft im RAM).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QHideEvent, QPainter, QPaintEvent, QPixmap, QShowEvent
from PySide6.QtWidgets import QWidget


class HeroBackground(QWidget):
    """Malt ein formatfuellendes Hintergrundbild, lazy geladen und wieder freigegeben."""

    def __init__(self, image_path: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = image_path if image_path is not None and image_path.is_file() else None
        self._pixmap = QPixmap()

    def has_image(self) -> bool:
        """True, wenn ein gueltiger Bildpfad hinterlegt ist."""
        return self._path is not None

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Beim Sichtbarwerden das Bild (nach)laden."""
        if self._path is not None and self._pixmap.isNull():
            self._pixmap = QPixmap(str(self._path))
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        """Beim Verbergen (Daten geladen) das Bild aus dem Speicher werfen."""
        self._pixmap = QPixmap()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = self.rect()
        scaled = self._pixmap.scaled(
            area.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Zentriert zuschneiden: den ueberstehenden Rand gleichmaessig kappen.
        x = (scaled.width() - area.width()) // 2
        y = (scaled.height() - area.height()) // 2
        painter.drawPixmap(area, scaled, QRect(x, y, area.width(), area.height()))
        painter.end()

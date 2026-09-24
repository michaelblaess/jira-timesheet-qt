"""Kleiner Lade-Kreisel fuer Stellen, an denen ein Abruf ohne Fortschrittszahl laeuft.

Ein drehender Kreisbogen, selbst gezeichnet - Qt bringt keinen mit, und eine
QProgressBar ohne Bereich ist ein Balken, kein Kreis.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

# Grad je Schritt und Schrittweite in ms - eine Umdrehung pro Sekunde.
_STEP_DEGREES = 30
_INTERVAL_MS = 1000 * _STEP_DEGREES // 360
# Laenge des sichtbaren Bogens in Grad.
_ARC_DEGREES = 270


class BusySpinner(QWidget):
    """Drehender Kreisbogen. Ausgeblendet haelt er seinen Platz, damit nichts springt."""

    def __init__(self, diameter: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(QSize(diameter, diameter))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        policy = self.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(policy)
        self.setToolTip("Wird geladen ...")
        self.hide()

    def start(self) -> None:
        """Zeigt den Kreisel und laesst ihn drehen."""
        self._angle = 0
        self.show()
        self._timer.start()

    def stop(self) -> None:
        """Haelt ihn an und blendet ihn aus."""
        self._timer.stop()
        self.hide()

    def is_spinning(self) -> bool:
        """Ob der Kreisel gerade laeuft."""
        return self._timer.isActive()

    def _advance(self) -> None:
        self._angle = (self._angle + _STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(2.0, self._diameter / 8)
        pen = QPen(self.palette().highlight().color(), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        inset = width / 2 + 0.5
        rect = QRectF(inset, inset, self._diameter - 2 * inset, self._diameter - 2 * inset)
        # Qt zaehlt in 1/16 Grad, gegen den Uhrzeigersinn - negativ dreht rechtsherum.
        painter.drawArc(rect, -self._angle * 16, _ARC_DEGREES * 16)
        painter.end()

"""Kurze, selbst verschwindende Benachrichtigung (Toast).

Ein schwebendes Panel unten rechts ueber dem Inhalt, das eine kurze Meldung
zeigt ("Einstellungen gespeichert") und nach wenigen Sekunden wieder ausblendet.
Es faengt keine Mausklicks ab und liegt als Kind des Zentral-Widgets ueber den
Ansichten, damit es beim Fensterwechsel mitwandert.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget


class Toast(QFrame):
    """Blendet eine kurze Meldung unten rechts ein und nach kurzer Zeit wieder aus."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        # Klicks gehen durch den Toast hindurch auf die Ansicht darunter.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 20, 14)
        layout.setSpacing(12)
        self._icon = QLabel(self)
        self._icon.setObjectName("ToastIcon")
        self._icon.setVisible(False)
        layout.addWidget(self._icon)
        self._label = QLabel(self)
        self._label.setObjectName("ToastText")
        layout.addWidget(self._label)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        self.hide()

    def show_message(self, text: str, icon: QPixmap | None = None, msec: int = 4200) -> None:
        """Zeigt die Meldung (optional mit Icon), blendet ein und laeuft nach msec aus."""
        self._label.setText(text)
        if icon is not None and not icon.isNull():
            self._icon.setPixmap(icon)
            self._icon.setVisible(True)
        else:
            self._icon.setVisible(False)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._fade(1.0, 180)
        self._timer.start(msec)

    def _fade_out(self) -> None:
        self._fade(0.0, 320)

    def _fade(self, target: float, duration: int) -> None:
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        # Nach dem Ausblenden wirklich verbergen (spart Neuzeichnen).
        if self._effect.opacity() <= 0.01:
            self.hide()

    def _reposition(self) -> None:
        """Setzt den Toast unten rechts im Elternbereich, mit Rand."""
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 24
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(max(margin, x), max(margin, y))

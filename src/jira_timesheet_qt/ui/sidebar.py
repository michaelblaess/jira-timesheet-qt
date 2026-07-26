"""Seitenleiste: Ansichtswechsel und Monatssumme.

Ersetzt die Reiter eines QTabWidget - Reiter sind eines der auffaelligsten
Merkmale einer Standard-Qt-Anwendung.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


class NavButton(QPushButton):
    """Eintrag der Seitenleiste. Der aktive Zustand haengt an einer Property.

    Qt kann Properties in QSS abfragen (NavButton[active="true"]), damit bleibt
    die Farbgebung vollstaendig im Stylesheet.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setProperty("active", False)

    def set_active(self, active: bool) -> None:
        """Setzt den aktiven Zustand und erzwingt ein Neuzeichnen."""
        self.setProperty("active", active)
        self.setChecked(active)
        # Qt wendet geaenderte Properties erst nach einem Style-Refresh an.
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class Sidebar(QWidget):
    """Linke Leiste mit Ansichtswahl und Summe."""

    view_changed = Signal(int)

    def __init__(self, views: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(3)

        caption = QLabel("ANSICHT")
        caption.setObjectName("SidebarSection")
        layout.addWidget(caption)

        self._buttons: list[NavButton] = []
        for position, name in enumerate(views):
            button = NavButton(name)
            button.clicked.connect(lambda _checked=False, i=position: self._on_click(i))
            layout.addWidget(button)
            self._buttons.append(button)

        layout.addStretch(1)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(divider)
        layout.addSpacing(10)

        total_caption = QLabel("SUMME")
        total_caption.setObjectName("SidebarTotalLabel")
        layout.addWidget(total_caption)

        self._total = QLabel("0,00 h")
        self._total.setObjectName("SidebarTotalValue")
        self._total.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._total)

        if self._buttons:
            self._buttons[0].set_active(True)

    def set_total(self, hours: float) -> None:
        """Aktualisiert die angezeigte Summe (deutsches Dezimalkomma)."""
        self._total.setText(f"{hours:.2f} h".replace(".", ","))

    def _on_click(self, position: int) -> None:
        for index, button in enumerate(self._buttons):
            button.set_active(index == position)
        self.view_changed.emit(position)

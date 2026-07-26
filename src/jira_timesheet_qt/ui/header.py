"""Kopfzeile mit Zeitraum, Monatsnavigation, Suche und Aktionen.

Ersetzt Menueleiste und Fusszeile der TUI. Eine QMenuBar kommt bewusst nicht
zum Einsatz - sie ist das deutlichste Merkmal einer Standard-Desktop-Anwendung.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

_MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


class Header(QWidget):
    """Obere Leiste der Anwendung."""

    previous_month = Signal()
    next_month = Signal()
    search_changed = Signal(str)
    settings_requested = Signal()
    theme_toggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        self._title = QLabel("Kein Zeitraum")
        self._title.setObjectName("HeaderTitle")
        self._subtitle = QLabel("Noch keine Daten geladen")
        self._subtitle.setObjectName("HeaderSubtitle")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        layout.addLayout(titles)

        layout.addSpacing(12)
        layout.addWidget(self._nav_button("‹", "Vorheriger Monat", self.previous_month.emit))
        layout.addWidget(self._nav_button("›", "Nächster Monat", self.next_month.emit))
        layout.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Suchen ...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self._search)

        layout.addWidget(self._nav_button("◐", "Erscheinungsbild wechseln", self.theme_toggled.emit))
        layout.addWidget(self._nav_button("⚙", "Einstellungen", self.settings_requested.emit))

    def set_period(self, title: str, subtitle: str) -> None:
        """Setzt Ueberschrift und Zusatzzeile."""
        self._title.setText(title)
        self._subtitle.setText(subtitle)

    def focus_search(self) -> None:
        """Setzt den Eingabefokus in das Suchfeld."""
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    @staticmethod
    def month_name(month: int) -> str:
        """Deutscher Monatsname zu einer Monatszahl von 1 bis 12."""
        return _MONTHS[month - 1] if 1 <= month <= len(_MONTHS) else ""

    def _nav_button(self, glyph: str, tooltip: str, slot: object) -> QPushButton:
        """Baut eine rahmenlose Schaltflaeche fuer die Kopfzeile."""
        button = QPushButton(glyph)
        button.setProperty("variant", "ghost")
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedWidth(36)
        button.clicked.connect(slot)  # type: ignore[arg-type]
        return button

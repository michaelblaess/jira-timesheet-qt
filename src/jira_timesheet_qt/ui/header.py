"""Kopfzeile mit Zeitraum, Monatsnavigation, Suche und Aktionen.

Ersetzt Menueleiste und Fusszeile der TUI. Eine QMenuBar kommt bewusst nicht
zum Einsatz - sie ist das deutlichste Merkmal einer Standard-Desktop-Anwendung.
Die Schaltflaechen tragen eigene SVG-Symbole statt Unicode-Glyphen: Windows
rendert ⚙ oder ◐ als farbige Emoji, verwaschen und nicht einfaerbbar.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from jira_timesheet_qt.ui.icons import load_icon
from jira_timesheet_qt.ui.theme import Mode

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
    about_requested = Signal()
    theme_toggled = Signal()
    reload_requested = Signal()
    log_toggled = Signal()
    manual_requested = Signal()

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(64)
        self._mode = mode
        self._buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        self._title = QLabel("Kein Zeitraum")
        self._title.setObjectName("HeaderTitle")
        self._subtitle = QLabel("Noch keine Daten geladen")
        self._subtitle.setObjectName("HeaderSubtitle")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        layout.addLayout(titles)

        layout.addSpacing(14)
        layout.addWidget(self._button("chevron-left", "Vorheriger Monat", self.previous_month.emit))
        layout.addWidget(self._button("chevron-right", "Nächster Monat", self.next_month.emit))
        layout.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Suchen ...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self._search)

        layout.addWidget(
            self._button("plus", "Manuelle Zeit erfassen (Strg+N)", self.manual_requested.emit)
        )
        layout.addWidget(self._button("refresh", "Neu laden (F5)", self.reload_requested.emit))
        layout.addWidget(self._button("log", "Log ein-/ausblenden (Strg+L)", self.log_toggled.emit))
        layout.addWidget(
            self._button(self._theme_icon(), "Erscheinungsbild wechseln", self.theme_toggled.emit, key="theme")
        )
        layout.addWidget(self._button("info", "Über diese Anwendung (F1)", self.about_requested.emit))
        layout.addWidget(self._button("settings", "Einstellungen (Strg+,)", self.settings_requested.emit))

    # --- Inhalte --------------------------------------------------------

    def set_period(self, title: str, subtitle: str) -> None:
        """Setzt Ueberschrift und Zusatzzeile."""
        self._title.setText(title)
        self._subtitle.setText(subtitle)

    def focus_search(self) -> None:
        """Setzt den Eingabefokus in das Suchfeld."""
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def apply_mode(self, mode: Mode) -> None:
        """Tauscht die Symbole, wenn das Erscheinungsbild wechselt."""
        self._mode = mode
        for key, button in self._buttons.items():
            button.setIcon(load_icon(self._theme_icon() if key == "theme" else key, mode))

    @staticmethod
    def month_name(month: int) -> str:
        """Deutscher Monatsname zu einer Monatszahl von 1 bis 12."""
        return _MONTHS[month - 1] if 1 <= month <= len(_MONTHS) else ""

    # --- Bausteine ------------------------------------------------------

    def _theme_icon(self) -> str:
        """Zeigt das Ziel des Wechsels, nicht den aktuellen Zustand."""
        return "sun" if self._mode is Mode.DARK else "moon"

    def _button(
        self,
        name: str,
        tooltip: str,
        slot: Callable[[], None],
        key: str = "",
    ) -> QPushButton:
        """Baut eine rahmenlose Schaltflaeche mit Symbol."""
        button = QPushButton()
        button.setProperty("variant", "ghost")
        button.setIcon(load_icon(name, self._mode))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(34, 34)
        button.clicked.connect(slot)
        self._buttons[key or name] = button
        return button

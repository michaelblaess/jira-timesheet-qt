"""Detailbereich rechts neben der Liste.

Ersetzt den Modal-Dialog der TUI: die Auswahl in der Tabelle aktualisiert ihn
unmittelbar, er verdeckt nichts und muss nicht geschlossen werden.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from jira_timesheet_qt.models.timesheet import WorklogEntry

_WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


class DetailPanel(QWidget):
    """Zeigt die Einzelheiten des gewaehlten Eintrags."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)

        self._key = QLabel()
        self._key.setObjectName("DetailKey")
        self._key.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._key)

        self._summary = QLabel()
        self._summary.setObjectName("DetailSummary")
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._summary)

        layout.addSpacing(8)
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._fields: dict[str, QLabel] = {}
        for key, caption in (
            ("date", "DATUM"),
            ("hours", "DAUER"),
            ("author", "AUTOR"),
            ("budget", "BUDGET"),
            ("source", "QUELLE"),
        ):
            label = QLabel(caption)
            label.setObjectName("DetailLabel")
            layout.addWidget(label)

            value = QLabel("-")
            value.setObjectName("DetailValueMono" if key in ("date", "hours") else "DetailValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(value)
            layout.addSpacing(8)
            self._fields[key] = value

        layout.addStretch(1)
        self.clear()

    def clear(self) -> None:
        """Zeigt den Zustand ohne Auswahl."""
        self._key.setText("Kein Eintrag gewählt")
        self._summary.setText("Wähle links eine Zeile aus, um die Einzelheiten zu sehen.")
        for value in self._fields.values():
            value.setText("-")

    def show_entry(self, entry: WorklogEntry) -> None:
        """Uebernimmt die Werte eines Eintrags in die Anzeige."""
        self._key.setText(entry.ticket or "Ohne Vorgang")
        self._summary.setText(entry.summary or "-")
        weekday = _WEEKDAYS[entry.date.weekday()]
        self._fields["date"].setText(f"{entry.date.strftime('%d.%m.%Y')} ({weekday})")
        self._fields["hours"].setText(f"{entry.hours:.2f} h".replace(".", ","))
        self._fields["author"].setText(entry.author or "-")
        self._fields["budget"].setText(entry.budget or "-")
        self._fields["source"].setText("Manuell erfasst" if entry.manual else "Aus Jira")

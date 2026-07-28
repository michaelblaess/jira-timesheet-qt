"""Modaler Dialog mit den Einzelheiten eines Eintrags.

Loest den frueheren Detailbereich rechts ab: der verbrauchte Platz und lieferte
in der Kalender-/Jahresansicht keine Zeilendaten. Wie in der TUI kommen die
Details jetzt per Doppelklick, Toolbar-Knopf oder Kontextmenue als eigenes
Fenster.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

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


class TicketDetailDialog(QDialog):
    """Zeigt alle Felder eines Eintrags in einem eigenen Fenster."""

    def __init__(self, entry: WorklogEntry, jira_host: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("TicketDetailDialog")
        self.setWindowTitle(entry.ticket or "Eintrag")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 20)
        outer.setSpacing(14)

        title = QLabel(self._title_text(entry))
        title.setObjectName("DetailDialogTitle")
        title.setWordWrap(True)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(title)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(divider)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for row, (caption, value) in enumerate(self._rows(entry)):
            label = QLabel(f"{caption}:")
            label.setObjectName("DetailDialogLabel")
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

            content = QLabel(value or "-")
            content.setObjectName("DetailDialogValue")
            content.setWordWrap(True)
            content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(content, row, 1)
        outer.addLayout(grid)

        link = self._link_label(entry, jira_host)
        if link is not None:
            outer.addSpacing(2)
            outer.addWidget(link)

        outer.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText("Schließen")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.reject)
        outer.addWidget(buttons)

    @staticmethod
    def _title_text(entry: WorklogEntry) -> str:
        """Titelzeile: Ticket und Beschreibung, oder nur die Beschreibung."""
        if entry.ticket and entry.summary:
            return f"{entry.ticket} - {entry.summary}"
        return entry.ticket or entry.summary or "Ohne Vorgang"

    @staticmethod
    def _rows(entry: WorklogEntry) -> list[tuple[str, str]]:
        """Beschriftung und Wert je Feld, in der Reihenfolge der TUI."""
        weekday = _WEEKDAYS[entry.date.weekday()]
        return [
            ("Datum", f"{entry.date.strftime('%d.%m.%Y')} ({weekday})"),
            ("Stunden", f"{entry.hours:.2f} h".replace(".", ",")),
            ("Kunde", entry.customer),
            ("Autor", entry.author),
            ("Bearbeiter", entry.assignee),
            ("Typ", entry.issuetype),
            ("Status", entry.status),
            ("Priorität", entry.priority),
            ("Budget", entry.budget or "nicht zugeordnet"),
            ("Erstellt", entry.created),
            ("Aktualisiert", entry.updated),
            ("Gesamt-Protokoll", entry.total_logged),
            ("Quelle", "Manuell erfasst" if entry.manual else "Aus Jira"),
        ]

    def _link_label(self, entry: WorklogEntry, jira_host: str) -> QLabel | None:
        """Klickbarer Jira-Link, oder None fuer manuelle Eintraege ohne Host."""
        host = jira_host.rstrip("/")
        if not host or not entry.ticket or entry.manual:
            return None
        url = f"{host}/browse/{html.escape(entry.ticket)}"
        label = QLabel(f'<a href="{url}">{url}</a>')
        label.setObjectName("DetailDialogLink")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(lambda target: QDesktopServices.openUrl(QUrl(target)))
        return label

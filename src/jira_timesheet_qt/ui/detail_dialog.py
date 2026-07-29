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
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Kopf-Banner wie im Info-Dialog: abgesetzte Flaeche mit Trennlinie
        # darunter (border-bottom). Ticket prominent, Beschreibung als Untertitel.
        banner = QWidget()
        banner.setObjectName("DetailBanner")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(24, 20, 24, 18)
        banner_layout.setSpacing(3)

        head_text, subtitle_text = self._header_parts(entry)
        head = QLabel(head_text)
        head.setObjectName("DetailBannerTicket")
        head.setWordWrap(True)
        head.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        banner_layout.addWidget(head)
        if subtitle_text:
            subtitle = QLabel(subtitle_text)
            subtitle.setObjectName("DetailBannerSummary")
            subtitle.setWordWrap(True)
            subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            banner_layout.addWidget(subtitle)
        outer.addWidget(banner)

        # Koerper mit eigenem Rand (getrennt vom randlosen Banner).
        body = QVBoxLayout()
        body.setContentsMargins(24, 18, 24, 16)
        body.setSpacing(12)
        outer.addLayout(body)

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
        body.addLayout(grid)

        link = self._link_label(entry, jira_host)
        if link is not None:
            body.addSpacing(2)
            body.addWidget(link)

        body.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText("Schließen")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.reject)
        body.addWidget(buttons)

    @staticmethod
    def _header_parts(entry: WorklogEntry) -> tuple[str, str]:
        """Kopfzeile und Untertitel: Ticket prominent, Beschreibung darunter.

        Ohne Ticket (manuelle Eintraege) traegt die Beschreibung den Kopf, der
        Untertitel bleibt leer.
        """
        if entry.ticket and entry.summary:
            return entry.ticket, entry.summary
        return entry.ticket or entry.summary or "Ohne Vorgang", ""

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

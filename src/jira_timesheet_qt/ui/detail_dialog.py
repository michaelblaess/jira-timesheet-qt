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
from jira_timesheet_qt.services.ticket_board import Ticket
from jira_timesheet_qt.ui.ticket_board_model import GROUP_TITLES, MARKER_LABELS

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

    def __init__(
        self,
        entry: WorklogEntry | Ticket,
        jira_host: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("TicketDetailDialog")
        self.setWindowTitle(self._window_title(entry))
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
    def _window_title(entry: WorklogEntry | Ticket) -> str:
        """Fenstertitel: die Ticketnummer, sonst ein Platzhalter."""
        if isinstance(entry, Ticket):
            return entry.key or "Ticket"
        return entry.ticket or "Eintrag"

    @staticmethod
    def _header_parts(entry: WorklogEntry | Ticket) -> tuple[str, str]:
        """Kopfzeile und Untertitel: Ticket prominent, Beschreibung darunter.

        Ohne Ticket (manuelle Eintraege) traegt die Beschreibung den Kopf, der
        Untertitel bleibt leer.
        """
        if isinstance(entry, Ticket):
            return entry.key or entry.summary or "Ticket", entry.summary if entry.key else ""
        if entry.ticket and entry.summary:
            return entry.ticket, entry.summary
        return entry.ticket or entry.summary or "Ohne Vorgang", ""

    @staticmethod
    def _ticket_rows(ticket: Ticket) -> list[tuple[str, str]]:
        """Felder eines Tickets aus den Ticket-Ansichten.

        Bewusst andere Felder als beim Zeiteintrag: Datum, Stunden und
        Kunde gibt es dort nicht, dafuer Liegezeit, Merkmale und Gruppe.
        """
        markers = ", ".join(MARKER_LABELS.get(m, m.value) for m in ticket.markers)
        booked = "-"
        if ticket.has_worklogs is not None:
            booked = (
                "keine Buchung"
                if ticket.booking_workdays is None
                else f"vor {ticket.booking_workdays:.0f} Arbeitstagen"
            )
        return [
            ("Status", ticket.status),
            ("Gruppe", GROUP_TITLES.get(ticket.role, ticket.role.value)),
            ("Autor", ticket.reporter),
            ("Bearbeiter", ticket.assignee),
            ("Typ", ticket.issue_type),
            ("Priorität", ticket.priority),
            (
                "Liegezeit",
                f"{ticket.idle_workdays:.0f} Arbeitstage "
                f"({ticket.idle_days} Kalendertage)",
            ),
            ("Letzte Buchung", booked),
            (
                "Erstellt",
                ticket.created.strftime("%d.%m.%Y") if ticket.created else "-",
            ),
            (
                "Aktualisiert",
                ticket.updated.strftime("%d.%m.%Y %H:%M") if ticket.updated else "-",
            ),
            ("Merkmale", markers or "keine"),
        ]

    @staticmethod
    def _rows(entry: WorklogEntry | Ticket) -> list[tuple[str, str]]:
        """Beschriftung und Wert je Feld, in der Reihenfolge der TUI."""
        if isinstance(entry, Ticket):
            return TicketDetailDialog._ticket_rows(entry)
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

    def _link_label(self, entry: WorklogEntry | Ticket, jira_host: str) -> QLabel | None:
        """Klickbarer Jira-Link, oder None fuer manuelle Eintraege ohne Host."""
        if isinstance(entry, Ticket):
            if not entry.url:
                return None
            url = html.escape(entry.url)
        else:
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

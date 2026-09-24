"""Abruf des Reiters "Neue Tickets" in einem Hintergrund-Thread.

Eine einzige Suche ueber den laengsten Zeitraum und alle Mitglieder. Keine
Widget-Zugriffe, Ergebnisse ausschliesslich ueber Signale.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Sequence

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.new_tickets import FIELDS, build_new_tickets, new_tickets_jql
from jira_timesheet_qt.services.ssl_support import tls_from_settings
from jira_timesheet_qt.services.team import TeamMember
from jira_timesheet_qt.services.ticket_board import AccountIdError, BoardConfig, Ticket


class NewTicketsWorker(QThread):
    """Holt die neuen Tickets aller Mitglieder seit einem Tag."""

    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        config: BoardConfig,
        members: Sequence[TeamMember],
        since: dt.date,
        parent: QObject | None = None,
    ) -> None:
        """Baut den Faden.

        Args:
            settings:
                Die geladenen Benutzereinstellungen.
            config:
                Rollenzuordnung und Prioritaeten.
            members:
                Die Merkliste. Leer ist ein Aufruferfehler - das Fenster
                meldet den Fall vorher selbst.
            since:
                Erster Tag des Abrufs, einschliesslich.
            parent:
                Das Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._config = config
        self._members = tuple(members)
        self._since = since

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            tickets = asyncio.run(self._fetch())
        except AccountIdError:
            self.failed.emit("Eine Kennung in der Merkliste von Mein Team ist unbrauchbar.")
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(tickets)

    async def _fetch(self) -> list[Ticket]:
        """Holt die Rohantworten und baut daraus die Liste."""
        settings = self._settings
        self.progress.emit("Neue Tickets werden geladen ...")
        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            tls=tls_from_settings(settings),
            on_log=self.log.emit,
        )
        # Vor der Sitzung bauen, damit eine kaputte Kennung ohne Netzverkehr abbricht.
        jql = new_tickets_jql(self._members, self._since)
        _, issues = await client.fetch_issues(lambda _aid: [jql], FIELDS)
        tickets = build_new_tickets(
            issues, self._members, self._config, dt.datetime.now(dt.UTC), browse_base=settings.jira_host
        )
        self.log.emit(f"Neue Tickets: {len(tickets)} seit {self._since:%d.%m.%Y}")
        return tickets

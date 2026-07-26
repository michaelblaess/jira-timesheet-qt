"""Abruf der Worklogs in einem Hintergrund-Thread.

Entscheidung E2 des Plans: QThread statt qasync. Der Client ist zwar async,
aber es geht um wenige Netzwerkaufrufe pro Abruf - dafuer reicht ein
Arbeitsfaden, der eine eigene asyncio-Schleife oeffnet. Das spart ein
zusaetzliches Paket und haelt die Qt-Ereignisschleife unberuehrt.

Der Faden darf keine Widgets anfassen. Ergebnisse gehen ausschliesslich ueber
Signale zurueck, die Qt in den Hauptfaden zustellt.
"""

from __future__ import annotations

import asyncio
from datetime import date

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.manual_entry_service import ManualEntryService
from jira_timesheet_qt.services.timesheet_service import TimesheetService


class WorklogWorker(QThread):
    """Holt die Worklogs eines Zeitraums und baut den Stundenzettel."""

    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        settings: Settings,
        date_from: date,
        date_to: date,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._from = date_from
        self._to = date_to

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            timesheet = asyncio.run(self._fetch())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(timesheet)

    async def _fetch(self) -> Timesheet:
        """Holt die Eintraege und mischt die manuell erfassten Zeiten dazu."""
        settings = self._settings
        self.progress.emit("Verbinde mit Jira ...")

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            on_log=self.progress.emit,
        )
        entries = await client.get_worklogs(self._from, self._to)
        self.progress.emit(f"{len(entries)} Einträge aus Jira erhalten")

        manual = ManualEntryService().worklogs_between(self._from, self._to, author=settings.email)
        if manual:
            entries = [*entries, *manual]
            self.progress.emit(f"{len(manual)} manuell erfasste Einträge ergänzt")

        return TimesheetService.build_timesheet(
            entries=entries,
            developer=settings.email or "Unbekannt",
            email=settings.email,
            date_from=self._from,
            date_to=self._to,
        )

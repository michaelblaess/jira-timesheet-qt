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

from jira_timesheet_qt.i18n import t
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.ticket_lifecycle import TicketLifecycleData
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.manual_entry_service import ManualEntryService
from jira_timesheet_qt.services.ticket_report import lifecycle
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


class TicketReportWorker(QThread):
    """Holt die Rohdaten eines Tickets fuer die Ticket-Analyse.

    Der Abruf dauert je nach Ticketgroesse ein bis mehrere Sekunden - er
    gehoert deshalb wie der Worklog-Abruf in einen eigenen Faden.
    """

    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, settings: Settings, key: str, parent: QObject | None = None) -> None:
        """Merkt sich Zugang und Ticket.

        Args:
            settings:
                Zugangsdaten aus den Einstellungen.
            key:
                Ticket-Key, z.B. "ABC-123".
            parent:
                Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._key = key

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            data = asyncio.run(self._fetch())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(data)

    async def _fetch(self) -> TicketLifecycleData:
        """Holt Issue, Aenderungsprotokoll und Kommentare."""
        settings = self._settings
        self.progress.emit(t("ticket_report.progress_fetch").format(ticket=self._key))

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            on_log=self.progress.emit,
        )
        daten = await client.get_ticket_lifecycle(self._key)

        # Titel der nur im Text erwaehnten Tickets nachreichen - ein Aufruf
        # fuer alle, damit die Karten im Bericht nicht nur den Key zeigen.
        leben = lifecycle.from_raw(daten.issue, daten.changelog, daten.comments)
        offen = [key for key in leben.mentioned if key not in leben.titles]
        if offen:
            daten.titles = await client.get_ticket_summaries(offen)
        return daten


class BudgetFieldWorker(QThread):
    """Ermittelt das Budget-Custom-Field ueber die Jira-Cloud-API.

    Laeuft im Hintergrund, damit der Einstellungsdialog waehrend des einen
    Netzwerkaufrufs nicht einfriert. Ergebnis ist eine Liste von
    (field_id, field_name)-Tupeln - leer, wenn kein Feld passt.
    """

    found = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        host: str,
        email: str,
        token: str,
        proxy: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._email = email
        self._token = token
        self._proxy = proxy

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            matches = asyncio.run(self._detect())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - jede Netz-/Parse-Panne gemeldet, nie stiller Tod
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.found.emit(matches)

    async def _detect(self) -> list[tuple[str, str]]:
        """Fragt die Custom-Fields ab (Cloud-Modus, Autoerkennung nur dort)."""
        client = JiraClient(
            host=self._host,
            email=self._email,
            token=self._token,
            legacy=False,
            proxy=self._proxy,
        )
        return await client.detect_budget_field("budget")

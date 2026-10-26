"""Abruf des Ticketflusses in einem Hintergrund-Thread.

Wie bei den uebrigen Ansichten: QThread mit eigener asyncio-Schleife, keine
Widget-Zugriffe, Ergebnisse nur ueber Signale. Die Abfolge der Abrufe steht
im Kern (services.ticket_flow.load_flow), hier wird nur verdrahtet.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.performance import SELF_NAME, ChangelogCache
from jira_timesheet_qt.services.ssl_support import tls_from_settings
from jira_timesheet_qt.services.team import TeamMember
from jira_timesheet_qt.services.ticket_board import AccountIdError
from jira_timesheet_qt.services.ticket_flow import FlowLoad, load_flow


class TicketFlowWorker(QThread):
    """Holt alle Tickets mit Beteiligung einer Person samt Aenderungsprotokoll."""

    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        member: TeamMember | None,
        since: dt.date | None,
        cache_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        """Baut den Faden.

        Args:
            settings:
                Die geladenen Benutzereinstellungen.
            member:
                Die Person in der Mitte. None = der angemeldete Benutzer.
            since:
                Erster Tag der Suche, None = ohne Untergrenze.
            cache_dir:
                Wurzel der Protokoll-Ablage. Eine eigene, nicht die des
                Performance-Boosters - der stempelt mit dem Abschlussdatum,
                hier wird mit ``updated`` gestempelt, und zwei Stempel auf
                denselben Dateien wuerden sich gegenseitig verdraengen.
            parent:
                Das Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._ids = member.account_ids if member is not None else ()
        self._name = member.display_name if member is not None else SELF_NAME
        self._since = since
        self._cache_dir = cache_dir

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            result = asyncio.run(self._fetch())
        except AccountIdError:
            self.failed.emit("Die Kennung dieser Person ist unbrauchbar - bitte in der Merkliste prüfen.")
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(result)

    def _phase(self, text: str) -> None:
        """Meldet einen Zwischenstand in Statuszeile und Verlauf."""
        self.progress.emit(text)
        self.log.emit(text)

    async def _fetch(self) -> FlowLoad:
        """Holt Suche und Protokolle und baut die Kanten."""
        settings = self._settings
        span = f"seit {self._since:%d.%m.%Y}" if self._since is not None else "ohne Untergrenze"
        self._phase(f"Ticketfluss: {self._name}, {span} wird geladen ...")
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
        cache = ChangelogCache(self._cache_dir, settings.jira_host)
        result = await load_flow(client, cache, self._ids, self._since, self._phase)
        data = result.data
        self.log.emit(
            f"Ticketfluss: {len(data.edges)} Wege, Protokolle {result.cached} aus der Ablage, "
            f"{result.fetched} abgerufen, {len(data.missing)} ohne Protokoll"
        )
        if data.missing:
            # Die Schluessel ins Protokoll, damit "fehlt" nachpruefbar bleibt.
            self.log.emit(f"Ohne Protokoll (keine Wege): {', '.join(data.missing)}")
        return result

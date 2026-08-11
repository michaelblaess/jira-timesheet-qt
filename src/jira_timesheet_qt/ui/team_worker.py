"""Hintergrund-Faden fuer die Personensuche der Merkliste "Mein Team".

Die Suche laeuft in zwei Stufen: erst die Konten zum Suchbegriff, dann je
Konto die Zahl offener Tickets und das juengste Ticket. Die zweite Stufe
kostet zwei Abrufe je Treffer und ist trotzdem noetig - ohne sie kann niemand
entscheiden, welches von mehreren Konten einer Person das aktuelle ist.
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.team import (
    AccountCandidate,
    parse_search,
    sort_candidates,
    with_last_touch,
)
from jira_timesheet_qt.services.ticket_board import assigned_jql, last_touch_jql


class TeamSearchWorker(QThread):
    """Sucht Konten zu einem Namen und reichert sie um Zahlen an."""

    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        settings: Settings,
        query: str,
        parent: QObject | None = None,
    ) -> None:
        """Baut den Faden fuer eine Suche.

        Args:
            settings:
                Die geladenen Benutzereinstellungen, liefern den Zugang.
            query:
                Der Suchbegriff, ueblicherweise ein Nachname.
            parent:
                Das Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._query = query

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            hits = asyncio.run(self._search())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(hits)

    async def _search(self) -> list[AccountCandidate]:
        """Holt die Treffer und reichert sie an.

        Returns:
            Die Kandidaten, nach Aktualitaet sortiert. Konten, deren Zahlen
            nicht abrufbar waren, bleiben mit leeren Spalten enthalten -
            weglassen waere schlimmer als eine Luecke, denn gerade das Konto
            mit der meisten Arbeit gibt oft am wenigsten preis.
        """
        settings = self._settings
        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
        )

        found = parse_search(await client.fetch_people(self._query))
        facts = await client.fetch_account_facts(
            [candidate.account_id for candidate in found],
            lambda aid: assigned_jql([aid]),
            last_touch_jql,
        )

        enriched: list[AccountCandidate] = []
        for candidate in found:
            numbers = facts.get(candidate.account_id)
            if numbers is None:
                # Abruf gescheitert: Spalten bleiben leer statt geraten.
                enriched.append(candidate)
                continue
            open_count, youngest = numbers
            dated = with_last_touch(candidate, youngest)
            enriched.append(
                AccountCandidate(
                    account_id=dated.account_id,
                    display_name=dated.display_name,
                    email=dated.email,
                    avatar_url=dated.avatar_url,
                    open_count=open_count,
                    last_touch=dated.last_touch,
                )
            )

        return sort_candidates(enriched)

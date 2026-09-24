"""Abruf des Performance-Boosters in einem Hintergrund-Thread.

Wie bei den Ticket-Ansichten: QThread mit eigener asyncio-Schleife, keine
Widget-Zugriffe, Ergebnisse nur ueber Signale. Hier kommen Client und Kern
zusammen.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.performance import (
    PERF_FIELDS,
    SELF_NAME,
    ChangelogCache,
    HintConfig,
    PerformanceReport,
    build_report,
    closed_jql,
    created_jql,
    done_since_jql,
    period_for,
    worklog_jql,
)
from jira_timesheet_qt.services.ssl_support import tls_from_settings
from jira_timesheet_qt.services.team import TeamMember
from jira_timesheet_qt.services.ticket_board import AccountIdError, BoardConfig, assigned_jql, parse_ts
from jira_timesheet_qt.services.ticket_preview import resolve_field_ids

# Obergrenze fuer die Fertig-Status im Rollenprofil, wenn keine gepflegt sind.
_MAX_CLOSED_STATUSES = 25


def _unique_count(issues: list[dict[str, Any]]) -> int:
    """Anzahl verschiedener Tickets - eine OR-Suche kann eines mehrfach liefern."""
    return len({str(issue.get("key") or "") for issue in issues} - {""})


def hint_config_from(settings: Settings) -> HintConfig:
    """Uebersetzt die Einstellungen in die Schwellen des Kerns."""
    return HintConfig(
        long_days=float(settings.perf_long_days),
        small_hours=float(settings.perf_small_hours),
        small_share=float(settings.perf_small_share),
        wip_limit=int(settings.perf_wip_limit),
        days_per_point=float(settings.perf_days_per_point),
    )


class PerformanceWorker(QThread):
    """Holt Tickets, Protokolle und Buchungen einer Person und baut den Bericht."""

    finished_ok = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        config: BoardConfig,
        member: TeamMember | None,
        period: str,
        cache_dir: Path,
        parent: QObject | None = None,
        today: dt.date | None = None,
    ) -> None:
        """Baut den Faden.

        Args:
            settings:
                Die geladenen Benutzereinstellungen.
            config:
                Rollenzuordnung der Status.
            member:
                Die gemeinte Person. None = der angemeldete Benutzer.
            period:
                Kuerzel des Zeitraums (1M, 3M, 6M, YTD).
            cache_dir:
                Wurzel der Protokoll-Ablage.
            parent:
                Das Qt-Elternobjekt.
            today:
                Enddatum, fuer Tests. Vorgabe: heute.
        """
        super().__init__(parent)
        self._settings = settings
        self._config = config
        self._member = member
        self._ids = member.account_ids if member is not None else ()
        self._name = member.display_name if member is not None else SELF_NAME
        self._period = period
        self._cache_dir = cache_dir
        self._today = today or dt.date.today()

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            report = asyncio.run(self._fetch())
        except AccountIdError:
            self.failed.emit("Die Kennung dieser Person ist unbrauchbar - bitte in der Merkliste prüfen.")
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(report)

    def _phase(self, text: str) -> None:
        """Meldet einen Zwischenstand in Statuszeile und Verlauf."""
        self.progress.emit(text)
        self.log.emit(text)

    async def _fetch(self) -> PerformanceReport:
        """Holt alle Rohdaten und baut den Bericht."""
        settings = self._settings
        current, prior = period_for(self._period, self._today)
        self._phase(f"Performance-Booster: {self._name}, {self._period} wird geladen ...")
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
        ids = self._ids
        notes: list[str] = []

        points_field = await self._points_field(client, notes)
        fields = f"{PERF_FIELDS},{points_field}" if points_field else PERF_FIELDS
        _, issues = await client.fetch_issues(
            lambda _aid: [done_since_jql(ids, prior.start), assigned_jql(ids)], fields
        )
        statuses = await client.fetch_statuses()
        categories = {name.casefold(): category for name, category in statuses}

        histories = await self._changelogs(client, issues)

        self._phase("Buchungen werden gezählt ...")
        worklogs = await client.fetch_person_worklogs(
            worklog_jql(ids, prior.start, current.end), ids, prior.start, current.end
        )
        # Ohne diese Zeile ist "0,0 h" nicht zu deuten: bucht die Person nicht
        # in Jira, oder trifft die Abfrage nicht?
        self.log.emit(
            f"Buchungen von {self._name}: {len(worklogs)} Einträge, "
            f"{sum(seconds for _, seconds in worklogs) / 3600:.2f} h seit {prior.start:%d.%m.%Y}"
        )

        self._phase("Erstellte und geschlossene Tickets werden gezählt ...")
        _, created_raw = await client.fetch_issues(lambda _aid: [created_jql(ids, prior.start, current.end)], fields)
        created: list[dt.date] = []
        seen: set[str] = set()
        for issue in created_raw:
            key = str(issue.get("key") or "")
            when = parse_ts(str((issue.get("fields") or {}).get("created") or ""))
            if key and key not in seen and when is not None:
                seen.add(key)
                created.append(when.date())

        closed_now = await self._closed(client, statuses, current.start, current.end, notes, fields)
        closed_before = await self._closed(client, statuses, prior.start, prior.end, notes, "summary")
        closed = (
            _unique_count(closed_now) if closed_now is not None else None,
            _unique_count(closed_before) if closed_before is not None else None,
        )

        report = build_report(
            member=self._name,
            period=current,
            prior_period=prior,
            issues=issues,
            histories=histories,
            worklogs=worklogs,
            config=self._config,
            categories=categories,
            hint_config=hint_config_from(settings),
            browse_base=settings.jira_host,
            created=created,
            closed=closed,
            points_field=points_field,
            notes=notes,
            created_issues=created_raw,
            closed_issues=closed_now or [],
        )
        self._phase(f"Performance-Booster: {report.current.done} erledigte Tickets ausgewertet")
        return report

    async def _points_field(self, client: JiraClient, notes: list[str]) -> str:
        """Loest den Namen des Story-Points-Feldes in seine ID auf.

        Returns:
            Die Feld-ID, leer ohne Feld. Ein nicht gefundenes Feld haelt den
            Bericht nicht an - er rechnet dann ohne Schaetzung und sagt es.
        """
        name = self._settings.perf_points_field.strip()
        if not name:
            return ""
        try:
            ids = resolve_field_ids(await client.get_fields(), [name])
        except JiraClientError as exc:
            notes.append(f"Story Points nicht verfügbar: {exc}")
            return ""
        if name not in ids:
            notes.append(f'Feld "{name}" nicht gefunden - ohne Story Points gerechnet.')
            return ""
        self.log.emit(f"Story Points aus Feld {ids[name]} ({name})")
        return ids[name]

    async def _closed(
        self,
        client: JiraClient,
        statuses: list[tuple[str, str]],
        start: dt.date,
        end: dt.date,
        notes: list[str],
        fields: str,
    ) -> list[dict[str, Any]] | None:
        """Zaehlt die Tickets, die die Person im Zeitraum in einen Fertig-Status zog.

        Als Fertig-Status gelten zuerst die in den Einstellungen gepflegten
        Abschluss- und Fertig-Status. Ohne Pflege alle Status der Jira-Kategorie
        Fertig, hoechstens _MAX_CLOSED_STATUSES - die Suche laeuft per GET, und
        je Status entsteht ein eigenes Praedikat.

        Returns:
            Die Tickets, oder None, wenn die Abfrage scheitert. Der uebrige
            Bericht bleibt davon unberuehrt.
        """
        names = [*self._config.closing_status, *self._config.done_status]
        if not names:
            names = [name for name, category in statuses if category == "done"]
            if len(names) > _MAX_CLOSED_STATUSES:
                names = names[:_MAX_CLOSED_STATUSES]
                if not any(note.startswith("Geschlossen:") for note in notes):
                    notes.append(
                        f"Geschlossen: nur die ersten {_MAX_CLOSED_STATUSES} Fertig-Status - "
                        "unter Einstellungen > Tickets die eigenen pflegen."
                    )
        jql = closed_jql(self._ids, names, start, end)
        if not jql:
            return None
        try:
            _, raw = await client.fetch_issues(lambda _aid: [jql], fields)
        except JiraClientError as exc:
            self.log.emit(f"Geschlossene Tickets nicht ermittelbar: {exc}")
            if not any(note.startswith("Geschlossen nicht") for note in notes):
                notes.append("Geschlossen nicht ermittelbar - Details im Meldungsfenster.")
            return None
        return raw

    async def _changelogs(self, client: JiraClient, issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Protokolle der erledigten Tickets - aus der Ablage, was dort passt."""
        cache = ChangelogCache(self._cache_dir, self._settings.jira_host)
        # Die Suche liefert ueber "updated" eine Obermenge. Was vor der
        # Vorperiode erledigt wurde, braucht kein Protokoll.
        first = period_for(self._period, self._today)[1].start
        stamps: dict[str, str] = {}
        for issue in issues:
            fields = issue.get("fields") or {}
            category = ((fields.get("status") or {}).get("statusCategory") or {}).get("key")
            done_at = parse_ts(str(fields.get("statuscategorychangedate") or ""))
            if category == "done" and done_at is not None and done_at.date() >= first:
                stamps[str(issue.get("key") or "")] = str(fields.get("statuscategorychangedate") or "")
        histories: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        for key, stamp in stamps.items():
            cached = cache.load(key, stamp)
            if cached is None:
                missing.append(key)
            else:
                histories[key] = cached
        if missing:
            self._phase(f"Änderungsprotokolle von {len(missing)} Tickets werden geholt ...")
            fetched = await client.fetch_changelogs(missing)
            for key, entries in fetched.items():
                cache.save(key, stamps[key], entries)
            histories.update(fetched)
        self.log.emit(f"Protokolle: {len(stamps) - len(missing)} aus der Ablage, {len(missing)} abgerufen")
        return histories

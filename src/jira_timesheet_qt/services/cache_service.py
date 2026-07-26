"""Cache-Service fuer Worklog-Daten abgeschlossener Monate."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from jira_timesheet_qt.models.timesheet import WorklogEntry

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".jira-timesheet-qt" / "cache"

# Karenzzeit (in Tagen), bevor ein abgeschlossener Monat in den Cache
# eingefroren wird. Ein gerade beendeter Monat bleibt so lange "live", weil
# dort noch haeufig Worklogs nachgetragen werden (z.B. die letzte Woche zu
# Monatsbeginn). Erst danach ist ein Monat stabil genug fuers Cachen.
_CACHE_GRACE_DAYS = 7


class CacheService:
    """Cached Worklog-Daten fuer abgeschlossene Monate.

    Nur Monate die seit mehr als der Karenzzeit (_CACHE_GRACE_DAYS) vorbei sind
    werden gecached. Der aktuelle und der gerade beendete Monat werden immer
    frisch abgerufen.
    """

    @staticmethod
    def is_cacheable(year: int, month: int) -> bool:
        """Prueft ob ein Monat gecached werden darf.

        True nur, wenn der Monat seit mindestens _CACHE_GRACE_DAYS Tagen
        komplett vorbei ist - ein gerade abgeschlossener Monat bleibt waehrend
        der Karenzzeit live (nachtraegliche Worklog-Eintraege).
        """
        # Erster Tag des Folgemonats = Zeitpunkt, ab dem der Monat vorbei ist.
        month_over = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return (date.today() - month_over).days >= _CACHE_GRACE_DAYS

    @staticmethod
    def has_cache(year: int, month: int, email: str) -> bool:
        """Prueft ob ein Cache fuer diesen Monat existiert."""
        cache_file = CacheService._cache_path(year, month, email)
        return cache_file.is_file()

    @staticmethod
    def load(year: int, month: int, email: str) -> list[WorklogEntry]:
        """Laedt gecachte Worklog-Eintraege."""
        cache_file = CacheService._cache_path(year, month, email)
        if not cache_file.is_file():
            return []

        try:
            raw = cache_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []

            entries: list[WorklogEntry] = []
            for item in data:
                entries.append(
                    WorklogEntry(
                        date=date.fromisoformat(item["date"]),
                        ticket=item.get("ticket", ""),
                        summary=item.get("summary", ""),
                        author=item.get("author", ""),
                        budget=item.get("budget", ""),
                        hours=item.get("hours", 0.0),
                        status=item.get("status", ""),
                        issuetype=item.get("issuetype", ""),
                        epic=item.get("epic", ""),
                        components=item.get("components", ""),
                        labels=item.get("labels", ""),
                        priority=item.get("priority", ""),
                        resolution=item.get("resolution", ""),
                        assignee=item.get("assignee", ""),
                        created=item.get("created", ""),
                        updated=item.get("updated", ""),
                        total_logged=item.get("total_logged", ""),
                    )
                )
            return entries

        except Exception as exc:
            logger.warning("Cache laden fehlgeschlagen fuer %d-%02d: %s", year, month, exc)
            return []

    @staticmethod
    def save(year: int, month: int, email: str, entries: list[WorklogEntry]) -> None:
        """Speichert Worklog-Eintraege im Cache."""
        if not CacheService.is_cacheable(year, month):
            return

        cache_file = CacheService._cache_path(year, month, email)

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            data = []
            for e in entries:
                data.append(
                    {
                        "date": e.date.isoformat(),
                        "ticket": e.ticket,
                        "summary": e.summary,
                        "author": e.author,
                        "budget": e.budget,
                        "hours": e.hours,
                        "status": e.status,
                        "issuetype": e.issuetype,
                        "epic": e.epic,
                        "components": e.components,
                        "labels": e.labels,
                        "priority": e.priority,
                        "resolution": e.resolution,
                        "assignee": e.assignee,
                        "created": e.created,
                        "updated": e.updated,
                        "total_logged": e.total_logged,
                    }
                )

            cache_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Cache speichern fehlgeschlagen fuer %d-%02d: %s", year, month, exc)

    @staticmethod
    def _cache_path(year: int, month: int, email: str) -> Path:
        """Erzeugt den Dateipfad fuer einen Cache-Eintrag."""
        safe_email = email.replace("@", "_at_").replace(".", "_")
        return CACHE_DIR / f"{year}-{month:02d}_{safe_email}.json"

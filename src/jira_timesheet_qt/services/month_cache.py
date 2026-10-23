"""Abgeschlossene Monate gegen Archivierung absichern.

Jira archiviert alte, abgeschlossene Tickets. Sie existieren weiter, sind fuer
das eigene Konto aber unsichtbar - und mit ihnen die eigenen Worklogs darauf.
Ein Live-Abruf zeigt die betroffenen Monate dann still zu niedrig an (gemessen
am 22.10.2026: Januar 92,75 h statt 161,25 h, 16 Tickets fehlten).

Deshalb wird jeder abgeschlossene Monat nach dem Abruf mit dem Monats-Cache
abgeglichen, statt ihn zu ueberschreiben:

- Was Jira liefert, gilt.
- Steht im Cache ein Ticket, das Jira nicht mehr liefert, wird dieses Ticket
  einzeln abgefragt. Unsichtbar (404): die Buchungen bleiben aus dem Cache.
  Sichtbar: die Buchung wurde in Jira wirklich entfernt, dann gilt Jira.
  Laesst sich das nicht klaeren (Netz, Rechte): die Buchungen bleiben - im
  Zweifel fuer die Daten.

Die TUI ueberschreibt ihren Cache bei F5. Dort hat nur Glueck die Stunden
gerettet, hier soll es die Regel tun.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jira_timesheet_qt.models.timesheet import WorklogEntry
from jira_timesheet_qt.services import cache_service
from jira_timesheet_qt.services.cache_service import CacheService

# Antwort der Sichtbarkeitspruefung: True sichtbar, False unsichtbar,
# None nicht klaerbar.
VisibilityCheck = Callable[[str], Awaitable[bool | None]]


@dataclass
class MonthRescue:
    """Was ein abgeschlossener Monat aus dem Cache zurueckbekommen hat.

    Attributes:
        year: Jahr des Monats.
        month: Monat (1-12).
        tickets: Tickets, deren Buchungen aus dem Cache stammen.
        hours: Summe dieser Buchungen in Stunden.
        unclear: Tickets, deren Sichtbarkeit sich nicht klaeren liess.
    """

    year: int
    month: int
    tickets: list[str] = field(default_factory=list)
    hours: float = 0.0
    unclear: list[str] = field(default_factory=list)


@dataclass
class ReconcileResult:
    """Ergebnis des Abgleichs.

    Attributes:
        entries: Alle Eintraege des Zeitraums, Jira plus gerettete.
        rescued: Je Monat, was aus dem Cache kam. Nur Monate mit Treffern.
    """

    entries: list[WorklogEntry]
    rescued: list[MonthRescue]


def months_between(first: date, last: date) -> list[tuple[int, int]]:
    """Alle Monate von `first` bis `last`, jeweils als (Jahr, Monat)."""
    result: list[tuple[int, int]] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


async def reconcile(
    fresh: list[WorklogEntry],
    first: date,
    last: date,
    email: str,
    is_visible: VisibilityCheck,
) -> ReconcileResult:
    """Gleicht einen Live-Abruf mit dem Cache der abgeschlossenen Monate ab.

    Nur ganze, abgeschlossene Monate (CacheService.is_cacheable) werden
    angefasst. Ein angeschnittener Monat am Rand des Zeitraums bleibt, wie
    Jira ihn liefert - sein Cache deckt den ganzen Monat ab und passt nicht.

    Args:
        fresh: Die Eintraege aus Jira, ohne manuelle Zeiten.
        first: Erster Tag des Zeitraums.
        last: Letzter Tag des Zeitraums.
        email: Schluessel des Caches.
        is_visible: Fragt ein einzelnes Ticket ab.

    Returns:
        Die abgeglichenen Eintraege und was gerettet wurde.
    """
    entries = list(fresh)
    rescued: list[MonthRescue] = []
    # Ein Ticket nur einmal fragen, auch wenn es in mehreren Monaten steht.
    known: dict[str, bool | None] = {}

    for year, month in months_between(first, last):
        if not CacheService.is_cacheable(year, month):
            continue
        month_first = date(year, month, 1)
        month_last = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        if first > month_first or last < date.fromordinal(month_last.toordinal() - 1):
            continue

        in_month = [e for e in fresh if e.date.year == year and e.date.month == month]
        cached = CacheService.load(year, month, email)
        fresh_tickets = {e.ticket for e in in_month}
        missing = sorted({e.ticket for e in cached} - fresh_tickets)

        rescue = MonthRescue(year, month)
        kept: list[WorklogEntry] = []
        for ticket in missing:
            if ticket not in known:
                try:
                    known[ticket] = await is_visible(ticket)
                except Exception:  # noqa: BLE001 - im Zweifel fuer die Daten
                    known[ticket] = None
            if known[ticket] is True:
                continue
            ticket_entries = [e for e in cached if e.ticket == ticket]
            kept.extend(ticket_entries)
            rescue.tickets.append(ticket)
            rescue.hours += sum(e.hours for e in ticket_entries)
            if known[ticket] is None:
                rescue.unclear.append(ticket)

        merged = [*in_month, *kept]
        entries.extend(kept)
        if rescue.tickets:
            rescued.append(rescue)
        # Ein leerer Abruf ueberschreibt keinen vorhandenen Cache.
        if merged:
            _backup(year, month, email)
            CacheService.save(year, month, email, merged)

    entries.sort(key=lambda e: (e.date, e.ticket))
    return ReconcileResult(entries, rescued)


def _backup(year: int, month: int, email: str) -> None:
    """Legt die bisherige Monatsdatei als .bak daneben, bevor sie neu geschrieben wird.

    Ein Netz fuer Faelle, an die der Abgleich nicht denkt. Es bleibt genau eine
    Sicherung je Monat, die vorige wird ersetzt.
    """
    pfad = CacheService._cache_path(year, month, email)
    if pfad.is_file():
        # Eine fehlende Sicherung darf den Abruf nicht aufhalten.
        with contextlib.suppress(OSError):
            shutil.copy2(pfad, pfad.with_suffix(".json.bak"))


def import_legacy_cache(source: Path, target: Path | None = None) -> int:
    """Uebernimmt die Monatsdateien der Textual-TUI, die hier noch fehlen.

    Das Format ist dasselbe (beide CacheService sind identisch). Eine Datei,
    die hier schon liegt, wird nie ueberschrieben.

    Args:
        source: Cache-Ordner der TUI.
        target: Eigener Cache-Ordner. Ohne Angabe der aktuelle CACHE_DIR.

    Returns:
        Anzahl der uebernommenen Dateien.
    """
    ziel = target if target is not None else cache_service.CACHE_DIR
    if not source.is_dir():
        return 0
    copied = 0
    for datei in sorted(source.glob("*-*_*.json")):
        neu = ziel / datei.name
        if neu.exists():
            continue
        ziel.mkdir(parents=True, exist_ok=True)
        shutil.copy2(datei, neu)
        copied += 1
    return copied

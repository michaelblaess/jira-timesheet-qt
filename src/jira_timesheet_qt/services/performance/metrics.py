"""Kennzahlen des Performance-Boosters aus den Rohantworten von Jira.

Die Durchlaufzeit zaehlt nur die Arbeitstage, in denen das Ticket in einem
aktiven Status stand. Wartezeiten - beim Autor, bei der Abnahme, im Backlog -
fallen heraus. Sonst misst die Kurve, wie lange der Kunde zum Testen braucht,
und nicht, wie lange gearbeitet wurde.

Die Groesse eines Tickets sind die insgesamt darauf gebuchten Stunden
(``timespent``). Tickets ganz ohne Buchung zaehlen fuer den Anteil kleiner
Tickets nicht mit: das sind meist Dubletten oder verworfene Anfragen.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from jira_timesheet_qt.services.ticket_board import BoardConfig, Role, parse_ts, workdays_between

from .hints import build_hints
from .models import (
    INVOLVE_ACTIVE,
    INVOLVE_CLOSED,
    INVOLVE_CREATED,
    INVOLVE_DONE,
    INVOLVEMENTS,
    Figures,
    HintConfig,
    OpenTicket,
    PerformanceReport,
    PeriodTicket,
    TicketMetric,
)
from .period import Period

# Felder der Ticketsuche. timespent ist die Summe aller Buchungen.
PERF_FIELDS = "summary,status,issuetype,created,updated,statuscategorychangedate,timespent"

StatusSpan = tuple[str, dt.datetime, dt.datetime]


# Container-Typen, falls Jira keine Hierarchiestufe mitliefert.
_CONTAINER_NAMES = frozenset({"epic", "initiative", "initiativ", "theme", "thema"})


def is_container(fields: Mapping[str, Any]) -> bool:
    """Ob ein Ticket ein Container ist (Epic, Initiative) statt eines Arbeitspakets.

    Container laufen ueber Monate und buendeln andere Tickets. In Durchlaufzeit
    und "In Arbeit" verzerren sie jede Aussage - aufgefallen an Epics, die seit
    Jahren "In Analyse" stehen (23.09.2026).

    Entscheidend ist die Hierarchiestufe des Vorgangstyps (0 = Standard,
    -1 = Unteraufgabe, ab 1 = Epic und darueber). Fehlt sie, entscheidet der Name.
    """
    issuetype = fields.get("issuetype") or {}
    level = issuetype.get("hierarchyLevel")
    if isinstance(level, int) and not isinstance(level, bool):
        return level > 0
    return str(issuetype.get("name") or "").strip().casefold() in _CONTAINER_NAMES


def _status(fields: Mapping[str, Any]) -> tuple[str, str]:
    """Statusname und Statuskategorie eines Tickets."""
    status = fields.get("status") or {}
    category = status.get("statusCategory") or {}
    return str(status.get("name") or ""), str(category.get("key") or "")


def status_spans(
    histories: Sequence[Mapping[str, Any]],
    created: dt.datetime,
    until: dt.datetime,
) -> list[StatusSpan]:
    """Leitet aus dem Aenderungsprotokoll die Phasen je Status ab.

    Der Anlage-Status steht nicht als eigenes Ereignis im Protokoll, er ist
    der fromString des ersten Wechsels.

    Args:
        histories:
            Eintraege des Aenderungsprotokolls, Reihenfolge egal.
        created:
            Anlagezeitpunkt des Tickets.
        until:
            Ende der letzten Phase, ueblicherweise der Abschluss.

    Returns:
        Phasen als (Status, Beginn, Ende), chronologisch. Phasen nach
        ``until`` fallen weg, eine ueberlappende wird gekappt.
    """
    changes: list[tuple[dt.datetime, str, str]] = []
    for entry in histories:
        when = parse_ts(str(entry.get("created") or ""))
        if when is None:
            continue
        for item in entry.get("items") or []:
            if item.get("field") == "status":
                changes.append((when, str(item.get("fromString") or ""), str(item.get("toString") or "")))
    if not changes:
        return []
    changes.sort(key=lambda change: change[0])

    spans: list[StatusSpan] = []
    start, status = created, changes[0][1]
    for when, _old, new in changes:
        spans.append((status, start, when))
        start, status = when, new
    spans.append((status, start, until))
    return [(name, begin, min(end, until)) for name, begin, end in spans if begin < until]


def active_workdays(
    histories: Sequence[Mapping[str, Any]],
    created: dt.datetime,
    done_at: dt.datetime,
    config: BoardConfig,
    categories: Mapping[str, str],
) -> float | None:
    """Arbeitstage, die ein Ticket bis zum Abschluss in aktiven Status stand.

    Args:
        histories:
            Aenderungsprotokoll des Tickets.
        created:
            Anlagezeitpunkt.
        done_at:
            Zeitpunkt des Wechsels in die Kategorie Done.
        config:
            Rollenzuordnung der Status.
        categories:
            Statusname (casefold) auf Jira-Kategorie, fuer Status ohne
            ausdrueckliche Zuordnung.

    Returns:
        Die Arbeitstage, oder None, wenn das Ticket nie aktiv war - etwa weil
        es direkt verworfen wurde. Das ist keine Null, sondern keine Aussage.
    """
    total = 0.0
    seen = False
    for name, begin, end in status_spans(histories, created, done_at):
        if config.role_of(name, categories.get(name.casefold(), "")) is Role.ACTIVE:
            seen = True
            total += workdays_between(begin, end)
    return total if seen else None


def done_tickets(
    issues: Iterable[Mapping[str, Any]],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
    config: BoardConfig,
    categories: Mapping[str, str],
    points_field: str = "",
) -> list[TicketMetric]:
    """Baut die Kennzahlen aller erledigten Tickets.

    Args:
        issues:
            Rohantworten der Suche, Dubletten erlaubt.
        histories:
            Aenderungsprotokoll je Schluessel. Fehlt eines, bleibt die
            Durchlaufzeit leer statt geraten.
        config:
            Rollenzuordnung der Status.
        categories:
            Statusname (casefold) auf Jira-Kategorie.
        points_field:
            Feld-ID der Story Points, leer = ohne Schaetzung.

    Returns:
        Erledigte Tickets, nach Abschluss sortiert.
    """
    result: dict[str, TicketMetric] = {}
    for issue in issues:
        key = str(issue.get("key") or "")
        fields = issue.get("fields") or {}
        _name, category = _status(fields)
        done_at = parse_ts(str(fields.get("statuscategorychangedate") or ""))
        created = parse_ts(str(fields.get("created") or ""))
        if not key or category != "done" or done_at is None or created is None or key in result:
            continue
        if is_container(fields):
            continue
        log = histories.get(key)
        active = active_workdays(log, created, done_at, config, categories) if log is not None else None
        issuetype = fields.get("issuetype") or {}
        result[key] = TicketMetric(
            key=key,
            summary=str(fields.get("summary") or ""),
            issuetype=str(issuetype.get("name") or ""),
            done_at=done_at,
            active_days=active,
            hours=float(fields.get("timespent") or 0) / 3600.0,
            story_points=_points(fields.get(points_field)) if points_field else None,
        )
    return sorted(result.values(), key=lambda ticket: ticket.done_at)


def _points(value: Any) -> float | None:
    """Liest eine Schaetzung. Null und Unlesbares zaehlen als keine Schaetzung."""
    try:
        points = float(value)
    except (TypeError, ValueError):
        return None
    return points if points > 0 else None


def _skipped_containers(issues: Iterable[Mapping[str, Any]], period: Period) -> int:
    """Container, die ohne den Ausschluss im Zeitraum mitgezaehlt worden waeren."""
    keys: set[str] = set()
    for issue in issues:
        fields = issue.get("fields") or {}
        key = str(issue.get("key") or "")
        if not key or not is_container(fields):
            continue
        _name, category = _status(fields)
        stamp = "statuscategorychangedate" if category == "done" else "updated"
        when = parse_ts(str(fields.get(stamp) or ""))
        if when is not None and when.date() >= period.start:
            keys.add(key)
    return len(keys)


def active_open(
    issues: Iterable[Mapping[str, Any]], config: BoardConfig, since: dt.date | None = None
) -> list[OpenTicket]:
    """Offene Tickets in einem aktiven Status, die im Zeitraum bewegt wurden.

    Args:
        issues:
            Rohantworten der Suche.
        config:
            Rollenzuordnung der Status.
        since:
            Nur Tickets, deren letzte Aenderung an oder nach diesem Tag liegt.
            Ohne Grenze zaehlte jedes Ticket, das seit Jahren unberuehrt in
            einem aktiven Status liegt, als Arbeit im Zeitraum.

    Returns:
        Die Tickets, ohne Container (Epics, Initiativen).
    """
    result: dict[str, OpenTicket] = {}
    for issue in issues:
        key = str(issue.get("key") or "")
        fields = issue.get("fields") or {}
        name, category = _status(fields)
        if not key or category == "done" or key in result or is_container(fields):
            continue
        updated = parse_ts(str(fields.get("updated") or ""))
        if since is not None and (updated is None or updated.date() < since):
            continue
        if config.role_of(name, category) is Role.ACTIVE:
            result[key] = OpenTicket(key=key, summary=str(fields.get("summary") or ""))
    return list(result.values())


def small_tickets(tickets: Iterable[TicketMetric], config: HintConfig) -> list[TicketMetric]:
    """Gebuchte Tickets unter der Schwelle - ohne Tickets ganz ohne Buchung."""
    return [t for t in tickets if 0 < t.hours < config.small_hours]


def figures(
    tickets: Sequence[TicketMetric],
    booked_hours: float,
    config: HintConfig,
    created: int = 0,
    closed: int | None = None,
) -> Figures:
    """Verdichtet einen Zeitraum zu den Kacheln.

    Args:
        tickets:
            Erledigte Tickets des Zeitraums.
        booked_hours:
            Eigene Buchungen der Person im Zeitraum.
        config:
            Schwellen, gebraucht fuer "klein".
        created:
            Von der Person angelegte Tickets.
        closed:
            Von der Person in einen Fertig-Status gezogene Tickets, None = unbekannt.

    Returns:
        Die Kennzahlen. Die Werte je Story Point rechnen nur ueber geschaetzte
        Tickets - ein ungeschaetztes Ticket ist keine Null.
    """
    actives = [t.active_days for t in tickets if t.active_days is not None]
    booked = [t for t in tickets if t.hours > 0]
    small = small_tickets(booked, config)
    estimated = [t for t in tickets if t.story_points]
    per_point = [v for v in (t.days_per_point for t in estimated) if v is not None]
    points = sum(t.story_points or 0.0 for t in estimated)
    return Figures(
        done=len(tickets),
        median_active_days=statistics.median(actives) if actives else None,
        small_share=100.0 * len(small) / len(booked) if booked else None,
        booked_hours=booked_hours,
        created=created,
        closed=closed,
        estimated=len(estimated),
        median_days_per_point=statistics.median(per_point) if per_point else None,
        hours_per_point=sum(t.hours for t in estimated) / points if points else None,
    )


def hours_in(worklogs: Iterable[tuple[dt.date, float]], period: Period) -> float:
    """Summe der Buchungen (Datum, Sekunden) innerhalb eines Zeitraums, in Stunden."""
    return sum(seconds for day, seconds in worklogs if period.contains(day)) / 3600.0


def build_report(
    *,
    member: str,
    period: Period,
    prior_period: Period,
    issues: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
    worklogs: Sequence[tuple[dt.date, float]],
    config: BoardConfig,
    categories: Mapping[str, str],
    hint_config: HintConfig,
    browse_base: str = "",
    created: Sequence[dt.date] = (),
    closed: tuple[int | None, int | None] = (None, None),
    points_field: str = "",
    notes: Sequence[str] = (),
    created_issues: Sequence[Mapping[str, Any]] = (),
    closed_issues: Sequence[Mapping[str, Any]] = (),
) -> PerformanceReport:
    """Baut den kompletten Bericht aus den Rohantworten.

    Args:
        member:
            Anzeigename der Person.
        period:
            Der gewaehlte Zeitraum.
        prior_period:
            Die Vorperiode.
        issues:
            Erledigte und offene Tickets der Person.
        histories:
            Aenderungsprotokolle der erledigten Tickets.
        worklogs:
            Eigene Buchungen der Person als (Tag, Sekunden).
        config:
            Rollenzuordnung der Status.
        categories:
            Statusname (casefold) auf Jira-Kategorie.
        hint_config:
            Schwellen der Hinweisregeln.
        browse_base:
            Jira-Adresse fuer Links.
        created:
            Anlagetage der von der Person angelegten Tickets, beide Zeitraeume.
        closed:
            Von der Person geschlossene Tickets in Zeitraum und Vorperiode.
        points_field:
            Feld-ID der Story Points, leer = ohne Schaetzung.
        notes:
            Einschraenkungen, die der Bericht anzeigen soll.
        created_issues:
            Rohantworten der selbst angelegten Tickets, fuer die Tabelle.
        closed_issues:
            Rohantworten der im Zeitraum selbst geschlossenen Tickets.

    Returns:
        Der Bericht samt Hinweisen.
    """
    done = done_tickets(issues, histories, config, categories, points_field)
    created_now = sorted(day for day in created if period.contains(day))
    created_before = sorted(day for day in created if prior_period.contains(day))
    current = [t for t in done if period.contains(t.done_at.date())]
    prior = [t for t in done if prior_period.contains(t.done_at.date())]
    report = PerformanceReport(
        member=member,
        period=period,
        prior_period=prior_period,
        current=figures(current, hours_in(worklogs, period), hint_config, len(created_now), closed[0]),
        prior=figures(prior, hours_in(worklogs, prior_period), hint_config, len(created_before), closed[1]),
        tickets=current,
        prior_tickets=prior,
        active_open=active_open(issues, config, period.start),
        created=created_now,
        prior_created=created_before,
        config=hint_config,
        browse_base=browse_base,
        notes=list(notes),
    )
    containers = _skipped_containers(issues, period)
    if containers:
        report.notes.insert(0, f"{containers} Epics/Initiativen nicht mitgezählt (Container, keine Arbeitspakete)")
    report.all_tickets = period_tickets(
        report.tickets,
        report.active_open,
        issues,
        [i for i in created_issues if _created_in(i, period)],
        closed_issues,
        points_field,
    )
    report.hints = build_hints(report)
    return report


def _created_in(issue: Mapping[str, Any], period: Period) -> bool:
    """Ob ein Ticket im Zeitraum angelegt wurde."""
    when = parse_ts(str((issue.get("fields") or {}).get("created") or ""))
    return when is not None and period.contains(when.date())


def period_tickets(
    done: Sequence[TicketMetric],
    active: Sequence[OpenTicket],
    issues: Sequence[Mapping[str, Any]],
    created_issues: Sequence[Mapping[str, Any]],
    closed_issues: Sequence[Mapping[str, Any]],
    points_field: str = "",
) -> list[PeriodTicket]:
    """Fuehrt alle Beteiligungen einer Person im Zeitraum zu einer Liste zusammen.

    Ein Ticket steht einmal darin, auch wenn es zugleich erstellt, erledigt und
    geschlossen wurde - die Beteiligungen stehen dann nebeneinander.

    Args:
        done:
            Im Zeitraum erledigte Tickets.
        active:
            Gerade in einem aktiven Status stehende Tickets.
        issues:
            Rohantworten der eigenen Tickets, liefern Titel, Typ und Status.
        created_issues:
            Rohantworten der im Zeitraum angelegten Tickets.
        closed_issues:
            Rohantworten der im Zeitraum selbst geschlossenen Tickets.
        points_field:
            Feld-ID der Story Points, leer = ohne.

    Returns:
        Die Tickets, ohne feste Reihenfolge - die Anzeige sortiert.
    """
    raw: dict[str, Mapping[str, Any]] = {}
    for source in (issues, created_issues, closed_issues):
        for issue in source:
            key = str(issue.get("key") or "")
            if key and key not in raw:
                raw[key] = issue
    involved: dict[str, set[str]] = {}
    for key in (t.key for t in done):
        involved.setdefault(key, set()).add(INVOLVE_DONE)
    for key in (str(i.get("key") or "") for i in created_issues):
        involved.setdefault(key, set()).add(INVOLVE_CREATED)
    for key in (str(i.get("key") or "") for i in closed_issues):
        involved.setdefault(key, set()).add(INVOLVE_CLOSED)
    for key in (t.key for t in active):
        involved.setdefault(key, set()).add(INVOLVE_ACTIVE)
    metrics = {t.key: t for t in done}

    result: list[PeriodTicket] = []
    for key, kinds in involved.items():
        if not key:
            continue
        fields = (raw.get(key) or {}).get("fields") or {}
        metric = metrics.get(key)
        name, _category = _status(fields)
        result.append(
            PeriodTicket(
                key=key,
                summary=str(fields.get("summary") or (metric.summary if metric else "")),
                issuetype=str((fields.get("issuetype") or {}).get("name") or (metric.issuetype if metric else "")),
                status=name,
                involvement=tuple(k for k in INVOLVEMENTS if k in kinds),
                hours=float(fields.get("timespent") or 0) / 3600.0 if fields else (metric.hours if metric else 0.0),
                story_points=_points(fields.get(points_field)) if points_field and fields else None,
                metric=metric,
            )
        )
    return result


def cumulative_done(tickets: Sequence[TicketMetric], period: Period) -> list[int]:
    """Erledigte Tickets kumuliert je Tag des Zeitraums.

    Args:
        tickets:
            Erledigte Tickets, beliebige Reihenfolge.
        period:
            Der Zeitraum. Tickets ausserhalb zaehlen nicht.

    Returns:
        Ein Wert je Kalendertag, der erste gehoert zu ``period.start``.
    """
    return cumulative_days([t.done_at.date() for t in tickets], period)


def cumulative_days(days: Iterable[dt.date], period: Period) -> list[int]:
    """Ereignisse kumuliert je Tag des Zeitraums - fuer erledigt wie fuer erstellt.

    Args:
        days:
            Tage der Ereignisse, beliebige Reihenfolge.
        period:
            Der Zeitraum. Tage ausserhalb zaehlen nicht.

    Returns:
        Ein Wert je Kalendertag, der erste gehoert zu ``period.start``.
    """
    per_day = [0] * period.days
    for day in days:
        if period.contains(day):
            per_day[(day - period.start).days] += 1
    total = 0
    result: list[int] = []
    for count in per_day:
        total += count
        result.append(total)
    return result


def _hours_label(value: float) -> str:
    """Stundenangabe mit deutschem Komma, ohne ueberfluessige Nachkommastelle."""
    text = f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text} h"


def size_buckets(tickets: Sequence[TicketMetric], small_hours: float) -> list[tuple[str, int, bool]]:
    """Verteilung der Ticketgroessen in gebuchten Stunden.

    Die erste Grenze ist die Schwelle fuer "klein", damit genau diese Klasse
    im Diagramm hervorgehoben werden kann. Tickets ohne Buchung stehen in
    einer eigenen Klasse vorn - sie sind weder klein noch gross.

    Args:
        tickets:
            Erledigte Tickets.
        small_hours:
            Schwelle fuer "klein".

    Returns:
        Je Klasse (Beschriftung, Anzahl, ist klein).
    """
    edges = sorted({e for e in (small_hours, 4.0, 8.0, 24.0) if e > 0})
    labels = [f"< {_hours_label(edges[0])}"]
    labels += [f"{_hours_label(low)[:-2]}-{_hours_label(high)}" for low, high in zip(edges, edges[1:], strict=False)]
    labels.append(f"> {_hours_label(edges[-1])}")
    counts = [0] * len(labels)
    unbooked = 0
    for ticket in tickets:
        if ticket.hours <= 0:
            unbooked += 1
            continue
        index = next((i for i, edge in enumerate(edges) if ticket.hours < edge), len(edges))
        counts[index] += 1
    result = [("0 h", unbooked, False)]
    result += [
        (label, count, index == 0 and edges[0] == small_hours)
        for index, (label, count) in enumerate(zip(labels, counts, strict=True))
    ]
    return result


def _days_label(value: float) -> str:
    """Arbeitstage ohne ueberfluessige Nachkommastelle."""
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def cycle_buckets(tickets: Sequence[TicketMetric], long_days: float) -> list[tuple[str, int, bool]]:
    """Verteilung der Durchlaufzeit in Klassen aktiver Arbeitstage.

    Die oberste Grenze ist die Schwelle fuer "lang", damit genau diese Klasse
    im Diagramm hervorgehoben werden kann. Tickets, die nie aktiv waren,
    stehen in einer eigenen Klasse vorn.

    Args:
        tickets:
            Erledigte Tickets.
        long_days:
            Schwelle fuer "lang". 0 = ohne Hervorhebung.

    Returns:
        Je Klasse (Beschriftung, Anzahl, ist lang). Grenzen gehoeren zur
        oberen Klasse: 2,0 AT zaehlt zu "2-5".
    """
    edges = sorted({e for e in (2.0, 5.0, long_days if long_days > 0 else 15.0) if e > 0})
    labels = [f"< {_days_label(edges[0])}"]
    labels += [f"{_days_label(low)}-{_days_label(high)}" for low, high in zip(edges, edges[1:], strict=False)]
    labels.append(f"> {_days_label(edges[-1])}")
    counts = [0] * len(labels)
    never = 0
    for ticket in tickets:
        if ticket.active_days is None:
            never += 1
            continue
        index = next((i for i, edge in enumerate(edges) if ticket.active_days < edge), len(edges))
        counts[index] += 1
    long_index = len(edges) if long_days > 0 and edges[-1] == long_days else -1
    result = [("nie aktiv", never, False)]
    result += [
        (label, count, index == long_index) for index, (label, count) in enumerate(zip(labels, counts, strict=True))
    ]
    return result

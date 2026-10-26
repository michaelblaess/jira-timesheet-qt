"""Kanten aus Suche und Aenderungsprotokoll, und daraus der Stern um eine Mitte.

Auftrag: Ersteller an den ersten Bearbeiter, zum Zeitpunkt dieser ersten
Zuweisung. Uebergabe: jeder spaetere Wechsel vom letzten Bearbeiter an einen
neuen. Ein Zwischenstand ohne Bearbeiter unterbricht die Kette nicht - wer
zuletzt dran war, gibt an den naechsten ab.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jira_timesheet_qt.services.ticket_report.lifecycle import display_name, parse_ts

from .models import EDGE_HANDOVER, EDGE_ORDER, FlowEdge, FlowStar, Person, Spoke

DEFAULT_SPOKES = 8
"""So viele Personen stehen einzeln im Kreis, der Rest unter "Sonstige"."""


@dataclass(frozen=True)
class FlowData:
    """Alle Kanten einer Abfrage, unabhaengig von Mitte und Zeitraum."""

    edges: tuple[FlowEdge, ...]
    people: Mapping[str, str]
    """accountId auf Anzeigenamen."""
    missing: tuple[str, ...]
    """Tickets ohne Aenderungsprotokoll - fuer sie gibt es keine Kanten."""


def _account(raw: Any) -> tuple[str, str]:
    """accountId und Anzeigename aus einem Personen-Objekt der API."""
    if not isinstance(raw, Mapping):
        return "", ""
    return str(raw.get("accountId") or ""), display_name(str(raw.get("displayName") or ""))


def _assignee_changes(histories: Sequence[Mapping[str, Any]]) -> list[tuple[dt.datetime, str, str, str, str]]:
    """Bearbeiterwechsel als (Zeitpunkt, alt, alter Name, neu, neuer Name), zeitlich sortiert."""
    changes: list[tuple[dt.datetime, str, str, str, str]] = []
    for entry in histories:
        when = parse_ts(str(entry.get("created") or ""))
        if when is None:
            continue
        for item in entry.get("items") or ():
            if (item.get("fieldId") or item.get("field")) != "assignee":
                continue
            changes.append(
                (
                    when,
                    str(item.get("from") or ""),
                    display_name(str(item.get("fromString") or "")),
                    str(item.get("to") or ""),
                    display_name(str(item.get("toString") or "")),
                )
            )
    changes.sort(key=lambda change: change[0])
    return changes


def ticket_edges(
    issue: Mapping[str, Any],
    histories: Sequence[Mapping[str, Any]],
    people: dict[str, str],
) -> list[FlowEdge]:
    """Baut die Kanten eines Tickets.

    Args:
        issue:
            Rohantwort der Suche mit reporter, assignee und created.
        histories:
            Aenderungsprotokoll des Tickets.
        people:
            Wird um die gesehenen Namen ergaenzt, der erste Name gewinnt.

    Returns:
        Die Kanten in zeitlicher Reihenfolge.
    """
    key = str(issue.get("key") or "")
    fields = issue.get("fields") or {}
    created = parse_ts(str(fields.get("created") or ""))
    reporter, reporter_name = _account(fields.get("reporter"))
    current, current_name = _account(fields.get("assignee"))
    for account, name in ((reporter, reporter_name), (current, current_name)):
        if account and name:
            people.setdefault(account, name)
    if not key or created is None:
        return []

    changes = _assignee_changes(histories)
    for _when, old, old_name, new, new_name in changes:
        for account, name in ((old, old_name), (new, new_name)):
            if account and name:
                people.setdefault(account, name)

    # Ohne Wechsel ist der heutige Bearbeiter auch der erste. Mit Wechsel
    # verraet der erste Eintrag, wer es vorher war.
    holder = changes[0][1] if changes else current
    edges: list[FlowEdge] = []
    ordered = bool(holder)
    if holder and reporter and reporter != holder:
        edges.append(FlowEdge(EDGE_ORDER, reporter, holder, key, created))

    for when, _old, _old_name, new, _new_name in changes:
        if not new:
            continue
        if not ordered:
            ordered = True
            if reporter and reporter != new:
                edges.append(FlowEdge(EDGE_ORDER, reporter, new, key, when))
        elif holder and holder != new:
            edges.append(FlowEdge(EDGE_HANDOVER, holder, new, key, when))
        holder = new
    return edges


def extract_flow(
    issues: Iterable[Mapping[str, Any]],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
) -> FlowData:
    """Baut die Kanten aller Tickets einer Abfrage.

    Args:
        issues:
            Rohantworten der Suche, Dubletten erlaubt.
        histories:
            Aenderungsprotokoll je Schluessel. Fehlt eines, entstehen fuer das
            Ticket keine Kanten - geraten wird nicht, es steht in ``missing``.

    Returns:
        Kanten, Namen und die Tickets ohne Protokoll.
    """
    seen: set[str] = set()
    edges: list[FlowEdge] = []
    people: dict[str, str] = {}
    missing: list[str] = []
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        log = histories.get(key)
        if log is None:
            missing.append(key)
            # Die Namen trotzdem merken, sie helfen bei der Personenwahl.
            for account, name in (_account((issue.get("fields") or {}).get(f)) for f in ("reporter", "assignee")):
                if account and name:
                    people.setdefault(account, name)
            continue
        edges.extend(ticket_edges(issue, log, people))
    edges.sort(key=lambda edge: edge.when)
    return FlowData(tuple(edges), people, tuple(missing))


def build_star(
    data: FlowData,
    center: Sequence[str],
    kinds: Collection[str],
    since: dt.date | None,
    limit: int = DEFAULT_SPOKES,
    center_name: str = "",
) -> FlowStar:
    """Faltet die Kanten zu einem Stern um eine Person.

    Kanten zwischen zwei anderen Personen bleiben aussen vor. Welche Personen
    einzeln erscheinen, entscheidet die Zahl der Wege - angezeigt werden sie
    alphabetisch, damit der Kreis keine Rangfolge nahelegt.

    Args:
        data:
            Ergebnis von extract_flow.
        center:
            Kennungen der Person in der Mitte. Eine Person kann mehrere
            Konten fuehren, Wege zwischen ihnen zaehlen nicht.
        kinds:
            Die zugeschalteten Kantenarten.
        since:
            Erster Tag, None = alle Kanten.
        limit:
            Hoechstens so viele Personen einzeln, der Rest unter "Sonstige".
        center_name:
            Name der Mitte. Leer = der Jira-Name der ersten bekannten Kennung.

    Returns:
        Der Stern.
    """
    own = set(center)
    outgoing: dict[str, dict[str, None]] = {}
    incoming: dict[str, dict[str, None]] = {}
    for edge in data.edges:
        if edge.kind not in kinds or (since is not None and edge.when.date() < since):
            continue
        if edge.source in own and edge.target not in own:
            outgoing.setdefault(edge.target, {})[edge.key] = None
            incoming.setdefault(edge.target, {})
        elif edge.target in own and edge.source not in own:
            incoming.setdefault(edge.source, {})[edge.key] = None
            outgoing.setdefault(edge.source, {})

    def name_of(account: str) -> str:
        return data.people.get(account) or account

    def size(account: str) -> int:
        return len(outgoing[account]) + len(incoming[account])

    chosen = sorted(outgoing, key=lambda account: (-size(account), name_of(account).casefold()))
    shown, rest = chosen[: max(0, limit)], chosen[max(0, limit) :]

    spokes = tuple(
        Spoke(Person(account, name_of(account)), tuple(outgoing[account]), tuple(incoming[account]))
        for account in sorted(shown, key=lambda account: name_of(account).casefold())
    )
    others: Spoke | None = None
    if rest:
        out_keys: dict[str, None] = {}
        in_keys: dict[str, None] = {}
        for account in rest:
            out_keys.update(outgoing[account])
            in_keys.update(incoming[account])
        others = Spoke(None, tuple(out_keys), tuple(in_keys), members=len(rest))
    first = center[0] if center else ""
    known = next((account for account in center if account in data.people), first)
    return FlowStar(Person(first, center_name or name_of(known)), spokes, others)

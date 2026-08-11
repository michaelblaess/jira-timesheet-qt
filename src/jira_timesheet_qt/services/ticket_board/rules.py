"""Wandelt Jira-Rohantworten in das Anzeigemodell und setzt die Marker.

Der Kern kennt keinen Client: die aufrufende Anwendung holt die Antworten
selbst und reicht sie herein - derselbe Schnitt wie bei ``build_report``.
So laeuft dieselbe Logik in der Textual-Oberflaeche, in der Qt-Oberflaeche
und im Terminal.

Grundsatz: jeder Marker muss aus den Ticketdaten belegbar sein. Es wird
nichts geschaetzt und niemand bewertet.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from ..ticket_report.viewmodel import (
    WORK_END_HOUR,
    WORK_START_HOUR,
    business_seconds,
)
from .config import BLOCKER_PHRASES, GROUP_ORDER, BoardConfig
from .models import Board, Group, Marker, Role, Ticket, WorklogInfo

_HOURS_PER_WORKDAY = WORK_END_HOUR - WORK_START_HOUR


def parse_ts(raw: str) -> dt.datetime | None:
    """Liest einen Jira-Zeitstempel.

    Jira liefert bereits Ortszeit mit Offset. Das Z am Ende kommt nur bei
    manchen Endpunkten vor und wird auf den ISO-Offset gedreht.

    Args:
        raw:
            Zeitstempel wie "2026-07-28T10:00:00.000+0200".

    Returns:
        Zeitzonenbewusstes datetime, oder None bei leerer Eingabe.
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def workdays_between(start: dt.datetime | None, end: dt.datetime) -> float:
    """Rechnet eine Zeitspanne in Arbeitstage um.

    Kalendertage taugen dafuer nicht: drei Tage ueber ein Wochenende sind
    ein Arbeitstag, und genau diese Unterscheidung entscheidet bei frischen
    Tickets ueber die Bewertung.

    Args:
        start:
            Beginn, None ergibt 0.
        end:
            Ende, ueblicherweise jetzt.

    Returns:
        Arbeitstage im Fenster Mo-Fr, WORK_START_HOUR bis WORK_END_HOUR.
    """
    if start is None:
        return 0.0
    return business_seconds(start, end) / _HOURS_PER_WORKDAY / 3600


def _person(field: Any, key: str) -> str:
    """Liest einen Anzeigenamen aus einem Personenfeld."""
    if not isinstance(field, dict):
        return ""
    value = field.get(key, "")
    return str(value) if value else ""


def is_blocked(fields: dict[str, Any]) -> bool:
    """Prueft, ob ein offener Vorgaenger dieses Ticket aufhaelt.

    Client-seitig bestimmt, weil nicht jede Instanz einen Blocks-Typ kennt.
    Ein bereits erledigter Vorgaenger blockiert nicht - genau das
    unterscheidet eine echte Abhaengigkeit von einer historischen.

    Args:
        fields:
            Das fields-Objekt eines Issues, mit issuelinks.

    Returns:
        True, wenn mindestens ein Vorgaenger noch offen ist.
    """
    links = fields.get("issuelinks")
    if not isinstance(links, list):
        return False
    for link in links:
        if not isinstance(link, dict):
            continue
        inward = str((link.get("type") or {}).get("inward", "")).casefold()
        other = link.get("inwardIssue")
        if not isinstance(other, dict):
            continue
        if not any(phrase in inward for phrase in BLOCKER_PHRASES):
            continue
        status = (other.get("fields") or {}).get("status") or {}
        category = str((status.get("statusCategory") or {}).get("key", "")).casefold()
        if category != "done":
            return True
    return False


def to_ticket(
    issue: dict[str, Any],
    config: BoardConfig,
    now: dt.datetime,
    account_id: str = "",
    browse_base: str = "",
    account_ids: Sequence[str] = (),
) -> Ticket:
    """Baut aus einem Jira-Issue eine Zeile der Ansicht.

    Args:
        issue:
            Ein Element aus der issues-Liste der Suchantwort.
        config:
            Die geltende Konfiguration.
        now:
            Bezugszeitpunkt fuer die Liegezeit.
        account_id:
            accountId der Person, aus deren Sicht die Ansicht gebaut wird.
        browse_base:
            Basis-URL fuer den Absprung, ohne abschliessenden Schraegstrich.
        account_ids:
            Weitere Kennungen derselben Person. Wer mehrere Konten fuehrt,
            meldet ein Ticket unter dem einen und bearbeitet es unter dem
            anderen - ohne die vollstaendige Liste gilt der eigene Vorgang
            dann faelschlich als fremder.

    Returns:
        Das gefuellte Ticket, noch ohne Marker.
    """
    fields = issue.get("fields") or {}
    status_field = fields.get("status") or {}
    status = str(status_field.get("name", ""))
    category = str((status_field.get("statusCategory") or {}).get("key", ""))
    priority = _person(fields.get("priority"), "name")
    issue_type = _person(fields.get("issuetype"), "name")
    reporter_field = fields.get("reporter") or {}
    updated = parse_ts(str(fields.get("updated", "")))
    key = str(issue.get("key", ""))

    reporter_id = str(reporter_field.get("accountId", "")) if isinstance(reporter_field, dict) else ""
    own_ids = {value for value in (account_id, *account_ids) if value}
    foreign = bool(own_ids) and bool(reporter_id) and reporter_id not in own_ids

    role = config.role_of(status, category)
    if role is Role.HANDBACK and own_ids and not foreign:
        # Ein Rueckgabe-Status mit EIGENEM Autor heisst: ich bin selbst der
        # Adressat der Bewertung. Es gibt niemanden, dem man das Ticket
        # zurueckgeben koennte - der Ball liegt bei mir. Ohne diese
        # Unterscheidung verschwinden solche Tickets in einer Gruppe, die
        # "nicht bearbeiten" heisst, und liegen dort ewig.
        role = Role.ACTIVE

    return Ticket(
        key=key,
        summary=str(fields.get("summary", "")),
        status=status,
        category=category,
        priority=priority,
        priority_rank=config.priority_rank(priority),
        issue_type=issue_type,
        is_bug=issue_type.strip().casefold() in ("bug", "fehler"),
        reporter=_person(reporter_field, "displayName"),
        assignee=_person(fields.get("assignee"), "displayName"),
        foreign_reporter=foreign,
        created=parse_ts(str(fields.get("created", ""))),
        updated=updated,
        role=role,
        idle_workdays=workdays_between(updated, now),
        idle_days=(now - updated).days if updated is not None else 0,
        url=f"{browse_base.rstrip('/')}/browse/{key}" if browse_base and key else "",
    )


def markers_for(
    ticket: Ticket,
    fields: dict[str, Any],
    config: BoardConfig,
    worklog: WorklogInfo | None = None,
    now: dt.datetime | None = None,
) -> tuple[Marker, ...]:
    """Bestimmt den Handlungsbedarf eines Tickets.

    Mehrere Marker gleichzeitig sind ausdruecklich moeglich - ein Ticket
    kann verwaist UND hochpriorisiert sein. Genau deshalb sind es Marker
    und keine Gruppen: eine Schublade koennte es nur einmal einsortieren.

    Args:
        ticket:
            Das bereits gefuellte Ticket.
        fields:
            Das zugehoerige fields-Objekt, fuer die Verknuepfungen.
        config:
            Die geltende Konfiguration.
        worklog:
            Buchungslage, falls nachgeladen. None = noch nicht bekannt,
            dann bleibt der Pile of Shame ungesetzt statt geraten.
        now:
            Bezugszeitpunkt fuer die Buchungs-Liegezeit.

    Returns:
        Die gesetzten Marker, in stabiler Reihenfolge. Fuer abgeschlossene
        Tickets ist das Ergebnis IMMER leer.
    """
    if ticket.role is Role.DONE:
        # Ein abgeschlossenes Ticket ist endgueltig - es kann nicht verwaisen,
        # nicht blockiert sein und keine Prioritaet mehr haben, die zu etwas
        # auffordert. Jeder Marker hier waere eine Aufforderung ohne Adressat,
        # und die rote Einfaerbung stiehlt die Aufmerksamkeit den Gruppen, in
        # denen tatsaechlich etwas zu tun ist.
        return ()

    found: list[Marker] = []

    if ticket.role is Role.HANDBACK and ticket.foreign_reporter:
        found.append(Marker.HANDBACK)

    if ticket.role is Role.ACCEPTANCE:
        found.append(Marker.ACCEPTANCE)

    if ticket.idle_days >= config.stale_days:
        found.append(Marker.STALE)

    if config.is_high_priority(ticket.priority):
        found.append(Marker.HIGH_PRIORITY)

    if is_blocked(fields):
        found.append(Marker.BLOCKED)

    if _is_pile_of_shame(ticket, config, worklog, now):
        found.append(Marker.PILE_OF_SHAME)

    return tuple(found)


def _is_pile_of_shame(
    ticket: Ticket,
    config: BoardConfig,
    worklog: WorklogInfo | None,
    now: dt.datetime | None,
) -> bool:
    """Prueft die Pile-of-Shame-Bedingung.

    Der Status behauptet Aktivitaet, aber es gibt seit der Schwelle weder
    eine Aenderung noch eine gebuchte Stunde.

    Die zweite Haelfte ist der entscheidende Teil. Ohne sie landen bewusst
    offengehaltene Dauertickets in der Liste, obwohl sie in Benutzung sind:
    ein seit Jahren offenes Ticket mit regelmaessigen Buchungen ist nicht
    vergessen. Eine Ausnahmeliste braucht es damit nicht - hoert das Buchen
    auf, taucht es auf, und das ist dann richtig.

    Args:
        ticket:
            Das Ticket.
        config:
            Die geltende Konfiguration.
        worklog:
            Buchungslage, oder None wenn nicht geladen.
        now:
            Bezugszeitpunkt.

    Returns:
        True, wenn beide Haelften zutreffen.
    """
    threshold = config.threshold_of(ticket.role)
    if threshold is None:
        return False
    if ticket.idle_workdays < threshold:
        return False
    if worklog is None:
        # Ohne Buchungslage laesst sich die zweite Haelfte nicht pruefen.
        # Lieber nichts behaupten als raten.
        return False
    if worklog.count == 0:
        return True
    if worklog.last is None or now is None:
        return False
    return workdays_between(worklog.last, now) >= threshold


def build_board(
    issues: list[dict[str, Any]],
    config: BoardConfig | None = None,
    now: dt.datetime | None = None,
    account_id: str = "",
    browse_base: str = "",
    worklogs: dict[str, WorklogInfo] | None = None,
    account_ids: Sequence[str] = (),
) -> Board:
    """Baut aus einer Suchantwort die fertige Ansicht.

    Args:
        issues:
            Die issues-Liste einer oder mehrerer Suchantworten.
        config:
            Konfiguration, None nimmt die Vorgaben.
        now:
            Bezugszeitpunkt, None nimmt die aktuelle Zeit.
        account_id:
            accountId der Person, aus deren Sicht die Ansicht gebaut wird.
        browse_base:
            Basis-URL fuer den Absprung.
        worklogs:
            Buchungslage je Ticketschluessel, soweit nachgeladen. Fuer fremde
            Personen bleibt das leer, siehe ``load_board``.
        account_ids:
            Weitere Kennungen derselben Person.

    Returns:
        Das Board mit Gruppen, Tickets und den nicht zugeordneten Status.
    """
    settings = config or BoardConfig()
    moment = now or dt.datetime.now(dt.UTC)
    bookings = worklogs or {}

    tickets: list[Ticket] = []
    unknown: list[str] = []
    seen: set[str] = set()

    for issue in issues:
        key = str(issue.get("key", ""))
        if not key or key in seen:
            # Die relevanten Tickets stammen aus mehreren Quellen und
            # koennen sich ueberschneiden.
            continue
        seen.add(key)

        ticket = to_ticket(
            issue, settings, moment, account_id, browse_base, account_ids
        )
        fields = issue.get("fields") or {}
        booking = bookings.get(key)
        ticket.markers = markers_for(ticket, fields, settings, booking, moment)
        if booking is not None:
            ticket.has_worklogs = booking.count > 0
            ticket.booking_workdays = (
                workdays_between(booking.last, moment) if booking.last else None
            )
        tickets.append(ticket)

        if not settings.is_configured(ticket.status) and ticket.status not in unknown:
            unknown.append(ticket.status)

    groups: list[Group] = []
    for role in GROUP_ORDER:
        members = [t for t in tickets if t.role is role]
        if members:
            groups.append(Group(role=role, tickets=sort_tickets(members, role)))

    return Board(groups=groups, tickets=tickets, unknown_status=sorted(unknown))


def sort_tickets(tickets: list[Ticket], role: Role) -> list[Ticket]:
    """Sortiert die Tickets einer Gruppe.

    Im Backlog gilt: erst alle Fehler nach Prioritaet, danach alles andere
    nach Prioritaet. Das ist die Reihenfolge, in der Arbeit gezogen wird.
    In allen anderen Gruppen steht das Aelteste oben.

    Args:
        tickets:
            Die Tickets der Gruppe.
        role:
            Die Rolle der Gruppe.

    Returns:
        Eine neue, sortierte Liste.
    """
    if role is Role.BACKLOG:
        return sorted(tickets, key=lambda t: (not t.is_bug, t.priority_rank, t.key))
    return sorted(tickets, key=lambda t: (-t.idle_workdays, t.priority_rank, t.key))


def pending_worklog_keys(board: Board, config: BoardConfig | None = None) -> list[str]:
    """Nennt die Tickets, fuer die sich ein Worklog-Abruf lohnt.

    Nur die bereits auffaelligen, nicht alle: Worklogs kosten einen Abruf
    je Ticket. Der billige Test entscheidet, welche das sind.

    Args:
        board:
            Das aus der Grundladung gebaute Board.
        config:
            Konfiguration, None nimmt die Vorgaben.

    Returns:
        Die Ticketschluessel in der Reihenfolge der Ansicht.
    """
    settings = config or BoardConfig()
    keys: list[str] = []
    for ticket in board.tickets:
        if ticket.has_worklogs is not None:
            continue
        threshold = settings.threshold_of(ticket.role)
        if threshold is not None and ticket.idle_workdays >= threshold:
            keys.append(ticket.key)
    return keys

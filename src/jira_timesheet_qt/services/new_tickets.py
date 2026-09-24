"""Reiter "Neue Tickets": was die Team-Mitglieder zuletzt angelegt haben.

Gedacht fuer den Blick am Morgen. Oberflaechenfrei - die Qt-Schicht liegt in
ui/new_tickets_*. Ein Abruf holt den laengsten Zeitraum fuer alle Mitglieder,
Person und Zeitraum filtern danach nur noch lokal. So ist jeder Wechsel
sofort da, statt erneut Jira zu fragen.

Der Zeitraum zaehlt in ARBEITSTAGEN, nicht in Stunden: rollende 24 Stunden
zeigen am Montagmorgen nur den Sonntag, also meistens nichts. "1T" heisst
deshalb "seit Beginn des letzten Arbeitstags" - am Montag ab Freitag, sonst
ab dem Vortag.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from .team import TeamMember
from .ticket_board import BoardConfig, Ticket, check_account_id, key_sort_value, to_ticket

# Die Zeitraum-Knoepfe, Kuerzel -> Arbeitstage zurueck.
WINDOWS: dict[str, int] = {"1T": 1, "2T": 2, "3T": 3, "7T": 7}
DEFAULT_WINDOW = "1T"
# Der Abruf deckt den laengsten Zeitraum ab, die anderen filtern daraus.
LONGEST_WINDOW = max(WINDOWS, key=lambda kind: WINDOWS[kind])

# Wie Jira die Filterauswahl "alle Mitglieder" nennt, steht nur in der
# Oberflaeche. Im Kern heisst "alle" schlicht: kein Name.
ALL_MEMBERS = ""

# Felder der Liste. Bewusst schlank - der Rest steht in der Vorschau.
FIELDS = "summary,status,priority,issuetype,assignee,reporter,created,updated"

# Obergrenze gegen eine Endlosschleife bei einer kaputten Pruefung.
_MAX_STEPS = 60


def _weekday(day: dt.date) -> bool:
    """Mo-Fr - der Rueckfall ohne Feiertagskalender."""
    return day.weekday() < 5


def window_start(
    today: dt.date,
    workdays: int,
    is_workday: Callable[[dt.date], bool] = _weekday,
) -> dt.date:
    """Erster Tag eines Zeitraums, gezaehlt in Arbeitstagen vor heute.

    Heute selbst zaehlt nicht mit, liegt aber immer im Zeitraum: wer am
    Dienstag um 9 Uhr schaut, sieht mit 1T den Montag UND das, was seit dem
    Morgen dazugekommen ist.

    Args:
        today:
            Der Bezugstag.
        workdays:
            Wie viele Arbeitstage zurueck. Werte unter 1 gelten als 1.
        is_workday:
            Ob ein Tag ein Arbeitstag ist. Die Anwendung reicht den
            Feiertagskalender ihres Bundeslands herein, ohne ihn zaehlen nur
            Mo-Fr.

    Returns:
        Der frueheste Tag, dessen Tickets noch in den Zeitraum fallen.
    """
    day = today
    remaining = max(1, workdays)
    for _ in range(_MAX_STEPS * remaining):
        day -= dt.timedelta(days=1)
        if is_workday(day):
            remaining -= 1
            if remaining == 0:
                return day
    # Kein Arbeitstag in Sicht (kaputter Kalender): lieber zu weit als leer.
    return today - dt.timedelta(days=max(1, workdays))


def new_tickets_jql(members: Sequence[TeamMember], since: dt.date) -> str:
    """Tickets, die eines der Mitglieder seit einem Tag angelegt hat.

    Args:
        members:
            Die Merkliste. Jede Kennung jedes Mitglieds zaehlt - eine Person
            kann mehrere Konten fuehren (siehe TeamMember).
        since:
            Erster Tag des Zeitraums, einschliesslich.

    Returns:
        Der JQL-Ausdruck, oder ein leerer String ohne eine einzige Kennung.

    Raises:
        AccountIdError:
            Wenn eine Kennung unbrauchbar ist. Bewusst ein Abbruch: eine
            still uebersprungene Person faellt in der Liste nicht auf.
    """
    ids = [check_account_id(a) for member in members for a in member.account_ids]
    if not ids:
        return ""
    names = ", ".join(f'"{a}"' for a in dict.fromkeys(ids))
    return f'reporter IN ({names}) AND created >= "{since:%Y-%m-%d}" ORDER BY created DESC'


def build_new_tickets(
    issues: Iterable[Mapping[str, Any]],
    members: Sequence[TeamMember],
    config: BoardConfig,
    now: dt.datetime,
    browse_base: str = "",
) -> list[Ticket]:
    """Baut die Liste, neueste zuerst, mit dem Namen aus der Merkliste.

    Als Ersteller steht der Name, unter dem die Person in "Mein Team" gefuehrt
    wird - nicht der Jira-Anzeigename. Nur so passt die Liste zur
    Personenauswahl, und dieselbe Person heisst nicht an zwei Stellen
    verschieden.

    Args:
        issues:
            Die Rohantworten der Suche. Doppelte Schluessel werden entfernt.
        members:
            Die Merkliste.
        config:
            Rollenzuordnung und Prioritaeten.
        now:
            Bezugszeitpunkt.
        browse_base:
            Basis-URL fuer den Absprung nach Jira.

    Returns:
        Die Tickets, nach Anlage absteigend sortiert.
    """
    names = {account: member.display_name for member in members for account in member.account_ids}
    result: dict[str, Ticket] = {}
    for issue in issues:
        ticket = to_ticket(dict(issue), config, now, browse_base=browse_base)
        if not ticket.key or ticket.key in result:
            continue
        name = names.get(ticket.reporter_id)
        result[ticket.key] = replace(ticket, reporter=name) if name else ticket
    return sorted(result.values(), key=_newest_first)


def _newest_first(ticket: Ticket) -> tuple[float, tuple[str, int, str]]:
    """Sortierschluessel: juengste Anlage zuerst, bei Gleichstand nach Nummer."""
    stamp = ticket.created.timestamp() if ticket.created is not None else 0.0
    project, number, raw = key_sort_value(ticket.key)
    return (-stamp, (project, -number, raw))


_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def created_label(created: dt.datetime | None, today: dt.date) -> str:
    """Anlagezeitpunkt in Leseform: "heute 08:14", "gestern 16:02", "Fr 19.09. 10:30".

    Args:
        created:
            Der Zeitstempel aus Jira, bereits in Ortszeit.
        today:
            Der Bezugstag.

    Returns:
        Die Beschriftung, leer ohne Zeitstempel.
    """
    if created is None:
        return ""
    day = created.date()
    clock = f"{created:%H:%M}"
    if day == today:
        return f"heute {clock}"
    if day == today - dt.timedelta(days=1):
        return f"gestern {clock}"
    return f"{_WEEKDAYS[day.weekday()]} {day:%d.%m.} {clock}"


def visible_tickets(tickets: Iterable[Ticket], member: str, since: dt.date) -> list[Ticket]:
    """Die Tickets der gewaehlten Person und des gewaehlten Zeitraums.

    Args:
        tickets:
            Die geladene Liste.
        member:
            Name aus der Merkliste, ALL_MEMBERS fuer alle.
        since:
            Erster Tag des Zeitraums, einschliesslich.

    Returns:
        Die passenden Tickets in unveraenderter Reihenfolge. Ein Ticket ohne
        Anlagedatum faellt heraus - es laesst sich keinem Zeitraum zuordnen.
    """
    return [
        ticket
        for ticket in tickets
        if ticket.created is not None
        and ticket.created.date() >= since
        and (member == ALL_MEMBERS or ticket.reporter == member)
    ]

"""JQL-Ausdruecke des Performance-Boosters.

Anders als ``history_jql`` in den Ticket-Ansichten nehmen diese Ausdruecke
bewusst fremde Kennungen an: der Booster zeigt Kennzahlen je Team-Mitglied.
Entschieden am 23.09.2026, siehe PLAN-performance-booster.md.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from jira_timesheet_qt.services.ticket_board import assignee_clause, check_account_id


def done_since_jql(account_ids: Sequence[str], since: dt.date) -> str:
    """Erledigte Tickets einer Person, die seit einem Tag bewegt wurden.

    Gefiltert wird ueber ``updated`` statt ueber das Datum des
    Kategoriewechsels: jeder Wechsel setzt auch ``updated``, die Menge ist
    also eine Obermenge. Den genauen Abschluss liest der Kern aus
    ``statuscategorychangedate``.

    Args:
        account_ids:
            Kennungen der Person. Leer = der angemeldete Benutzer.
        since:
            Erster Tag der Vorperiode.

    Returns:
        Der JQL-Ausdruck.
    """
    return (
        f"{assignee_clause(account_ids)} AND statusCategory = Done "
        f'AND updated >= "{since:%Y-%m-%d}" ORDER BY updated ASC'
    )


def worklog_jql(account_ids: Sequence[str], since: dt.date, until: dt.date) -> str:
    """Tickets, auf die eine Person im Zeitraum gebucht hat.

    Args:
        account_ids:
            Kennungen der Person. Leer = der angemeldete Benutzer.
        since:
            Erster Tag.
        until:
            Letzter Tag.

    Returns:
        Der JQL-Ausdruck.
    """
    if account_ids:
        names = ", ".join(f'"{check_account_id(a)}"' for a in account_ids)
        author = f"worklogAuthor IN ({names})"
    else:
        author = "worklogAuthor = currentUser()"
    return f'{author} AND worklogDate >= "{since:%Y-%m-%d}" AND worklogDate <= "{until:%Y-%m-%d}"'


def _people(account_ids: Sequence[str]) -> list[str]:
    """Die Personen als JQL-Werte. Leer = der angemeldete Benutzer."""
    if not account_ids:
        return ["currentUser()"]
    return [f'"{check_account_id(a)}"' for a in account_ids]


def created_jql(account_ids: Sequence[str], since: dt.date, until: dt.date) -> str:
    """Tickets, die eine Person im Zeitraum angelegt hat - der Zulauf.

    Args:
        account_ids:
            Kennungen der Person. Leer = der angemeldete Benutzer.
        since:
            Erster Tag.
        until:
            Letzter Tag.

    Returns:
        Der JQL-Ausdruck.
    """
    people = _people(account_ids)
    reporter = f"reporter = {people[0]}" if len(people) == 1 else f"reporter IN ({', '.join(people)})"
    return f'{reporter} AND created >= "{since:%Y-%m-%d}" AND created <= "{until:%Y-%m-%d} 23:59"'


def _quote(value: str) -> str:
    """Setzt einen Statusnamen in Anfuehrungszeichen, eingebettete maskiert."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def closed_jql(account_ids: Sequence[str], statuses: Sequence[str], since: dt.date, until: dt.date) -> str:
    """Tickets, die eine Person im Zeitraum in einen Fertig-Status gezogen hat.

    Egal, wem sie zugewiesen waren - das ist das "zumachen" im Rollenprofil.
    Als Fertig-Status zaehlen alle uebergebenen Namen. Je Status und Person
    ein eigenes CHANGED-Praedikat, verbunden mit OR: ob TO eine Liste annimmt,
    ist nicht belegt, die Einzelform ist es.

    Args:
        account_ids:
            Kennungen der Person. Leer = der angemeldete Benutzer.
        statuses:
            Namen der Fertig-Status.
        since:
            Erster Tag.
        until:
            Letzter Tag.

    Returns:
        Der JQL-Ausdruck, leer ohne Status.
    """
    names = list(dict.fromkeys(name.strip() for name in statuses if name.strip()))
    if not names:
        return ""
    during = f'DURING ("{since:%Y-%m-%d}", "{until:%Y-%m-%d} 23:59")'
    parts = [
        f"status CHANGED TO {_quote(name)} BY {person} {during}" for name in names for person in _people(account_ids)
    ]
    return " OR ".join(parts)

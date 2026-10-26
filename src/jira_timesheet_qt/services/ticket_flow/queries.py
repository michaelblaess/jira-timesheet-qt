"""JQL des Ticketflusses: alle Tickets, an denen eine Person beteiligt war.

Belegt am 26.10.2026 gegen Jira Cloud: ``assignee WAS "<accountId>"`` greift,
siehe PLAN-ticketfluss.md.
"""

from __future__ import annotations

import datetime as dt

from jira_timesheet_qt.services.ticket_board import check_account_id

FLOW_FIELDS = "summary,status,created,updated,reporter,assignee"


def flow_jql(account_id: str, since: dt.date | None) -> str:
    """Tickets, die eine Person angelegt oder irgendwann bearbeitet hat.

    Gefiltert wird ueber ``updated``: jeder Bearbeiterwechsel setzt es, die
    Menge ist also eine Obermenge. Den genauen Zeitpunkt jeder Kante liest
    der Kern aus dem Aenderungsprotokoll.

    Args:
        account_id:
            Kennung der Person in der Mitte.
        since:
            Erster Tag, None = ohne Untergrenze.

    Returns:
        Der JQL-Ausdruck.

    Raises:
        AccountIdError:
            Wenn die Kennung leer ist oder unerlaubte Zeichen enthaelt.
    """
    person = f'"{check_account_id(account_id)}"'
    who = f"(reporter = {person} OR assignee WAS {person})"
    if since is None:
        return f"{who} ORDER BY updated DESC"
    return f'{who} AND updated >= "{since:%Y-%m-%d}" ORDER BY updated DESC'

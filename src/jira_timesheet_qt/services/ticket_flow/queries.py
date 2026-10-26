"""JQL des Ticketflusses: alle Tickets, an denen eine Person beteiligt war.

Belegt am 26.10.2026 gegen Jira Cloud: ``assignee WAS "<accountId>"`` greift,
siehe PLAN-ticketfluss.md.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from jira_timesheet_qt.services.ticket_board import AccountIdError, check_account_id

FLOW_FIELDS = "summary,status,created,updated,statuscategorychangedate,reporter,assignee"


def flow_jqls(account_ids: Sequence[str], since: dt.date | None) -> list[str]:
    """Tickets, die eine Person angelegt oder irgendwann bearbeitet hat.

    Zwei Ausdruecke statt einem mit OR: getrennt und gleichzeitig ausgefuehrt
    brauchten sie am 26.10.2026 2,0 s statt 8,3 s fuer dieselben 338 Tickets.
    Doppelte Treffer fasst der Kern zusammen.

    Gefiltert wird ueber ``updated``: jeder Bearbeiterwechsel setzt es, die
    Menge ist also eine Obermenge. Den genauen Zeitpunkt jeder Kante liest
    der Kern aus dem Aenderungsprotokoll.

    Mehrere Kennungen werden beim Bearbeiter per OR verknuepft statt per
    ``WAS IN`` - belegt ist nur die Form mit einer einzelnen Kennung.

    Args:
        account_ids:
            Kennungen der Person in der Mitte, eine Person kann mehrere
            Konten fuehren.
        since:
            Erster Tag, None = ohne Untergrenze.

    Returns:
        Die Ausdruecke fuer Ersteller und Bearbeiter.

    Raises:
        AccountIdError:
            Wenn keine Kennung kommt oder eine davon unbrauchbar ist.
    """
    if not account_ids:
        raise AccountIdError("Keine Kennung fuer die Mitte")
    people = [f'"{check_account_id(account)}"' for account in account_ids]
    reporter = f"reporter IN ({', '.join(people)})"
    assignee = " OR ".join(f"assignee WAS {person}" for person in people)
    tail = " ORDER BY updated DESC" if since is None else f' AND updated >= "{since:%Y-%m-%d}" ORDER BY updated DESC'
    if len(people) > 1:
        assignee = f"({assignee})"
    return [f"{reporter}{tail}", f"{assignee}{tail}"]

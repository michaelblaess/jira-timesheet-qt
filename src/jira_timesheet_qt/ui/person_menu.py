"""Personen-Eintraege der Kontextmenues: Tickets ansehen, ins Team aufnehmen.

Von allen Ticketlisten geteilt, damit das Menue an jeder Zeile gleich aussieht.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from jira_timesheet_qt.services.ticket_board import AccountIdError, Ticket, check_account_id

PersonHandler = Callable[[str, str], None]


def menu_people(ticket: Ticket | None, anonymized: bool) -> list[tuple[str, str]]:
    """Bearbeiter und Autor mit brauchbarer Kennung, dieselbe Person nur einmal.

    Args:
        ticket:
            Das Ticket der Zeile, oder None auf einer Gruppenzeile.
        anonymized:
            Im Screenshot-Modus sind die Namen erfunden - dann niemand.

    Returns:
        (Name, Kennung) in der Reihenfolge Bearbeiter, Autor.
    """
    people: list[tuple[str, str]] = []
    if ticket is None or anonymized:
        return people
    for name, account_id in ((ticket.assignee, ticket.assignee_id), (ticket.reporter, ticket.reporter_id)):
        try:
            checked = check_account_id(account_id)
        except AccountIdError:
            continue
        if name and all(checked != known for _, known in people):
            people.append((name, checked))
    return people


def person_actions(
    menu: QMenu,
    ticket: Ticket | None,
    anonymized: bool,
    team_ids: Collection[str],
    on_show: PersonHandler,
    on_add: PersonHandler,
) -> list[QAction]:
    """Je Person "Tickets von ... anzeigen" und, wer fehlt, "... zu meinem Team hinzufügen".

    Ohne Person bleibt ein ausgegrauter Eintrag stehen - so ist das Menue an
    jeder Zeile gleich aufgebaut.

    Args:
        menu:
            Das Menue, dem die Eintraege gehoeren.
        ticket:
            Das Ticket der Zeile.
        anonymized:
            Screenshot-Modus.
        team_ids:
            Alle Kennungen der Merkliste. Wer darin steht, bekommt keinen
            Eintrag zum Hinzufuegen.
        on_show:
            Bekommt (Kennung, Name) fuer "Tickets anzeigen".
        on_add:
            Bekommt (Kennung, Name) fuer "zu meinem Team hinzufügen".

    Returns:
        Die Eintraege.
    """
    people = menu_people(ticket, anonymized)
    if not people:
        placeholder = QAction("Tickets der Person anzeigen", menu)
        placeholder.setEnabled(False)
        return [placeholder]
    actions: list[QAction] = []
    for name, account_id in people:
        show = QAction(f"Tickets von {name} anzeigen", menu)
        show.triggered.connect(lambda _=False, a=account_id, n=name: on_show(a, n))
        actions.append(show)
        if account_id not in team_ids:
            add = QAction(f"{name} zu meinem Team hinzufügen", menu)
            add.triggered.connect(lambda _=False, a=account_id, n=name: on_add(a, n))
            actions.append(add)
    return actions

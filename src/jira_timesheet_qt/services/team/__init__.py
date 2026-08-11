"""Merkliste "Mein Team" - Ticket-Stand von Kollegen ansehen.

Der Kern ist bewusst abhaengigkeitsfrei und kennt weder Jira-Client noch
Oberflaeche, wie ``ticket_board`` auch. So laesst sich derselbe Code in der
Textual-Oberflaeche, in der Qt-Oberflaeche und im Terminal verwenden.

Wo die Grenze liegt und warum: Das Jira-Board zeigt jedem im Team die Tickets
der anderen, aber weder Zeitbuchungen noch Durchsatz. Genau daran haelt sich
diese Ansicht. Sie ist eine schnellere Linse auf das, was im Board ohnehin
steht - kein Werkzeug zur Leistungsmessung. Deshalb entstehen fuer fremde
Personen weder der Pile-of-Shame-Marker noch die Auswertung, und zwar nicht
ueber einen Schalter, sondern weil die Abfragen dafuer gar nicht erst laufen.

Typischer Ablauf:

    from jira_timesheet_qt.services.team import merge_accounts, parse_search

    treffer = parse_search(await client.fetch_people("Nachname"))
    # Anzahl und juengstes Datum je Konto nachladen, dann:
    mitglied = merge_accounts(treffer, name="Vorname Nachname")
"""

from __future__ import annotations

from .models import AccountCandidate, Roster, TeamMember
from .roster import (
    from_storage,
    merge_accounts,
    parse_people,
    parse_search,
    sort_candidates,
    to_storage,
    with_last_touch,
)

__all__ = [
    "AccountCandidate",
    "Roster",
    "TeamMember",
    "from_storage",
    "merge_accounts",
    "parse_people",
    "parse_search",
    "sort_candidates",
    "to_storage",
    "with_last_touch",
]

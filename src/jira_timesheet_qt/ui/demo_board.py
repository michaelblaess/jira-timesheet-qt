"""Beispieldaten fuer die Ticket-Ansichten.

Frei erfunden - KEINE realen Ticketdaten, keine realen Statusnamen. Die
Statusnamen sind bewusst dieselben wie die Beispiele im Einstellungsdialog:
wer den Screenshot sieht und danach die Einstellungen oeffnet, erkennt die
Zuordnung wieder.

Die Daten laufen durch denselben Kern wie echte Jira-Antworten (build_board,
build_statistics). Damit zeigt ein Screenshot auch wirklich das, was die
Anwendung rechnet - und nicht ein von Hand gemaltes Wunschbild.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from jira_timesheet_qt.services.ticket_board import (
    Board,
    BoardConfig,
    Role,
    Statistics,
    WorklogInfo,
    build_board,
    build_statistics,
)

# Fester Bezugszeitpunkt - Screenshots duerfen sich nicht mit dem Kalender
# aendern, sonst rutschen Liegezeiten und Diagramme von Lauf zu Lauf.
NOW = dt.datetime(2026, 7, 31, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))

BROWSE_BASE = "https://beispiel.atlassian.net"

_SELF = "acc-demo-self"
_OTHER = "acc-demo-other"


def demo_config() -> BoardConfig:
    """Die Zuordnung, die zu den Beispieldaten passt."""
    return BoardConfig(
        active_status=("In Bearbeitung", "Im Review"),
        backlog_status=("Bereit", "Eingeplant"),
        handback_status=("Ausgeliefert",),
        acceptance_status=("Wartet auf Freigabe",),
        closing_status=("Zur Abnahme",),
        priorities=("Blocker", "Kritisch", "Hoch", "Mittel", "Niedrig"),
        high_priority_ranks=2,
        thresholds={Role.ACTIVE: 20.0, Role.ACCEPTANCE: 10.0},
    )


def _stamp(year: int, month: int, day: int) -> str:
    """Baut einen Jira-Zeitstempel im Format der Cloud-API."""
    return f"{year:04d}-{month:02d}-{day:02d}T09:15:00.000+0200"


def _issue(  # noqa: PLR0913 - ein Feld je Jira-Feld, Buendeln verschleiert nur
    key: str,
    summary: str,
    status: str,
    category: str,
    priority: str,
    issue_type: str,
    created: str,
    updated: str,
    *,
    foreign: bool = False,
    blocked_by: str = "",
) -> dict[str, Any]:
    """Baut ein Issue-JSON im Format der Jira-Suchantwort."""
    links: list[dict[str, Any]] = []
    if blocked_by:
        links.append(
            {
                "type": {"inward": "is blocked by"},
                "inwardIssue": {
                    "key": blocked_by,
                    "fields": {
                        "status": {"statusCategory": {"key": "indeterminate"}},
                    },
                },
            }
        )
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status, "statusCategory": {"key": category}},
            "priority": {"name": priority},
            "issuetype": {"name": issue_type},
            "reporter": {
                "displayName": "Erika Musterfrau" if foreign else "Max Mustermann",
                "accountId": _OTHER if foreign else _SELF,
            },
            "assignee": {"displayName": "Max Mustermann", "accountId": _SELF},
            "created": created,
            "updated": updated,
            "issuelinks": links,
        },
    }


# Eigene Tickets. Die Auswahl deckt bewusst jede Gruppe und jeden Marker ab -
# ein Screenshot, der nur "In Bearbeitung" zeigt, erklaert die Ansicht nicht.
_ASSIGNED: tuple[dict[str, Any], ...] = (
    _issue(
        "PROJ-201", "Sicherheitshinweis aus dem Scan bewerten",
        "In Bearbeitung", "indeterminate", "Kritisch", "Bug",
        _stamp(2026, 7, 20), _stamp(2026, 7, 29),
    ),
    _issue(
        "PROJ-202", "Suchindex auf den neuen Dienst umstellen",
        "In Bearbeitung", "indeterminate", "Mittel", "Story",
        _stamp(2025, 9, 3), _stamp(2026, 1, 15),
    ),
    _issue(
        "PROJ-203", "Bibliothek zentralisieren, Bundle-Ballast entfernen",
        "Im Review", "indeterminate", "Hoch", "Story",
        _stamp(2026, 7, 6), _stamp(2026, 7, 30),
    ),
    _issue(
        "PROJ-204", "Formular-Zusammenfassung als PDF ausliefern",
        "In Bearbeitung", "indeterminate", "Mittel", "Aufgabe",
        _stamp(2026, 6, 12), _stamp(2026, 7, 24),
        blocked_by="PROJ-240",
    ),
    _issue(
        "PROJ-205", "Anmeldung bricht bei abgelaufener Sitzung ab",
        "Bereit", "new", "Blocker", "Bug",
        _stamp(2026, 7, 27), _stamp(2026, 7, 30),
    ),
    _issue(
        "PROJ-206", "Bildergroessen beim Hochladen begrenzen",
        "Eingeplant", "new", "Mittel", "Story",
        _stamp(2026, 7, 2), _stamp(2026, 7, 18),
    ),
    _issue(
        "PROJ-207", "Neustart-Schwellwert justieren",
        "Wartet auf Freigabe", "indeterminate", "Mittel", "Aufgabe",
        _stamp(2026, 4, 8), _stamp(2026, 5, 20),
    ),
    _issue(
        "PROJ-208", "Consent-Dialog nachziehen",
        "Ausgeliefert", "indeterminate", "Mittel", "Story",
        _stamp(2026, 6, 2), _stamp(2026, 7, 10),
        foreign=True,
    ),
    _issue(
        "PROJ-209", "Linkliste um den NRE-Guard ergaenzen",
        "Zur Abnahme", "done", "Niedrig", "Aufgabe",
        _stamp(2026, 5, 11), _stamp(2026, 6, 30),
    ),
    _issue(
        "PROJ-210", "Alte Medienablage in den Objektspeicher verschieben",
        "In Bearbeitung", "indeterminate", "Niedrig", "Story",
        _stamp(2024, 11, 4), _stamp(2025, 8, 12),
    ),
)

# Tickets, an denen der Benutzer nur mitgewirkt hat - andere Zuweisung, andere
# Lage. Hier gibt es bewusst keinen Pile of Shame: fremde Tickets sind nicht
# die eigene Schande.
_RELEVANT: tuple[dict[str, Any], ...] = (
    _issue(
        "PROJ-221", "Zahlungsart im Bestellstrecken-Formular ergaenzen",
        "Im Review", "indeterminate", "Hoch", "Story",
        _stamp(2026, 7, 14), _stamp(2026, 7, 30), foreign=True,
    ),
    _issue(
        "PROJ-222", "Wartungsfenster im Kundenportal ankuendigen",
        "In Bearbeitung", "indeterminate", "Mittel", "Aufgabe",
        _stamp(2026, 7, 9), _stamp(2026, 7, 28), foreign=True,
    ),
    _issue(
        "PROJ-223", "Tarifrechner rundet den Abschlag falsch",
        "Bereit", "new", "Kritisch", "Bug",
        _stamp(2026, 7, 21), _stamp(2026, 7, 27), foreign=True,
    ),
    _issue(
        "PROJ-224", "Suchergebnisse nach Relevanz sortieren",
        "Wartet auf Freigabe", "indeterminate", "Mittel", "Story",
        _stamp(2026, 5, 26), _stamp(2026, 7, 6), foreign=True,
    ),
    _issue(
        "PROJ-225", "Barrierefreiheit der Navigation pruefen",
        "Eingeplant", "new", "Niedrig", "Aufgabe",
        _stamp(2026, 6, 18), _stamp(2026, 7, 2), foreign=True,
    ),
    _issue(
        "PROJ-226", "Protokollierung im Anmeldedienst vereinheitlichen",
        "Zur Abnahme", "done", "Mittel", "Story",
        _stamp(2026, 4, 30), _stamp(2026, 6, 24), foreign=True,
    ),
)

# Buchungslage der auffaelligen Tickets. PROJ-202 und PROJ-210 liegen ohne
# jede Buchung - genau das macht den Pile of Shame aus. PROJ-207 wurde
# dagegen zuletzt gebucht und bleibt deshalb draussen.
_WORKLOGS: dict[str, WorklogInfo] = {
    "PROJ-202": WorklogInfo(count=0, last=None),
    "PROJ-210": WorklogInfo(count=4, last=dt.datetime(2025, 8, 12, 10, 0, tzinfo=NOW.tzinfo)),
    "PROJ-207": WorklogInfo(count=6, last=dt.datetime(2026, 7, 27, 10, 0, tzinfo=NOW.tzinfo)),
}


def demo_board(*, relevant: bool = False) -> Board:
    """Baut eine Beispielansicht ueber den echten Kern.

    Args:
        relevant:
            True liefert die Ansicht "Relevante Tickets", sonst die eigenen.

    Returns:
        Die fertige Ansicht mit Gruppen und Markern.
    """
    issues = list(_RELEVANT if relevant else _ASSIGNED)
    return build_board(
        issues,
        demo_config(),
        NOW,
        account_id=_SELF,
        browse_base=BROWSE_BASE,
        worklogs=None if relevant else _WORKLOGS,
    )


# Je Monat: (Jahr, Monat, angelegt, davon spaeter erledigt). Der Abgang wird
# aus dem Zulauf gebildet, nicht daneben gestellt - sonst waechst der Bestand
# ins Unsinnige und die Altersverteilung besteht nur noch aus Karteileichen.
_HISTORY: tuple[tuple[int, int, int, int], ...] = (
    (2025, 8, 5, 4),
    (2025, 9, 4, 3),
    (2025, 10, 7, 5),
    (2025, 11, 3, 3),
    (2025, 12, 2, 2),
    (2026, 1, 6, 4),
    (2026, 2, 5, 5),
    (2026, 3, 4, 3),
    (2026, 4, 8, 6),
    (2026, 5, 3, 3),
    (2026, 6, 6, 4),
    (2026, 7, 4, 2),
)

# Wie viele Tage nach dem Anlegen ein offen gebliebenes Ticket zuletzt
# angefasst wurde. Reihum, damit die Altersverteilung mehrere Balken hat und
# nicht alles in einem Eimer landet.
_TOUCH_AFTER_DAYS: tuple[int, ...] = (3, 12, 40, 95)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Verschiebt einen Monat um delta Monate."""
    index = (year * 12 + month - 1) + delta
    return index // 12, index % 12 + 1


def demo_statistics() -> Statistics:
    """Baut die Auswertung der Diagramme aus einer erfundenen Historie."""
    issues: list[dict[str, Any]] = []
    counter = 0
    open_index = 0

    for year, month, created, resolved in _HISTORY:
        # Erledigt wird einen Monat nach dem Anlegen - liegt das hinter dem
        # Bezugszeitpunkt, bleibt das Ticket offen. Ein Abgang in der Zukunft
        # waere ein sichtbarer Rechenfehler im Diagramm.
        done_year, done_month = _shift_month(year, month, 1)
        closes = done_year * 12 + done_month <= NOW.year * 12 + NOW.month

        for position in range(created):
            counter += 1
            key = f"PROJ-{300 + counter}"
            if position < resolved and closes:
                issues.append(
                    {
                        "key": key,
                        "fields": {
                            "created": _stamp(year, month, 5),
                            "updated": _stamp(done_year, done_month, 18),
                            "statuscategorychangedate": _stamp(done_year, done_month, 18),
                            "status": {"name": "Fertig", "statusCategory": {"key": "done"}},
                            "issuetype": {"name": "Story"},
                        },
                    }
                )
                continue

            touched = dt.date(year, month, 5) + dt.timedelta(
                days=_TOUCH_AFTER_DAYS[open_index % len(_TOUCH_AFTER_DAYS)]
            )
            open_index += 1
            issues.append(
                {
                    "key": key,
                    "fields": {
                        "created": _stamp(year, month, 5),
                        "updated": _stamp(touched.year, touched.month, touched.day),
                        "status": {"name": "Bereit", "statusCategory": {"key": "new"}},
                        "issuetype": {"name": "Story"},
                    },
                }
            )

    # Die offenen Tickets der Ansicht gehoeren mit in die Altersverteilung.
    issues.extend(_ASSIGNED)
    return build_statistics(issues, NOW)

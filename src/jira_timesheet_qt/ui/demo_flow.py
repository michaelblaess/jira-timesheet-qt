"""Beispieldaten fuer den Reiter Teamflow.

Frei erfunden - KEINE realen Personen, Tickets oder Titel. Die Namen sind
dieselben unmissverstaendlich erfundenen wie im Anonymisierer, Max Mustermann
steht wie in demo_board in der Mitte.

Die Daten laufen durch denselben Kern wie echte Jira-Antworten (extract_flow,
build_star). Ein Screenshot zeigt damit, was die Anwendung rechnet.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

from jira_timesheet_qt.services.ticket_flow import FlowLoad, extract_flow

# Fester Bezugszeitpunkt - Screenshots duerfen sich nicht mit dem Kalender aendern.
NOW = dt.datetime(2026, 7, 31, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))

SELF = "acc-demo-self"
SELF_NAME = "Mustermann, Max"

# Jira-Schreibweise "Nachname, Vorname"; das Gewicht steuert, wie viel mit der
# Mitte hin und her geht - so entstehen dicke und duenne Pfeile und "Sonstige".
_PEOPLE: tuple[tuple[str, str, int], ...] = (
    ("acc-demo-erika", "Musterfrau, Erika", 9),
    ("acc-demo-bernd", "Beispiel, Bernd", 7),
    ("acc-demo-martina", "Muster, Martina", 6),
    ("acc-demo-berta", "Beispiel, Berta", 5),
    ("acc-demo-paula", "Probe, Paula", 4),
    ("acc-demo-tobias", "Test, Tobias", 4),
    ("acc-demo-pia", "Platzhalter, Pia", 3),
    ("acc-demo-dieter", "Dummy, Dieter", 2),
    ("acc-demo-frida", "Fiktiv, Frida", 1),
    ("acc-demo-lena", "Lorem, Lena", 1),
    ("acc-demo-igor", "Ipsum, Igor", 1),
)

_TOPICS = (
    "Anmeldeformular prüfen",
    "Suchergebnisse paginieren",
    "Fehlermeldung beim Export",
    "Startseite überarbeiten",
    "Schnittstelle dokumentieren",
    "Ladezeit der Übersicht",
    "Barrierefreiheit der Navigation",
    "Testdaten aufräumen",
    "Benachrichtigung per E-Mail",
    "Filter in der Liste",
)


def _person(account: str, name: str) -> dict[str, str]:
    return {"accountId": account, "displayName": name}


def _ts(moment: dt.datetime) -> str:
    return moment.isoformat(timespec="milliseconds")


def demo_flow() -> FlowLoad:
    """Baut einen Teamflow-Abruf mit Max Mustermann in der Mitte.

    Returns:
        Der Abruf, wie ihn der Worker liefern wuerde - rund 140 Tickets ueber
        ein Jahr, Auftraege und Uebergaben in beide Richtungen.
    """
    rng = random.Random(26)
    people = {account: name for account, name, _weight in _PEOPLE}
    people[SELF] = SELF_NAME
    weighted = [account for account, _name, weight in _PEOPLE for _ in range(weight)]

    issues: list[dict[str, Any]] = []
    histories: dict[str, list[dict[str, Any]]] = {}
    for number in range(1, 141):
        key = f"DEMO-{1000 + number}"
        other = rng.choice(weighted)
        created = NOW - dt.timedelta(days=rng.randrange(5, 360), hours=rng.randrange(0, 8))
        outgoing = rng.random() < 0.55
        reporter, first = (SELF, other) if outgoing else (other, SELF)
        log: list[dict[str, Any]] = []
        assignee = first
        # Jedes dritte Ticket wandert danach noch einmal weiter.
        if rng.random() < 0.35:
            nxt = rng.choice(weighted) if assignee == SELF else SELF
            if nxt != assignee:
                moment = created + dt.timedelta(days=rng.randrange(1, 20))
                if moment < NOW:
                    log.append(
                        {
                            "created": _ts(moment),
                            "items": [
                                {
                                    "field": "assignee",
                                    "fieldId": "assignee",
                                    "from": assignee,
                                    "fromString": people[assignee],
                                    "to": nxt,
                                    "toString": people[nxt],
                                }
                            ],
                        }
                    )
                    assignee = nxt
        issues.append(
            {
                "key": key,
                "id": str(90000 + number),
                "fields": {
                    "summary": f"{rng.choice(_TOPICS)} ({number})",
                    "created": _ts(created),
                    "updated": _ts(created + dt.timedelta(days=1)),
                    "reporter": _person(reporter, people[reporter]),
                    "assignee": _person(assignee, people[assignee]),
                },
            }
        )
        histories[key] = log
    return FlowLoad((SELF,), None, extract_flow(issues, histories), cached=0, fetched=len(issues))

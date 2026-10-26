"""Datenmodell des Ticketflusses: Personen, Kanten und der Stern um eine Mitte.

Wege, keine Leistung: das Modell kennt Anzahlen je Weg, aber keine Rangfolge.
Die Auswahl der sichtbaren Speichen sortiert die Oberflaeche alphabetisch.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# Kantenarten. Die Kuerzel wandern unveraendert in QSettings.
EDGE_ORDER = "order"
"""Auftrag: Ersteller an ersten Bearbeiter."""
EDGE_HANDOVER = "handover"
"""Uebergabe: Bearbeiterwechsel im Aenderungsprotokoll, alter an neuen."""
EDGE_ACCEPTANCE = "acceptance"
"""Abnahme: wer das Ticket beim Wechsel nach Fertig hatte, an den Ersteller."""
EDGE_KINDS: tuple[str, ...] = (EDGE_ORDER, EDGE_HANDOVER, EDGE_ACCEPTANCE)


@dataclass(frozen=True)
class Person:
    """Eine Person im Fluss, erkannt an der accountId."""

    account_id: str
    name: str


@dataclass(frozen=True)
class FlowEdge:
    """Ein Ticket, das von einer Person zu einer anderen gewandert ist."""

    kind: str
    source: str
    target: str
    key: str
    when: dt.datetime


@dataclass(frozen=True)
class Spoke:
    """Die Wege zwischen der Mitte und einer Person (oder allen Uebrigen).

    Die Schluessel stehen einzeln, nicht nur als Zahl - ein Klick auf den
    Pfeil listet genau diese Tickets.
    """

    person: Person | None
    """None = "Sonstige", die zusammengefassten Personen jenseits des Limits."""
    outgoing: tuple[str, ...]
    """Tickets von der Mitte an die Person."""
    incoming: tuple[str, ...]
    """Tickets von der Person an die Mitte."""
    members: int = 1
    """Wie viele Personen die Speiche vertritt, bei "Sonstige" mehr als eine."""

    @property
    def total(self) -> int:
        """Anzahl aller Wege in beide Richtungen."""
        return len(self.outgoing) + len(self.incoming)


@dataclass(frozen=True)
class FlowStar:
    """Der Stern: eine Person in der Mitte und ihre Speichen."""

    center: Person
    spokes: tuple[Spoke, ...]
    """Die einzeln gezeigten Personen, alphabetisch nach Name."""
    others: Spoke | None
    """Alle uebrigen zusammengefasst, None wenn es keine gibt."""

    @property
    def is_empty(self) -> bool:
        """True, wenn die Mitte im Zeitraum mit niemandem verbunden ist."""
        return not self.spokes and self.others is None

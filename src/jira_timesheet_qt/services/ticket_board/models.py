"""Anzeigemodell fuer die Ticket-Ansichten.

Reine Datenklassen ohne Verhalten und ohne Kenntnis von Jira oder einer
Oberflaeche. Wer sie fuellt, steht in ``rules``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """Rolle eines Status: wer ist am Zug.

    Die Zuordnung konkreter Statusnamen ist Konfiguration, nicht Code -
    jede Jira-Instanz fuehrt eigene Workflows.
    """

    ACTIVE = "active"
    """Ich bin am Zug, es wird gerade gearbeitet."""

    BACKLOG = "backlog"
    """Bereit zum Ziehen, aber noch nicht begonnen."""

    HANDBACK = "handback"
    """Ausgeliefert, wartet auf Bewertung durch den Autor."""

    ACCEPTANCE = "acceptance"
    """Wartet auf Freigabe durch jemand anderen."""

    CLOSING = "closing"
    """Von Jira als fertig gezaehlt, aber mit Restarbeit."""

    UNKNOWN = "unknown"
    """Status ist keiner Rolle zugeordnet - faellt auf die Jira-Kategorie zurueck."""


class Marker(StrEnum):
    """Handlungsbedarf eines Tickets. Mehrere gleichzeitig sind moeglich."""

    HANDBACK = "handback"
    """Ausgeliefert, fremder Autor - gehoert zurueckgegeben, nicht bearbeitet."""

    PILE_OF_SHAME = "pile_of_shame"
    """Status behauptet Aktivitaet, aber weder Aenderung noch gebuchte Stunde."""

    STALE = "stale"
    """Seit sehr langer Zeit unveraendert."""

    HIGH_PRIORITY = "high_priority"
    """Prioritaet in der oberen Gruppe der konfigurierten Rangfolge."""

    ACCEPTANCE = "acceptance"
    """Wartet auf Freigabe - nachhaken."""

    BLOCKED = "blocked"
    """Ein Vorgaenger ist noch offen."""


@dataclass(frozen=True)
class WorklogInfo:
    """Buchungslage eines Tickets.

    Wird nachgeladen und nur fuer die Tickets gebraucht, die der billige
    Test schon auffaellig fand.
    """

    count: int = 0
    last: dt.datetime | None = None


@dataclass
class Ticket:
    """Eine Zeile der Ticket-Ansicht."""

    key: str = ""
    summary: str = ""
    status: str = ""
    category: str = ""
    """Jira-Statuskategorie: new, indeterminate oder done."""

    priority: str = ""
    priority_rank: int = 99
    """Position in der konfigurierten Rangfolge, kleiner ist dringender."""

    issue_type: str = ""
    is_bug: bool = False
    reporter: str = ""
    assignee: str = ""
    foreign_reporter: bool = False
    created: dt.datetime | None = None
    updated: dt.datetime | None = None

    role: Role = Role.UNKNOWN
    markers: tuple[Marker, ...] = ()

    idle_workdays: float = 0.0
    """Arbeitstage seit der letzten Aenderung (Mo-Fr im Arbeitszeitfenster)."""

    idle_days: int = 0
    """Kalendertage seit der letzten Aenderung - fuer die Anzeige."""

    booking_workdays: float | None = None
    """Arbeitstage seit der letzten gebuchten Stunde, None = nicht geladen."""

    has_worklogs: bool | None = None
    """None = Buchungslage nicht geladen."""

    url: str = ""

    def has(self, marker: Marker) -> bool:
        """Prueft, ob ein bestimmter Marker gesetzt ist."""
        return marker in self.markers


@dataclass
class Group:
    """Eine Gruppe der Ansicht, ueblicherweise eine Rolle."""

    role: Role
    tickets: list[Ticket] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Anzahl der Tickets in dieser Gruppe."""
        return len(self.tickets)


@dataclass
class Board:
    """Das fertig aufbereitete Ergebnis einer Ticket-Ansicht."""

    groups: list[Group] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    unknown_status: list[str] = field(default_factory=list)
    """Status ohne Rollenzuordnung - gehoeren ins Protokoll, nicht verschwiegen."""

    @property
    def count(self) -> int:
        """Gesamtzahl der Tickets."""
        return len(self.tickets)

    def with_marker(self, marker: Marker) -> list[Ticket]:
        """Alle Tickets, die einen bestimmten Marker tragen."""
        return [t for t in self.tickets if t.has(marker)]

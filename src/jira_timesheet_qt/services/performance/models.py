"""Datenmodell des Performance-Boosters."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .period import Period

# Anzeigename fuer den angemeldeten Benutzer selbst.
SELF_NAME = "Ich"


@dataclass(frozen=True)
class HintConfig:
    """Schwellen der Hinweisregeln, alle aus den Einstellungen."""

    long_days: float = 15.0
    """Ab so vielen aktiven Arbeitstagen gilt ein ungeschaetztes Ticket als lang."""

    small_hours: float = 1.0
    """Unter so vielen gebuchten Stunden gilt ein Ticket als klein."""

    small_share: float = 40.0
    """Ab diesem Anteil kleiner Tickets (Prozent) gibt es einen Hinweis."""

    wip_limit: int = 3
    """Ab so vielen gleichzeitig aktiven Tickets gibt es einen Hinweis."""

    trend_percent: float = 30.0
    """Ab diesem Anstieg der Durchlaufzeit gegenueber der Vorperiode."""

    days_per_point: float = 3.0
    """Ab so vielen aktiven Arbeitstagen je Story Point gilt ein geschaetztes Ticket als lang."""


@dataclass(frozen=True)
class TicketMetric:
    """Ein erledigtes Ticket mit seinen Kennzahlen."""

    key: str
    summary: str
    issuetype: str
    done_at: dt.datetime
    active_days: float | None
    """Arbeitstage in aktiven Status. None, wenn es nie aktiv war."""
    hours: float
    """Insgesamt auf dem Ticket gebuchte Stunden (alle Personen)."""
    story_points: float | None = None
    """Schaetzung. None ohne Schaetzung oder ohne gefundenes Feld."""

    @property
    def days_per_point(self) -> float | None:
        """Aktive Arbeitstage je Story Point, None ohne Schaetzung oder ohne aktive Zeit."""
        if self.active_days is None or not self.story_points:
            return None
        return self.active_days / self.story_points


@dataclass(frozen=True)
class OpenTicket:
    """Ein offenes Ticket, das gerade in einem aktiven Status steht."""

    key: str
    summary: str


# Wie eine Person an einem Ticket beteiligt ist. Die Werte sind zugleich die
# Beschriftung der Filter im Reiter.
INVOLVE_DONE = "Erledigt"
INVOLVE_CREATED = "Erstellt"
INVOLVE_CLOSED = "Geschlossen"
INVOLVE_ACTIVE = "In Arbeit"
INVOLVEMENTS: tuple[str, ...] = (INVOLVE_DONE, INVOLVE_CREATED, INVOLVE_CLOSED, INVOLVE_ACTIVE)


@dataclass(frozen=True)
class PeriodTicket:
    """Ein Ticket, an dem die Person im Zeitraum beteiligt war - eine Zeile der Tabelle."""

    key: str
    summary: str
    issuetype: str
    status: str
    involvement: tuple[str, ...]
    """Beteiligungen in der Reihenfolge von INVOLVEMENTS."""
    hours: float
    story_points: float | None = None
    metric: TicketMetric | None = None
    """Kennzahlen, wenn das Ticket im Zeitraum erledigt wurde."""


@dataclass(frozen=True)
class Figures:
    """Die Kennzahlen eines Zeitraums - eine Zeile der Kacheln."""

    done: int
    median_active_days: float | None
    small_share: float | None
    """Anteil kleiner Tickets in Prozent. None ohne gebuchte Tickets."""
    booked_hours: float
    created: int = 0
    """Von der Person angelegte Tickets - der Zulauf."""
    closed: int | None = None
    """Von der Person in einen Fertig-Status gezogene Tickets. None, wenn nicht ermittelbar."""
    estimated: int = 0
    """Erledigte Tickets mit Story Points."""
    median_days_per_point: float | None = None
    hours_per_point: float | None = None


@dataclass(frozen=True)
class Hint:
    """Ein Verbesserungshinweis mit den Tickets, auf die er sich stuetzt."""

    rule: str
    title: str
    text: str
    keys: tuple[str, ...] = ()


@dataclass
class PerformanceReport:
    """Alles, was der Reiter zeigt."""

    member: str
    period: Period
    prior_period: Period
    current: Figures
    prior: Figures
    tickets: list[TicketMetric] = field(default_factory=list)
    """Erledigte Tickets im Zeitraum, nach Abschluss sortiert."""
    prior_tickets: list[TicketMetric] = field(default_factory=list)
    active_open: list[OpenTicket] = field(default_factory=list)
    created: list[dt.date] = field(default_factory=list)
    """Anlagetage der von der Person angelegten Tickets im Zeitraum."""
    prior_created: list[dt.date] = field(default_factory=list)
    all_tickets: list[PeriodTicket] = field(default_factory=list)
    """Alle Tickets, an denen die Person im Zeitraum beteiligt war."""
    hints: list[Hint] = field(default_factory=list)
    config: HintConfig = field(default_factory=HintConfig)
    browse_base: str = ""
    notes: list[str] = field(default_factory=list)
    """Einschraenkungen des Berichts, etwa ein nicht gefundenes Story-Points-Feld."""

    def flagged_keys(self) -> set[str]:
        """Alle Tickets, die in einem Hinweis vorkommen."""
        return {key for hint in self.hints for key in hint.keys}

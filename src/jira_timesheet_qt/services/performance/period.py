"""Zeitraeume des Performance-Boosters: 1M, 3M, 6M, YTD und ihre Vorperiode.

Die Vorperiode ist gleich lang und endet direkt vor dem Beginn des Zeitraums.
Daraus entsteht die Veraenderung auf den Kacheln - die Aktien-Analogie.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# Die Kuerzel wandern unveraendert in QSettings, deshalb Zeichenketten.
PERIOD_1M = "1M"
PERIOD_3M = "3M"
PERIOD_6M = "6M"
PERIOD_YTD = "YTD"
PERIODS: tuple[str, ...] = (PERIOD_1M, PERIOD_3M, PERIOD_6M, PERIOD_YTD)
DEFAULT_PERIOD = PERIOD_3M

_MONTHS: dict[str, int] = {PERIOD_1M: 1, PERIOD_3M: 3, PERIOD_6M: 6}


@dataclass(frozen=True)
class Period:
    """Ein Zeitraum aus ganzen Tagen, beide Grenzen eingeschlossen."""

    start: dt.date
    end: dt.date

    @property
    def days(self) -> int:
        """Anzahl der Kalendertage."""
        return (self.end - self.start).days + 1

    def contains(self, day: dt.date) -> bool:
        """Prueft, ob ein Tag im Zeitraum liegt."""
        return self.start <= day <= self.end


def _months_back(day: dt.date, months: int) -> dt.date:
    """Gleicher Kalendertag einige Monate frueher, am Monatsende gekappt."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return dt.date(year, month, candidate)
        except ValueError:
            continue
    return dt.date(year, month, 28)


def period_for(kind: str, today: dt.date) -> tuple[Period, Period]:
    """Berechnet Zeitraum und Vorperiode.

    Wie beim Kursverlauf einer Aktie: 1M heisst vom gleichen Tag im Vormonat
    bis heute, YTD vom 1. Januar bis heute.

    Args:
        kind:
            Eines der Kuerzel aus PERIODS.
        today:
            Das Enddatum, ueblicherweise heute.

    Returns:
        Der Zeitraum und die gleich lange Vorperiode davor.

    Raises:
        ValueError:
            Bei einem unbekannten Kuerzel.
    """
    if kind == PERIOD_YTD:
        start = dt.date(today.year, 1, 1)
    elif kind in _MONTHS:
        start = _months_back(today, _MONTHS[kind]) + dt.timedelta(days=1)
    else:
        raise ValueError(f"Unbekannter Zeitraum: {kind!r}")
    current = Period(start, today)
    prior_end = start - dt.timedelta(days=1)
    prior = Period(prior_end - dt.timedelta(days=current.days - 1), prior_end)
    return current, prior

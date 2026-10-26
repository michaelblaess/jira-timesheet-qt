"""Zeitraeume des Ticketflusses: YTD, 1M, 3M, 12M und Alle.

Anders als beim Performance-Booster gibt es keine Vorperiode - der Fluss
zeigt Wege, keinen Verlauf.
"""

from __future__ import annotations

import datetime as dt

from jira_timesheet_qt.services.performance.period import months_back

# Die Kuerzel wandern unveraendert in QSettings, deshalb Zeichenketten.
FLOW_YTD = "YTD"
FLOW_1M = "1M"
FLOW_3M = "3M"
FLOW_12M = "12M"
FLOW_ALL = "ALL"
FLOW_PERIODS: tuple[str, ...] = (FLOW_YTD, FLOW_1M, FLOW_3M, FLOW_12M, FLOW_ALL)
DEFAULT_FLOW_PERIOD = FLOW_12M

_MONTHS: dict[str, int] = {FLOW_1M: 1, FLOW_3M: 3, FLOW_12M: 12}


def flow_since(kind: str, today: dt.date) -> dt.date | None:
    """Erster Tag eines Zeitraums.

    Args:
        kind:
            Eines der Kuerzel aus FLOW_PERIODS.
        today:
            Das Enddatum, ueblicherweise heute.

    Returns:
        Der erste Tag, None bei "Alle" (keine Untergrenze).

    Raises:
        ValueError:
            Bei einem unbekannten Kuerzel.
    """
    if kind == FLOW_ALL:
        return None
    if kind == FLOW_YTD:
        return dt.date(today.year, 1, 1)
    if kind in _MONTHS:
        return months_back(today, _MONTHS[kind]) + dt.timedelta(days=1)
    raise ValueError(f"Unbekannter Zeitraum: {kind!r}")

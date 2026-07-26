"""Parsen und Formatieren von Zeitaufwaenden.

Die Eingabe im Dialog soll so tolerant sein wie die Schreibweise im
Ticket-Alltag: "3h 30m", "5h", "15m", "3:30", "3,5" und "3.5" meinen alle
dasselbe.
"""

from __future__ import annotations

import re

# "3h 30m", "3 h", "30m", "3h30" - Stunden- und Minutenanteil je optional.
_HOURS_MINUTES = re.compile(
    r"^(?:(?P<hours>\d+(?:[.,]\d+)?)\s*(?:h|std|stunden?)\s*)?"
    r"(?:(?P<minutes>\d+)\s*(?:m|min|minuten?)?\s*)?$",
    re.IGNORECASE,
)
# "3:30" - Doppelpunkt-Notation.
_COLON = re.compile(r"^(?P<hours>\d+)\s*:\s*(?P<minutes>[0-5]?\d)$")


def parse_hours(text: str) -> float | None:
    """Wandelt eine Aufwandseingabe in Dezimalstunden.

    Args:
        text:
            Benutzereingabe, z.B. "3h 30m", "3:30", "3,5" oder "45m".

    Returns:
        Der Aufwand in Dezimalstunden, oder None bei ungueltiger Eingabe.
        Negative Werte gelten als ungueltig.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    colon = _COLON.match(raw)
    if colon is not None:
        return int(colon.group("hours")) + int(colon.group("minutes")) / 60.0

    # Reine Zahl mit Komma oder Punkt als Dezimaltrenner (de-DE tolerant).
    plain = raw.replace(",", ".")
    try:
        value = float(plain)
    except ValueError:
        pass
    else:
        return value if value >= 0 else None

    match = _HOURS_MINUTES.match(raw)
    if match is None:
        return None

    hours_part = match.group("hours")
    minutes_part = match.group("minutes")
    if hours_part is None and minutes_part is None:
        return None

    hours = float(hours_part.replace(",", ".")) if hours_part else 0.0
    minutes = float(minutes_part) if minutes_part else 0.0
    total = hours + minutes / 60.0
    return total if total >= 0 else None


def format_hours(hours: float) -> str:
    """Formatiert Dezimalstunden als "3h 30m" bzw. "5h" oder "15m"."""
    total_minutes = int(round(hours * 60))
    whole_hours, minutes = divmod(total_minutes, 60)
    if whole_hours and minutes:
        return f"{whole_hours}h {minutes}m"
    if whole_hours:
        return f"{whole_hours}h"
    return f"{minutes}m"

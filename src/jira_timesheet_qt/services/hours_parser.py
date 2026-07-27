"""Parser fuer Aufwandseingaben.

Akzeptiert die Schreibweisen der TUI: Dezimalzahl (3,5 / 3.5), Stunden-Doppel-
punkt (3:30), sowie die h/m-Form (3h 30m, 90m, 2h). Ergebnis sind Stunden als
Fliesskommazahl; ungueltige oder nicht-positive Eingaben liefern None.
"""

from __future__ import annotations

import re

# Doppelpunkt-Form H:MM (z.B. 3:30 -> 3,5 Stunden).
_COLON = re.compile(r"^\s*(\d+):([0-5]?\d)\s*$")
# h/m-Form: optionale Stunden (mit Dezimalteil) und/oder Minuten (3h 30m, 90m).
_HM = re.compile(r"^\s*(?:(\d+(?:[.,]\d+)?)\s*h)?\s*(?:(\d+)\s*m)?\s*$", re.IGNORECASE)


def parse_hours(text: str) -> float | None:
    """Wandelt eine Aufwandseingabe in Stunden um.

    Args:
        text:
            Die Benutzereingabe, z.B. "3h 30m", "3:30", "3,5" oder "90m".

    Returns:
        Die Stunden als positive Fliesskommazahl, oder None bei ungueltiger
        bzw. nicht-positiver Eingabe.
    """
    if text is None:
        return None
    raw = text.strip()
    if not raw:
        return None

    colon = _COLON.match(raw)
    if colon is not None:
        return _positive(int(colon.group(1)) + int(colon.group(2)) / 60.0)

    # Reine Dezimalzahl (Komma oder Punkt).
    try:
        return _positive(float(raw.replace(",", ".")))
    except ValueError:
        pass

    hm = _HM.match(raw)
    if hm is not None and (hm.group(1) or hm.group(2)):
        hours = float((hm.group(1) or "0").replace(",", "."))
        minutes = int(hm.group(2) or 0)
        return _positive(hours + minutes / 60.0)

    return None


def _positive(value: float) -> float | None:
    """Gibt den Wert zurueck, aber nur wenn er groesser als 0 ist."""
    return value if value > 0 else None

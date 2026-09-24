"""Ablage der Aenderungsprotokolle erledigter Tickets.

Ein erledigtes Ticket aendert sich kaum noch. Das Protokoll kostet einen
Abruf je Ticket, bei 6M also schnell hundert - deshalb bleibt es liegen, bis
sich der Zeitpunkt des Abschlusses aendert (etwa weil jemand es wieder
geoeffnet und erneut geschlossen hat).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


class ChangelogCache:
    """Aenderungsprotokolle je Ticket, getrennt nach Jira-Host."""

    def __init__(self, root: Path, host: str) -> None:
        """Legt die Ablage fest, ohne etwas anzulegen.

        Args:
            root:
                Wurzel der Ablage.
            host:
                Jira-Adresse. Zwei Instanzen koennen dieselben Schluessel fuehren.
        """
        digest = hashlib.sha256(host.strip().casefold().encode("utf-8")).hexdigest()[:12]
        self._dir = root / digest

    def _path(self, key: str) -> Path | None:
        """Dateipfad eines Tickets - None bei einem Schluessel, der kein Dateiname sein darf."""
        return self._dir / f"{key}.json" if _KEY.match(key) else None

    def load(self, key: str, stamp: str) -> list[dict[str, Any]] | None:
        """Liest ein Protokoll, wenn es zum Abschlusszeitpunkt passt.

        Args:
            key:
                Ticketschluessel.
            stamp:
                ``statuscategorychangedate`` aus der aktuellen Suche.

        Returns:
            Das Protokoll, oder None, wenn nichts oder ein veralteter Stand liegt.
        """
        path = self._path(key)
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Protokoll-Cache von %s unlesbar: %s", key, exc)
            return None
        if not isinstance(data, dict) or data.get("stamp") != stamp:
            return None
        histories = data.get("histories")
        return histories if isinstance(histories, list) else None

    def save(self, key: str, stamp: str, histories: list[dict[str, Any]]) -> None:
        """Legt ein Protokoll ab. Fehler werden protokolliert, nicht geworfen."""
        path = self._path(key)
        if path is None:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"stamp": stamp, "histories": histories}, ensure_ascii=False),
                encoding="utf-8",
                newline="\n",
            )
        except OSError as exc:
            logger.warning("Protokoll-Cache von %s nicht schreibbar: %s", key, exc)

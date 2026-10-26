"""Ablage der Profilbilder aus Jira.

Ein Bild aendert sich selten, das Laden kostet je Person einen Abruf bei
Atlassian oder Gravatar. Deshalb bleibt es eine Woche liegen. Getrennt nach
Jira-Host, weil dieselbe Kennung in zwei Instanzen zwei Personen sein kann.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

AVATAR_MAX_AGE = dt.timedelta(days=7)
"""So lange gilt ein abgelegtes Bild."""

_ACCOUNT = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")


class AvatarStore:
    """Profilbilder je Kennung, getrennt nach Jira-Host."""

    def __init__(self, root: Path, host: str, max_age: dt.timedelta = AVATAR_MAX_AGE) -> None:
        """Legt die Ablage fest, ohne etwas anzulegen.

        Args:
            root:
                Wurzel der Ablage.
            host:
                Jira-Adresse.
            max_age:
                Aelter abgelegte Bilder gelten als fehlend.
        """
        digest = hashlib.sha256(host.strip().casefold().encode("utf-8")).hexdigest()[:12]
        self._dir = root / digest
        self._max_age = max_age

    def _path(self, account: str) -> Path | None:
        """Dateipfad einer Kennung - None, wenn sie kein Dateiname sein darf."""
        # Der Doppelpunkt in "712020:..." ist unter Windows kein Dateizeichen.
        return self._dir / f"{account.replace(':', '_')}.img" if _ACCOUNT.match(account) else None

    def load(self, account: str) -> bytes | None:
        """Liest ein Bild, solange es nicht zu alt ist."""
        path = self._path(account)
        if path is None or not path.is_file():
            return None
        try:
            if time.time() - path.stat().st_mtime > self._max_age.total_seconds():
                return None
            return path.read_bytes()
        except OSError as exc:
            logger.warning("Profilbild von %s unlesbar: %s", account, exc)
            return None

    def save(self, account: str, data: bytes) -> None:
        """Legt ein Bild ab. Fehler werden protokolliert, nicht geworfen."""
        path = self._path(account)
        if path is None or not data:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            logger.warning("Profilbild von %s nicht schreibbar: %s", account, exc)

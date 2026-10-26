"""Laedt Profilbilder im Hintergrund.

Erst aus der Ablage, dann aus dem Netz. Wer keine Adresse mitbringt (nur im
Aenderungsprotokoll gesehen), bekommt sie ueber /rest/api/3/user nachgeschlagen.
Was nicht zu laden ist, fehlt im Ergebnis - die Ansicht zeigt dann Initialen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.avatars import AvatarStore
from jira_timesheet_qt.services.jira_client import JiraClient
from jira_timesheet_qt.services.ssl_support import tls_from_settings

# Gleichzeitige Bildabrufe - es sind selten mehr als zehn.
_CONCURRENCY = 6


class AvatarWorker(QThread):
    """Holt die Bilder zu einer Menge von Kennungen."""

    # Kennung auf Bilddaten, nur was geladen werden konnte.
    finished_ok = Signal(object)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        wanted: Mapping[str, str],
        cache_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        """Baut den Faden.

        Args:
            settings:
                Die geladenen Benutzereinstellungen.
            wanted:
                Kennung auf Bildadresse, leer = Adresse nachschlagen.
            cache_dir:
                Wurzel der Bildablage.
            parent:
                Das Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._wanted = dict(wanted)
        self._cache_dir = cache_dir

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread. Scheitern ist kein Fehler, nur ein fehlendes Bild."""
        try:
            images = asyncio.run(self._fetch())
        except Exception as exc:  # noqa: BLE001 - Bilder sind Beiwerk, der Faden meldet nur
            self.log.emit(f"Profilbilder nicht geladen: {type(exc).__name__}: {exc}")
            images = {}
        self.finished_ok.emit(images)

    async def _fetch(self) -> dict[str, bytes]:
        settings = self._settings
        store = AvatarStore(self._cache_dir, settings.jira_host)
        images: dict[str, bytes] = {}
        missing: dict[str, str] = {}
        for account, url in self._wanted.items():
            cached = store.load(account)
            if cached is not None:
                images[account] = cached
            else:
                missing[account] = url
        if not missing:
            return images

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            tls=tls_from_settings(settings),
        )
        unknown = [account for account, url in missing.items() if not url]
        if unknown:
            missing.update(await client.fetch_avatar_urls(unknown))

        gate = asyncio.Semaphore(_CONCURRENCY)

        async def one(account: str, url: str) -> None:
            if not url:
                return
            async with gate:
                data = await client.fetch_avatar(url)
            if data:
                store.save(account, data)
                images[account] = data

        await asyncio.gather(*(one(account, url) for account, url in missing.items()))
        return images

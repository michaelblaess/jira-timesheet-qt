"""Holt Suche und Aenderungsprotokolle fuer den Ticketfluss.

Oberflaechenfrei: der Abruf laeuft gegen eine Quelle mit der Schnittstelle
des JiraClient und eine Ablage mit der Schnittstelle des ChangelogCache.
Der Qt-Faden reicht nur noch durch, die Tests kommen ohne Netz aus.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .edges import FlowData, extract_flow
from .queries import FLOW_FIELDS, flow_jql

CHANGELOG_CHUNK = 40
"""So viele Protokolle je Abruf - dazwischen meldet der Lader seinen Stand."""


class FlowSource(Protocol):
    """Was der Lader vom Jira-Client braucht."""

    async def fetch_issues(
        self,
        build_jqls: Callable[[str], Sequence[str]],
        fields: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Fuehrt die Suchen aus und liefert die eigene accountId mit."""
        ...

    async def fetch_changelogs(
        self,
        keys: Sequence[str],
        concurrency: int = 4,
    ) -> dict[str, list[dict[str, Any]]]:
        """Holt Protokolle, gescheiterte fehlen im Ergebnis."""
        ...


class HistoryStore(Protocol):
    """Was der Lader von der Protokoll-Ablage braucht."""

    def load(self, key: str, stamp: str) -> list[dict[str, Any]] | None:
        """Liest ein Protokoll, wenn es zum Stempel passt."""
        ...

    def save(self, key: str, stamp: str, histories: list[dict[str, Any]]) -> None:
        """Legt ein Protokoll ab."""
        ...


@dataclass(frozen=True)
class FlowLoad:
    """Ergebnis eines Abrufs."""

    center: tuple[str, ...]
    """Kennungen der Mitte - beim angemeldeten Benutzer die aus der Sitzung."""
    since: dt.date | None
    """Untergrenze der Suche. Jeder spaetere Zeitraum laesst sich ohne neuen
    Abruf aus denselben Daten schneiden."""
    data: FlowData
    cached: int
    """Protokolle aus der Ablage."""
    fetched: int
    """Protokolle frisch abgerufen. Was fehlschlug, steht in data.missing."""


async def load_flow(
    source: FlowSource,
    store: HistoryStore,
    account_ids: Sequence[str],
    since: dt.date | None,
    on_progress: Callable[[str], None] | None = None,
) -> FlowLoad:
    """Holt alle Tickets mit Beteiligung der Mitte samt Protokoll.

    Gestempelt wird mit ``updated``: jeder Bearbeiterwechsel setzt es, ein
    abgelegtes Protokoll mit gleichem Stempel kann also keinen Wechsel
    verpasst haben.

    Args:
        source:
            Der Jira-Client.
        store:
            Ablage der Protokolle.
        account_ids:
            Kennungen der Mitte. Leer = der angemeldete Benutzer.
        since:
            Erster Tag, None = ohne Untergrenze.
        on_progress:
            Bekommt Zwischenstaende als Lesetext.

    Returns:
        Kanten, Namen und die Zahlen fuer das Protokoll.

    Raises:
        AccountIdError:
            Wenn keine brauchbare Kennung der Mitte feststeht.
    """
    report = on_progress or (lambda _text: None)
    own_ids = tuple(account_ids)

    def jqls(own: str) -> list[str]:
        return [flow_jql(own_ids or (own,), since)]

    own, issues = await source.fetch_issues(jqls, FLOW_FIELDS)
    center = own_ids or (own,)

    stamps: dict[str, str] = {}
    for issue in issues:
        key = str(issue.get("key") or "")
        if key:
            stamps[key] = str((issue.get("fields") or {}).get("updated") or "")

    histories: dict[str, list[dict[str, Any]]] = {}
    pending: list[str] = []
    for key, stamp in stamps.items():
        cached = store.load(key, stamp) if stamp else None
        if cached is None:
            pending.append(key)
        else:
            histories[key] = cached
    cached_count = len(histories)

    fetched = 0
    for start in range(0, len(pending), CHANGELOG_CHUNK):
        report(f"Änderungsverläufe: {start} von {len(pending)} geholt ...")
        chunk = pending[start : start + CHANGELOG_CHUNK]
        result = await source.fetch_changelogs(chunk)
        for key, entries in result.items():
            if stamps.get(key):
                store.save(key, stamps[key], entries)
        histories.update(result)
        fetched += len(result)

    return FlowLoad(center, since, extract_flow(issues, histories), cached_count, fetched)

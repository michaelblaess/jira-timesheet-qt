"""Rohdaten eines Tickets fuer die Ticket-Analyse.

Buendelt die drei Antworten der Jira-API, aus denen der Bericht entsteht.
Bewusst ohne Auswertung: die Aufbereitung macht ``services.ticket_report``,
der dafuer keinen Client kennen muss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TicketLifecycleData:
    """Issue, Aenderungsprotokoll und Kommentare eines Tickets."""

    issue: dict[str, Any] = field(default_factory=dict)
    changelog: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Ticket-Key aus dem Issue-JSON."""
        return str(self.issue.get("key", ""))

    @property
    def summary(self) -> str:
        """Titel des Tickets."""
        fields = self.issue.get("fields") or {}
        return str(fields.get("summary", ""))

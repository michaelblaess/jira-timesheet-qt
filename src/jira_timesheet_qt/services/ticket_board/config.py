"""Konfiguration der Ticket-Ansichten.

Welcher Status welche Rolle hat, ist bewusst KEINE Konstante im Code. Jede
Jira-Instanz fuehrt eigene Workflows - eine vermessene Instanz hatte
zweiundvierzig verschiedene Statuswerte. Fest verdrahtete Namen waeren
zugleich instanzspezifisch und, bei fremden Instanzen, fremde
Betriebsinterna in einem oeffentlichen Repo.

Ohne Konfiguration faellt alles auf die von Jira gelieferte Statuskategorie
zurueck. Das ist groeber, funktioniert aber sofort und ueberall.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Role

# Rangfolge der Prioritaeten, dringendstes zuerst. Deckt die Stufen mehrerer
# Jira-Schemata ab; unbekannte Stufen landen hinter allen bekannten.
DEFAULT_PRIORITIES: tuple[str, ...] = (
    "gesetzlich",
    "Blocker",
    "Kritisch",
    "Highest",
    "High",
    "Medium",
    "Low",
    "Lowest",
    "Geringfügig",
    "None",
)

# So viele Stufen vom oberen Ende gelten als hohe Prioritaet. Vier trifft die
# echten Ausnahmen und bleibt selten genug, um aufzufallen - eine Markierung,
# die auf jedem dritten Ticket klebt, sagt nichts mehr.
DEFAULT_HIGH_PRIORITY_RANKS = 4

# Ab so vielen Kalendertagen ohne Aenderung gilt ein Ticket als verwaist.
# Uebernommen aus dem Morgen-Briefing (morning.py, STALE_DAYS).
DEFAULT_STALE_DAYS = 180

# Zeitfenster der Ansicht "Relevante Tickets", in Kalendertagen. Ohne Fenster
# ist die Liste ein Archiv und kein Arbeitsvorrat.
DEFAULT_WINDOW_DAYS = 90

# Ab so vielen ARBEITSTAGEN ohne Regung faellt ein Ticket je Rolle auf.
#
# ACHTUNG - das ist eine Setzung, keine Messung. Der Startwert stammt aus
# LONG_PHASE_WORKDAYS des Ticket-Berichts, wo dieselbe Frage schon einmal
# beantwortet werden musste. Belastbar waere er erst, wenn er aus dem
# Aenderungsprotokoll abgeschlossener Tickets abgeleitet wird: wie lange
# liegt ein Ticket bei diesem Benutzer ueblicherweise in jedem Zustand.
# Bis dahin gehoert die Zahl in die Oberflaeche, damit sie nicht als
# Naturgesetz missverstanden wird.
#
# Rollen ohne Eintrag erzeugen keinen Pile of Shame:
#   BACKLOG  - Vorrat ist keine Schuld, ein altes Backlog-Ticket ist normal.
#   HANDBACK - dort liegt der Ball bei jemand anderem. Die Handlung heisst
#              "zurueckgeben", nicht "aufholen", und hat einen eigenen Marker.
DEFAULT_THRESHOLDS: dict[Role, float] = {
    Role.ACTIVE: 5.0,
    Role.ACCEPTANCE: 5.0,
    Role.CLOSING: 5.0,
}

# Reihenfolge der Gruppen in der Anzeige: aktiv oben, Wartendes unten.
GROUP_ORDER: tuple[Role, ...] = (
    Role.ACTIVE,
    Role.ACCEPTANCE,
    Role.BACKLOG,
    Role.HANDBACK,
    Role.CLOSING,
    Role.UNKNOWN,
)

# Rueckfall ohne Konfiguration: die Jira-Statuskategorie bestimmt die Rolle.
CATEGORY_ROLES: dict[str, Role] = {
    "indeterminate": Role.ACTIVE,
    "new": Role.BACKLOG,
    "done": Role.CLOSING,
}

# Eingehende Verknuepfungsphrasen, die "haengt von jenem ab" bedeuten. Nicht
# jede Instanz kennt einen Blocks-Typ; im vermessenen Projekt war die
# faktische Abhaengigkeit der Gantt-Vorgaenger "has to be done after".
BLOCKER_PHRASES: tuple[str, ...] = (
    "is blocked by",
    "has to be done after",
    "depends on",
)


@dataclass(frozen=True)
class BoardConfig:
    """Alle Stellschrauben der Ticket-Ansichten an einer Stelle."""

    active_status: tuple[str, ...] = ()
    backlog_status: tuple[str, ...] = ()
    handback_status: tuple[str, ...] = ()
    acceptance_status: tuple[str, ...] = ()
    closing_status: tuple[str, ...] = ()

    priorities: tuple[str, ...] = DEFAULT_PRIORITIES
    high_priority_ranks: int = DEFAULT_HIGH_PRIORITY_RANKS
    stale_days: int = DEFAULT_STALE_DAYS
    window_days: int = DEFAULT_WINDOW_DAYS
    thresholds: dict[Role, float] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )

    def role_of(self, status: str, category: str) -> Role:
        """Bestimmt die Rolle eines Status.

        Der Vergleich ist case-insensitiv, weil dieselbe Instanz denselben
        Zustand in verschiedenen Workflows unterschiedlich schreibt.

        Args:
            status:
                Statusname aus Jira.
            category:
                Statuskategorie aus Jira (new, indeterminate, done).

        Returns:
            Die zugeordnete Rolle. UNKNOWN nur dann, wenn weder eine
            Konfiguration greift noch die Kategorie bekannt ist.
        """
        needle = status.strip().casefold()
        configured: tuple[tuple[tuple[str, ...], Role], ...] = (
            (self.active_status, Role.ACTIVE),
            (self.backlog_status, Role.BACKLOG),
            (self.handback_status, Role.HANDBACK),
            (self.acceptance_status, Role.ACCEPTANCE),
            (self.closing_status, Role.CLOSING),
        )
        for names, role in configured:
            if any(needle == n.strip().casefold() for n in names):
                return role

        return CATEGORY_ROLES.get(category.strip().casefold(), Role.UNKNOWN)

    def is_configured(self, status: str) -> bool:
        """Prueft, ob fuer diesen Status eine ausdrueckliche Zuordnung besteht."""
        needle = status.strip().casefold()
        for names in (
            self.active_status,
            self.backlog_status,
            self.handback_status,
            self.acceptance_status,
            self.closing_status,
        ):
            if any(needle == n.strip().casefold() for n in names):
                return True
        return False

    def priority_rank(self, priority: str) -> int:
        """Position einer Prioritaetsstufe in der Rangfolge.

        Args:
            priority:
                Name der Stufe, wie Jira ihn liefert.

        Returns:
            Nullbasierter Rang, kleiner ist dringender. Unbekannte Stufen
            landen hinter allen bekannten, statt sich nach vorn zu draengen.
        """
        needle = (priority or "").strip().casefold()
        for index, name in enumerate(self.priorities):
            if name.strip().casefold() == needle:
                return index
        return len(self.priorities)

    def is_high_priority(self, priority: str) -> bool:
        """Prueft, ob eine Stufe zur oberen Gruppe zaehlt."""
        if not (priority or "").strip():
            return False
        return self.priority_rank(priority) < self.high_priority_ranks

    def threshold_of(self, role: Role) -> float | None:
        """Schwelle in Arbeitstagen fuer eine Rolle, None = keine."""
        return self.thresholds.get(role)

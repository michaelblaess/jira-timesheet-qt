"""Auswertung fuer die Diagramme ueber der Ticket-Tabelle.

Drei Fragen, drei Zahlenreihen:

1. Zulauf gegen Abgang je Monat - waechst der Bestand oder schrumpft er?
2. Bestand kumuliert - dieselbe Aussage als Kurve.
3. Altersverteilung - wie viel liegt wie lange?

Wichtig fuer die Zeitreihe ist ``statuscategorychangedate`` und NICHT
``resolutiondate``. In einer vermessenen Instanz war das Aufloesungsdatum
nur bei der Haelfte der erledigten Tickets gesetzt; wer damit rechnet,
halbiert den Durchsatz, ohne es zu merken.

Was diese Zahlen NICHT sind: ein Leistungsmass. Gezaehlt werden Tickets,
und ein mehrjaehriges Refactoring zaehlt genauso wie ein einzeiliger
Fehler. Als Selbstbeobachtung taugt die Reihe, mehr nicht - siehe die
Warnung in ``FOOTNOTE``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .rules import parse_ts, workdays_between

# Gehoert unter jedes Diagramm. Gezaehlt wird nur, was aktuell dieser Person
# zugewiesen ist - Erledigtes, das danach jemand anders uebernommen hat,
# fehlt. Die Kurve ist eine Untergrenze, kein Gesamtbild.
FOOTNOTE = (
    "Gezählt wird nur, was aktuell dir zugewiesen ist. Erledigtes, das danach "
    "jemand anders übernommen hat, fehlt - die Kurve ist eine Untergrenze."
)

# Klassengrenzen der Altersverteilung in Arbeitstagen.
AGE_BUCKETS: tuple[tuple[str, float], ...] = (
    ("0-5", 5.0),
    ("6-20", 20.0),
    ("21-60", 60.0),
    ("> 60", float("inf")),
)


@dataclass
class MonthValue:
    """Ein Monat der Zulauf-Abgang-Reihe."""

    month: str
    """Monat als JJJJ-MM."""

    inflow: int = 0
    outflow: int = 0
    cumulative: int = 0

    @property
    def balance(self) -> int:
        """Saldo des Monats, positiv heisst der Bestand waechst."""
        return self.inflow - self.outflow


@dataclass
class AgeBucket:
    """Eine Klasse der Altersverteilung."""

    label: str
    count: int = 0


@dataclass
class Statistics:
    """Alle Zahlen fuer die Diagramme."""

    months: list[MonthValue] = field(default_factory=list)
    buckets: list[AgeBucket] = field(default_factory=list)
    open_count: int = 0
    resolved_recent: int = 0
    """Erledigt in den letzten 30 Tagen."""

    resolved_quarter: int = 0
    """Erledigt in den letzten 90 Tagen."""

    lead_time_median: float = 0.0
    """Median der Durchlaufzeit Anlage bis Fertig, in Arbeitstagen."""

    lead_time_upper: float = 0.0
    """Beginn des oberen Viertels der Durchlaufzeit, in Arbeitstagen."""

    @property
    def inflow_total(self) -> int:
        """Zulauf ueber den ausgewerteten Zeitraum."""
        return sum(m.inflow for m in self.months)

    @property
    def outflow_total(self) -> int:
        """Abgang ueber den ausgewerteten Zeitraum."""
        return sum(m.outflow for m in self.months)

    @property
    def balance_total(self) -> int:
        """Saldo ueber den ausgewerteten Zeitraum."""
        return self.inflow_total - self.outflow_total


def _quantile(values: list[float], share: float) -> float:
    """Liefert ein Quantil einer bereits sortierten Liste."""
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(len(values) * share)))
    return values[index]


def build_statistics(
    issues: list[dict[str, Any]],
    now: dt.datetime | None = None,
    months: int = 12,
) -> Statistics:
    """Wertet die Ticket-Historie fuer die Diagramme aus.

    Args:
        issues:
            Alle Tickets des Benutzers, offen wie erledigt.
        now:
            Bezugszeitpunkt, None nimmt die aktuelle Zeit.
        months:
            Wie viele Monate die Reihe zurueckreicht. 0 = alle.

    Returns:
        Die ausgewerteten Zahlen.
    """
    moment = now or dt.datetime.now(dt.UTC)
    inflow: dict[str, int] = {}
    outflow: dict[str, int] = {}
    lead_times: list[float] = []
    ages: list[float] = []
    open_count = 0
    recent = 0
    quarter = 0

    for issue in issues:
        fields = issue.get("fields") or {}
        created = parse_ts(str(fields.get("created", "")))
        if created is not None:
            inflow[created.strftime("%Y-%m")] = inflow.get(created.strftime("%Y-%m"), 0) + 1

        status = fields.get("status") or {}
        category = str((status.get("statusCategory") or {}).get("key", "")).casefold()
        changed = parse_ts(str(fields.get("statuscategorychangedate", "")))

        if category == "done":
            if changed is not None:
                stamp = changed.strftime("%Y-%m")
                outflow[stamp] = outflow.get(stamp, 0) + 1
                age = (moment - changed).days
                if age <= 30:
                    recent += 1
                if age <= 90:
                    quarter += 1
                if created is not None:
                    lead_times.append(workdays_between(created, changed))
        else:
            open_count += 1
            updated = parse_ts(str(fields.get("updated", "")))
            if updated is not None:
                ages.append(workdays_between(updated, moment))

    series = _month_series(inflow, outflow, months, moment)
    lead_times.sort()

    return Statistics(
        months=series,
        buckets=_age_buckets(ages),
        open_count=open_count,
        resolved_recent=recent,
        resolved_quarter=quarter,
        lead_time_median=_quantile(lead_times, 0.5),
        lead_time_upper=_quantile(lead_times, 0.75),
    )


def _month_series(
    inflow: dict[str, int],
    outflow: dict[str, int],
    months: int,
    now: dt.datetime,
) -> list[MonthValue]:
    """Baut die lueckenlose Monatsreihe mit kumuliertem Bestand.

    Die Reihe muss lueckenlos sein: ein Monat ohne jede Bewegung ist eine
    Aussage und darf im Diagramm nicht einfach fehlen, sonst staucht sich
    die Zeitachse.

    Args:
        inflow:
            Zulauf je Monat.
        outflow:
            Abgang je Monat.
        months:
            Laenge der Reihe, 0 = ab dem ersten bekannten Monat.
        now:
            Bezugszeitpunkt, bestimmt das Ende der Reihe.

    Returns:
        Die Monatswerte in aufsteigender Reihenfolge.
    """
    stamps = sorted(set(inflow) | set(outflow))
    if not stamps:
        return []

    first = dt.date.fromisoformat(f"{stamps[0]}-01")
    last = dt.date(now.year, now.month, 1)

    # Der kumulierte Bestand muss ab dem ersten bekannten Monat zaehlen,
    # auch wenn die Anzeige spaeter einsetzt - sonst startet die Kurve
    # faelschlich bei null.
    running = 0
    values: list[MonthValue] = []
    cursor = first
    while cursor <= last:
        stamp = cursor.strftime("%Y-%m")
        running += inflow.get(stamp, 0) - outflow.get(stamp, 0)
        values.append(
            MonthValue(
                month=stamp,
                inflow=inflow.get(stamp, 0),
                outflow=outflow.get(stamp, 0),
                cumulative=running,
            )
        )
        cursor = dt.date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)

    return values[-months:] if months > 0 else values


def _age_buckets(ages: list[float]) -> list[AgeBucket]:
    """Verteilt die Liegezeiten auf die Klassen.

    Args:
        ages:
            Liegezeiten der offenen Tickets in Arbeitstagen.

    Returns:
        Alle Klassen, auch die leeren - eine fehlende Klasse waere eine
        Luecke im Diagramm.
    """
    buckets = [AgeBucket(label=label) for label, _ in AGE_BUCKETS]
    for age in ages:
        for index, (_, limit) in enumerate(AGE_BUCKETS):
            if age <= limit:
                buckets[index].count += 1
                break
    return buckets

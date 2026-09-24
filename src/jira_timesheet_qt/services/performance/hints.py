"""Hinweisregeln des Performance-Boosters.

Jede Regel beschreibt ein Verhalten und einen naechsten Schritt, nie die
Person. Sie nennt die Tickets, auf die sie sich stuetzt - ein Hinweis ohne
Beleg waere eine Behauptung. Eine Schwelle von 0 schaltet die Regel ab.
"""

from __future__ import annotations

from .models import Hint, HintConfig, PerformanceReport, TicketMetric

RULE_LONG = "long"
RULE_SMALL = "small"
RULE_WIP = "wip"
RULE_TREND = "trend"


def _number(value: float) -> str:
    """Zahl mit deutschem Dezimalkomma und hoechstens einer Nachkommastelle."""
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def _tickets(count: int) -> str:
    """1 Ticket war oder N Tickets waren."""
    return "1 Ticket war" if count == 1 else f"{count} Tickets waren"


def is_long(ticket: TicketMetric, config: HintConfig) -> bool:
    """Ob ein Ticket laenger lief als erwartet.

    Mit Schaetzung zaehlt die Zeit je Story Point - ein grosses Ticket darf
    laenger dauern. Ohne Schaetzung gilt die feste Grenze in Arbeitstagen.
    """
    per_point = ticket.days_per_point
    if per_point is not None and config.days_per_point > 0:
        return per_point > config.days_per_point
    return ticket.active_days is not None and config.long_days > 0 and ticket.active_days > config.long_days


def build_hints(report: PerformanceReport) -> list[Hint]:
    """Wendet alle Regeln auf einen Bericht an.

    Args:
        report:
            Der Bericht ohne Hinweise.

    Returns:
        Die ausgeloesten Hinweise in fester Reihenfolge.
    """
    config = report.config
    hints: list[Hint] = []

    long = [t for t in report.tickets if is_long(t, config)]
    if long:
        estimated = [t for t in long if t.days_per_point is not None]
        limits = []
        if len(estimated) < len(long):
            limits.append(f"über {_number(config.long_days)} Arbeitstage")
        if estimated:
            limits.append(f"über {_number(config.days_per_point)} Arbeitstage je Story Point")
        hints.append(
            Hint(
                rule=RULE_LONG,
                title="Lange Tickets",
                text=(
                    f"{_tickets(len(long))} länger in Arbeit als erwartet ({' bzw. '.join(limits)}). "
                    "Größere Tickets früher schneiden oder Zwischenstände abnehmen lassen."
                ),
                keys=tuple(t.key for t in long),
            )
        )

    booked = [t for t in report.tickets if t.hours > 0]
    small = [t for t in booked if t.hours < config.small_hours]
    share = report.current.small_share
    if share is not None and config.small_share > 0 and share >= config.small_share and small:
        hints.append(
            Hint(
                rule=RULE_SMALL,
                title="Viele kleine Tickets",
                text=(
                    f"{_number(share)} % der gebuchten Tickets hatten weniger als "
                    f"{_number(config.small_hours)} h ({len(small)} von {len(booked)}). "
                    "Kleinteile bündeln, etwa als Sammelticket je Sprint - jedes Ticket "
                    "kostet Verwaltung und einen Kontextwechsel."
                ),
                keys=tuple(t.key for t in small),
            )
        )

    if len(report.active_open) >= config.wip_limit > 0:
        hints.append(
            Hint(
                rule=RULE_WIP,
                title="Viel parallel in Arbeit",
                text=(
                    f"{len(report.active_open)} Tickets stehen gleichzeitig in einem aktiven "
                    "Status. Weniger parallel beginnen und erst abschließen."
                ),
                keys=tuple(t.key for t in report.active_open),
            )
        )

    now_median = report.current.median_active_days
    before = report.prior.median_active_days
    if now_median is not None and before is not None and before > 0:
        rise = 100.0 * (now_median - before) / before
        if config.trend_percent > 0 and rise >= config.trend_percent:
            hints.append(
                Hint(
                    rule=RULE_TREND,
                    title="Durchlaufzeit steigt",
                    text=(
                        f"Der Median der Durchlaufzeit ist von {_number(before)} auf "
                        f"{_number(now_median)} Arbeitstage gestiegen (+{_number(rise)} %). "
                        "Prüfen, ob die Tickets größer geworden sind oder öfter warten."
                    ),
                )
            )

    return hints

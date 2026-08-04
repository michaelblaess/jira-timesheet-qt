"""Bereitet einen Ticket-Lebenszyklus fuer die Darstellung auf.

Die Rohdaten kommen aus dem Skill jira-specialist (Paket jira_read, nur
GET). Hier entsteht daraus ein reines Anzeigemodell: Marker fuer die
Zeitachse, Segmente fuer das Statusband, Kennzahlen, Beteiligte und
automatisch abgeleitete Befunde.

Grundsatz: jeder Befund muss aus den Ticketdaten belegbar sein. Es wird
nichts geschaetzt und niemand bewertet - keine Personen-Kennzahlen.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from . import lifecycle
from .lifecycle import Lifecycle, humanize

# Arbeitszeitfenster fuer die Netto-Liegezeit. Kalenderzeit allein macht aus
# einem Wochenende eine Verzoegerung, die niemand zu verantworten hat.
WORK_START_HOUR = 8
WORK_END_HOUR = 18
WORK_DAYS = (0, 1, 2, 3, 4)

# Status-Zuordnung fuer die Einfaerbung. Deckt die ueblichen deutschen und
# englischen Statusnamen ab, Unbekanntes bleibt neutral.
STATUS_TONE = {
    "offen": "wait",
    "schreiben": "wait",
    "schätzen": "wait",
    "fertig für entwicklung": "wait",
    "backlog": "wait",
    "in arbeit": "work",
    "prüfen": "work",
    "im code review": "work",
    "in abnahme": "work",
    "evaluation": "work",
    "fertig": "done",
    "livesetzen": "done",
    "schließen": "done",
    "geschlossen": "done",
}

# Status, in denen tatsaechlich am Ticket gearbeitet wird. Alles andere gilt
# als Warten. Diese Zuordnung ist eine Setzung und wird im Bericht offen
# ausgewiesen - sie bestimmt die Flow-Effizienz.
ACTIVE_STATUS = {"in arbeit", "im code review"}

# Ab dieser Liegezeit gilt eine Phase als auffaellig lang. Gerechnet in
# ARBEITSTAGEN (netto), nicht in Kalendertagen - sonst schlaegt jedes
# Wochenende zu Buche. Die Schwelle steht im Bericht.
LONG_PHASE_WORKDAYS = 5.0

# Felder, deren Aenderung nach Arbeitsbeginn eine Aenderung am Auftrag ist.
SCOPE_FIELDS = ("summary", "description")

EVENT_TONE = {
    "created": "pine",
    "status": "work",
    "assignee": "pine",
    "comment": "done",
    "attachment": "done",
    "link": "wait",
    "field": "wait",
}

EVENT_KIND_LABEL = {
    "created": "Anlage",
    "status": "Statuswechsel",
    "assignee": "Zuweisung",
    "comment": "Kommentar",
    "attachment": "Anhang",
    "link": "Verknüpfung",
    "field": "Feldänderung",
}

# Marker, die naeher als dieser Anteil der Achse beieinander liegen, teilen
# sich einen Punkt - sonst ueberdecken sie sich gegenseitig.
MERGE_PCT = 1.2

# Mindestabstand, damit eine Beschriftung an der Achse Platz hat.
LABEL_PCT = 9.0


def business_seconds(start: dt.datetime, end: dt.datetime) -> float:
    """Zaehlt die Sekunden zwischen zwei Zeitpunkten innerhalb der Arbeitszeit.

    Args:
        start:
            Beginn des Zeitraums.
        end:
            Ende des Zeitraums.

    Returns:
        Sekunden, die auf Werktage im Zeitfenster fallen.
    """
    if end <= start:
        return 0.0

    total = 0.0
    day = start.date()
    while day <= end.date():
        if day.weekday() in WORK_DAYS:
            window_start = dt.datetime.combine(day, dt.time(WORK_START_HOUR), tzinfo=start.tzinfo)
            window_end = dt.datetime.combine(day, dt.time(WORK_END_HOUR), tzinfo=start.tzinfo)
            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds()
        day += dt.timedelta(days=1)
    return total


def humanize_seconds(seconds: float) -> str:
    """Formatiert Sekunden als deutschen Kurztext."""
    return humanize(dt.timedelta(seconds=seconds))


def off_hours(start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """Findet alle Abschnitte ausserhalb der Arbeitszeit.

    Daraus entsteht der einblendbare Layer ueber der Zeitachse: er zeigt,
    welcher Teil einer langen Phase ueberhaupt niemand haette bearbeiten
    koennen.

    Args:
        start:
            Beginn des betrachteten Zeitraums.
        end:
            Ende des betrachteten Zeitraums.

    Returns:
        Liste aus Paaren (Beginn, Ende) der arbeitsfreien Abschnitte.
    """
    windows: list[tuple[dt.datetime, dt.datetime]] = []
    day = start.date()
    while day <= end.date():
        if day.weekday() in WORK_DAYS:
            windows.append(
                (
                    dt.datetime.combine(day, dt.time(WORK_START_HOUR), tzinfo=start.tzinfo),
                    dt.datetime.combine(day, dt.time(WORK_END_HOUR), tzinfo=start.tzinfo),
                )
            )
        day += dt.timedelta(days=1)

    gaps: list[tuple[dt.datetime, dt.datetime]] = []
    cursor = start
    for window_start, window_end in windows:
        if window_start > cursor:
            gaps.append((cursor, min(window_start, end)))
        cursor = max(cursor, min(window_end, end))
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return [(gap_start, gap_end) for gap_start, gap_end in gaps if gap_end > gap_start]


@dataclass
class Marker:
    """Ein Punkt auf der Zeitachse - ein oder mehrere gleichzeitige Ereignisse."""

    key: str
    pct: float
    when: dt.datetime
    actor: str
    tone: str
    kind: str
    title: str
    lead: str
    bullets: list[str] = field(default_factory=list)
    count: int = 1
    label: str = ""
    show_label: bool = False
    above: bool = True
    is_status: bool = False
    status_target: str = ""


@dataclass
class Segment:
    """Ein Statusabschnitt im Band unter der Achse."""

    status: str
    tone: str
    left: float
    width: float
    gross: str
    net: str
    gross_seconds: float
    net_seconds: float
    start: dt.datetime
    end: dt.datetime | None
    open_ended: bool
    comments: int = 0
    attachments: int = 0
    active: bool = False
    long: bool = False
    workdays: float = 0.0


@dataclass
class Metric:
    """Eine Kennzahl mit Wert, Erlaeuterung und Beleg."""

    label: str
    value: str
    note: str
    tone: str = "mut"


@dataclass
class Person:
    """Eine beteiligte Person mit Besitzzeit und Aktionsanteil."""

    name: str
    roles: str
    owner_pct: float
    owner_text: str
    action_pct: float
    actions: int
    comments: int
    changes: int
    first: str
    last: str
    is_current: bool


@dataclass
class Finding:
    """Ein automatisch abgeleiteter Befund samt Beleg."""

    tone: str
    title: str
    text: str


@dataclass
class Report:
    """Vollstaendiges Anzeigemodell eines Ticket-Lebenszyklus."""

    key: str
    summary: str
    url: str
    status: str
    status_tone: str
    issue_type: str
    priority: str
    reporter: str
    assignee: str
    parent: str
    created: dt.datetime
    stats: list[tuple[str, str]]
    markers: list[Marker]
    segments: list[Segment]
    metrics: list[Metric]
    people: list[Person]
    related: list[dict[str, str]]
    findings: list[Finding]
    offhours: list[tuple[float, float]]
    generated: str


def _tone_for_status(status: str) -> str:
    return STATUS_TONE.get(status.strip().lower(), "wait")


def _marker_title(event: lifecycle.Event) -> str:
    """Ueberschrift der Detailkarte eines Ereignisses."""
    if event.kind == "status":
        return event.text
    if event.kind == "created":
        return "Ticket angelegt"
    if event.kind == "assignee":
        return event.text.replace("Zuweisung: ", "")
    return event.text


def _marker_label(event: lifecycle.Event, count: int) -> str:
    """Knappe Beschriftung an der Achse."""
    who = event.actor
    if event.kind == "status":
        # Der Zielstatus steht als eigener Chip darunter, hier nur der Name.
        text = "Statuswechsel"
    elif event.kind == "assignee":
        text = f"an {event.text.split(' -> ')[-1]}"
    elif event.kind == "created":
        text = "angelegt"
    else:
        text = EVENT_KIND_LABEL.get(event.kind, event.kind)
    suffix = f" +{count - 1}" if count > 1 else ""
    return f"{who}: {text}{suffix}"


def _build_markers(life: Lifecycle, start: dt.datetime, span: float) -> list[Marker]:
    """Rechnet Ereignisse auf Achsenpositionen um und fasst Nahes zusammen."""
    groups: list[list[lifecycle.Event]] = []
    for event in life.events:
        pct = (event.when - start).total_seconds() / span * 100
        if groups:
            last = groups[-1][0]
            last_pct = (last.when - start).total_seconds() / span * 100
            if pct - last_pct <= MERGE_PCT:
                groups[-1].append(event)
                continue
        groups.append([event])

    markers: list[Marker] = []
    for index, members in enumerate(groups):
        lead_event = members[0]
        # Der inhaltlich staerkste Eintrag benennt die Gruppe.
        rank = {"status": 0, "created": 1, "assignee": 2, "comment": 3}
        lead_event = min(members, key=lambda item: rank.get(item.kind, 9))
        pct = (members[0].when - start).total_seconds() / span * 100

        bullets = []
        for item in members:
            stamp = f"{item.when:%H:%M}"
            entry = f"{stamp} - {EVENT_KIND_LABEL.get(item.kind, item.kind)}: {item.text}"
            if item.detail:
                entry += f" - {item.detail}"
            bullets.append(entry)

        # Ein Statuswechsel in der Gruppe bestimmt Form und Farbe des
        # Markers - der Wechsel ist das Gelenk, alles andere Aktivitaet.
        is_status = lead_event.kind == "status"
        target = lead_event.text.split(" -> ")[-1] if is_status else ""
        tone = _tone_for_status(target) if is_status else EVENT_TONE.get(lead_event.kind, "wait")

        markers.append(
            Marker(
                key=f"m{index}",
                pct=max(0.0, min(100.0, pct)),
                when=members[0].when,
                actor=lead_event.actor,
                tone=tone,
                is_status=is_status,
                status_target=target,
                kind=EVENT_KIND_LABEL.get(lead_event.kind, lead_event.kind),
                title=_marker_title(lead_event),
                lead=lead_event.detail or "",
                bullets=bullets,
                count=len(members),
                label=_marker_label(lead_event, len(members)),
            )
        )

    # Beschriftungen abwechselnd ueber und unter die Achse, und nur dort, wo
    # zum letzten Label derselben Seite genug Platz bleibt.
    last_above = -100.0
    last_below = -100.0
    for position, marker in enumerate(markers):
        marker.above = position % 2 == 0
        reference = last_above if marker.above else last_below
        if marker.pct - reference >= LABEL_PCT:
            marker.show_label = True
            if marker.above:
                last_above = marker.pct
            else:
                last_below = marker.pct
    return markers


def _build_segments(life: Lifecycle, start: dt.datetime, span: float, end: dt.datetime) -> list[Segment]:
    """Baut das Statusband mit Brutto- und Nettodauer."""
    segments: list[Segment] = []
    for status_span in life.spans:
        stop = status_span.end or end
        left = (status_span.start - start).total_seconds() / span * 100
        width = (stop - status_span.start).total_seconds() / span * 100
        net = business_seconds(status_span.start, stop)
        segments.append(
            Segment(
                status=status_span.status,
                tone=_tone_for_status(status_span.status),
                left=max(0.0, left),
                width=max(0.4, width),
                gross=humanize(status_span.duration),
                net=humanize_seconds(net),
                gross_seconds=status_span.duration.total_seconds(),
                net_seconds=net,
                start=status_span.start,
                end=status_span.end,
                open_ended=status_span.open_ended,
                active=status_span.status.strip().lower() in ACTIVE_STATUS,
                workdays=net / (WORK_END_HOUR - WORK_START_HOUR) / 3600,
                long=net / (WORK_END_HOUR - WORK_START_HOUR) / 3600 >= LONG_PHASE_WORKDAYS,
            )
        )
    return segments


def _build_people(life: Lifecycle) -> list[Person]:
    """Fasst Besitzzeit, Aktionen und Rollen je Person zusammen."""
    owner = {who: (span, pct) for who, span, pct in life.ownership_share()}
    actions = {who: (count, pct) for who, count, pct in life.action_share()}

    people: list[Person] = []
    for actor in life.actors.values():
        span, owner_pct = owner.get(actor.name, (dt.timedelta(), 0.0))
        count, action_pct = actions.get(actor.name, (0, 0.0))
        people.append(
            Person(
                name=actor.name,
                roles=", ".join(sorted(actor.roles)),
                owner_pct=owner_pct,
                owner_text=humanize(span) if span else "-",
                action_pct=action_pct,
                actions=count,
                comments=actor.comments,
                changes=actor.changes,
                first=f"{actor.first_seen:%d.%m.}" if actor.first_seen else "-",
                last=f"{actor.last_seen:%d.%m.}" if actor.last_seen else "-",
                is_current=actor.name == life.assignee,
            )
        )
    people.sort(key=lambda item: (-item.owner_pct, -item.action_pct))
    return people


def _count_in_phases(life: Lifecycle, segments: list[Segment], end: dt.datetime) -> None:
    """Zaehlt Kommentare und Anhaenge je Statusphase.

    Wo diskutiert und belegt wurde, lag die Unklarheit - das ist an der
    Phase ablesbar, nicht an der Gesamtzahl.
    """
    for segment in segments:
        stop = segment.end or end
        for event in life.events:
            if not (segment.start <= event.when < stop):
                continue
            if event.kind == "comment":
                segment.comments += 1
            elif event.kind == "attachment":
                # Ein gebuendeltes Ereignis traegt die Anzahl im Text.
                match = re.match(r"(\d+) Anh", event.text)
                segment.attachments += int(match.group(1)) if match else 1


def _first_reaction(life: Lifecycle) -> lifecycle.Event | None:
    """Findet die erste Handlung einer anderen Person als dem Ersteller."""
    return next(
        (event for event in life.events if event.actor and event.actor != life.reporter),
        None,
    )


def _first_pickup(life: Lifecycle) -> lifecycle.Event | None:
    """Findet die erste echte Zuweisung an eine Person."""
    return next(
        (
            event
            for event in life.events
            if event.kind == "assignee" and event.text.split(" -> ")[-1] not in ("", "(niemand)")
        ),
        None,
    )


def _scope_changes(life: Lifecycle, segments: list[Segment]) -> list[lifecycle.Event]:
    """Sammelt Auftragsaenderungen nach dem ersten Arbeitsbeginn.

    Eine geaenderte Beschreibung vor Arbeitsbeginn ist Praezisierung. Nach
    dem Arbeitsbeginn ist sie eine Aenderung am Auftrag und erklaert
    Nacharbeit.
    """
    started = next((segment.start for segment in segments if segment.active), None)
    if None is started:
        return []
    return [
        event
        for event in life.events
        if event.kind == "field"
        and event.when > started
        and any(f"'{name}'" in event.text for name in SCOPE_FIELDS)
    ]


def _build_metrics(
    life: Lifecycle, segments: list[Segment], start: dt.datetime, now: dt.datetime
) -> list[Metric]:
    """Berechnet die Fluss- und Reibungskennzahlen des Tickets."""
    metrics: list[Metric] = []

    total = sum(segment.gross_seconds for segment in segments)
    active = sum(segment.gross_seconds for segment in segments if segment.active)
    active_names = [segment.status for segment in segments if segment.active]
    if total:
        share = active / total * 100
        metrics.append(
            Metric(
                label="Flow-Effizienz",
                value=f"{share:.0f} %",
                note=(
                    f"{humanize_seconds(active)} in einem arbeitenden Status, "
                    f"{humanize_seconds(total)} insgesamt. Als Arbeit gezählt: "
                    f"{', '.join(sorted(set(active_names))) or 'kein Status'}."
                ),
                tone="work" if share < 50 else "done",
            )
        )

    reaction = _first_reaction(life)
    if reaction:
        gross = (reaction.when - start).total_seconds()
        metrics.append(
            Metric(
                label="Erste Reaktion",
                value=humanize_seconds(gross),
                note=(
                    f"{humanize_seconds(business_seconds(start, reaction.when))} Arbeitszeit. "
                    f"{reaction.actor} am {reaction.when:%d.%m.%Y %H:%M} - {reaction.text}."
                ),
            )
        )
    else:
        metrics.append(
            Metric(label="Erste Reaktion", value="keine",
                   note=f"Bisher hat niemand ausser {life.reporter} etwas am Ticket getan.",
                   tone="warn")
        )

    pickup = _first_pickup(life)
    if pickup:
        metrics.append(
            Metric(
                label="Aufgreifzeit",
                value=humanize_seconds((pickup.when - start).total_seconds()),
                note=(
                    f"{humanize_seconds(business_seconds(start, pickup.when))} Arbeitszeit bis zur "
                    f"ersten Zuweisung ({pickup.text.replace('Zuweisung: ', '')}, "
                    f"{pickup.when:%d.%m.%Y %H:%M})."
                ),
            )
        )
    else:
        metrics.append(
            Metric(label="Aufgreifzeit", value="offen", note="Das Ticket wurde nie zugewiesen.",
                   tone="warn")
        )

    seen: dict[str, int] = {}
    for segment in segments:
        seen[segment.status] = seen.get(segment.status, 0) + 1
    loops = {status: count - 1 for status, count in seen.items() if count > 1}
    loop_total = sum(loops.values())
    metrics.append(
        Metric(
            label="Rework-Schleifen",
            value=str(loop_total),
            note=(
                ", ".join(f"{status} {count + 1}x betreten" for status, count in loops.items())
                if loops
                else "Kein Status wurde ein zweites Mal betreten - das Ticket lief geradeaus durch."
            ),
            tone="warn" if loop_total else "done",
        )
    )

    scope = _scope_changes(life, segments)
    metrics.append(
        Metric(
            label="Auftragsänderungen",
            value=str(len(scope)),
            note=(
                "; ".join(
                    f"{event.text.replace('Feld ', '').replace(' geaendert', '')} durch "
                    f"{event.actor} am {event.when:%d.%m. %H:%M}"
                    for event in scope
                )
                if scope
                else "Titel und Beschreibung blieben nach Arbeitsbeginn unverändert."
            ),
            tone="warn" if scope else "done",
        )
    )

    return metrics


def _build_findings(life: Lifecycle, segments: list[Segment]) -> list[Finding]:
    """Leitet belegbare Beobachtungen ab - ohne Bewertung und ohne Raten."""
    findings: list[Finding] = []

    if segments:
        peak = max(segments, key=lambda item: item.gross_seconds)
        share = peak.net_seconds / peak.gross_seconds * 100 if peak.gross_seconds else 0
        findings.append(
            Finding(
                tone="clock",
                title=f"Längste Phase: {peak.status}",
                text=(
                    f"{peak.gross} nach Kalenderzeit, davon {peak.net} innerhalb der Arbeitszeit "
                    f"(Mo-Fr, {WORK_START_HOUR}-{WORK_END_HOUR} Uhr) - {share:.0f} %. "
                    f"Von {peak.start:%d.%m.%Y %H:%M} bis "
                    + (f"{peak.end:%d.%m.%Y %H:%M}." if peak.end else "jetzt (läuft noch).")
                ),
            )
        )

    for segment in (s for s in segments if s.long):
        findings.append(
            Finding(
                tone="warn",
                title=f"Lange Liegezeit: {segment.status}",
                text=(
                    f"{segment.gross} nach Kalenderzeit, das sind "
                    f"{segment.workdays:.1f} Arbeitstage".replace(".", ",")
                    + f" - ab {LONG_PHASE_WORKDAYS:.0f} gilt eine Phase hier als auffällig. "
                    f"Von {segment.start:%d.%m.%Y %H:%M} bis "
                    + (
                        f"{segment.end:%d.%m.%Y %H:%M}."
                        if segment.end
                        else "jetzt (läuft noch)."
                    )
                ),
            )
        )

    seen: dict[str, int] = {}
    for segment in segments:
        seen[segment.status] = seen.get(segment.status, 0) + 1
    loops = [status for status, count in seen.items() if count > 1]
    if loops:
        findings.append(
            Finding(
                tone="warn",
                title="Status mehrfach durchlaufen",
                text=(
                    f"{', '.join(loops)} wurde mehr als einmal betreten. Das Ticket ist an dieser "
                    "Stelle in eine Schleife zurückgelaufen."
                ),
            )
        )

    clicked = [event for event in life.events if event.kind == "status" and "durchgeklickt" in event.detail]
    for event in clicked:
        findings.append(
            Finding(
                tone="mut",
                title="Workflow nachgezogen",
                text=(
                    f"{event.actor} hat am {event.when:%d.%m.%Y %H:%M} mehrere Status in Folge "
                    f"gesetzt ({event.detail}). Diese Zwischenstufen sind keine echten Phasen und "
                    "zählen hier nicht als Liegezeit."
                ),
            )
        )

    removed = [event for event in life.events if event.kind == "link" and "ENTFERNT" in event.text]
    for event in removed:
        findings.append(
            Finding(
                tone="warn",
                title="Verknüpfung wieder entfernt",
                text=(
                    f"{event.actor} hat am {event.when:%d.%m.%Y %H:%M} eine Verknüpfung gelöst: "
                    f"{event.text.replace('Verknuepfung ENTFERNT: ', '')}. Sie steht nur noch im "
                    "Änderungsprotokoll, nicht mehr am Ticket."
                ),
            )
        )

    handovers = life.handovers()
    if handovers:
        owners = " -> ".join(span.who for span in life.ownership)
        findings.append(
            Finding(
                tone="pine",
                title=f"{handovers} Übergaben",
                text=f"Der Bearbeiter wechselte: {owners}.",
            )
        )

    silence = life.longest_silence()
    if silence:
        when, gap = silence
        net = business_seconds(when, when + gap)
        findings.append(
            Finding(
                tone="mut",
                title="Längste Pause ohne Ereignis",
                text=(
                    f"{humanize(gap)} ab {when:%d.%m.%Y %H:%M}, davon {humanize_seconds(net)} "
                    "innerhalb der Arbeitszeit."
                ),
            )
        )

    last_comment = next((event for event in reversed(life.events) if event.kind == "comment"), None)
    if last_comment and "?" in last_comment.detail:
        findings.append(
            Finding(
                tone="warn",
                title="Letzter Kommentar enthält eine Frage",
                text=(
                    f"{last_comment.actor} am {last_comment.when:%d.%m.%Y %H:%M}: "
                    f'"{last_comment.detail[:150]}" - danach kam kein weiterer Kommentar.'
                ),
            )
        )

    return findings


def build(
    issue: dict[str, Any],
    changelog: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    browse_base: str,
    titles: dict[str, str] | None = None,
) -> Report:
    """Baut aus den Rohdaten eines Tickets das vollstaendige Anzeigemodell.

    Args:
        issue:
            Issue-JSON aus der Jira-API.
        changelog:
            Alle Eintraege der Aenderungshistorie.
        comments:
            Alle Kommentare des Tickets.
        browse_base:
            Basis fuer Ticket-Links, z.B.
            "https://example.atlassian.net/browse".
        titles:
            Titel weiterer erwaehnter Tickets. Parent und echte
            Verknuepfungen bringen ihren Titel selbst mit - fuer nur im Text
            erwaehnte Tickets kann die Anwendung sie hier nachreichen.

    Returns:
        Fertiges Report-Objekt fuer die Darstellung.
    """
    life = lifecycle.from_raw(issue, changelog, comments)

    start = life.created or life.events[0].when
    now = dt.datetime.now(tz=start.tzinfo)
    end = max(life.events[-1].when, now)
    span = (end - start).total_seconds() or 1

    segments = _build_segments(life, start, span, end)
    _count_in_phases(life, segments, end)
    markers = _build_markers(life, start, span)
    metrics = _build_metrics(life, segments, start, now)
    people = _build_people(life)
    findings = _build_findings(life, segments)

    gross_total = (now - start).total_seconds()
    net_total = business_seconds(start, now)
    peak = max(segments, key=lambda item: item.gross_seconds) if segments else None

    stats = [
        ("Laufzeit", humanize_seconds(gross_total)),
        ("davon Arbeitszeit", humanize_seconds(net_total)),
        ("Ereignisse", str(len(life.events))),
        ("Beteiligte", str(len(people))),
        ("Übergaben", str(life.handovers())),
        ("Längste Phase", f"{peak.status} ({peak.gross})" if peak else "-"),
    ]

    offhours = [
        (
            max(0.0, (gap_start - start).total_seconds() / span * 100),
            (gap_end - gap_start).total_seconds() / span * 100,
        )
        for gap_start, gap_end in off_hours(start, end)
    ]

    bekannte_titel = dict(life.titles)
    bekannte_titel.update(titles or {})
    related = []
    for ticket_key, origin in life.mentioned.items():
        related.append(
            {
                "key": ticket_key,
                "origin": origin,
                "summary": bekannte_titel.get(ticket_key, ""),
                "url": f"{browse_base}/{ticket_key}",
            }
        )

    return Report(
        key=life.key,
        summary=life.summary,
        url=f"{browse_base}/{life.key}",
        status=life.current_status,
        status_tone=_tone_for_status(life.current_status),
        issue_type=life.issue_type,
        priority=life.priority,
        reporter=life.reporter,
        assignee=life.assignee,
        parent=life.parent,
        created=start,
        stats=stats,
        markers=markers,
        segments=segments,
        metrics=metrics,
        people=people,
        related=related,
        findings=findings,
        offhours=offhours,
        generated=f"{now:%d.%m.%Y %H:%M}",
    )

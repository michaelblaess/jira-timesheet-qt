"""Lebenszyklus eines Tickets - Changelog, Kommentare und Akteure als Timeline.

Grundlage fuer retro-from-ticket: das Changelog liefert das Rueckgrat
(Status-Uebergaenge, Zuweisungen, Verknuepfungen), die Kommentare die
Aktivitaet. Beides zusammen ergibt eine belegte Zeitleiste plus die
Liegezeit je Status.

Bewusste Grenze: dieses Modul stellt nur fest, WAS wann geschah und WER es
tat. Es bewertet nicht, ob das schnell oder langsam war, und es rankt keine
Personen - Attribution ist keine Personen-KPI.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from . import adf

# Jira liefert Zeitstempel als "2026-07-30T08:55:24.808+0200" - mit Offset,
# aber ohne Doppelpunkt darin. fromisoformat mag das erst ab 3.11, deshalb
# wird der Offset vorher normalisiert.
_TS_OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")

# Ticket-Keys, die in Fliesstext erwaehnt werden (Kommentar, Beschreibung).
_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

# Changelog-Felder, die als eigene Ereignisart in der Timeline auftauchen.
# Alles andere wird als generische Feldaenderung gesammelt.
FIELD_STATUS = "status"
FIELD_ASSIGNEE = "assignee"
FIELD_LINK = "Link"
FIELD_ATTACHMENT = "Attachment"
FIELD_PARENT = "IssueParentAssociation"

# Rollen, die ein Akteur im Ticket eingenommen haben kann.
ROLE_REPORTER = "Ersteller"
ROLE_ASSIGNEE = "Bearbeiter"
ROLE_COMMENTER = "Kommentar"
ROLE_MOVER = "Statuswechsel"
ROLE_EDITOR = "Feldaenderung"

# Feldaenderungen werden nur bis zu dieser Gesamtlaenge im Klartext gezeigt.
MAX_FIELD_PREVIEW = 120

# Folgen aufeinanderfolgender Status-Wechsel derselben Person innerhalb
# dieser Zeitspanne sind Durchklicken durch den Workflow, keine echten
# Phasen. Sie werden zu einem Uebergang zusammengefasst.
CLICK_THROUGH_SECONDS = 120

# Laenge der Kommentar-Vorschau in der Zeitleiste.
COMMENT_PREVIEW = 150

# Zeilen, die als blosse Anrede oder Gruss gelten und in der Vorschau
# uebersprungen werden. Die Laengengrenze ist entscheidend: "Hallo @Name"
# ist Fueller, "Hallo @Name, ich habe die Komponente gebaut ..." nicht.
_FILLER = re.compile(r"^(hallo|hi|guten (morgen|tag)|moin|servus|danke|vielen dank|lg|viele gr)", re.IGNORECASE)
FILLER_MAX_LEN = 60


def parse_ts(raw: str | None) -> dt.datetime | None:
    """Wandelt einen Jira-Zeitstempel in ein datetime mit Zeitzone.

    Args:
        raw:
            Rohwert aus der API, z.B. "2026-07-30T08:55:24.808+0200".

    Returns:
        Zeitzonenbehaftetes datetime oder None, wenn nichts parsbar war.
    """
    if not raw:
        return None
    text = _TS_OFFSET.sub(r"\1:\2", raw.strip())
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def humanize(delta: dt.timedelta) -> str:
    """Formatiert eine Dauer als kurzen deutschen Lesertext."""
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} h".replace(".", ",")
    days = hours / 24
    return f"{days:.1f} Tage".replace(".", ",")


@dataclass
class Event:
    """Ein einzelnes belegtes Ereignis im Lebenszyklus."""

    when: dt.datetime
    kind: str
    actor: str
    text: str
    detail: str = ""


@dataclass
class Ownership:
    """Zeitraum, in dem eine Person das Ticket zugewiesen hatte."""

    who: str
    start: dt.datetime
    end: dt.datetime | None

    @property
    def duration(self) -> dt.timedelta:
        """Besitzzeit - bei laufendem Zeitraum bis jetzt."""
        end = self.end or dt.datetime.now(tz=self.start.tzinfo)
        return end - self.start


@dataclass
class StatusSpan:
    """Eine Phase, in der das Ticket in genau einem Status stand."""

    status: str
    start: dt.datetime
    end: dt.datetime | None
    open_ended: bool = False

    @property
    def duration(self) -> dt.timedelta:
        """Liegezeit in diesem Status - bei laufender Phase bis jetzt."""
        end = self.end or dt.datetime.now(tz=self.start.tzinfo)
        return end - self.start


@dataclass
class Actor:
    """Eine am Ticket beteiligte Person mit ihren belegten Rollen."""

    name: str
    roles: set[str] = field(default_factory=set)
    comments: int = 0
    changes: int = 0
    first_seen: dt.datetime | None = None
    last_seen: dt.datetime | None = None

    def touch(self, when: dt.datetime | None) -> None:
        """Schreibt den Zeitraum fort, in dem die Person aktiv war."""
        if None is when:
            return
        if None is self.first_seen or when < self.first_seen:
            self.first_seen = when
        if None is self.last_seen or when > self.last_seen:
            self.last_seen = when


@dataclass
class Lifecycle:
    """Vollstaendig eingelesener Lebenszyklus eines Tickets."""

    key: str
    summary: str
    issue_type: str
    priority: str
    created: dt.datetime | None
    updated: dt.datetime | None
    current_status: str
    reporter: str
    assignee: str
    parent: str
    events: list[Event] = field(default_factory=list)
    spans: list[StatusSpan] = field(default_factory=list)
    ownership: list[Ownership] = field(default_factory=list)
    actors: dict[str, Actor] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    mentioned: dict[str, str] = field(default_factory=dict)

    @property
    def total_age(self) -> dt.timedelta | None:
        """Gesamtlaufzeit von der Anlage bis jetzt."""
        if None is self.created:
            return None
        return dt.datetime.now(tz=self.created.tzinfo) - self.created

    def bottleneck(self) -> StatusSpan | None:
        """Liefert die Phase mit der laengsten Liegezeit."""
        return max(self.spans, key=lambda span: span.duration) if self.spans else None

    def ownership_share(self) -> list[tuple[str, dt.timedelta, float]]:
        """Besitzzeit je Person, absteigend, mit Anteil an der Laufzeit.

        Beantwortet "wer hatte den Ball wie lange" - im Gegensatz zur
        Aktionszahl misst das Verantwortung, nicht Betriebsamkeit.
        """
        totals: dict[str, dt.timedelta] = {}
        for span in self.ownership:
            totals[span.who] = totals.get(span.who, dt.timedelta()) + span.duration
        overall = sum(totals.values(), dt.timedelta())
        if not overall:
            return []
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        return [(who, span, span / overall * 100) for who, span in ranked]

    def action_share(self) -> list[tuple[str, int, float]]:
        """Aktionen je Person (Kommentare plus Aenderungen) mit Anteil."""
        totals = {actor.name: actor.comments + actor.changes for actor in self.actors.values()}
        totals = {name: count for name, count in totals.items() if count}
        overall = sum(totals.values())
        if not overall:
            return []
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        return [(name, count, count / overall * 100) for name, count in ranked]

    def handovers(self) -> int:
        """Anzahl der Zuweisungswechsel - ein Mass fuer Reibung im Ablauf."""
        return max(0, len(self.ownership) - 1)

    def longest_silence(self) -> tuple[dt.datetime, dt.timedelta] | None:
        """Findet die laengste Strecke ganz ohne Ereignis."""
        if len(self.events) < 2:
            return None
        gaps = [
            (self.events[index].when, self.events[index + 1].when - self.events[index].when)
            for index in range(len(self.events) - 1)
        ]
        return max(gaps, key=lambda item: item[1])


def _actor(store: dict[str, Actor], name: str, role: str, when: dt.datetime | None) -> Actor:
    """Legt einen Akteur an oder ergaenzt Rolle und Zeitraum."""
    entry = store.setdefault(name, Actor(name=name))
    entry.roles.add(role)
    entry.touch(when)
    return entry


def _preview(body: str) -> str:
    """Baut eine aussagekraeftige Kurzvorschau eines Kommentars.

    Reine Anreden ("Hallo @Name") werden uebersprungen - sonst steht in der
    Zeitleiste bei jedem zweiten Eintrag nur eine Begruessung.
    """
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    meaningful = [
        line for line in lines if not (len(line) <= FILLER_MAX_LEN and _FILLER.match(line))
    ] or lines
    return " ".join(meaningful)[:COMMENT_PREVIEW]


def _collect_keys(text: str, into: dict[str, str], origin: str) -> None:
    """Sammelt Ticket-Keys aus Fliesstext samt Fundstelle."""
    for key in _KEY_PATTERN.findall(text or ""):
        into.setdefault(key, origin)


def from_raw(
    issue: dict[str, Any],
    changelog: list[dict[str, Any]],
    comments: list[dict[str, Any]],
) -> Lifecycle:
    """Baut den Lebenszyklus aus den Rohdaten der Jira-API.

    Bewusst ohne Client-Abhaengigkeit: jede Anwendung bringt ihren eigenen
    Zugang mit und reicht hier nur die drei Antworten herein.

    Args:
        issue:
            Issue-JSON aus ``GET /rest/api/3/issue/<key>``.
        changelog:
            Eintraege aus ``GET /rest/api/3/issue/<key>/changelog``
            (Feld ``values``, ueber alle Seiten).
        comments:
            Kommentare aus ``GET /rest/api/3/issue/<key>/comment``
            (Feld ``comments``).

    Returns:
        Gefuelltes Lifecycle-Objekt mit Ereignissen, Phasen und Akteuren.
    """
    key = str(issue.get("key", ""))
    fields = issue.get("fields") or {}

    created = parse_ts(fields.get("created"))
    life = Lifecycle(
        key=issue.get("key", key),
        summary=fields.get("summary", ""),
        issue_type=adf.field_to_text(fields.get("issuetype")),
        priority=adf.field_to_text(fields.get("priority")),
        created=created,
        updated=parse_ts(fields.get("updated")),
        current_status=adf.field_to_text(fields.get("status")),
        reporter=adf.field_to_text(fields.get("reporter")),
        assignee=adf.field_to_text(fields.get("assignee")),
        parent="",
    )

    parent = fields.get("parent")
    if parent:
        parent_summary = (parent.get("fields") or {}).get("summary", "")
        life.parent = f"{parent.get('key')} - {parent_summary}"
        life.mentioned.setdefault(str(parent.get("key")), "Parent (Epic)")

    for link in fields.get("issuelinks") or []:
        outward = "outwardIssue" in link
        other = link.get("outwardIssue") or link.get("inwardIssue") or {}
        relation = (link.get("type") or {}).get("outward" if outward else "inward", "?")
        summary = (other.get("fields") or {}).get("summary", "")
        life.links.append(f"{relation}: {other.get('key')} - {summary}")
        life.mentioned.setdefault(str(other.get("key")), f"Verknuepfung ({relation})")

    _collect_keys(adf.field_to_text(fields.get("description")), life.mentioned, "Beschreibung")

    if life.reporter:
        _actor(life.actors, life.reporter, ROLE_REPORTER, created)
    if created:
        life.events.append(
            Event(when=created, kind="created", actor=life.reporter, text=f"{life.key} angelegt", detail=life.summary)
        )

    _add_changelog(changelog, life)
    _add_comments(comments, life)

    life.events.sort(key=lambda event: event.when)
    life.events = _collapse_click_through(life.events)
    life.events = _collapse_attachments(life.events)
    life.spans = _spans(life)
    life.ownership = _ownership(life)
    return life


def _collapse_click_through(events: list[Event]) -> list[Event]:
    """Fasst durchgeklickte Status-Ketten zu einem Uebergang zusammen.

    Wer den Workflow nachzieht, erzeugt mehrere Wechsel in Sekunden. Fuer
    die Auswertung zaehlt nur der Zielstatus - die Zwischenstufen werden im
    Detail als "durchgeklickt" ausgewiesen, damit nichts verschwindet.

    Args:
        events:
            Chronologisch sortierte Ereignisliste.

    Returns:
        Neue Liste, in der Klick-Ketten je ein Ereignis belegen.
    """
    status_events = [event for event in events if event.kind == "status"]
    if len(status_events) < 2:
        return events

    chains: list[list[Event]] = [[status_events[0]]]
    for event in status_events[1:]:
        previous = chains[-1][-1]
        same_person = event.actor == previous.actor
        quick = (event.when - previous.when).total_seconds() <= CLICK_THROUGH_SECONDS
        if same_person and quick:
            chains[-1].append(event)
        else:
            chains.append([event])

    merged: dict[int, Event] = {}
    dropped: set[int] = set()
    for chain in chains:
        if len(chain) < 2:
            continue
        first, last = chain[0], chain[-1]
        source = first.text.split(" -> ")[0]
        target = last.text.split(" -> ")[-1]
        skipped = [item.text.split(" -> ")[-1] for item in chain[:-1]]
        merged[id(first)] = Event(
            when=first.when,
            kind="status",
            actor=first.actor,
            text=f"{source} -> {target}",
            detail=f"durchgeklickt in {humanize(last.when - first.when)}: {', '.join(skipped)}",
        )
        dropped |= {id(item) for item in chain[1:]}

    return [merged.get(id(event), event) for event in events if id(event) not in dropped]


def _collapse_attachments(events: list[Event]) -> list[Event]:
    """Fasst Anhaenge derselben Person aus derselben Minute zusammen.

    Ein Kommentar mit fuenf Screenshots erzeugt fuenf Changelog-Eintraege.
    Auf der Zeitachse ist das ein Ereignis.
    """
    result: list[Event] = []
    bucket: list[Event] = []

    def flush() -> None:
        if not bucket:
            return
        if len(bucket) == 1:
            result.append(bucket[0])
        else:
            names = [item.text.replace("Anhang: ", "") for item in bucket]
            result.append(
                Event(
                    when=bucket[0].when,
                    kind="attachment",
                    actor=bucket[0].actor,
                    text=f"{len(bucket)} Anhaenge",
                    detail=", ".join(names),
                )
            )
        bucket.clear()

    for event in events:
        if event.kind != "attachment":
            flush()
            result.append(event)
            continue
        if bucket and (event.actor != bucket[0].actor or (event.when - bucket[0].when).total_seconds() > 60):
            flush()
        bucket.append(event)

    flush()
    return result


def _ownership(life: Lifecycle) -> list[Ownership]:
    """Leitet aus den Zuweisungen ab, wer das Ticket wann in der Hand hatte."""
    changes = [event for event in life.events if event.kind == "assignee"]
    start = life.created
    if None is start:
        return []

    spans: list[Ownership] = []
    if changes:
        first_owner = changes[0].text.replace("Zuweisung: ", "").split(" -> ")[0]
        if first_owner and first_owner != "(niemand)":
            spans.append(Ownership(first_owner, start, changes[0].when))
        for index, event in enumerate(changes):
            owner = event.text.split(" -> ")[-1]
            end = changes[index + 1].when if index + 1 < len(changes) else None
            if owner and owner != "(niemand)":
                spans.append(Ownership(owner, event.when, end))
    elif life.assignee:
        spans.append(Ownership(life.assignee, start, None))

    return spans


def _add_changelog(entries: list[dict[str, Any]], life: Lifecycle) -> None:
    """Haengt alle Changelog-Eintraege als Ereignisse an."""
    for entry in entries:
        when = parse_ts(entry.get("created"))
        if None is when:
            continue
        who = (entry.get("author") or {}).get("displayName", "?")

        for item in entry.get("items") or []:
            field_name = item.get("field", "")
            old = item.get("fromString") or ""
            new = item.get("toString") or ""

            if field_name == FIELD_STATUS:
                _actor(life.actors, who, ROLE_MOVER, when).changes += 1
                life.events.append(Event(when, "status", who, f"{old} -> {new}"))
            elif field_name == FIELD_ASSIGNEE:
                _actor(life.actors, who, ROLE_EDITOR, when).changes += 1
                if new:
                    _actor(life.actors, new, ROLE_ASSIGNEE, when)
                life.events.append(Event(when, "assignee", who, f"Zuweisung: {old or '(niemand)'} -> {new or '(niemand)'}"))
            elif field_name in (FIELD_LINK, FIELD_PARENT):
                _actor(life.actors, who, ROLE_EDITOR, when).changes += 1
                # Ein entferntes Link-Item hat toString=None - das ist die
                # Spur einer geloesten Verknuepfung und bleibt sichtbar.
                removed = bool(old) and not new
                if field_name == FIELD_PARENT:
                    text = f"Parent gesetzt: {new or old}"
                elif removed:
                    text = f"Verknuepfung ENTFERNT: {old}"
                else:
                    text = f"Verknuepfung: {new or old}"
                life.events.append(Event(when, "link", who, text))
                _collect_keys(f"{old} {new}", life.mentioned, "Changelog-Verknuepfung")
            elif field_name == FIELD_ATTACHMENT:
                _actor(life.actors, who, ROLE_EDITOR, when).changes += 1
                life.events.append(Event(when, "attachment", who, f"Anhang: {new or old}"))
            else:
                _actor(life.actors, who, ROLE_EDITOR, when).changes += 1
                # Kurze Werte (Titel, Prioritaet) direkt zeigen - lange Texte
                # wie eine Beschreibung wuerden die Zeitleiste zumuellen.
                short = len(old) + len(new) <= MAX_FIELD_PREVIEW
                detail = f"{old or '(leer)'} -> {new or '(leer)'}" if short else ""
                life.events.append(Event(when, "field", who, f"Feld '{field_name}' geaendert", detail))


def _add_comments(comments: list[dict[str, Any]], life: Lifecycle) -> None:
    """Haengt alle Kommentare als Ereignisse an und sammelt erwaehnte Tickets."""
    for index, comment in enumerate(comments, start=1):
        when = parse_ts(comment.get("created"))
        if None is when:
            continue
        who = (comment.get("author") or {}).get("displayName", "?")
        _actor(life.actors, who, ROLE_COMMENTER, when).comments += 1

        body = adf.field_to_text(comment.get("body"))
        life.events.append(Event(when, "comment", who, f"Kommentar [{index}]", _preview(body)))
        _collect_keys(body, life.mentioned, f"Kommentar [{index}] ({who})")

    life.mentioned.pop(life.key, None)


def _spans(life: Lifecycle) -> list[StatusSpan]:
    """Leitet aus den Status-Ereignissen die Liegezeit je Phase ab.

    Der erste Status ergibt sich aus dem fromString des ersten Wechsels -
    das ist der Anlage-Status, den das Changelog selbst nicht als Ereignis
    fuehrt.
    """
    changes = [event for event in life.events if event.kind == "status"]
    if not changes:
        if None is life.created:
            return []
        return [StatusSpan(life.current_status, life.created, None, open_ended=True)]

    first_from = changes[0].text.split(" -> ")[0]
    start = life.created or changes[0].when
    spans = [StatusSpan(first_from, start, changes[0].when)]

    for index, event in enumerate(changes):
        target = event.text.split(" -> ")[-1]
        end = changes[index + 1].when if index + 1 < len(changes) else None
        spans.append(StatusSpan(target, event.when, end, open_ended=None is end))

    return spans

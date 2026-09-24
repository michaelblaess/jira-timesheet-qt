"""Ticket-Vorschau: Daten, Abbildung aus dem Jira-JSON und Cache.

Oberflaechenfrei - die Vorschau im Stundenzettel zeigt, was hier entsteht.
Der Abruf selbst steht im JiraClient, der Ablauf im Worker.

Welche Zusatzfelder (Environments, Team, ...) gezeigt werden, steht bewusst
nicht im Code: Feldnamen und ihre customfield-Nummern sind je Jira-Instanz
verschieden. Die Namen kommen aus den Einstellungen, die Nummern ermittelt
die Anwendung ueber die Feldliste und merkt sie sich im Cache.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jira_timesheet_qt.services.ticket_report import adf

logger = logging.getLogger(__name__)

# Standardfelder, die jede Jira-Instanz kennt. Die Zusatzfelder kommen dazu.
BASE_FIELDS: tuple[str, ...] = (
    "summary",
    "status",
    "issuetype",
    "priority",
    "assignee",
    "creator",
    "duedate",
    "updated",
    "parent",
    "description",
    # In Jira "Zeiterfassung": die gebuchte Zeit des Tickets in Sekunden.
    "timespent",
    "timeoriginalestimate",
    # In Jira "Loesungsversionen".
    "fixVersions",
)

# Nur solche Schluessel landen als Dateiname im Cache - ein Wert wie
# "../x" darf nie einen Pfad ausserhalb des Cache-Verzeichnisses bilden.
_KEY_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*-\d+")
_FIELD_IDS_FILE = "_fields.json"

# Fassung der Cache-Dateien. Hochzaehlen, sobald neue Felder dazukommen: die
# Pruefung auf Aenderungen vergleicht nur updated und die gebuchte Zeit, ein
# alter Eintrag ohne das neue Feld bliebe sonst dauerhaft ohne es.
CACHE_SCHEMA = 6

# Statuskategorien, die Jira an jedem Status mitliefert (statusCategory.key).
STATUS_CATEGORIES = frozenset({"new", "indeterminate", "done"})

# Bilder der Beschreibung: hoechstens so viele je Ticket und so gross je Bild.
MAX_IMAGES = 20
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_IMAGE_TYPES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_ATTR = re.compile(r'\b(src|alt)\s*=\s*"([^"]*)"', re.IGNORECASE)


@dataclass
class TicketPreviewData:
    """Was die Vorschau von einem Ticket zeigt."""

    key: str
    summary: str = ""
    status: str = ""
    # Kategorie des Status: new, indeterminate oder done - faerbt das Etikett.
    status_category: str = ""
    issue_type: str = ""
    priority: str = ""
    assignee: str = ""
    creator: str = ""
    # accountId zu Bearbeiter und Autor, leer wenn unbekannt. Darueber fuehrt
    # die Vorschau zu "Mein Team" - der Name allein trifft nicht sicher.
    assignee_id: str = ""
    creator_id: str = ""
    # Roh aus Jira (ISO), die Oberflaeche formatiert.
    due_date: str = ""
    updated: str = ""
    parent: str = ""
    # Gebuchte Zeit und urspruengliche Schaetzung in Sekunden, 0 = keine.
    time_spent_seconds: int = 0
    original_estimate_seconds: int = 0
    # Loesungsversionen, mit Komma verbunden.
    fix_versions: str = ""
    # Zusatzfelder in der Reihenfolge der Einstellungen: (Feldname, Wert).
    extra: list[tuple[str, str]] = field(default_factory=list)
    # Schaetzung aus dem Story-Points-Feld der Einstellungen, None = keine.
    story_points: float | None = None
    description_html: str = ""
    # Bildadresse aus dem Jira-HTML -> Dateiname im Bildordner des Tickets.
    images: dict[str, str] = field(default_factory=dict)
    # Wann abgerufen (ISO, lokale Zeit) - die Vorschau zeigt den Stand an.
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Fuer die Cache-Datei, mit Fassungsnummer."""
        data = asdict(self)
        data["schema"] = CACHE_SCHEMA
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TicketPreviewData:
        """Aus der Cache-Datei. JSON kennt keine Tupel - die Paare kommen als Listen."""
        extra = [
            (str(pair[0]), str(pair[1]))
            for pair in data.get("extra", [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        bilder = data.get("images")
        images = {str(k): str(v) for k, v in bilder.items()} if isinstance(bilder, dict) else {}
        return TicketPreviewData(
            key=str(data["key"]),
            summary=str(data.get("summary", "")),
            status=str(data.get("status", "")),
            status_category=str(data.get("status_category", "")),
            issue_type=str(data.get("issue_type", "")),
            priority=str(data.get("priority", "")),
            assignee=str(data.get("assignee", "")),
            creator=str(data.get("creator", "")),
            assignee_id=str(data.get("assignee_id", "")),
            creator_id=str(data.get("creator_id", "")),
            due_date=str(data.get("due_date", "")),
            updated=str(data.get("updated", "")),
            parent=str(data.get("parent", "")),
            time_spent_seconds=seconds_value(data.get("time_spent_seconds")),
            original_estimate_seconds=seconds_value(data.get("original_estimate_seconds")),
            fix_versions=str(data.get("fix_versions", "")),
            extra=extra,
            story_points=points_value(data.get("story_points")),
            description_html=str(data.get("description_html", "")),
            images=images,
            fetched_at=str(data.get("fetched_at", "")),
        )


def parse_extra_field_names(text: str) -> list[str]:
    """Liest die Zusatzfelder aus der Eingabe: kommagetrennt, doppelte fallen weg."""
    names: list[str] = []
    for part in text.split(","):
        name = part.strip()
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return names


def resolve_field_ids(fields: Sequence[dict[str, Any]], names: Sequence[str]) -> dict[str, str]:
    """Ordnet Feldnamen ihre ID zu.

    Verglichen wird ohne Gross- und Kleinschreibung, aber ganz: "Team" trifft
    nicht "Team[Single]". Viele Instanzen fuehren aehnlich benannte Felder
    nebeneinander, ein Teiltreffer wuerde dann das falsche zeigen.

    Returns:
        Name (wie in den Einstellungen) -> Feld-ID, in der Reihenfolge der
        Namen. Nicht gefundene Namen fehlen.
    """
    by_name: dict[str, str] = {}
    for item in fields:
        name = str(item.get("name", "")).strip().lower()
        field_id = str(item.get("id", ""))
        if name and field_id and name not in by_name:
            by_name[name] = field_id
    return {name: by_name[name.strip().lower()] for name in names if name.strip().lower() in by_name}


def field_value_text(value: Any) -> str:
    """Macht aus einem Jira-Feldwert einen kurzen Text.

    Personen tragen displayName, Status und Teams name, Auswahlfelder value.
    Mehrfachauswahlen werden mit Komma verbunden.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(text for text in (field_value_text(item) for item in value) if text)
    if isinstance(value, dict):
        for attribute in ("displayName", "name", "value", "key"):
            text = value.get(attribute)
            if isinstance(text, str) and text:
                return text
    return ""


def person_id(value: Any) -> str:
    """Die accountId aus einem Personenfeld, leer ohne Person oder Kennung.

    Ungeprueft: wer die Kennung in eine Abfrage gibt, prueft sie dort.
    """
    if not isinstance(value, dict):
        return ""
    account_id = value.get("accountId")
    return account_id if isinstance(account_id, str) else ""


def _description_html(fields: dict[str, Any], rendered: dict[str, Any]) -> str:
    """Die Beschreibung als HTML.

    Bevorzugt das fertige HTML aus renderedFields. Fehlt es (aeltere Instanz,
    Abruf ohne expand), wird der Text aus dem Jira-Dokumentformat escaped und
    in Absaetze gesetzt - lieber schlicht als gar nicht.
    """
    fertig = rendered.get("description")
    if isinstance(fertig, str) and fertig.strip():
        return fertig
    text = adf.to_text(fields.get("description")).strip()
    if not text:
        return ""
    absaetze = [a for a in re.split(r"\n\s*\n", text) if a.strip()]
    return "".join(f"<p>{html.escape(a.strip()).replace(chr(10), '<br>')}</p>" for a in absaetze)


def status_category(value: Any) -> str:
    """Die Kategorie eines Status aus Jira, oder "" wenn sie fehlt oder unbekannt ist.

    Die Farbe haengt an der Kategorie, nicht am Namen: Statusnamen sind je
    Instanz verschieden, die drei Kategorien fuehrt jede Jira-Instanz.
    """
    if not isinstance(value, dict):
        return ""
    kategorie = value.get("statusCategory")
    key = kategorie.get("key") if isinstance(kategorie, dict) else None
    return key if isinstance(key, str) and key in STATUS_CATEGORIES else ""


def points_value(value: Any) -> float | None:
    """Liest eine Schaetzung. Null und Unlesbares zaehlen als keine."""
    try:
        points = float(value)
    except (TypeError, ValueError):
        return None
    return points if points > 0 else None


def parse_issue(
    raw: dict[str, Any], field_ids: dict[str, str], fetched_at: datetime, points_field: str = ""
) -> TicketPreviewData:
    """Baut die Vorschau-Daten aus der Jira-Antwort.

    Args:
        raw:
            Die Antwort von /rest/api/{version}/issue/{key}.
        field_ids:
            Zusatzfelder als Name -> ID (siehe resolve_field_ids).
        fetched_at:
            Zeitpunkt des Abrufs.
        points_field:
            Feld-ID der Story Points, leer = ohne.
    """
    fields = raw.get("fields") or {}
    rendered = raw.get("renderedFields") or {}

    parent_raw = fields.get("parent")
    parent = ""
    if isinstance(parent_raw, dict):
        parent_summary = field_value_text((parent_raw.get("fields") or {}).get("summary"))
        parent = f"{parent_raw.get('key', '')} {parent_summary}".strip()

    return TicketPreviewData(
        key=str(raw.get("key", "")),
        summary=field_value_text(fields.get("summary")),
        status=field_value_text(fields.get("status")),
        status_category=status_category(fields.get("status")),
        issue_type=field_value_text(fields.get("issuetype")),
        priority=field_value_text(fields.get("priority")),
        assignee=field_value_text(fields.get("assignee")),
        creator=field_value_text(fields.get("creator")),
        assignee_id=person_id(fields.get("assignee")),
        creator_id=person_id(fields.get("creator")),
        due_date=field_value_text(fields.get("duedate")),
        updated=field_value_text(fields.get("updated")),
        parent=parent,
        time_spent_seconds=seconds_value(fields.get("timespent")),
        original_estimate_seconds=seconds_value(fields.get("timeoriginalestimate")),
        fix_versions=field_value_text(fields.get("fixVersions")),
        extra=[(name, field_value_text(fields.get(field_id))) for name, field_id in field_ids.items()],
        story_points=points_value(fields.get(points_field)) if points_field else None,
        description_html=_description_html(fields, rendered),
        fetched_at=fetched_at.isoformat(timespec="seconds"),
    )


def german_date(iso: str) -> str:
    """'2026-09-30' oder ein ISO-Zeitstempel -> '30.09.2026'. Unlesbares bleibt stehen."""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso


def german_datetime(iso: str) -> str:
    """ISO-Zeitstempel -> '14.09.2026 15:03'. Ohne Uhrzeit nur das Datum."""
    datum = german_date(iso)
    uhrzeit = iso[11:16] if len(iso) >= 16 and iso[10] in "T " else ""
    return f"{datum} {uhrzeit}".strip()


# Ab wie vielen Werktagen vor der Faelligkeit die Vorschau warnt. Gezaehlt
# werden Montag bis Freitag, Feiertage nicht - dafuer braeuchte die Vorschau
# das Bundesland aus den Einstellungen.
DUE_SOON_WORKDAYS = 3

# Jira fuehrt "None" als eigene Prioritaet fuer "keine gesetzt".
_EMPTY_PRIORITIES = frozenset({"", "none"})

_TIMESTAMP_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")


def is_empty_priority(priority: str) -> bool:
    """True, wenn die Prioritaet nichts aussagt: leer oder Jiras "None"."""
    return priority.strip().casefold() in _EMPTY_PRIORITIES


def due_state(due_iso: str, today: date) -> str:
    """Wie dringend eine Faelligkeit ist.

    Args:
        due_iso:
            Faelligkeitsdatum aus Jira ('2026-09-30'), leer ohne Faelligkeit.
        today:
            Bezugstag.

    Returns:
        'overdue' vor dem Bezugstag, 'soon' bis DUE_SOON_WORKDAYS Werktage
        danach, sonst ''.
    """
    if not due_iso:
        return ""
    try:
        due = datetime.strptime(due_iso[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    if due < today:
        return "overdue"
    workdays = 0
    day = today
    while day < due:
        day += timedelta(days=1)
        if day.weekday() < 5:
            workdays += 1
            if workdays > DUE_SOON_WORKDAYS:
                return ""
    return "soon"


def relative_time(iso: str, now: datetime) -> str:
    """Abstand eines Zeitstempels zu jetzt in Worten: 'vor 6 Std.', 'vor 3 Tagen'.

    Unlesbares, Zukuenftiges und alles ab 30 Tagen steht als Datum da.
    """
    moment: datetime | None = None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            moment = datetime.strptime(iso, fmt)
            break
        except ValueError:
            continue
    if moment is None:
        return german_datetime(iso)
    if moment.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone()
    elif moment.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 0:
        # Geht die Uhr des Rechners nach, lieber das Datum als "vor -3 Min.".
        return german_datetime(iso)
    if minutes < 1:
        return "gerade eben"
    if minutes < 60:
        return f"vor {minutes} Min."
    hours = minutes // 60
    if hours < 24:
        return f"vor {hours} Std."
    days = hours // 24
    if days == 1:
        return "vor 1 Tag"
    if days < 30:
        return f"vor {days} Tagen"
    return german_date(iso)


def split_parent(parent: str) -> tuple[str, str]:
    """'ABC-1 Titel' -> ('ABC-1', 'Titel'). Ohne Schluessel vorn: ('', parent)."""
    match = _KEY_PATTERN.match(parent)
    if match is None:
        return "", parent
    return match.group(0), parent[match.end() :].strip()


def seconds_value(value: Any) -> int:
    """Eine Sekundenangabe aus Jira. None, Unlesbares und Negatives ergeben 0."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def hours_text(seconds: int) -> str:
    """Sekunden als Stunden mit zwei Nachkommastellen: 9000 -> '2,50 h'."""
    return f"{seconds / 3600:.2f} h".replace(".", ",")


def _img_attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): html.unescape(m.group(2)) for m in _IMG_ATTR.finditer(tag)}


def image_sources(description_html: str, host: str) -> list[str]:
    """Die Bildadressen der Beschreibung, die zum Jira-Host gehoeren.

    Nur diese werden mit Anmeldung geholt - die Zugangsdaten gehen nie an eine
    fremde Adresse. Bilder anderer Hosts bleiben unberuehrt und werden spaeter
    zum Hinweis.

    Returns:
        Die Adressen ohne Doppelte, hoechstens MAX_IMAGES.
    """
    eigener = urlparse(host).netloc.lower()
    quellen: list[str] = []
    for tag in _IMG_TAG.findall(description_html):
        src = _img_attrs(tag).get("src", "")
        netloc = urlparse(src).netloc.lower()
        eigen = netloc == eigener if netloc else src.startswith("/")
        if src and eigener and eigen and src not in quellen:
            quellen.append(src)
    return quellen[:MAX_IMAGES]


def rewrite_images(description_html: str, local: dict[str, str]) -> str:
    """Setzt geladene Bilder auf ihre Datei im Cache, alle anderen auf einen Hinweis.

    Breite, Hoehe und style fallen weg: die Vorschau skaliert selbst auf ihre
    Breite. Jira setzt dort Werte fuer die eigene Oberflaeche, in der
    schmaleren Vorschau stand ein Bild sonst weit ueber den Rand hinaus.
    """

    def ersetzen(treffer: re.Match[str]) -> str:
        attrs = _img_attrs(treffer.group(0))
        name = local.get(attrs.get("src", ""))
        alt = attrs.get("alt", "")
        if name:
            return f'<img src="{html.escape(name)}" alt="{html.escape(alt)}">'
        return f"<i>[Bild{': ' + html.escape(alt) if alt else ''}]</i>"

    return _IMG_TAG.sub(ersetzen, description_html)


def image_file_name(src: str, content_type: str) -> str | None:
    """Dateiname fuer ein Bild: Hash der Adresse plus Endung zum Typ. Unbekannter Typ -> None."""
    endung = _IMAGE_TYPES.get(content_type.split(";")[0].strip().lower())
    if endung is None:
        return None
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:20] + endung


def image_folder(root: Path, key: str) -> Path | None:
    """Der Bildordner eines Tickets unter dem Cache des Hosts, oder None bei unsauberem Schluessel."""
    if not _KEY_PATTERN.fullmatch(key):
        return None
    return root / f"{key.upper()}.files"


def _host_slug(host: str) -> str:
    """Verzeichnisname fuer einen Jira-Host - Tickets zweier Instanzen mischen sich nie."""
    netloc = urlparse(host).netloc or host
    slug = re.sub(r"[^a-z0-9.-]+", "_", netloc.lower()).strip("._")
    return slug or "unbekannt"


class IssuePreviewCache:
    """Merkt sich abgerufene Tickets als JSON-Datei je Ticket.

    Bewusst eine Instanz mit Wurzelpfad statt einer statischen Klasse mit
    festem Pfad: die Anwendung reicht das Verzeichnis zur Laufzeit herein,
    und Tests koennen es nicht versehentlich mit den echten Daten teilen.
    """

    def __init__(self, root: Path, host: str) -> None:
        self._dir = root / _host_slug(host)

    @property
    def directory(self) -> Path:
        """Das Verzeichnis dieses Hosts."""
        return self._dir

    def _path(self, key: str) -> Path | None:
        if not _KEY_PATTERN.fullmatch(key):
            return None
        return self._dir / f"{key.upper()}.json"

    def load(self, key: str) -> TicketPreviewData | None:
        """Der gemerkte Stand, oder None - auch bei einer kaputten Datei."""
        path = self._path(key)
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != CACHE_SCHEMA:
                # Aeltere Fassung: neu laden statt mit fehlenden Feldern anzeigen.
                return None
            return TicketPreviewData.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Vorschau-Cache %s nicht lesbar: %s", path, exc)
            return None

    def save(self, data: TicketPreviewData) -> None:
        """Schreibt den Stand. Ein Fehler beim Schreiben kostet nur den naechsten Abruf."""
        path = self._path(data.key)
        if path is None:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data.to_dict(), ensure_ascii=False), encoding="utf-8", newline="\n")
        except OSError as exc:
            logger.warning("Vorschau-Cache %s nicht schreibbar: %s", path, exc)

    def load_field_ids(self, names: Sequence[str]) -> dict[str, str] | None:
        """Die gemerkten Feld-IDs - nur, wenn sie fuer genau diese Namen ermittelt wurden."""
        path = self._dir / _FIELD_IDS_FILE
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("names") != list(names):
            return None
        ids = data.get("ids")
        return {str(k): str(v) for k, v in ids.items()} if isinstance(ids, dict) else None

    def save_field_ids(self, names: Sequence[str], ids: dict[str, str]) -> None:
        """Merkt sich die ermittelten Feld-IDs zu diesen Namen."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            (self._dir / _FIELD_IDS_FILE).write_text(
                json.dumps({"names": list(names), "ids": ids}, ensure_ascii=False), encoding="utf-8", newline="\n"
            )
        except OSError as exc:
            logger.warning("Feld-IDs nicht schreibbar: %s", exc)

    def save_image(self, key: str, src: str, data: bytes, content_type: str) -> str | None:
        """Legt ein Bild in den Bildordner des Tickets.

        Returns:
            Der Dateiname, oder None bei unbekanntem Typ, zu grossem Bild,
            unsauberem Schluessel oder einem Schreibfehler.
        """
        folder = image_folder(self._dir, key)
        name = image_file_name(src, content_type)
        if folder is None or name is None or len(data) > MAX_IMAGE_BYTES:
            return None
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(data)
        except OSError as exc:
            logger.warning("Bild fuer %s nicht schreibbar: %s", key, exc)
            return None
        return name

    def prune(self, now: datetime, max_age: timedelta = timedelta(days=90)) -> int:
        """Loescht Tickets, die laenger als max_age nicht abgerufen wurden.

        Unlesbare Dateien gehen mit, ebenso der Bildordner. Die Feld-IDs bleiben.

        Returns:
            Wie viele Dateien geloescht wurden.
        """
        if not self._dir.is_dir():
            return 0
        removed = 0
        for path in self._dir.glob("*.json"):
            if path.name == _FIELD_IDS_FILE:
                continue
            data = self.load(path.stem)
            try:
                fetched = datetime.fromisoformat(data.fetched_at) if data is not None else None
            except ValueError:
                fetched = None
            if fetched is not None and now - fetched <= max_age:
                continue
            try:
                path.unlink()
                removed += 1
                shutil.rmtree(self._dir / f"{path.stem.upper()}.files", ignore_errors=True)
            except OSError as exc:
                logger.warning("Vorschau-Cache %s nicht loeschbar: %s", path, exc)
        return removed

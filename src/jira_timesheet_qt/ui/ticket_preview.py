"""Ticket-Vorschau rechts neben dem Stundenzettel und den Ticketlisten.

Nur lesend. Oben ein Kopf wie eine Ticketkarte: Schluessel und Titel, darunter
Status, Typ und die gebuchte Zeit, dann drei Feldbloecke (Personen, Termine,
Einordnung). Leere Felder bleiben weg. Darunter die Beschreibung, sie kommt als
HTML aus Jira und steht auf weissem Grund in einem QTextBrowser - der fuehrt
kein JavaScript aus und laedt keine fremden Bilder. Bilder zeigt er nur aus dem
Cache-Ordner des Tickets, dorthin hat sie der Worker mit Anmeldung geholt.
Links oeffnen nicht von selbst, sondern ueber _open_link, und dort nur mit http
oder https.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QTextDocument
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from QAppFramework.color import ensure_contrast

from jira_timesheet_qt.services.ticket_board import AccountIdError, check_account_id
from jira_timesheet_qt.services.ticket_preview import (
    TicketPreviewData,
    due_state,
    german_date,
    german_datetime,
    hours_text,
    image_folder,
    is_empty_priority,
    relative_time,
    split_parent,
)
from jira_timesheet_qt.ui.icons import load_icon
from jira_timesheet_qt.ui.theme import PREVIEW_PAPER, Mode, palette_for

# Links in der Beschreibung sind Fliesstext auf weissem Grund - dafuer gilt
# das Kontrastziel fuer normalen Text.
LINK_CONTRAST = 4.5

# Rand zwischen Bild und Kante der Beschreibung, damit ein breites Bild nicht
# an den Rahmen stoesst.
_IMAGE_MARGIN = 32
# Kleiner wird ein Bild nie - sonst waere bei schmaler Vorschau nichts mehr zu erkennen.
_IMAGE_MIN_WIDTH = 160

# Breiter werden die Feldbloecke im Kopf nicht. Vorher verteilten sich die Felder
# ueber die ganze Vorschau, und zwischen Wert und naechster Beschriftung lag eine
# Handbreit Leerraum. Titel und Status nutzen dagegen die volle Breite.
HEADER_MAX_WIDTH = 760
# Breite eines Feldblocks: waechst bis zur Hoechstbreite, laengere Werte brechen um.
_BLOCK_MIN_WIDTH = 120
_BLOCK_MAX_WIDTH = 240

# Linkziel fuer Personen im Kopf: "person:<accountId>". Kein http - der Klick
# bleibt in der Anwendung und fuehrt nach "Mein Team".
PERSON_SCHEME = "person"


def link_color(mode: Mode) -> str:
    """Linkfarbe fuer die Beschreibung: der Akzent des Themes, auf Weiss lesbar gemacht."""
    return ensure_contrast(palette_for(mode).accent, PREVIEW_PAPER, LINK_CONTRAST)


class _Field(NamedTuple):
    """Ein Feld im Kopf, so wie es angezeigt wird."""

    label: str
    value: str
    # RichText-Fassung mit Link, sonst wird value als reiner Text gezeigt.
    rich: str = ""
    # Faelligkeit: overdue, soon oder leer - faerbt den Wert.
    due: str = ""
    # Ersatztext fuer einen fehlenden Wert, der trotzdem wichtig ist.
    missing: bool = False
    tooltip: str = ""
    # accountId, wenn der Wert eine Person ist, die sich in "Mein Team" zeigen laesst.
    person_id: str = ""


class PreviewBrowser(QTextBrowser):
    """QTextBrowser, der Bilder nur aus dem Cache-Ordner des Tickets laedt.

    Jede andere Bildquelle bleibt leer. Aus der Adresse zaehlt nur der
    Dateiname - ein Pfad wie "../x.png" kann den Ordner nicht verlassen.
    Breite Bilder werden auf die Breite der Vorschau verkleinert, die Groesse
    aus dem Jira-HTML ist vorher schon entfernt.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_dir: Path | None = None

    def loadResource(self, type: int, name: QUrl | str) -> Any:  # noqa: A002, N802 - Qt gibt die Namen vor
        if type == QTextDocument.ResourceType.ImageResource.value:
            return self.local_image(name if isinstance(name, QUrl) else QUrl(name))
        return super().loadResource(type, name)

    def local_image(self, url: QUrl) -> QImage:
        """Das Bild zur Adresse, verkleinert auf die Breite - oder ein leeres."""
        if self.image_dir is None or url.scheme():
            return QImage()
        path = self.image_dir / Path(url.path()).name
        image = QImage(str(path)) if path.is_file() else QImage()
        max_width = max(_IMAGE_MIN_WIDTH, self.viewport().width() - _IMAGE_MARGIN)
        if not image.isNull() and image.width() > max_width:
            image = image.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        return image


class TicketPreview(QWidget):
    """Zeigt ein Ticket nur lesend: Kopf als Ticketkarte, Beschreibung, Fusszeile."""

    refresh_requested = Signal()
    # Klick auf eine Person: accountId und Anzeigename.
    person_requested = Signal(str, str)

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._host = ""
        self._image_root: Path | None = None
        self._data: TicketPreviewData | None = None
        self._fields: list[_Field] = []
        # Austauschbar fuer Tests - Faelligkeit und "vor 6 Std." haengen am Heute.
        self.today: Callable[[], date] = date.today
        self.now: Callable[[], datetime] = datetime.now
        self.setMinimumWidth(320)

        self._stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        # Seite 0: Platzhalter (nichts gewaehlt, laedt, Fehler, Screenshot-Modus).
        self._placeholder = QLabel()
        self._placeholder.setObjectName("PreviewPlaceholder")
        self._placeholder.setTextFormat(Qt.TextFormat.PlainText)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setMargin(24)
        self._stack.addWidget(self._placeholder)

        # Seite 1: das Ticket.
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())

        self._body = PreviewBrowser()
        self._body.setObjectName("PreviewBody")
        # Links nie von selbst oeffnen - weder im Browser-Widget noch extern.
        self._body.setOpenLinks(False)
        self._body.setOpenExternalLinks(False)
        self._body.anchorClicked.connect(self._open_link)
        layout.addWidget(self._body, 1)
        layout.addLayout(self._build_footer())
        self._stack.addWidget(page)

        self._apply_document_style()
        self.show_placeholder("Kein Eintrag gewählt")

    # --- Aufbau ---------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("PreviewHeader")
        content = QVBoxLayout(header)
        content.setContentsMargins(14, 10, 8, 12)
        content.setSpacing(6)

        # Zeile 1: worum es geht - Schluessel und Titel -, rechts die gebuchte
        # Zeit, im Stundenzettel die wichtigste Zahl zu einem Ticket. Neben dem
        # oft zweizeiligen Titel kostet sie keine eigene Hoehe. Diese Zeile
        # nutzt die volle Breite, sonst bricht ein langer Titel unnoetig um.
        top = QHBoxLayout()
        top.setSpacing(10)
        self._key = QLabel()
        self._key.setObjectName("PreviewKey")
        self._key.setTextFormat(Qt.TextFormat.RichText)
        self._key.setOpenExternalLinks(False)
        self._key.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._key.linkActivated.connect(lambda href: self._open_link(QUrl(href)))
        self._title = QLabel()
        self._title.setObjectName("PreviewTitle")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        hours_widget = QWidget()
        hours_box = QVBoxLayout(hours_widget)
        hours_box.setContentsMargins(0, 0, 0, 0)
        hours_box.setSpacing(0)
        self._hours = QLabel()
        self._hours.setObjectName("PreviewHours")
        self._hours_hint = QLabel()
        self._hours_hint.setObjectName("PreviewHoursHint")
        self._estimate = QProgressBar()
        self._estimate.setObjectName("PreviewEstimate")
        self._estimate.setTextVisible(False)
        self._estimate.setRange(0, 100)
        self._estimate.setFixedHeight(4)
        # Keine feste Breite: der Balken folgt der Zeile aus Zahl und Hinweis.
        # Mit fester Breite bestimmte er die Spalte und schob den Hinweis ab.
        self._estimate.setMinimumWidth(60)
        # Zahl und Hinweis nebeneinander: untereinander machten sie die Titelzeile
        # zweizeilig, auch wenn der Titel nur eine Zeile braucht.
        hours_line = QHBoxLayout()
        hours_line.setSpacing(6)
        hours_line.addWidget(self._hours, 0, Qt.AlignmentFlag.AlignBaseline)
        hours_line.addWidget(self._hours_hint, 0, Qt.AlignmentFlag.AlignBaseline)
        hours_box.addLayout(hours_line)
        # Abstand zur Zahl - direkt darunter liest sich der Balken wie eine Unterstreichung.
        hours_box.addSpacing(4)
        hours_box.addWidget(self._estimate)

        self._refresh = QToolButton()
        self._refresh.setObjectName("PreviewRefresh")
        self._refresh.setAutoRaise(True)
        self._refresh.setToolTip("Ticket neu aus Jira laden")
        self._refresh.setIcon(load_icon("refresh", self._mode))
        self._refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())

        top.addWidget(self._key, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self._title, 1)
        top.addSpacing(16)
        top.addWidget(hours_widget, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self._refresh, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(top)

        # Zeile 2: nur noch Status, Typ und Prioritaet - einzeilig.
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self._status = QLabel()
        self._status.setObjectName("PreviewStatus")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._meta = QLabel()
        self._meta.setObjectName("PreviewMeta")
        self._meta.setTextFormat(Qt.TextFormat.PlainText)
        meta_row.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)
        meta_row.addWidget(self._meta, 0, Qt.AlignmentFlag.AlignVCenter)
        meta_row.addStretch(1)
        content.addLayout(meta_row)

        # Die Trennlinie laeuft ueber die volle Breite, wie Titel und Status.
        content.addSpacing(4)
        rule = QFrame()
        rule.setObjectName("PreviewRule")
        rule.setFixedHeight(1)
        content.addWidget(rule)

        # Nur die Felder sind in der Breite begrenzt. Ohne Grenze verteilten
        # sie sich ueber die ganze Vorschau.
        self._fields_area = QWidget()
        self._fields_area.setMaximumWidth(HEADER_MAX_WIDTH)
        fields = QVBoxLayout(self._fields_area)
        fields.setContentsMargins(0, 2, 0, 0)
        fields.setSpacing(8)
        area_row = QHBoxLayout()
        area_row.addWidget(self._fields_area, 1)
        area_row.addStretch(0)
        content.addLayout(area_row)

        # Drei Bloecke nebeneinander, jeder mit fester Hoechstbreite.
        blocks = QHBoxLayout()
        blocks.setSpacing(24)
        self._blocks: list[tuple[QWidget, QVBoxLayout]] = []
        for _ in range(3):
            block = QWidget()
            block.setObjectName("PreviewBlock")
            block.setMinimumWidth(_BLOCK_MIN_WIDTH)
            block.setMaximumWidth(_BLOCK_MAX_WIDTH)
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(6)
            # Ohne Ausrichtung, mit Streckfaktor: mit Ausrichtung bekaeme der
            # Block nur seine Wunschbreite, und lange Werte braechen schon bei
            # viel Platz dreizeilig um. Oben bleibt er durch den Stretch im Block.
            blocks.addWidget(block, 1)
            self._blocks.append((block, block_layout))
        blocks.addStretch(1)
        fields.addLayout(blocks)
        return header

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(14, 0, 14, 8)
        footer.setSpacing(8)
        # Zwei Zeitangaben, die man leicht verwechselt: wann Jira das Ticket
        # zuletzt geaendert hat, und wann die Vorschau es abgerufen hat.
        self._updated = QLabel()
        self._updated.setObjectName("PreviewStand")
        self._stand = QLabel()
        self._stand.setObjectName("PreviewStand")
        footer.addWidget(self._updated)
        footer.addStretch(1)
        footer.addWidget(self._stand)
        return footer

    # --- Inhalte --------------------------------------------------------

    @property
    def current_data(self) -> TicketPreviewData | None:
        """Das gezeigte Ticket, oder None bei einem Platzhalter."""
        return self._data

    def set_host(self, host: str) -> None:
        """Jira-Host fuer den Link aufs Ticket und fuer relative Links in der Beschreibung."""
        self._host = host.rstrip("/")

    def set_image_root(self, root: Path | None) -> None:
        """Cache-Verzeichnis des Hosts - darunter liegen die Bilder je Ticket."""
        self._image_root = root

    def show_placeholder(self, text: str, error: bool = False) -> None:
        """Zeigt einen Hinweis statt eines Tickets."""
        self._data = None
        self._fields = []
        self._placeholder.setText(text)
        self._placeholder.setProperty("state", "error" if error else "")
        self._repolish(self._placeholder)
        self._stack.setCurrentIndex(0)

    def show_data(self, data: TicketPreviewData, note: str | None = None) -> None:
        """Zeigt ein Ticket.

        Args:
            data:
                Das Ticket.
            note:
                Text rechts unten. Ohne Angabe der Stand des Abrufs.
        """
        self._data = data
        url = f"{self._host}/browse/{data.key}" if self._host else ""
        if url:
            self._key.setText(f'<a href="{html.escape(url)}">{html.escape(data.key)}</a>')
            self._key.setToolTip("In Jira öffnen")
        else:
            self._key.setText(html.escape(data.key))
            self._key.setToolTip("")
        self._title.setText(data.summary or "Ohne Titel")
        self._set_status(data)
        self._meta.setText(self._meta_text(data))
        self._set_hours(data)
        self._fill_blocks(data)
        self._set_updated(data)
        self._set_body(data)
        self.set_note(note if note is not None else f"Stand {german_datetime(data.fetched_at)}")
        self._stack.setCurrentIndex(1)

    def set_note(self, text: str, error: bool = False) -> None:
        """Text rechts in der Fusszeile: Stand, laufende Pruefung oder Fehler."""
        self._stand.setText(text)
        self._stand.setProperty("state", "error" if error else "")
        self._repolish(self._stand)

    def field_pairs(self) -> list[tuple[str, str]]:
        """Die angezeigten Kopffelder in Reihenfolge. Leere Felder stehen nicht darin."""
        return [(field.label, field.value) for field in self._fields]

    def field_due_state(self) -> str:
        """Zustand der Faelligkeit, wie er den Wert faerbt: overdue, soon oder leer."""
        return next((field.due for field in self._fields if field.label == "Fälligkeitsdatum"), "")

    def meta_text(self) -> str:
        """Typ und Prioritaet neben dem Status, wie angezeigt."""
        return self._meta.text()

    def hours_texts(self) -> tuple[str, str]:
        """Gebuchte Zeit und Hinweis daneben, wie angezeigt."""
        return self._hours.text(), self._hours_hint.text()

    def estimate_state(self) -> tuple[bool, int, bool]:
        """Ob der Schaetzungsbalken sichtbar ist, sein Wert und ob die Schaetzung ueberschritten ist."""
        return not self._estimate.isHidden(), self._estimate.value(), bool(self._estimate.property("over"))

    def status_label(self) -> tuple[str, str, bool]:
        """Text, Kategorie und ob das Status-Etikett ausgeblendet ist."""
        return self._status.text(), str(self._status.property("category") or ""), self._status.isHidden()

    def updated_text(self) -> str:
        """Die Aenderungszeit aus Jira in der Fusszeile, wie angezeigt."""
        return self._updated.text()

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild - Symbol und Linkfarbe haengen daran."""
        self._mode = mode
        self._refresh.setIcon(load_icon("refresh", mode))
        self._apply_document_style()
        if self._data is not None:
            # Der Dokument-Stil gilt nur fuer neu gesetztes HTML.
            self._set_body(self._data)

    # --- Intern ---------------------------------------------------------

    @staticmethod
    def _meta_text(data: TicketPreviewData) -> str:
        parts = [data.issue_type]
        if data.story_points:
            points = data.story_points
            parts.append(f"{points:g} SP".replace(".", ","))
        if not is_empty_priority(data.priority):
            parts.append(f"Priorität {data.priority}")
        return " · ".join(part for part in parts if part)

    def _groups(self, data: TicketPreviewData) -> list[list[_Field]]:
        """Die drei Bloecke: Personen, Termine und Version, Einordnung."""
        persons: list[_Field] = []
        if self._same_person(data):
            persons.append(self._person_field("Zugewiesen und Autor", data.assignee, data.assignee_id))
        else:
            if data.assignee:
                persons.append(self._person_field("Zugewiesene Person", data.assignee, data.assignee_id))
            else:
                persons.append(_Field("Zugewiesene Person", "nicht zugewiesen", missing=True))
            if data.creator:
                persons.append(self._person_field("Autor", data.creator, data.creator_id))

        dates: list[_Field] = []
        if data.due_date:
            dates.append(
                _Field("Fälligkeitsdatum", german_date(data.due_date), due=due_state(data.due_date, self.today()))
            )
        else:
            # Die Faelligkeit bleibt auch leer sichtbar - dass es keine gibt, ist eine Auskunft.
            dates.append(_Field("Fälligkeitsdatum", "keine", missing=True))
        if data.fix_versions:
            dates.append(_Field("Lösungsversionen", data.fix_versions))

        context: list[_Field] = []
        if data.parent:
            key, summary = split_parent(data.parent)
            rich = ""
            if key and self._host:
                href = html.escape(f"{self._host}/browse/{key}")
                rich = f'<a href="{href}">{html.escape(key)}</a> {html.escape(summary)}'.strip()
            context.append(_Field("Übergeordnet", data.parent, rich=rich, tooltip=data.parent))
        context.extend(_Field(name, value) for name, value in data.extra if value)
        return [persons, dates, context]

    @staticmethod
    def _same_person(data: TicketPreviewData) -> bool:
        """Ob Bearbeiter und Autor dieselbe Person sind."""
        if not data.assignee:
            return False
        # Mit Kennungen entscheiden die - zwei Personen koennen gleich heissen.
        if data.assignee_id and data.creator_id:
            return data.assignee_id == data.creator_id
        return data.assignee == data.creator

    @staticmethod
    def _person_field(label: str, name: str, account_id: str) -> _Field:
        """Ein Personenfeld. Mit brauchbarer Kennung wird der Name zum Link nach "Mein Team"."""
        try:
            checked = check_account_id(account_id)
        except AccountIdError:
            # Aeltere Cache-Eintraege und anonyme Konten haben keine Kennung.
            return _Field(label, name)
        href = html.escape(f"{PERSON_SCHEME}:{checked}")
        return _Field(
            label,
            name,
            rich=f'<a href="{href}">{html.escape(name)}</a>',
            tooltip=f'Tickets von {name} in "Mein Team" anzeigen',
            person_id=checked,
        )

    def person_links(self) -> list[tuple[str, str]]:
        """Die Personenfelder mit Link: (Beschriftung, accountId)."""
        return [(field.label, field.person_id) for field in self._fields if field.person_id]

    def _on_value_link(self, href: str) -> None:
        """Link in einem Kopffeld: eine Person fuehrt nach "Mein Team", alles andere in den Browser."""
        prefix = f"{PERSON_SCHEME}:"
        if not href.startswith(prefix):
            self._open_link(QUrl(href))
            return
        account_id = href[len(prefix) :]
        # Nur Kennungen, die die Vorschau selbst verlinkt hat.
        name = next((field.value for field in self._fields if field.person_id == account_id), "")
        if name:
            self.person_requested.emit(account_id, name)

    def _fill_blocks(self, data: TicketPreviewData) -> None:
        groups = self._groups(data)
        self._fields = [field for group in groups for field in group]
        for (block, block_layout), fields in zip(self._blocks, groups, strict=True):
            self._clear(block_layout)
            for field in fields:
                block_layout.addWidget(self._field_widget(field))
            block_layout.addStretch(1)
            block.setHidden(not fields)

    def _field_widget(self, field: _Field) -> QWidget:
        widget = QWidget()
        widget_layout = QVBoxLayout(widget)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.setSpacing(1)
        name = QLabel(field.label)
        name.setObjectName("PreviewLabel")
        value = QLabel()
        value.setObjectName("PreviewValue")
        value.setWordWrap(True)
        if field.rich:
            value.setTextFormat(Qt.TextFormat.RichText)
            value.setOpenExternalLinks(False)
            value.setText(field.rich)
            value.linkActivated.connect(self._on_value_link)
        else:
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setText(field.value)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if field.tooltip:
            value.setToolTip(field.tooltip)
        value.setProperty("due", field.due)
        value.setProperty("missing", field.missing)
        widget_layout.addWidget(name)
        widget_layout.addWidget(value)
        return widget

    def _set_hours(self, data: TicketPreviewData) -> None:
        self._hours.setText(hours_text(data.time_spent_seconds))
        estimate = data.original_estimate_seconds
        # Im Stundenzettel sind Stunden gebuchte Stunden - ein "gebucht" daneben
        # wirkte angeklebt. Der Hinweis steht nur noch, wenn er etwas hinzufuegt.
        # Kurz gehalten: er steht neben dem Titel und nimmt ihm sonst die Breite.
        self._hours_hint.setText(f"von {hours_text(estimate)}" if estimate > 0 else "")
        self._hours_hint.setHidden(estimate <= 0)
        self._hours.setToolTip("In Jira auf dieses Ticket gebuchte Zeit, alle Personen")
        # Der Balken nur mit Schaetzung - ohne sie gibt es kein Ganzes, von dem er ein Teil waere.
        self._estimate.setHidden(estimate <= 0)
        if estimate > 0:
            percent = round(data.time_spent_seconds * 100 / estimate)
            self._estimate.setValue(min(100, percent))
            self._estimate.setProperty("over", percent > 100)
            self._estimate.setToolTip(f"{percent} % der Schätzung gebucht")
            self._repolish(self._estimate)

    def _set_status(self, data: TicketPreviewData) -> None:
        # Ohne Status kein leeres Kaestchen im Kopf.
        self._status.setText(data.status)
        self._status.setProperty("category", data.status_category)
        self._status.setHidden(not data.status)
        self._repolish(self._status)

    def _set_updated(self, data: TicketPreviewData) -> None:
        if data.updated:
            self._updated.setText(f"In Jira geändert {relative_time(data.updated, self.now())}")
            self._updated.setToolTip(german_datetime(data.updated))
        else:
            self._updated.setText("")
            self._updated.setToolTip("")

    def _set_body(self, data: TicketPreviewData) -> None:
        self._body.image_dir = (
            image_folder(self._image_root, data.key) if self._image_root is not None and data.images else None
        )
        self._body.setHtml(data.description_html or "<p><i>Keine Beschreibung</i></p>")

    def _apply_document_style(self) -> None:
        self._body.document().setDefaultStyleSheet(
            f"a {{ color: {link_color(self._mode)}; text-decoration: none; }}"
            " p { margin-top: 0px; margin-bottom: 8px; }"
        )

    def _open_link(self, url: QUrl) -> None:
        """Oeffnet einen Link im Browser - relative gegen den Jira-Host, nur http und https."""
        if url.isRelative() and self._host:
            url = QUrl(f"{self._host}/").resolved(url)
        if url.scheme().lower() not in ("http", "https"):
            return
        QDesktopServices.openUrl(url)

    @staticmethod
    def _clear(layout: QBoxLayout) -> None:
        """Leert ein Layout sofort."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Erst aus der Hierarchie nehmen, sonst malt das alte Label
                # bis zum naechsten Ereignisdurchlauf ueber das neue.
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        """Nach setProperty muss das Stylesheet neu greifen."""
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)

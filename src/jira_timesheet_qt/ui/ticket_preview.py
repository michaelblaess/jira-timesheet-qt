"""Ticket-Vorschau rechts neben dem Stundenzettel.

Nur lesend: ein Kopf mit der gebuchten Zeit und den wichtigsten Feldern,
darunter Titel und Beschreibung. Die Beschreibung kommt als HTML aus Jira und
steht auf weissem Grund in einem QTextBrowser - der fuehrt kein JavaScript aus
und laedt keine fremden Bilder. Bilder zeigt er nur aus dem Cache-Ordner des
Tickets, dorthin hat sie der Worker mit Anmeldung geholt. Links oeffnen nicht
von selbst, sondern ueber _open_link, und dort nur mit http oder https.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QTextDocument
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from QAppFramework.color import ensure_contrast

from jira_timesheet_qt.services.ticket_preview import (
    TicketPreviewData,
    german_date,
    german_datetime,
    hours_text,
    image_folder,
)
from jira_timesheet_qt.ui.icons import load_icon
from jira_timesheet_qt.ui.theme import PREVIEW_PAPER, Mode, palette_for

# Steht fuer ein leeres Feld - ein fehlender Wert soll sichtbar leer sein,
# nicht so aussehen, als sei die Zeile kaputt.
_LEER = "-"

# Links in der Beschreibung sind Fliesstext auf weissem Grund - dafuer gilt
# das Kontrastziel fuer normalen Text.
LINK_CONTRAST = 4.5

# Rand zwischen Bild und Kante der Beschreibung, damit ein breites Bild nicht
# an den Rahmen stoesst.
_IMAGE_MARGIN = 32
# Kleiner wird ein Bild nie - sonst waere bei schmaler Vorschau nichts mehr zu erkennen.
_IMAGE_MIN_WIDTH = 160


def link_color(mode: Mode) -> str:
    """Linkfarbe fuer die Beschreibung: der Akzent des Themes, auf Weiss lesbar gemacht."""
    return ensure_contrast(palette_for(mode).accent, PREVIEW_PAPER, LINK_CONTRAST)


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
    """Zeigt ein Ticket nur lesend: Kopf, Titel, Beschreibung."""

    refresh_requested = Signal()

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._host = ""
        self._image_root: Path | None = None
        self._data: TicketPreviewData | None = None
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

        header = QFrame()
        header.setObjectName("PreviewHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(8)

        top = QHBoxLayout()
        self._key = QLabel()
        self._key.setObjectName("PreviewKey")
        self._key.setTextFormat(Qt.TextFormat.RichText)
        self._key.setOpenExternalLinks(False)
        self._key.linkActivated.connect(lambda href: self._open_link(QUrl(href)))
        self._stand = QLabel()
        self._stand.setObjectName("PreviewStand")
        self._refresh = QToolButton()
        self._refresh.setObjectName("PreviewRefresh")
        self._refresh.setAutoRaise(True)
        self._refresh.setToolTip("Ticket neu aus Jira laden")
        self._refresh.setIcon(load_icon("refresh", mode))
        self._refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        top.addWidget(self._key)
        top.addStretch(1)
        top.addWidget(self._stand)
        top.addWidget(self._refresh)
        header_layout.addLayout(top)

        # Die gebuchte Zeit steht hervorgehoben: im Stundenzettel ist sie die
        # wichtigste Zahl zu einem Ticket.
        hours_row = QHBoxLayout()
        hours_row.setSpacing(10)
        self._hours = QLabel()
        self._hours.setObjectName("PreviewHours")
        self._hours_hint = QLabel()
        self._hours_hint.setObjectName("PreviewHoursHint")
        hours_row.addWidget(self._hours, 0, Qt.AlignmentFlag.AlignBaseline)
        hours_row.addWidget(self._hours_hint, 0, Qt.AlignmentFlag.AlignBaseline)
        # Der Status als Etikett daneben, gefaerbt nach seiner Kategorie.
        self._status = QLabel()
        self._status.setObjectName("PreviewStatus")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        hours_row.addSpacing(8)
        hours_row.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)
        hours_row.addStretch(1)
        header_layout.addLayout(hours_row)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnStretch(3, 1)
        header_layout.addLayout(self._grid)
        layout.addWidget(header)

        self._title = QLabel()
        self._title.setObjectName("PreviewTitle")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._title)

        self._body = PreviewBrowser()
        self._body.setObjectName("PreviewBody")
        # Links nie von selbst oeffnen - weder im Browser-Widget noch extern.
        self._body.setOpenLinks(False)
        self._body.setOpenExternalLinks(False)
        self._body.anchorClicked.connect(self._open_link)
        layout.addWidget(self._body, 1)
        self._stack.addWidget(page)

        self._apply_document_style()
        self.show_placeholder("Kein Eintrag gewählt")

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
                Text rechts oben. Ohne Angabe der Stand des Abrufs.
        """
        self._data = data
        url = f"{self._host}/browse/{data.key}" if self._host else ""
        if url:
            self._key.setText(f'<a href="{html.escape(url)}">{html.escape(data.key)}</a>')
            self._key.setToolTip("In Jira öffnen")
        else:
            self._key.setText(html.escape(data.key))
            self._key.setToolTip("")
        self._set_hours(data)
        self._set_status(data)
        self._title.setText(data.summary or _LEER)
        self._fill_grid(data)
        self._set_body(data)
        self.set_note(note if note is not None else f"Stand {german_datetime(data.fetched_at)}")
        self._stack.setCurrentIndex(1)

    def set_note(self, text: str, error: bool = False) -> None:
        """Text rechts oben im Kopf: Stand, laufende Pruefung oder Fehler."""
        self._stand.setText(text)
        self._stand.setProperty("state", "error" if error else "")
        self._repolish(self._stand)

    def field_pairs(self) -> list[tuple[str, str]]:
        """Die Kopffelder in angezeigter Reihenfolge, leere als "-"."""
        return self._pairs(self._data) if self._data is not None else []

    def hours_texts(self) -> tuple[str, str]:
        """Gebuchte Zeit und Hinweis daneben, wie angezeigt."""
        return self._hours.text(), self._hours_hint.text()

    def status_label(self) -> tuple[str, str, bool]:
        """Text, Kategorie und ob das Status-Etikett ausgeblendet ist."""
        return self._status.text(), str(self._status.property("category") or ""), self._status.isHidden()

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
    def _pairs(data: TicketPreviewData) -> list[tuple[str, str]]:
        pairs = [
            ("Zugewiesene Person", data.assignee),
            ("Autor", data.creator),
            ("Fälligkeitsdatum", german_date(data.due_date) if data.due_date else ""),
            ("Typ", data.issue_type),
            ("Priorität", data.priority),
            ("Lösungsversionen", data.fix_versions),
            ("Übergeordnet", data.parent),
            ("Aktualisiert", german_datetime(data.updated) if data.updated else ""),
            *data.extra,
        ]
        return [(label, value or _LEER) for label, value in pairs]

    def _set_hours(self, data: TicketPreviewData) -> None:
        self._hours.setText(hours_text(data.time_spent_seconds))
        if data.original_estimate_seconds > 0:
            self._hours_hint.setText(f"gebucht, geschätzt {hours_text(data.original_estimate_seconds)}")
        elif data.time_spent_seconds > 0:
            self._hours_hint.setText("gebucht")
        else:
            self._hours_hint.setText("noch nichts gebucht")

    def _set_status(self, data: TicketPreviewData) -> None:
        # Ohne Status kein leeres Kaestchen im Kopf.
        self._status.setText(data.status)
        self._status.setProperty("category", data.status_category)
        self._status.setHidden(not data.status)
        self._repolish(self._status)

    def _fill_grid(self, data: TicketPreviewData) -> None:
        """Baut die Kopffelder neu auf, zwei Paare je Zeile."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Erst aus der Hierarchie nehmen, sonst malt das alte Label
                # bis zum naechsten Ereignisdurchlauf ueber das neue.
                widget.setParent(None)
                widget.deleteLater()
        for index, (label, value) in enumerate(self._pairs(data)):
            row, column = divmod(index, 2)
            name = QLabel(label)
            name.setObjectName("PreviewLabel")
            wert = QLabel(value)
            wert.setObjectName("PreviewValue")
            wert.setTextFormat(Qt.TextFormat.PlainText)
            wert.setWordWrap(True)
            wert.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(name, row, column * 2)
            self._grid.addWidget(wert, row, column * 2 + 1)

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
    def _repolish(widget: QWidget) -> None:
        """Nach setProperty muss das Stylesheet neu greifen."""
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)

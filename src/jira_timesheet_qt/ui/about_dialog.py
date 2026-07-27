"""Info-Dialog.

Aufbau wie der AboutScreen der TUI: Name, dann Version, Autor und Jahr in einer
Zeile, Beschreibung, Lizenz, Trennlinie, ein wechselndes Zitat und die Links.

Der Zitatpool ist eine Auswahl aus textual-widgets. Das Paket wird hier NICHT
eingebunden, weil es textual mitzieht - dieselbe Ueberlegung wie beim
Haftungshinweis. Beides gehoert in ein gemeinsames Paket ohne
Oberflaechen-Abhaengigkeit, sobald es eine zweite Qt-Anwendung gibt.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt import __app_name__, __author__, __version__, __year__

REPO_URL = "https://github.com/michaelblaess/jira-timesheet-qt"
HOMEPAGE_URL = "https://www.michaelblaess.de/"

DESCRIPTION = "Stundenzettel aus Jira-Worklogs -\nmit manueller Nacherfassung und Export."


@dataclass(frozen=True)
class Quote:
    """Ein Zitat mit Urheber."""

    text: str
    author: str


QUOTES: tuple[Quote, ...] = (
    Quote(
        "Die Dunkelheit kann die Dunkelheit nicht vertreiben,\n"
        "das kann nur das Licht. Hass kann den Hass nicht\nvertreiben, das kann nur die Liebe.",
        "Martin Luther King jr.",
    ),
    Quote(
        "Wir müssen lernen, miteinander als Brüder zu leben,\noder wir werden als Narren untergehen.",
        "Martin Luther King jr.",
    ),
    Quote("Hoffnung ist das Ding mit Federn,\ndas in der Seele wohnt.", "Emily Dickinson"),
    Quote(
        "Zuerst ignorieren sie dich, dann lachen sie über dich,\n"
        "dann bekämpfen sie dich, dann gewinnst du.",
        "Mahatma Gandhi",
    ),
    Quote(
        "Jeder Narr kann Code schreiben, den ein Rechner versteht.\n"
        "Gute Programmierer schreiben Code, den Menschen verstehen.",
        "Martin Fowler",
    ),
)


class AboutDialog(QDialog):
    """Zeigt Version, Lizenz, ein Zitat und die Verweise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Über {__app_name__}")
        self.setFixedWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Farbige Kopfzone: gibt dem Dialog Kontur, statt ihn als weisse
        # Flaeche mit zentriertem Text stehen zu lassen.
        banner = QWidget()
        banner.setObjectName("AboutBanner")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(30, 26, 30, 24)
        banner_layout.setSpacing(4)

        name = QLabel(__app_name__)
        name.setObjectName("AboutName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_layout.addWidget(name)

        subtitle = QLabel(DESCRIPTION)
        subtitle.setObjectName("AboutBannerText")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_layout.addWidget(subtitle)
        banner_layout.addSpacing(10)

        version = QLabel(__version__)
        version.setObjectName("AboutBadge")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge_row.addWidget(version)
        badge_row.addStretch(1)
        banner_layout.addLayout(badge_row)

        outer.addWidget(banner)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 20, 30, 22)
        layout.setSpacing(4)
        outer.addLayout(layout)

        facts = QLabel(f"{__author__}  ·  {__year__}  ·  Apache-2.0")
        facts.setObjectName("AboutFacts")
        facts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(facts)
        layout.addSpacing(16)

        quote = self._pick_quote()
        quote_text = QLabel(quote.text)
        quote_text.setObjectName("AboutQuote")
        quote_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(quote_text)

        quote_author = QLabel(quote.author)
        quote_author.setObjectName("AboutQuoteAuthor")
        quote_author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(quote_author)
        layout.addSpacing(18)

        for url in (REPO_URL, HOMEPAGE_URL):
            link = QLabel(f'<a href="{url}" style="color:palette(link);">{url}</a>')
            link.setObjectName("AboutLink")
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            layout.addWidget(link)

        layout.addSpacing(18)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Schließen")
        close.setProperty("variant", "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    @staticmethod
    def _pick_quote() -> Quote:
        """Waehlt ein Zitat. secrets statt random, weil ruff Letzteres ruegt."""
        return QUOTES[secrets.randbelow(len(QUOTES))]

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        return line

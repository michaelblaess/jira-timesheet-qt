"""Info-Dialog.

Aufbau wie der AboutScreen der TUI: Name, dann Version, Autor und Jahr in einer
Zeile, Beschreibung, Lizenz, Trennlinie, ein wechselndes Zitat und die Links.

Der Zitatpool steht NICHT mehr im Code, sondern in `quotes/quotes.json`. Die
kanonische Quelle ist `claude-config/templates/zitate/zitate.json`, verteilt von
`sync_zitate.py` - dort stehen auch die Aufnahmeregeln. Kurz: nur gemeinfreie
Autoren (Schutz endet 70 Jahre nach dem Tod, § 64 UrhG), jede Uebersetzung
selbst erstellt, jede Quelle benennbar. Wer ein Zitat aendern will, aendert die
kanonische Datei und laesst neu verteilen - eine Aenderung hier waere beim
naechsten Lauf wieder weg.
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from importlib import resources

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
from jira_timesheet_qt.i18n import current_language

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/michaelblaess/jira-timesheet-qt"
HOMEPAGE_URL = "https://www.michaelblaess.de/"

DESCRIPTION = "Stundenzettel aus Jira-Worklogs -\nmit manueller Nacherfassung und Export."


@dataclass(frozen=True)
class Quote:
    """Ein Zitat mit Urheber und belegbarer Quelle."""

    text: str
    author: str
    source: str


def load_quotes(lang: str | None = None) -> tuple[Quote, ...]:
    """Laedt den Zitatpool aus den Paketdaten.

    Args:
        lang:
            Sprachkuerzel ('de' oder 'en'). Ohne Angabe die geladene UI-Sprache.

    Returns:
        Die Zitate der gewaehlten Sprache. Leer, wenn die Datei fehlt oder
        unlesbar ist - ein Info-Dialog darf daran nicht scheitern.
    """
    feld = "text_en" if (lang or current_language()) == "en" else "text_de"
    try:
        raw = (resources.files("jira_timesheet_qt") / "quotes" / "quotes.json").read_text(encoding="utf-8")
        eintraege = json.loads(raw)["zitate"]
    except Exception:
        logger.exception("Zitatpool konnte nicht geladen werden")
        return ()
    return tuple(
        Quote(text=eintrag[feld], author=eintrag["autor"], source=eintrag["quelle"]) for eintrag in eintraege
    )


class AboutDialog(QDialog):
    """Zeigt Version, Lizenz, ein Zitat und die Verweise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Über {__app_name__}")
        self.setSizeGripEnabled(True)
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

        # Der Pool traegt keine Umbrueche mehr (Daten ohne Layout) - die
        # Beschriftung bricht selbst um, der Dialog hat feste Breite.
        quote = self._pick_quote()
        if quote is not None:
            quote_text = QLabel(quote.text)
            quote_text.setObjectName("AboutQuote")
            quote_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            quote_text.setWordWrap(True)
            quote_text.setToolTip(quote.source)
            layout.addWidget(quote_text)

            quote_author = QLabel(quote.author)
            quote_author.setObjectName("AboutQuoteAuthor")
            quote_author.setAlignment(Qt.AlignmentFlag.AlignCenter)
            quote_author.setToolTip(quote.source)
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
    def _pick_quote() -> Quote | None:
        """Waehlt ein Zitat. secrets statt random, weil ruff Letzteres ruegt.

        Returns:
            Ein zufaelliges Zitat der aktuellen Sprache, oder None bei leerem Pool.
        """
        pool = load_quotes()
        return pool[secrets.randbelow(len(pool))] if pool else None

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.NoFrame)
        return line

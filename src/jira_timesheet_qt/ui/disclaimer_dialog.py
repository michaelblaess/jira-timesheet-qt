"""Bestaetigungspflichtiger Haftungshinweis beim ersten Start.

Grundregel fuer alle Anwendungen: ohne Zustimmung laeuft das Programm nicht.
Hier zusaetzlich begruendet dadurch, dass ueber die Jira-REST-API auf ein
fremdes System zugegriffen wird und je nach Rechtevergabe auch Buchungen
anderer Personen sichtbar werden.

Wortlaut und Fassung sind mit textual-widgets abgeglichen. Das Paket wird hier
NICHT eingebunden, weil es textual mitzieht und damit das gesamte TUI-Framework
in die Binary geraten wuerde. Sobald es eine zweite Qt-Anwendung gibt, gehoert
der Text in ein gemeinsames Paket ohne Oberflaechen-Abhaengigkeit.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Fassung des Hinweises. Bei inhaltlichen Aenderungen hochzaehlen - dann wird
# die Zustimmung erneut eingeholt, statt eine alte Fassung fortzuschreiben.
DISCLAIMER_VERSION = "2026-07-26"

TITLE = "Nutzung auf eigene Verantwortung"

INTRO = (
    "Dieses Programm greift über die REST-API auf eine Jira-Instanz zu und liest dort "
    "Arbeitszeit-Buchungen aus. Welche Vorgänge und welche Worklogs dabei sichtbar werden, "
    "bestimmen allein die Berechtigungen Ihres Zugangs. Je nach Rechtevergabe können darunter "
    "auch Buchungen anderer Personen sein."
)

DUTIES = (
    "Sie setzen das Programm ausschließlich gegen Jira-Instanzen ein, für die Ihnen eine "
    "ausdrückliche Berechtigung des Betreibers vorliegt.",
    "Sie werten nur Daten aus, zu deren Einsicht und Verarbeitung Sie befugt sind. Werden Ihnen "
    "Buchungen anderer Personen angezeigt, prüfen Sie vor jeder weiteren Verwendung, ob Sie diese "
    "verarbeiten dürfen.",
    "Erzeugte Stundenzettel und Exporte können personenbezogene Daten enthalten. Für deren "
    "Weitergabe, Aufbewahrung und Löschung sind Sie verantwortlich.",
)

LIABILITY = (
    'Die Software wird unentgeltlich und ohne jede Gewährleistung bereitgestellt ("as is"), wie in '
    "Abschnitt 7 der Apache-Lizenz 2.0 beschrieben.\n\n"
    "Eine Haftung des Autors für Schäden, die aus der Nutzung entstehen, ist ausgeschlossen, soweit "
    "dies gesetzlich zulässig ist.\n\n"
    "Unberührt bleibt die Haftung für Vorsatz und grobe Fahrlässigkeit, für Schäden aus der "
    "Verletzung des Lebens, des Körpers oder der Gesundheit sowie nach dem Produkthaftungsgesetz."
)


class DisclaimerStore:
    """Merkt die erteilte Zustimmung samt Fassung in einer JSON-Datei."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Speicherort der Zustimmung."""
        return self._path

    @property
    def accepted_version(self) -> str | None:
        """Fassung, der zugestimmt wurde, oder None ohne Zustimmung."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        version = data.get("accepted_version")
        return version if isinstance(version, str) else None

    def record(self, version: str = DISCLAIMER_VERSION) -> None:
        """Schreibt die Zustimmung mit Zeitstempel fest."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"accepted_version": version, "accepted_at": datetime.now(UTC).isoformat()},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Zustimmung konnte nicht gespeichert werden: %s", exc)


class DisclaimerDialog(QDialog):
    """Zeigt den Hinweis und laesst ihn bestaetigen."""

    def __init__(self, app_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setMinimumSize(640, 560)
        self.setModal(True)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        heading = QLabel(TITLE)
        heading.setObjectName("DisclaimerTitle")
        outer.addWidget(heading)

        app_label = QLabel(app_name)
        app_label.setObjectName("SettingsHint")
        outer.addWidget(app_label)

        outer.addWidget(self._scrollable_text())

        self._agree = QCheckBox("Ich habe den Hinweis gelesen und stimme zu")
        self._agree.toggled.connect(self._on_toggle)
        outer.addWidget(self._agree)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        quit_button = QPushButton("Beenden")
        quit_button.clicked.connect(self.reject)
        buttons.addWidget(quit_button)

        self._accept = QPushButton("Bestätigen")
        self._accept.setProperty("variant", "primary")
        self._accept.setEnabled(False)
        self._accept.clicked.connect(self.accept)
        buttons.addWidget(self._accept)
        outer.addLayout(buttons)

    def _scrollable_text(self) -> QScrollArea:
        """Baut den scrollbaren Textteil des Hinweises."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)

        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        intro.setObjectName("DisclaimerText")
        layout.addWidget(intro)

        duties_title = QLabel("Mit Ihrer Bestätigung erklären Sie:")
        duties_title.setObjectName("DisclaimerSection")
        layout.addWidget(duties_title)

        for duty in DUTIES:
            item = QLabel(f"•   {duty}")
            item.setWordWrap(True)
            item.setObjectName("DisclaimerText")
            item.setIndent(6)
            layout.addWidget(item)

        liability_title = QLabel("Gewährleistung und Haftung")
        liability_title.setObjectName("DisclaimerSection")
        layout.addWidget(liability_title)

        liability = QLabel(LIABILITY)
        liability.setWordWrap(True)
        liability.setObjectName("DisclaimerText")
        layout.addWidget(liability)
        layout.addStretch(1)

        area = QScrollArea()
        area.setObjectName("DisclaimerScroll")
        area.setWidget(content)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _on_toggle(self, checked: bool) -> None:
        """Die Bestaetigung wird erst mit gesetztem Haken moeglich."""
        self._accept.setEnabled(checked)

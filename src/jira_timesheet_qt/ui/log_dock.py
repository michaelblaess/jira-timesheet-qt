"""Meldungsfenster als andockbarer Bereich.

Ersatz fuer das LogPanel der TUI. Anders als dort ist es ein QDockWidget: der
Anwender kann es andocken, abreissen, schliessen und in der Groesse aendern -
die Position merkt sich das Hauptfenster.

Wichtig fuer die Fehlersuche in fremden Umgebungen: hinter einem Proxy oder bei
abgelehnten Zugangsdaten steht die eigentliche Ursache in der Antwort des
Servers, nicht in der einen Zeile der Statusleiste.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Level(StrEnum):
    """Bedeutung einer Meldung. Steuert nur die Farbe."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class LogDock(QDockWidget):
    """Zeigt die Meldungen der Anwendung mit Zeitstempel."""

    MAX_LINES = 2000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Meldungen", parent)
        self.setObjectName("LogDock")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = QPlainTextEdit()
        self._view.setObjectName("LogView")
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(self.MAX_LINES)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self._view, 1)

        buttons = QWidget()
        buttons.setObjectName("LogButtons")
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(10, 6, 10, 6)
        button_layout.setSpacing(8)
        button_layout.addStretch(1)

        copy = QPushButton("Kopieren")
        copy.setProperty("variant", "ghost")
        copy.clicked.connect(self.copy_all)
        button_layout.addWidget(copy)

        clear = QPushButton("Leeren")
        clear.setProperty("variant", "ghost")
        clear.clicked.connect(self.clear)
        button_layout.addWidget(clear)
        layout.addWidget(buttons)

        self.setWidget(body)

    # --- Schreiben ------------------------------------------------------

    def write(self, message: str, level: Level = Level.INFO) -> None:
        """Haengt eine Meldung mit Zeitstempel an."""
        stamp = datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005 - reine Anzeige
        color = _COLORS[level]
        # appendHtml, weil nur so einzelne Zeilen eingefaerbt werden koennen.
        self._view.appendHtml(
            f'<span style="color:{_STAMP_COLOR}">{stamp}</span>&nbsp;&nbsp;'
            f'<span style="color:{color}">{_escape(message)}</span>'
        )
        self._view.verticalScrollBar().setValue(self._view.verticalScrollBar().maximum())

    def clear(self) -> None:
        """Leert das Fenster."""
        self._view.clear()

    def copy_all(self) -> None:
        """Kopiert alle Meldungen als reinen Text."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.plain_text())

    def plain_text(self) -> str:
        """Alle Meldungen ohne Auszeichnung - fuer Zwischenablage und Tests."""
        return self._view.toPlainText()

    @property
    def line_count(self) -> int:
        """Anzahl der Meldungen."""
        text = self.plain_text()
        return len(text.splitlines()) if text else 0

    # --- Kontextmenue ---------------------------------------------------

    def _show_menu(self, position: QPoint) -> None:
        """Rechtsklick: kopieren oder leeren."""
        menu = QMenu(self._view)
        copy_action = QAction("Alles kopieren", menu)
        copy_action.triggered.connect(self.copy_all)
        menu.addAction(copy_action)

        clear_action = QAction("Leeren", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)

        menu.exec(self._view.mapToGlobal(position))


# Farben je Ebene. Bewusst hier und nicht im Stylesheet: die Auszeichnung
# passiert pro Zeile in HTML, nicht ueber einen Selektor.
_COLORS = {
    Level.INFO: "#9ba3b0",
    Level.SUCCESS: "#34d399",
    Level.WARNING: "#fbbf24",
    Level.ERROR: "#f87171",
}
_STAMP_COLOR = "#6b7280"


def _escape(text: str) -> str:
    """Macht Zeichen unschaedlich, die als Auszeichnung gelesen wuerden."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

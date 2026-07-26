"""Absturzschutz.

Gegenstueck zum CrashGuard der TUI. PySide6 leitet unbehandelte Ausnahmen an
sys.excepthook weiter und beendet den Prozess. Statt eines wortlosen Abbruchs
zeigt dieser Haken einen Dialog mit kopierbarem Bericht und laesst den Anwender
entscheiden, ob er weiterarbeitet oder beendet.

Wichtig fuer den Einsatz in fremden Umgebungen: ohne den Bericht bleibt von
einem Absturz nichts uebrig, was man weitergeben koennte.
"""

from __future__ import annotations

import sys
import traceback
from types import TracebackType

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ErrorDialog(QDialog):
    """Zeigt einen Fehlerbericht mit den Knoepfen Kopieren, Weiter und Beenden."""

    def __init__(self, report: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ein Fehler ist aufgetreten")
        self.setMinimumSize(680, 460)
        self._report = report

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        heading = QLabel("Ein Fehler ist aufgetreten")
        heading.setObjectName("DisclaimerTitle")
        layout.addWidget(heading)

        text = QLabel(
            "Entschuldige bitte. Der Bericht unten hilft bei der Ursachensuche - "
            "Du kannst ihn kopieren und weitergeben. Weiterarbeiten ist möglich, "
            "kann aber zu Folgefehlern führen."
        )
        text.setObjectName("DisclaimerText")
        text.setWordWrap(True)
        layout.addWidget(text)

        self._view = QPlainTextEdit(report)
        self._view.setObjectName("LogView")
        self._view.setReadOnly(True)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._view, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        copy = QPushButton("Bericht kopieren")
        copy.clicked.connect(self._copy)
        buttons.addWidget(copy)
        buttons.addStretch(1)

        quit_button = QPushButton("Beenden")
        quit_button.clicked.connect(self._quit)
        buttons.addWidget(quit_button)

        proceed = QPushButton("Weiterarbeiten")
        proceed.setProperty("variant", "primary")
        proceed.setDefault(True)
        proceed.clicked.connect(self.accept)
        buttons.addWidget(proceed)
        layout.addLayout(buttons)

    def _copy(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._report)

    def _quit(self) -> None:
        self.reject()
        app = QApplication.instance()
        if app is not None:
            app.quit()


def format_report(
    exc_type: type[BaseException],
    value: BaseException,
    tb: TracebackType | None,
) -> str:
    """Baut den Fehlerbericht mit Umgebungsangaben."""
    from jira_timesheet_qt import __version__

    lines = [
        f"jira-timesheet-qt {__version__}",
        f"Python {sys.version.split()[0]} auf {sys.platform}",
        "",
        *traceback.format_exception(exc_type, value, tb),
    ]
    return "".join(line if line.endswith("\n") else f"{line}\n" for line in lines)


def install(parent: QWidget | None = None) -> None:
    """Haengt den Fehlerdialog in sys.excepthook ein.

    Args:
        parent:
            Fenster, ueber dem der Dialog erscheinen soll.
    """
    previous = sys.excepthook
    # Verhindert, dass ein Fehler im Dialog selbst eine Schleife ausloest.
    busy = {"value": False}

    def handle(
        exc_type: type[BaseException],
        value: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if busy["value"]:
            previous(exc_type, value, tb)
            return
        busy["value"] = True
        try:
            report = format_report(exc_type, value, tb)
            # Immer auch auf die Fehlerausgabe, damit nichts verloren geht,
            # falls der Dialog nicht erscheinen kann.
            sys.stderr.write(report)
            dialog = ErrorDialog(report, parent)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.exec()
        except Exception:  # noqa: BLE001 - der Haken darf nie selbst sprengen
            previous(exc_type, value, tb)
        finally:
            busy["value"] = False

    sys.excepthook = handle

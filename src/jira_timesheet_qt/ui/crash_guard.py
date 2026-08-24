"""Absturzschutz - liegt in QAppFramework.

Hier bleibt nur, was diese Anwendung beisteuert: Name und Version fuer die
Kopfzeile des Berichts und die Sprache der Oberflaeche.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QWidget
from QAppFramework.absturz import FehlerDialog as ErrorDialog
from QAppFramework.absturz import abbruch_abfangen as _abbruch_abfangen
from QAppFramework.absturz import baue_bericht
from QAppFramework.absturz import einhaengen as _einhaengen

from jira_timesheet_qt import __app_name__, __version__
from jira_timesheet_qt.i18n import current_language

__all__ = ["ErrorDialog", "format_report", "install", "install_interrupt"]


def format_report(exc_type: type[BaseException], value: BaseException, tb: object) -> str:
    """Baut den Fehlerbericht mit Name, Version und Umgebung."""
    return baue_bericht(exc_type, value, tb, f"{__app_name__} {__version__}")  # type: ignore[arg-type]


def install(parent: QWidget | None = None) -> None:
    """Haengt den Fehlerdialog in sys.excepthook ein."""
    _einhaengen(
        parent,
        kopfzeile=f"{__app_name__} {__version__}",
        sprache=current_language(),
    )


def install_interrupt(app: QCoreApplication) -> QTimer:
    """Laesst Strg+C die Anwendung geordnet beenden.

    Ohne das trifft der Abbruch zufaelligen Python-Code - meist den
    eventFilter, weil der bei jeder Mausbewegung laeuft - und wirkt gar nicht,
    solange niemand die Anwendung bedient. Dann faellt auch closeEvent aus, und
    damit das Sichern der Einstellungen.
    """
    return _abbruch_abfangen(app)

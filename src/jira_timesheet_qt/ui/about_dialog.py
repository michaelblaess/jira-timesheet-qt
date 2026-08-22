"""Info-Dialog - die Angaben dieser Anwendung.

Der Dialog selbst steht in QAppFramework, damit ihn nicht jede Anwendung
nachbaut. Hier bleibt nur, was diese Anwendung ausmacht.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from QAppFramework.about import AboutDialog as _AboutDialog
from QAppFramework.about import Zitat, lade_zitate

from jira_timesheet_qt import __app_name__, __author__, __version__, __year__
from jira_timesheet_qt.i18n import current_language

REPO_URL = "https://github.com/michaelblaess/jira-timesheet-qt"
DESCRIPTION = "Stundenzettel aus Jira-Worklogs - mit manueller Nacherfassung und Export."

__all__ = ["DESCRIPTION", "REPO_URL", "AboutDialog", "Zitat", "lade_zitate"]


class AboutDialog(_AboutDialog):
    """Der Info-Dialog der Bibliothek, mit den Angaben dieser Anwendung."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            __app_name__,
            __version__,
            parent,
            autor=__author__,
            jahr=__year__,
            beschreibung=DESCRIPTION,
            repo_url=REPO_URL,
            sprache=current_language(),
        )

"""Zugriff auf die mitgelieferten Symbole.

Die Symbole liegen als SVG je Erscheinungsbild vor (erzeugt von
assets/make_icons.py). Unicode-Glyphen kommen NICHT in Frage: Windows rendert
⚙ oder ◐ als farbige Emoji - verwaschen und nicht einfaerbbar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from jira_timesheet_qt.ui.theme import ICON_DIR, Mode


def icon_path(name: str, mode: Mode) -> Path:
    """Liefert den Pfad zu einem Symbol im passenden Erscheinungsbild."""
    suffix = "dark" if mode is Mode.DARK else "light"
    return ICON_DIR / f"{name}-{suffix}.svg"


def load_icon(name: str, mode: Mode) -> QIcon:
    """Laedt ein Symbol. Fehlt die Datei, kommt ein leeres Symbol zurueck.

    Ein leeres Symbol ist besser als ein Absturz - die Schaltflaeche bleibt
    bedienbar, sie sieht nur nackt aus. Der Test test_about.py deckt ab, dass
    alle erwarteten Dateien vorhanden sind.
    """
    path = icon_path(name, mode)
    return QIcon(str(path)) if path.is_file() else QIcon()

"""Anzeigename und Paketname sind zwei verschiedene Dinge.

Seit dem 26.08.2026 heisst die Anwendung fuer den Anwender "JIRA-Timesheet" -
das steht in Fenstertitel, Info-Dialog und Absturzbericht. Der Paketname bleibt
"jira-timesheet-qt": an ihm haengen Repo, Einstellungsordner, Befehl und
PyPI-Name. Wer die beiden zusammenzieht, verschiebt den Einstellungsordner und
damit die Daten aller Anwender - lautlos, denn eine frische Anwendung legt
einfach einen neuen an und startet mit Vorgaben.
"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtWidgets import QApplication

from jira_timesheet_qt import __app_name__, __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.cache_service import CACHE_DIR
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode


class TestAnzeigename:
    def test_der_fenstertitel_zeigt_den_anzeigenamen(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)

        titel = window.windowTitle()
        assert titel.startswith("JIRA-Timesheet"), titel
        assert "-qt" not in titel, f"der technische Paketname steht im Titel: {titel!r}"
        assert __version__ in titel, "die Version gehoert in den Titel - sie steht auf jedem Screenshot"

    def test_der_anzeigename_traegt_keine_endung(self) -> None:
        assert __app_name__ == "JIRA-Timesheet"


class TestDatenpfade:
    """Die Umbenennung darf die Daten nicht verschieben."""

    def test_der_einstellungsordner_haengt_am_paketnamen(self) -> None:
        """Im eigenen Prozess gemessen - die Test-Isolation biegt SETTINGS_DIR um.

        Ein Test, der hier die gepatchte Klasse befragt, liest den
        Temp-Pfad der Fixture und koennte eine Verschiebung des echten
        Ordners gar nicht bemerken.
        """
        ergebnis = subprocess.run(
            [
                sys.executable,
                "-c",
                "from jira_timesheet_qt.models.settings import Settings; print(Settings.SETTINGS_DIR.name)",
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
        assert ergebnis.returncode == 0, ergebnis.stderr
        assert ergebnis.stdout.strip() == ".jira-timesheet-qt"

    def test_der_zwischenspeicher_liegt_daneben(self) -> None:
        assert CACHE_DIR.parent.name == ".jira-timesheet-qt"

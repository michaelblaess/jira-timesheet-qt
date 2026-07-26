"""Einstiegspunkt der Anwendung.

Absolute Importe, weil Nuitka und PyInstaller dieses Modul als Skript ausfuehren
und __package__ dann leer ist.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from jira_timesheet_qt import __version__

if TYPE_CHECKING:  # nur fuer die Typpruefung - Qt bleibt bis main() ungeladen
    from jira_timesheet_qt.models.settings import Settings
    from jira_timesheet_qt.ui.theme import Mode


def main() -> int:
    """Startet die Anwendung.

    Returns:
        Rueckgabewert des Prozesses.
    """
    parser = argparse.ArgumentParser(
        prog="jira-timesheet-qt",
        description="Stundenzettel aus Jira-Worklogs",
    )
    parser.add_argument("--version", action="version", version=f"jira-timesheet-qt {__version__}")
    parser.add_argument(
        "--theme",
        choices=("system", "dark", "light"),
        default=None,
        help="Erscheinungsbild fuer diesen Start (ueberschreibt die Einstellung nicht dauerhaft)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Startet mit Beispieldaten, ohne Jira zu befragen",
    )
    args = parser.parse_args()

    # Qt erst hier importieren, damit --version und --help ohne Fenster laufen.
    from PySide6.QtWidgets import QApplication

    from jira_timesheet_qt.models.settings import Settings
    from jira_timesheet_qt.ui.fonts import load_fonts
    from jira_timesheet_qt.ui.main_window import MainWindow
    from jira_timesheet_qt.ui.theme import Mode, build_qss

    app = QApplication(sys.argv)
    app.setApplicationName("jira-timesheet-qt")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("michaelblaess")
    # Fusion ist der einzige Qt-Stil, der sich vollstaendig ueber QSS steuern
    # laesst. Die nativen Stile ignorieren einzelne Angaben und lassen die
    # Anwendung je nach Betriebssystem anders aussehen.
    app.setStyle("Fusion")

    settings = Settings.load()
    fonts = load_fonts()
    mode = _resolve_mode(args.theme or settings.theme, app)

    def apply_theme(name: str) -> None:
        """Setzt das Stylesheet der Anwendung neu."""
        app.setStyleSheet(build_qss(Mode(name), fonts.sans, fonts.mono))

    apply_theme(mode.value)

    # Haftungshinweis vor allem anderen. Ohne Zustimmung startet nichts.
    if not _confirm_disclaimer(settings):
        return 0

    window = MainWindow(settings, mode)
    window.theme_changed.connect(apply_theme)

    if args.demo:
        from jira_timesheet_qt.ui.demo import demo_timesheet

        window.set_timesheet(demo_timesheet())
    else:
        window.set_timesheet(None)

    window.show()
    return app.exec()


def _confirm_disclaimer(settings: Settings) -> bool:
    """Holt die Zustimmung zum Haftungshinweis ein, falls sie noch fehlt.

    Args:
        settings:
            Die geladenen Einstellungen, fuer den Speicherort.

    Returns:
        True, wenn die Anwendung starten darf.
    """
    from jira_timesheet_qt import __version__ as version
    from jira_timesheet_qt.ui.disclaimer_dialog import (
        DISCLAIMER_VERSION,
        DisclaimerDialog,
        DisclaimerStore,
    )

    store = DisclaimerStore(settings.SETTINGS_DIR / "disclaimer.json")
    if store.accepted_version == DISCLAIMER_VERSION:
        return True

    dialog = DisclaimerDialog(f"Stundenzettel {version}")
    if dialog.exec() != int(DisclaimerDialog.DialogCode.Accepted):
        return False
    store.record()
    return True


def _resolve_mode(name: str, app: object) -> Mode:
    """Loest "system" in ein konkretes Erscheinungsbild auf.

    Args:
        name:
            Gewuenschtes Erscheinungsbild: system, dark oder light.
        app:
            Die laufende QApplication, fuer die Systemabfrage.

    Returns:
        Das anzuwendende Erscheinungsbild.
    """
    from PySide6.QtCore import Qt as QtCore
    from PySide6.QtGui import QGuiApplication

    from jira_timesheet_qt.ui.theme import Mode

    if name == "dark":
        return Mode.DARK
    if name == "light":
        return Mode.LIGHT

    # Qt 6.5 und neuer kennt das Farbschema des Betriebssystems.
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return Mode.LIGHT if scheme == QtCore.ColorScheme.Light else Mode.DARK
    except (AttributeError, TypeError):
        return Mode.DARK


if __name__ == "__main__":
    sys.exit(main())

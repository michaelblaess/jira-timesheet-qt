"""Einstiegspunkt der Anwendung.

Absolute Importe, weil Nuitka und PyInstaller dieses Modul als Skript ausfuehren
und __package__ dann leer ist.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from jira_timesheet_qt import __author__, __version__

if TYPE_CHECKING:  # nur fuer die Typpruefung - Qt bleibt bis main() ungeladen
    from pathlib import Path

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

    _setup_logging(Settings.SETTINGS_DIR)
    from jira_timesheet_qt.ui.fonts import load_fonts
    from jira_timesheet_qt.ui.main_window import MainWindow
    from jira_timesheet_qt.ui.theme import Mode, build_palette, build_qss, set_accent, set_scale

    app = QApplication(sys.argv)
    app.setApplicationName("jira-timesheet-qt")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("michaelblaess")
    # Fusion ist der einzige Qt-Stil, der sich vollstaendig ueber QSS steuern
    # laesst. Die nativen Stile ignorieren einzelne Angaben und lassen die
    # Anwendung je nach Betriebssystem anders aussehen.
    app.setStyle("Fusion")

    # App-Icon fuer Fenster, Dialoge und Taskleiste - alle Fenster erben es.
    from jira_timesheet_qt.ui.icons import app_icon

    app.setWindowIcon(app_icon())

    settings = Settings.load()

    # Sprachpaket laden, BEVOR Fenster und Dienste t() aufrufen - sonst geben
    # die Uebersetzer nur die Schluessel zurueck (z.B. "jira.budget_unassigned").
    from jira_timesheet_qt.i18n import load_locale

    load_locale(settings.language)

    # Einmalig die manuellen Zeiten der Textual-TUI uebernehmen, falls die
    # eigene Datenbank noch leer ist.
    from pathlib import Path as _Path

    from jira_timesheet_qt.services.manual_entry_service import ManualEntryService

    with ManualEntryService() as _manual:
        _manual.import_from_legacy(_Path.home() / ".jira-timesheet" / "manual-entries.db")

    fonts = load_fonts()
    mode = _resolve_mode(args.theme or settings.theme, app)

    set_accent(settings.accent)
    set_scale(settings.ui_scale)

    def apply_theme(name: str) -> None:
        """Setzt Palette und Stylesheet der Anwendung neu.

        Fusion faerbt die nativen Steuerelemente ueber die Palette, das duenne
        QSS uebernimmt nur die strukturellen Flaechen und die Typografie. Die
        Akzentfarbe wird zuvor ueber set_accent gesetzt (siehe MainWindow).
        """
        mode = Mode(name)
        app.setPalette(build_palette(mode))
        app.setStyleSheet(build_qss(mode, fonts.sans, fonts.mono))

    apply_theme(mode.value)

    # Haftungshinweis vor allem anderen. Ohne Zustimmung startet nichts.
    if not _confirm_disclaimer(settings):
        return 0

    window = MainWindow(settings, mode)
    window.theme_changed.connect(apply_theme)

    # Fehlerdialog statt wortlosem Abbruch - PySide6 beendet den Prozess sonst.
    from jira_timesheet_qt.ui import crash_guard

    crash_guard.install(window)

    if args.demo:
        from jira_timesheet_qt.ui.demo import demo_timesheet

        window.set_timesheet(demo_timesheet())
    else:
        window.set_timesheet(None)

    window.show()
    if not args.demo:
        window.start_initial_load()
    return app.exec()


def _setup_logging(log_dir: Path) -> None:
    """Richtet ein persistentes, rotierendes Datei-Log ein.

    Ohne das gehen alle logger-Aufrufe (Einstellungen, Jira-Client, ...) ins
    Leere - fuer die Fehlersuche unbrauchbar. Das Log liegt neben den
    Einstellungen und laesst sich im Speicherort-Tab oeffnen.

    Args:
        log_dir:
            Verzeichnis fuer die Logdatei (wird bei Bedarf angelegt).
    """
    import logging
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    if root.handlers:
        return  # schon eingerichtet (z.B. im Test)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        return  # kein Log ist besser als ein Absturz beim Start

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"),
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _confirm_disclaimer(settings: Settings) -> bool:
    """Holt die Zustimmung zum Haftungshinweis ein, falls sie noch fehlt.

    Args:
        settings:
            Die geladenen Einstellungen, fuer den Speicherort.

    Returns:
        True, wenn die Anwendung starten darf.
    """
    from jira_timesheet_qt import __app_name__ as app_name
    from jira_timesheet_qt import __version__ as version
    from jira_timesheet_qt.ui.disclaimer_dialog import (
        DISCLAIMER_VERSION,
        DUTIES,
        INTRO,
        DisclaimerDialog,
        DisclaimerStore,
    )

    store = DisclaimerStore(settings.SETTINGS_DIR / "disclaimer.json")
    if store.accepted_version == DISCLAIMER_VERSION:
        return True

    dialog = DisclaimerDialog(
        f"{app_name} {version}",
        autor=__author__,
        intro=INTRO,
        duties=DUTIES,
    )
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

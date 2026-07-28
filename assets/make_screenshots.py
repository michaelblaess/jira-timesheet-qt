"""Erzeugt die Screenshots in docs/screenshots neu.

Bewusst mit BLANKEN Settings() (keine echten Zugangsdaten im Bild) und den
Demodaten. Laeuft auf der echten Qt-Plattform - die Offscreen-Plattform kennt
keine Systemschriften und liefert leere Kaesten. Die Fenster werden mit
WA_DontShowOnScreen unsichtbar aufgebaut und per grab() abgelichtet.

Aufruf:  uv run python assets/make_screenshots.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# VOR dem Qt-Import: sicherstellen, dass NICHT die Offscreen-Plattform greift
# (die haette keine Schriften). Ein evtl. aus der Testumgebung gesetztes
# QT_QPA_PLATFORM=offscreen wird hier entfernt.
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QWidget  # noqa: E402

from jira_timesheet_qt.i18n import load_locale  # noqa: E402
from jira_timesheet_qt.models.settings import Settings  # noqa: E402
from jira_timesheet_qt.ui.about_dialog import AboutDialog  # noqa: E402
from jira_timesheet_qt.ui.demo import demo_timesheet  # noqa: E402
from jira_timesheet_qt.ui.detail_dialog import TicketDetailDialog  # noqa: E402
from jira_timesheet_qt.ui.disclaimer_dialog import DisclaimerDialog  # noqa: E402
from jira_timesheet_qt.ui.fonts import load_fonts  # noqa: E402
from jira_timesheet_qt.ui.main_window import MainWindow  # noqa: E402
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog  # noqa: E402
from jira_timesheet_qt.ui.theme import Mode, build_palette, build_qss  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def _grab(widget: QWidget, path: Path, width: int, height: int) -> None:
    """Baut ein Widget unsichtbar auf und speichert ein Bildschirmfoto."""
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()
    widget.grab().save(str(path))
    widget.close()


def _grab_combo_popup(path: Path) -> None:
    """Klappt ein gestyltes Auswahlfeld auf und lichtet das Popup ab."""
    combo = QComboBox()
    combo.addItems(["Sachsen", "Bayern", "Berlin", "Brandenburg", "Hamburg", "Hessen"])
    combo.setFixedWidth(240)
    combo.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    combo.show()
    QApplication.processEvents()
    combo.showPopup()
    QApplication.processEvents()
    QApplication.processEvents()
    view = combo.view()
    popup = view.window() if view is not None else None
    if popup is not None:
        popup.grab().save(str(path))
    combo.hidePopup()
    combo.close()


def _window(mode: Mode, *, with_data: bool = True) -> MainWindow:
    """Erzeugt ein Hauptfenster mit Demodaten (oder leer), flache Liste."""
    win = MainWindow(Settings(), mode)
    # Deterministisch die flache Liste zeigen - der Gruppierzustand kommt sonst
    # aus der Registry und schwankt zwischen Rechnern.
    win._grouped = False
    win.set_timesheet(demo_timesheet() if with_data else None)
    return win


def _apply_theme(app: QApplication, mode: Mode, sans: str, mono: str) -> None:
    app.setPalette(build_palette(mode))
    app.setStyleSheet(build_qss(mode, sans, mono))


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    fonts = load_fonts()
    # Sprachpaket laden, damit die Menueleiste "Datei/Ansicht/..." zeigt statt
    # der rohen i18n-Schluessel (t() gibt sonst den Schluessel zurueck).
    load_locale(Settings().language)
    OUT.mkdir(parents=True, exist_ok=True)

    W, H = 1480, 840
    for mode, tag in ((Mode.DARK, "dark"), (Mode.LIGHT, "light")):
        _apply_theme(app, mode, fonts.sans, fonts.mono)

        # Hauptfenster - Liste (README-Aufmacher)
        win = _window(mode)
        win._tabs.setCurrentIndex(0)
        _grab(win, OUT / f"main-{tag}.png", W, H)

        # Kalender
        win = _window(mode)
        win._tabs.setCurrentIndex(1)
        _grab(win, OUT / f"calendar-{tag}.png", W, H)

        # Jahresansicht
        win = _window(mode)
        win._tabs.setCurrentIndex(2)
        _grab(win, OUT / f"year-{tag}.png", W, H)

        # Meldungsfenster sichtbar
        win = _window(mode)
        win._tabs.setCurrentIndex(0)
        win._log.setVisible(True)
        _grab(win, OUT / f"log-{tag}.png", W, H)

        # Ticket-Detail-Dialog (modal) - ersetzt den frueheren Detailbereich
        entry = demo_timesheet().all_entries[0]
        _grab(TicketDetailDialog(entry, "https://beispiel.atlassian.net"), OUT / f"detail-{tag}.png", 540, 520)

        # Einstellungen - Arbeitszeit
        dlg = SettingsDialog(Settings())
        dlg._nav.setCurrentRow(1)
        _grab(dlg, OUT / f"settings-worktime-{tag}.png", 760, 560)

        # Info-Dialog
        _grab(AboutDialog(), OUT / f"about-{tag}.png", 520, 560)

        # Aufgeklapptes Auswahlfeld (gestyltes QComboBox-Popup)
        _grab_combo_popup(OUT / f"combo-popup-{tag}.png")

    # Nur-Dunkel-Bilder
    _apply_theme(app, Mode.DARK, fonts.sans, fonts.mono)

    # Leerzustand
    win = _window(Mode.DARK, with_data=False)
    win._stack.setCurrentIndex(0)
    _grab(win, OUT / "empty-dark.png", W, H)

    # Einstellungen - Zugang (blank, ohne echte Daten)
    dlg = SettingsDialog(Settings())
    dlg._nav.setCurrentRow(0)
    _grab(dlg, OUT / "settings-dark.png", 760, 560)

    # Haftungshinweis
    _grab(DisclaimerDialog("jira-timesheet-qt"), OUT / "disclaimer-dark.png", 640, 620)

    print("Screenshots erzeugt in", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

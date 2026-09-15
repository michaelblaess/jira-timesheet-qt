"""Tests fuer den Info-Dialog und die eigenen Symbole."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from jira_timesheet_qt import __author__, __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.about_dialog import DESCRIPTION, REPO_URL, AboutDialog
from jira_timesheet_qt.ui.icons import GLYPHS, load_icon
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode, build_qss


def _label_text(dialog: AboutDialog) -> str:
    """Sammelt den sichtbaren Text aller Beschriftungen eines Dialogs."""
    return " ".join(label.text() for label in dialog.findChildren(QLabel))


class TestAboutDialog:
    def test_shows_description(self, qapp: QApplication) -> None:
        """Die Beschreibung dieser Anwendung, nicht die einer anderen."""
        dialog = AboutDialog()
        assert DESCRIPTION in _label_text(dialog)

    def test_shows_version_and_author(self, qapp: QApplication) -> None:
        dialog = AboutDialog()
        joined = _label_text(dialog)
        assert __version__ in joined
        assert __author__ in joined
        assert "BUSL-1.1" in joined

    def test_links_are_present(self, qapp: QApplication) -> None:
        dialog = AboutDialog()
        joined = _label_text(dialog)
        assert REPO_URL in joined
        assert "michaelblaess.de" in joined

    def test_close_button_exists(self, qapp: QApplication) -> None:
        # Der Dialog MUSS an eine Variable: ohne Referenz raeumt der
        # Speicherbereiniger das C++-Objekt ab, waehrend der Python-Wrapper
        # noch lebt - "Internal C++ object already deleted".
        dialog = AboutDialog()
        buttons = [b.text() for b in dialog.findChildren(QPushButton)]
        assert "Schließen" in buttons


class TestIcons:
    def test_every_glyph_renders_in_both_modes(self, qapp: QApplication) -> None:
        """Jeder App-Symbolname muss ueber QtAwesome ein Icon liefern.

        Ein unbekannter mdi6-Name gaebe ein leeres QIcon - dann bliebe die
        Schaltflaeche leer.
        """
        # Die erwarteten Namen und ihre mdi6-Glyphen liegen in GLYPHS.
        assert "group" in GLYPHS and "refresh" in GLYPHS  # Vollstaendigkeit stichprobenartig
        for name in GLYPHS:
            for mode in (Mode.DARK, Mode.LIGHT):
                assert not load_icon(name, mode).isNull(), f"{name} ({mode.value})"

    def test_jedes_menuesymbol_existiert_und_keins_doppelt(self, qapp: QApplication) -> None:
        """Die Symbole aus menu.json laufen ueber _menu_icon, und das schweigt.

        Ein unbekannter Name gaebe dort wortlos ein leeres Icon. Und zwei
        Befehle mit demselben Glyph waeren in der Leiste nicht zu unterscheiden -
        bis 09/2026 sahen sich Ticket-Details und Log schon bei zwei aehnlichen
        Glyphen (card-text-outline, text-box-outline) zum Verwechseln aehnlich.
        """
        import json
        from pathlib import Path
        from typing import Any

        import qtawesome as qta

        import jira_timesheet_qt

        pfad = Path(jira_timesheet_qt.__file__).parent / "resources" / "menu.json"
        symbole: list[str] = []

        def sammeln(knoten: Any) -> None:
            if isinstance(knoten, dict):
                if isinstance(knoten.get("icon"), str):
                    symbole.append(knoten["icon"])
                for wert in knoten.values():
                    sammeln(wert)
            elif isinstance(knoten, list):
                for eintrag in knoten:
                    sammeln(eintrag)

        sammeln(json.loads(pfad.read_text(encoding="utf-8")))
        assert len(symbole) >= 8, symbole
        for name in symbole:
            assert not qta.icon(name, color="#000000").isNull(), name
        doppelt = sorted({name for name in symbole if symbole.count(name) > 1})
        assert not doppelt, doppelt

    def test_toolbar_month_buttons_carry_icons(self, qapp: QApplication) -> None:
        """Die Monatspfeile in der Toolbar tragen Symbole, keine Text-Glyphen."""
        from jira_timesheet_qt.models.settings import Settings
        from jira_timesheet_qt.ui.main_window import MainWindow

        window = MainWindow(Settings(), Mode.DARK)
        for button in (window._prev_button, window._next_button):
            assert not button.icon().isNull()
            assert button.text() == "", "Symbole statt Text-Glyphen"

    def test_stylesheet_has_no_dangling_icon_urls(self) -> None:
        """Jede url() im Stylesheet muss auf eine vorhandene Datei zeigen.

        Seit dem Wechsel auf den nativen Fusion-Look (E1) zeichnet Qt die Pfeile
        der Steuerelemente selbst - das QSS enthaelt in der Regel keine url()
        mehr. Kommt doch eine dazu, darf sie nicht ins Leere zeigen.
        """
        import re
        from pathlib import Path

        for mode in (Mode.DARK, Mode.LIGHT):
            qss = build_qss(mode, "Segoe UI", "Consolas")
            for url in re.findall(r"url\(([^)]+)\)", qss):
                assert Path(url).is_file(), url


class TestAboutReachable:
    def test_window_can_open_about(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        assert hasattr(window, "open_about")
        assert "help.about" in window._commands.ids()

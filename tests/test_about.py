"""Tests fuer den Info-Dialog und die eigenen Symbole."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from jira_timesheet_qt import __author__, __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.about_dialog import QUOTES, AboutDialog
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import ICON_DIR, Mode, build_qss


def _label_text(dialog: AboutDialog) -> str:
    """Sammelt den sichtbaren Text aller Beschriftungen eines Dialogs."""
    return " ".join(label.text() for label in dialog.findChildren(QLabel))


class TestAboutDialog:
    def test_shows_version_and_author(self, qapp: QApplication) -> None:
        dialog = AboutDialog()
        joined = _label_text(dialog)
        assert __version__ in joined
        assert __author__ in joined
        assert "Apache-2.0" in joined

    def test_links_are_present(self, qapp: QApplication) -> None:
        dialog = AboutDialog()
        joined = _label_text(dialog)
        assert "github.com/michaelblaess/jira-timesheet-qt" in joined
        assert "michaelblaess.de" in joined

    def test_every_quote_has_an_author(self) -> None:
        assert QUOTES
        for quote in QUOTES:
            assert quote.text.strip()
            assert quote.author.strip()

    def test_quote_comes_from_the_pool(self, qapp: QApplication) -> None:
        """Auch bei zufaelliger Auswahl darf nichts Fremdes erscheinen."""
        pool = {q.text for q in QUOTES}
        for _ in range(20):
            assert AboutDialog._pick_quote().text in pool

    def test_close_button_exists(self, qapp: QApplication) -> None:
        # Der Dialog MUSS an eine Variable: ohne Referenz raeumt der
        # Speicherbereiniger das C++-Objekt ab, waehrend der Python-Wrapper
        # noch lebt - "Internal C++ object already deleted".
        dialog = AboutDialog()
        buttons = [b.text() for b in dialog.findChildren(QPushButton)]
        assert "Schließen" in buttons


class TestIcons:
    def test_all_icon_files_exist(self) -> None:
        """Fehlt eine Datei, bleibt die Schaltflaeche leer."""
        names = (
            "chevron-down", "chevron-up", "chevron-left", "chevron-right",
            "info", "settings", "sun", "moon", "search", "refresh", "log", "plus",
        )
        for name in names:
            for variant in ("dark", "light"):
                assert (ICON_DIR / f"{name}-{variant}.svg").is_file(), f"{name}-{variant}"

    def test_header_buttons_carry_icons(self, qapp: QApplication) -> None:
        """Kein Knopf darf leer bleiben - Unicode-Glyphen sind hier verboten."""
        from PySide6.QtWidgets import QPushButton

        from jira_timesheet_qt.ui.header import Header

        header = Header(Mode.DARK)
        buttons = header.findChildren(QPushButton)
        # Das Suchfeld bringt eine eigene Loesch-Schaltflaeche mit.
        icon_buttons = [b for b in buttons if b.toolTip()]
        assert len(icon_buttons) == 8
        for button in icon_buttons:
            assert not button.icon().isNull(), button.toolTip()
            assert button.text() == "", "Symbole statt Text-Glyphen"

    def test_theme_switch_swaps_the_icons(self, qapp: QApplication) -> None:
        """Beim Wechsel muss das Gegenstueck angeboten werden."""
        from jira_timesheet_qt.ui.header import Header

        header = Header(Mode.DARK)
        assert header._theme_icon() == "sun"
        header.apply_mode(Mode.LIGHT)
        assert header._theme_icon() == "moon"

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
        assert window._header.about_requested is not None

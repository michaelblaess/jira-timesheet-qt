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
        """Fehlt eine Datei, zeichnet Qt wieder seine Standardpfeile."""
        for name in (
            "chevron-down-dark.svg",
            "chevron-down-light.svg",
            "chevron-up-dark.svg",
            "chevron-up-light.svg",
        ):
            assert (ICON_DIR / name).is_file(), name

    def test_stylesheet_points_at_existing_files(self) -> None:
        """Jede url() im Stylesheet muss auf eine vorhandene Datei zeigen."""
        import re

        for mode in (Mode.DARK, Mode.LIGHT):
            qss = build_qss(mode, "Segoe UI", "Consolas")
            urls = re.findall(r"url\(([^)]+)\)", qss)
            assert urls, "keine Symbole im Stylesheet"
            for url in urls:
                from pathlib import Path

                assert Path(url).is_file(), url

    def test_arrows_are_styled_for_both_widgets(self) -> None:
        qss = build_qss(Mode.DARK, "Segoe UI", "Consolas")
        for selector in (
            "QComboBox::down-arrow",
            "QSpinBox::up-arrow",
            "QDoubleSpinBox::down-arrow",
        ):
            assert selector in qss, selector


class TestAboutReachable:
    def test_window_can_open_about(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        assert hasattr(window, "open_about")
        assert window._header.about_requested is not None

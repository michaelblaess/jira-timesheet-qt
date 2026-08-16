"""Tests fuer den Info-Dialog und die eigenen Symbole."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from jira_timesheet_qt import __author__, __version__
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.about_dialog import AboutDialog, load_quotes
from jira_timesheet_qt.ui.icons import GLYPHS, load_icon
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode, build_qss


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

    def test_every_quote_has_an_author_and_source(self) -> None:
        """Ohne benennbare Quelle darf kein Zitat in den Dialog."""
        for lang in ("de", "en"):
            pool = load_quotes(lang)
            assert pool, lang
            for quote in pool:
                assert quote.text.strip()
                assert quote.author.strip()
                assert quote.source.strip()

    def test_quote_comes_from_the_pool(self, qapp: QApplication) -> None:
        """Auch bei zufaelliger Auswahl darf nichts Fremdes erscheinen."""
        pool = {q.text for q in load_quotes()}
        for _ in range(20):
            quote = AboutDialog._pick_quote()
            assert quote is not None
            assert quote.text in pool

    def test_no_copyrighted_author_in_the_pool(self) -> None:
        """Nur gemeinfreie Autoren - der Schutz endet 70 Jahre nach dem Tod (§ 64 UrhG).

        Die Namen unten sind die, die inhaltlich gepasst haetten und deshalb
        immer wieder hereinrutschen. Martin Luther King ist bis Ende 2038
        geschuetzt und stand bis August 2026 fest im Code dieses Dialogs.
        """
        gesperrt = ("martin luther king", "albert schweitzer", "c.s. lewis", "corrie ten boom", "martin fowler")
        for lang in ("de", "en"):
            for quote in load_quotes(lang):
                autor = quote.author.casefold()
                for name in gesperrt:
                    assert name not in autor, f"{quote.author} ist nicht gemeinfrei ({lang})"

    def test_pool_carries_a_rights_statement(self) -> None:
        """Jeder Eintrag der Paketdatei sagt, warum er verwendet werden darf."""
        import json
        from importlib import resources

        raw = (resources.files("jira_timesheet_qt") / "quotes" / "quotes.json").read_text(encoding="utf-8")
        eintraege = json.loads(raw)["zitate"]
        assert eintraege
        for eintrag in eintraege:
            assert eintrag.get("rechte", "").strip(), eintrag.get("autor")

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

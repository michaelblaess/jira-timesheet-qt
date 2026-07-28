"""Tests fuer die Such-Hervorhebung in der Tabelle."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.highlight_delegate import HighlightDelegate
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode


class TestHighlightHtml:
    def test_without_needle_returns_escaped_text(self) -> None:
        assert HighlightDelegate.highlight_html("PROJ-17301", "") == "PROJ-17301"

    def test_escapes_html_special_characters(self) -> None:
        assert HighlightDelegate.highlight_html("<b> & </b>", "") == "&lt;b&gt; &amp; &lt;/b&gt;"

    def test_wraps_a_match_in_a_span(self) -> None:
        result = HighlightDelegate.highlight_html("PROJ-17301", "17301")
        assert "<span" in result
        assert "17301</span>" in result
        # Der uebrige Text bleibt erhalten.
        assert result.startswith("PROJ-")

    def test_match_is_case_insensitive(self) -> None:
        result = HighlightDelegate.highlight_html("Beispiel Advisory", "beispiel")
        assert "<span" in result
        # Die Original-Gross-/Kleinschreibung des Treffers bleibt erhalten.
        assert ">Beispiel</span>" in result

    def test_no_match_leaves_text_unmarked(self) -> None:
        assert HighlightDelegate.highlight_html("PROJ-17301", "xyz") == "PROJ-17301"


class TestSearchWiring:
    def test_search_sets_the_needle(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_search_changed("PROJ")
        assert window._highlight._needle == "PROJ"
        # Der Filter des Proxys folgt derselben Eingabe.
        assert window._proxy.filterRegularExpression().pattern() != ""

    def test_clearing_search_clears_the_needle(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_search_changed("PROJ")
        window._on_search_changed("")
        assert window._highlight._needle == ""

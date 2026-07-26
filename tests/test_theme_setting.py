"""Tests fuer die Theme-Einstellung.

Der Kern stammt aus der Textual-TUI, wo das Theme ein Retro-Theme-Slug war
("brotkasten", "textual-dark", ...). In der GUI gibt es nur noch system, dark
und light. Eine aus der TUI uebernommene Einstellungsdatei darf die Anwendung
deshalb nicht mit einem unbekannten Theme starten lassen.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jira_timesheet_qt.models.settings import DEFAULT_THEME, THEMES, Settings


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Verlegt die Einstellungsdatei, damit die echte unberuehrt bleibt."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", path)
    return path


def _write(path: Path, theme: object) -> None:
    path.write_text(json.dumps({"theme": theme}), encoding="utf-8")


class TestThemeSetting:
    def test_default_is_system(self) -> None:
        assert Settings().theme == DEFAULT_THEME == "system"

    @pytest.mark.parametrize("theme", THEMES)
    def test_known_themes_survive_a_roundtrip(self, _isolated_settings: Path, theme: str) -> None:
        _write(_isolated_settings, theme)
        assert Settings.load().theme == theme

    @pytest.mark.parametrize("theme", ["brotkasten", "textual-dark", "gulf-racing", ""])
    def test_textual_theme_falls_back(self, _isolated_settings: Path, theme: str) -> None:
        """Ein Retro-Theme aus der TUI ist hier bedeutungslos."""
        _write(_isolated_settings, theme)
        assert Settings.load().theme == DEFAULT_THEME

    @pytest.mark.parametrize("theme", [None, 42, [], {}])
    def test_broken_value_falls_back(self, _isolated_settings: Path, theme: object) -> None:
        """Eine kaputte Datei darf den Start nicht verhindern."""
        _write(_isolated_settings, theme)
        assert Settings.load().theme == DEFAULT_THEME

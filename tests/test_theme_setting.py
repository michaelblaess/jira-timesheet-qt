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


class TestColorScheme:
    """Das Retro-Farbschema - ein zweites Feld neben dem Erscheinungsbild.

    Die beiden auseinanderzuhalten ist hier die halbe Miete: `theme` ist in
    dieser Anwendung seit jeher hell/dunkel/System, das Farbschema steht
    unter `color_scheme`. Ein Textual-Name wie "brotkasten" gehoert also ins
    zweite Feld und muss im ersten weiterhin verworfen werden.
    """

    def test_ohne_angabe_gilt_die_standardpalette(self) -> None:
        assert Settings().color_scheme == ""

    def test_die_wahl_ueberlebt_den_neustart(self, _isolated_settings: Path) -> None:
        s = Settings()
        s.color_scheme = "brotkasten"
        s.save()
        assert Settings.load().color_scheme == "brotkasten"

    def test_eine_datei_ohne_farbschema_bleibt_lesbar(self, _isolated_settings: Path) -> None:
        """Jede Einstellungsdatei von vor 09/2026 hat das Feld nicht."""
        _isolated_settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        geladen = Settings.load()
        assert geladen.color_scheme == ""
        assert geladen.theme == "dark"

    def test_die_beiden_felder_kommen_sich_nicht_ins_gehege(
        self, _isolated_settings: Path
    ) -> None:
        """Der Kern des Ganzen: ein Retro-Name im falschen Feld faellt weiter durch."""
        _isolated_settings.write_text(
            json.dumps({"theme": "brotkasten", "color_scheme": "warp"}), encoding="utf-8"
        )
        geladen = Settings.load()
        assert geladen.theme == DEFAULT_THEME, "Ein Retro-Name ist kein Erscheinungsbild"
        assert geladen.color_scheme == "warp"

    def test_das_feld_wird_auch_wirklich_geschrieben(self, _isolated_settings: Path) -> None:
        """Fehlt es in _FIELDS, geht die Wahl beim Speichern lautlos verloren."""
        s = Settings()
        s.color_scheme = "minty"
        s.save()
        roh = json.loads(_isolated_settings.read_text(encoding="utf-8"))
        assert roh["color_scheme"] == "minty"

    def test_ein_gewaehltes_schema_ueberlebt_die_einfuehrung_des_schalters(
        self, _isolated_settings: Path
    ) -> None:
        """Wer eines gewählt hatte, wollte es auch sehen.

        Ohne diese Regel wäre es nach dem Update kommentarlos verschwunden.
        """
        _isolated_settings.write_text(
            json.dumps({"theme": "dark", "color_scheme": "marley"}), encoding="utf-8"
        )
        geladen = Settings.load()
        assert geladen.color_scheme == "marley"
        assert geladen.use_color_scheme is True

    def test_ohne_schema_bleibt_der_schalter_aus(self, _isolated_settings: Path) -> None:
        """Gegenprobe - die Wanderung darf niemanden ungefragt beglücken."""
        _isolated_settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        assert Settings.load().use_color_scheme is False

    def test_der_schalter_ueberlebt_den_neustart(self, _isolated_settings: Path) -> None:
        s = Settings()
        s.color_scheme = "warp"
        s.use_color_scheme = True
        s.save()
        geladen = Settings.load()
        assert geladen.use_color_scheme is True
        assert geladen.color_scheme == "warp"

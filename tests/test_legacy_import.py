"""Tests fuer die Uebernahme der Einstellungen aus der Textual-TUI.

Die aeltere TUI "jira-timesheet" legt ihre Einstellungen unter
~/.jira-timesheet/settings.json ab - mit denselben Feldnamen wie die GUI.
Beim ersten Start soll die GUI diese Werte uebernehmen, damit der Jira-Zugang
nicht erneut eingegeben werden muss. Zusaetzlich gibt es einen ausdruecklichen
Import-Knopf, der NUR die Zugangsfelder liefert.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import jira_timesheet_qt.models.settings as settings_module
from jira_timesheet_qt.models.settings import ACCESS_FIELDS, Settings

# Ein realistischer Auszug aus einer TUI-Einstellungsdatei. Das Theme ist ein
# Retro-Slug, das Data-Center-Feld gesetzt - beides muss sauber ankommen.
_LEGACY = {
    "theme": "brotkasten",
    "jira_host": "https://firma.atlassian.net",
    "email": "max.muster@firma.de",
    "jira_token": "geheim-123",
    "use_legacy_api": True,
    "proxy_url": "http://proxy:8080",
    "budget_field": "customfield_99999",
    "hours_per_day": 7.5,
    "federal_state": "BY",
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Verlegt eigene UND Legacy-Datei, damit die echten unberuehrt bleiben."""
    own = tmp_path / "settings.json"
    legacy = tmp_path / "legacy" / "settings.json"
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", own)
    monkeypatch.setattr(settings_module, "LEGACY_SETTINGS_FILE", legacy)
    return own, legacy


def _write_legacy(legacy: Path) -> None:
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps(_LEGACY), encoding="utf-8")


class TestAutoImport:
    def test_first_start_adopts_legacy(self, _isolated: tuple[Path, Path]) -> None:
        """Ohne eigene Datei werden die TUI-Werte uebernommen."""
        _own, legacy = _isolated
        _write_legacy(legacy)

        s = Settings.load()

        assert s.jira_host == "https://firma.atlassian.net"
        assert s.jira_token == "geheim-123"
        assert s.use_legacy_api is True
        assert s.budget_field == "customfield_99999"
        assert s.hours_per_day == 7.5
        # Der Retro-Theme-Slug ist hier bedeutungslos und faellt zurueck.
        assert s.theme == "system"

    def test_own_file_wins_over_legacy(self, _isolated: tuple[Path, Path]) -> None:
        """Existiert eine eigene Datei, wird die Legacy-Datei ignoriert."""
        own, legacy = _isolated
        _write_legacy(legacy)
        own.write_text(json.dumps({"jira_host": "https://eigen.example"}), encoding="utf-8")

        assert Settings.load().jira_host == "https://eigen.example"

    def test_no_legacy_gives_defaults(self, _isolated: tuple[Path, Path]) -> None:
        """Ohne beide Dateien starten die Vorgaben."""
        assert Settings.load().jira_host == ""

    def test_own_empty_access_is_not_silently_healed(self, _isolated: tuple[Path, Path]) -> None:
        """Eigene Datei ohne Zugang wird NICHT still aus der TUI aufgefuellt.

        Bewusst: ein stiller Backfill wuerde den eigentlichen Fehler verdecken.
        """
        own, legacy = _isolated
        _write_legacy(legacy)
        own.write_text(json.dumps({"federal_state": "BE"}), encoding="utf-8")

        s = Settings.load()

        assert s.jira_host == ""
        assert s.jira_token == ""
        assert s.federal_state == "BE"


class TestSaveGuard:
    """Der Datenverlust-Schutz beim Speichern."""

    def test_blanking_access_is_prevented(self, _isolated: tuple[Path, Path]) -> None:
        """Ein Speichern mit leerem Zugang darf einen vorhandenen nicht loeschen."""
        own, _legacy = _isolated
        # Vorher: Datei mit gueltigem Zugang.
        Settings(jira_host="https://h", email="e@x.de", jira_token="TOK").save()
        assert Settings.load().jira_host == "https://h"

        # Jetzt: ein Objekt OHNE Zugang speichern (simuliert den Fehler).
        Settings(federal_state="BE").save()

        s = Settings.load()
        assert s.jira_host == "https://h"  # bewahrt
        assert s.jira_token == "TOK"

    def test_blanking_is_logged(self, _isolated: tuple[Path, Path], caplog: pytest.LogCaptureFixture) -> None:
        """Der verhinderte Datenverlust landet als Warnung im Log."""
        Settings(jira_host="https://h", email="e@x.de", jira_token="TOK").save()
        with caplog.at_level("WARNING"):
            Settings(federal_state="BE").save()
        assert any("DATENVERLUST VERHINDERT" in r.message for r in caplog.records)

    def test_intentional_change_still_saves(self, _isolated: tuple[Path, Path]) -> None:
        """Ein Speichern MIT Zugang schreibt normal (kein Fehlalarm)."""
        Settings(jira_host="https://a", email="a@x.de", jira_token="T1").save()
        Settings(jira_host="https://b", email="b@x.de", jira_token="T2", federal_state="BE").save()
        s = Settings.load()
        assert s.jira_host == "https://b"
        assert s.federal_state == "BE"


class TestExplicitAccessImport:
    def test_access_only(self, _isolated: tuple[Path, Path]) -> None:
        """Der Knopf liefert genau die Zugangsfelder - nicht mehr."""
        _own, legacy = _isolated
        _write_legacy(legacy)

        access = Settings.legacy_access()

        assert access is not None
        assert set(access.keys()) == set(ACCESS_FIELDS)
        assert access["jira_host"] == "https://firma.atlassian.net"
        assert access["use_legacy_api"] is True
        # Arbeitszeit gehoert NICHT dazu.
        assert "hours_per_day" not in access

    def test_none_without_legacy(self, _isolated: tuple[Path, Path]) -> None:
        assert Settings.legacy_access() is None

    def test_legacy_available_flag(self, _isolated: tuple[Path, Path]) -> None:
        _own, legacy = _isolated
        assert Settings.legacy_available() is False
        _write_legacy(legacy)
        assert Settings.legacy_available() is True

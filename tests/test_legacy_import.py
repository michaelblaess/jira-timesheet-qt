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
from jira_timesheet_qt.models.settings import ACCESS_FIELDS, CALC_FIELDS, MAX_BACKUPS, Settings

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
    "hourly_rate": 95.0,
    "vat_rate": 19.0,
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

    def test_partial_blanking_preserves_other_core_fields(self, _isolated: tuple[Path, Path]) -> None:
        """Nur-Host-Speichern darf E-Mail/Token nicht leeren (der echte Datenverlust).

        Frueher deckte ein gesetzter Host das stille Loeschen von E-Mail und
        Token - genau so gingen sie einmal in der echten Datei verloren.
        """
        Settings(jira_host="https://h", email="e@x.de", jira_token="TOK").save()
        Settings(jira_host="https://h2").save()  # nur Host, Rest leer
        s = Settings.load()
        assert s.jira_host == "https://h2"  # geaenderter Host kommt durch
        assert s.email == "e@x.de"  # bewahrt
        assert s.jira_token == "TOK"  # bewahrt

    def test_blanking_single_core_field_is_logged(
        self, _isolated: tuple[Path, Path], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Auch das Leeren eines EINZELNEN Kernfelds landet als Warnung im Log."""
        Settings(jira_host="https://h", email="e@x.de", jira_token="TOK").save()
        with caplog.at_level("WARNING"):
            Settings(jira_host="https://h", email="e@x.de").save()  # Token leer
        assert any("DATENVERLUST VERHINDERT" in r.message for r in caplog.records)


class TestBackup:
    """Sicherung, atomares Schreiben und goldene Kopie beim Speichern."""

    def _full(self, **extra: object) -> Settings:
        return Settings(jira_host="https://h", email="e@x.de", jira_token="TOK", **extra)

    def test_keeps_only_max_backups(self, _isolated: tuple[Path, Path]) -> None:
        """Es werden hoechstens MAX_BACKUPS Sicherungen aufgehoben."""
        for i in range(MAX_BACKUPS + 3):
            self._full(budget_field=f"cf_{i}").save()  # jeweils anderer Inhalt
        assert len(Settings._backups()) == MAX_BACKUPS

    def test_identical_saves_dedupe(self, _isolated: tuple[Path, Path]) -> None:
        """Unveraenderte Speicherungen legen keine weiteren gleichen Sicherungen an."""
        self._full().save()
        self._full().save()
        self._full().save()
        assert len(Settings._backups()) == 1

    def test_atomic_write_leaves_no_tmp(self, _isolated: tuple[Path, Path]) -> None:
        self._full().save()
        tmp = Settings.SETTINGS_FILE.with_name(f"{Settings.SETTINGS_FILE.name}.tmp")
        assert not tmp.exists()

    def test_lastgood_only_with_full_access(self, _isolated: tuple[Path, Path]) -> None:
        Settings(jira_host="https://h").save()  # Zugang unvollstaendig
        assert not Settings._lastgood_file().is_file()
        self._full().save()
        assert Settings._lastgood_file().is_file()

    def test_recovers_access_from_backup(self, _isolated: tuple[Path, Path]) -> None:
        """Nach einem geleerten Zugang findet die Wiederherstellung ihn in der Sicherung."""
        self._full().save()  # schreibt goldene Kopie
        # Hauptdatei von aussen leeren (Korruption/Fehledit simulieren).
        Settings.SETTINGS_FILE.write_text(json.dumps({"jira_host": "https://h"}), encoding="utf-8")
        loaded = Settings.load()
        assert not (loaded.email and loaded.jira_token)  # Zugang tatsaechlich weg

        recovered = Settings.latest_access_backup()
        assert recovered is not None
        _label, data = recovered
        assert data["jira_token"] == "TOK"
        assert data["email"] == "e@x.de"

    def test_no_backup_without_access(self, _isolated: tuple[Path, Path]) -> None:
        assert Settings.latest_access_backup() is None


class TestExplicitAccessImport:
    def test_access_and_calculation(self, _isolated: tuple[Path, Path]) -> None:
        """Der Knopf liefert Zugang UND Berechnung (Stundensatz, MwSt, Arbeitszeit)."""
        _own, legacy = _isolated
        _write_legacy(legacy)

        data = Settings.legacy_access()

        assert data is not None
        assert set(data.keys()) == set(ACCESS_FIELDS) | set(CALC_FIELDS)
        assert data["jira_host"] == "https://firma.atlassian.net"
        assert data["use_legacy_api"] is True
        # Berechnung kommt jetzt mit - sonst blieben Netto/Brutto leer.
        assert data["hours_per_day"] == 7.5
        assert data["hourly_rate"] == 95.0
        assert data["vat_rate"] == 19.0
        assert data["federal_state"] == "BY"

    def test_none_without_legacy(self, _isolated: tuple[Path, Path]) -> None:
        assert Settings.legacy_access() is None

    def test_legacy_available_flag(self, _isolated: tuple[Path, Path]) -> None:
        _own, legacy = _isolated
        assert Settings.legacy_available() is False
        _write_legacy(legacy)
        assert Settings.legacy_available() is True

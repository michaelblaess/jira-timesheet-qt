"""Die Verdrahtung der Registrierung in dieser Anwendung.

Den Baustein selbst prueft QAppFramework. Hier geht es um das, was diese
Anwendung beisteuert: der oeffentliche Schluessel, der Ablageort, die Strenge -
und dass ein selbst gebautes Programm niemanden aussperrt.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from QAppFramework.registration import (  # noqa: E402
    Registration,
    RegistrationMode,
    RegistrationOutcome,
    create_keypair,
    sign,
)

from jira_timesheet_qt.models.settings import Settings  # noqa: E402
from jira_timesheet_qt.ui import registration  # noqa: E402


@pytest.fixture(autouse=True)
def _isolierte_ablage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nie gegen die echte Ablage arbeiten - dort liegt Michaels Zugang."""
    monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", tmp_path / "settings.json")


class TestVerdrahtung:
    def test_der_oeffentliche_schluessel_ist_gesetzt(self) -> None:
        """Ein Ed25519-Schluessel ist genau 32 Byte lang."""
        assert len(registration.PUBLIC_KEY) == 32

    def test_der_modus_ist_freiwillig(self) -> None:
        assert registration.MODE is RegistrationMode.FREE

    def test_die_lizenz_liegt_neben_den_einstellungen(self, tmp_path: Path) -> None:
        assert registration.license_path() == tmp_path / "registration.json"

    def test_es_gibt_vorteile_zu_nennen(self) -> None:
        """Eine leere Aufzaehlung im Dialog wirkt schwaecher als gar keine."""
        assert registration.BENEFITS
        assert all(z.strip() for z in registration.BENEFITS)


class TestSelbstbau:
    def test_ohne_kennzeichen_wird_nicht_gefragt(self) -> None:
        """Wer aus dem Quelltext baut, darf laut Lizenz uneingeschraenkt
        nutzen - dann darf die Pruefung ihn auch nicht behelligen."""
        assert registration.is_enforced() is False
        assert registration.check() is RegistrationOutcome.CONTINUE

    def test_mit_kennzeichen_wird_einmal_gefragt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Im offiziellen Programmpaket kommt die Frage - genau einmal."""
        monkeypatch.setattr(registration, "is_enforced", lambda: True)
        assert registration.check() is RegistrationOutcome.REMIND
        for _ in range(3):
            assert registration.check() is RegistrationOutcome.CONTINUE

    def test_mit_schluessel_wird_gar_nicht_gefragt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(registration, "is_enforced", lambda: True)
        privat, oeffentlich = create_keypair()
        monkeypatch.setattr(registration, "PUBLIC_KEY", oeffentlich)
        registration.store().save(Registration(license=sign("michael@example.com", privat)))
        assert registration.check() is RegistrationOutcome.CONTINUE


class TestSpeicherort:
    def test_die_lizenz_steht_im_einstellungsdialog(self) -> None:
        """Damit niemand sie beim Zuruecksetzen der Zustimmung mitloescht."""
        from PySide6.QtWidgets import QApplication

        from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

        app = QApplication.instance() or QApplication([])
        assert app is not None
        dialog = SettingsDialog(Settings())
        orte = dict(dialog.speicherorte())
        assert "Registrierung (Lizenz)" in orte
        assert orte["Registrierung (Lizenz)"].name == "registration.json"
        dialog.close()

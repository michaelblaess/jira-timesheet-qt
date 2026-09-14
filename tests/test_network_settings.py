"""Tests fuer den Reiter "Netzwerk" und die Zertifikatspruefung.

Der Dienst dahinter (`services/ssl_support.py`) hat eigene Tests, die aus der
Textual-Fassung stammen. Hier geht es um das, was diese Anwendung beisteuert:
die Seite im Einstellungsdialog, die Verdrahtung bis in den Jira-Client und
die Frage, ob die Pruefung ueberhaupt eingeschaltet ist.

Bis v0.10.0 stand in jedem HTTPS-Aufruf `verify=False`. Ein Test, der das
festhaelt, ist der eigentliche Wert dieser Datei - er wuerde einen Rueckfall
sofort melden.
"""

from __future__ import annotations

import ssl

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit

from jira_timesheet_qt.i18n import load_locale
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient
from jira_timesheet_qt.services.ssl_support import TlsSettings, tls_from_settings
from jira_timesheet_qt.ui.jira_worker import BudgetFieldWorker
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog

# Reihenfolge und Beschriftung der Reiter, abgeglichen mit der Textual-Fassung.
# Die letzten beiden liefert QAppFramework.
ERWARTETE_SEITEN = [
    "Jira",
    "Netzwerk",
    "Export",
    "Spalten",
    "Arbeitszeit",
    "Tickets",
    "Mein Team",
    "Darstellung",
    "Speicherort",
]


def seitennamen(dialog: SettingsDialog) -> list[str]:
    """Liest die Beschriftungen der Seiten in ihrer Reihenfolge."""
    nav = dialog._nav
    return [nav.item(i).text() for i in range(nav.count()) if nav.item(i) is not None]


class TestSeitenschnitt:
    """Beide Fassungen sollen dieselben Reiter in derselben Folge zeigen."""

    def test_reiter_stimmen_mit_der_textual_fassung_ueberein(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            assert seitennamen(dialog) == ERWARTETE_SEITEN
        finally:
            dialog.close()

    def test_zugang_heisst_jetzt_jira(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            assert "Zugang" not in seitennamen(dialog)
        finally:
            dialog.close()

    def test_der_proxy_steht_auf_netzwerk(self, qapp: QApplication) -> None:
        # Er stand vorher beim Zugang. In der Textual-Fassung liegt er auf
        # "Netzwerk", zusammen mit den Zertifikaten - beides betrifft die
        # Verbindung, nicht die Anmeldung.
        dialog = SettingsDialog(Settings())
        try:
            netzwerk = dialog._page_network()
            assert dialog.proxy in netzwerk.findChildren(QLineEdit)
        finally:
            dialog.close()


class TestFelder:
    """Die fuenf Zertifikatsfelder muessen durch den Dialog laufen."""

    def test_alle_felder_stehen_auf_der_seite(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            seite = dialog._page_network()
            assert dialog.verify_ssl in seite.findChildren(QCheckBox)
            felder = seite.findChildren(QLineEdit)
            for feld in (
                dialog.ca_bundle,
                dialog.client_cert,
                dialog.client_key,
                dialog.client_key_password,
            ):
                assert feld in felder
        finally:
            dialog.close()

    def test_das_schluessel_passwort_ist_verdeckt(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            assert dialog.client_key_password.echoMode() is QLineEdit.EchoMode.Password
        finally:
            dialog.close()

    def test_werte_kommen_aus_dem_dialog_zurueck(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            dialog.verify_ssl.setChecked(False)
            dialog.ca_bundle.setText("  C:/tmp/firma.pem  ")
            dialog.client_cert.setText("C:/tmp/client.pem")
            dialog.client_key.setText("C:/tmp/client.key")
            dialog.client_key_password.setText("geheim")
            ergebnis = dialog.result_settings()
        finally:
            dialog.close()

        assert ergebnis.verify_ssl is False
        # Pfade werden getrimmt, das Passwort NICHT - dort kann ein Leerzeichen
        # Teil des Werts sein.
        assert ergebnis.ca_bundle == "C:/tmp/firma.pem"
        assert ergebnis.client_key_password == "geheim"

    def test_die_felder_werden_gespeichert(self, qapp: QApplication) -> None:
        # Ein Feld, das nicht in _FIELDS steht, ist beim naechsten Start weg.
        einstellungen = Settings(verify_ssl=False, ca_bundle="C:/tmp/firma.pem")
        wieder = Settings._from_dict(einstellungen.to_dict())
        assert wieder.verify_ssl is False
        assert wieder.ca_bundle == "C:/tmp/firma.pem"


class TestVerdrahtung:
    """Vom Feld bis in den HTTPS-Aufruf."""

    def test_die_pruefung_ist_vorgabemaessig_an(self) -> None:
        assert Settings().verify_ssl is True

    def test_der_client_prueft_ohne_weitere_angabe(self) -> None:
        # Der Rueckfall auf TlsSettings() heisst "pruefen". Bis v0.10.0 stand
        # hier an acht Stellen verify=False.
        client = JiraClient(host="https://example.invalid", email="a@b.c", token="x")
        assert client._verify is not False
        assert isinstance(client._verify, ssl.SSLContext)

    def test_abgeschaltet_kommt_wirklich_false_an(self) -> None:
        client = JiraClient(
            host="https://example.invalid",
            email="a@b.c",
            token="x",
            tls=TlsSettings(verify=False),
        )
        assert client._verify is False

    def test_kein_einziger_aufruf_traegt_noch_verify_false(self) -> None:
        # Der Rueckfall waere lautlos: eine einzelne vergessene Stelle
        # verbindet ungeprueft, und niemand merkt es.
        from pathlib import Path

        quelle = Path(JiraClient.__module__.replace(".", "/") + ".py")
        text = (Path.cwd() / "src" / quelle).read_text(encoding="utf-8")
        assert "verify=False" not in text
        # Jeder Verbindungsaufbau traegt die Pruefung. Bis 09/2026 stand hier
        # eine feste Anzahl - die schlug bei jedem neuen Aufruf an, auch wenn
        # der die Pruefung korrekt mitbrachte.
        verbindungen = text.count("httpx.AsyncClient(")
        assert verbindungen > 0
        assert text.count("verify=self._verify") == verbindungen

    def test_eine_fehlende_zertifikatsdatei_meldet_sich_sofort(self) -> None:
        # Nicht erst beim ersten Abruf: der Konstruktor liest die Datei, und
        # ein Tippfehler im Pfad soll dort auffallen.
        from jira_timesheet_qt.services.jira_client import JiraClientError

        load_locale("de")
        with pytest.raises(JiraClientError, match="nicht gefunden"):
            JiraClient(
                host="https://example.invalid",
                email="a@b.c",
                token="x",
                tls=TlsSettings(ca_bundle="C:/gibt/es/nicht.pem"),
            )

    def test_die_einstellungen_werden_umgerechnet(self) -> None:
        tls = tls_from_settings(Settings(verify_ssl=False, ca_bundle="C:/tmp/firma.pem"))
        assert tls.verify is False
        assert tls.ca_bundle == "C:/tmp/firma.pem"


class TestBudgeterkennung:
    """Auch der Nebenweg geht ueber TLS."""

    def test_der_worker_nimmt_die_tls_angaben(self, qapp: QApplication) -> None:
        # Diese Signatur hat einen Parameter DAZWISCHEN bekommen. Wird sie
        # weiter positionell gerufen, landet das Elternobjekt im tls-Feld -
        # ein Fehler, den erst der naechste Klick auf "Automatisch ermitteln"
        # zeigen wuerde.
        tls = TlsSettings(verify=False)
        worker = BudgetFieldWorker("https://example.invalid", "a@b.c", "x", "", tls, None)
        assert worker._tls is tls

    def test_der_dialog_reicht_die_felder_durch(self, qapp: QApplication) -> None:
        dialog = SettingsDialog(Settings())
        try:
            dialog.verify_ssl.setChecked(False)
            dialog.ca_bundle.setText("C:/tmp/firma.pem")
            tls = dialog._tls_from_fields()
        finally:
            dialog.close()

        # Aus den FELDERN, nicht aus den gespeicherten Einstellungen: wer das
        # Bundle gerade erst eingetragen hat, soll es sofort nutzen koennen.
        assert tls.verify is False
        assert tls.ca_bundle == "C:/tmp/firma.pem"

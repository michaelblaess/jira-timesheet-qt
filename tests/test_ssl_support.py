"""Tests der TLS-Einstellungen.

Bis v1.21.0 stand in jedem httpx-Client `verify=False`. Diese Tests halten
fest, dass die Pruefung wieder laeuft, dass sie sich bewusst abschalten laesst
und dass ein falscher Pfad auffliegt statt stillschweigend zu wirken.
"""

from __future__ import annotations

import ast
import ssl
from pathlib import Path

import httpx
import pytest

from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.ssl_support import TlsSettings, build_verify, is_ssl_error

QUELLEN = Path(__file__).resolve().parent.parent / "src"


# --- Die Regression, um die es geht ---------------------------------------------


def _verify_false_stellen(wurzel: Path) -> list[str]:
    """Findet echte Aufrufe mit `verify=False`.

    Bewusst ueber den Syntaxbaum und nicht per Textsuche: Kommentare und
    Docstrings erwaehnen `verify=False`, um zu erklaeren, warum es weg ist -
    eine Textsuche wuerde ausgerechnet die Erklaerung als Verstoss melden.

    Args:
        wurzel:
            Verzeichnis, das durchsucht wird.

    Returns:
        Fundstellen als "datei:zeile", leer wenn sauber.
    """
    treffer: list[str] = []
    for datei in wurzel.rglob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            for argument in knoten.keywords:
                ist_false = isinstance(argument.value, ast.Constant) and argument.value.value is False
                if argument.arg == "verify" and ist_false:
                    treffer.append(f"{datei.relative_to(wurzel)}:{knoten.lineno}")
    return treffer


def test_kein_verify_false_mehr_im_quellcode() -> None:
    """Die eigentliche Zusage: nirgends ist die Pruefung fest abgeschaltet.

    Ein Verhaltenstest reicht hier nicht - `verify=False` an einer einzelnen
    vergessenen Stelle traefe er nicht, solange die anderen sieben stimmen.
    """
    assert _verify_false_stellen(QUELLEN) == []


def test_die_suche_wuerde_einen_rueckfall_finden(tmp_path: Path) -> None:
    """Positivkontrolle - ohne sie sagt der Test darueber nichts aus."""
    (tmp_path / "rueckfall.py").write_text("import httpx\nhttpx.AsyncClient(verify=False)\n", encoding="utf-8")
    assert _verify_false_stellen(tmp_path) == ["rueckfall.py:2"]


# --- build_verify ---------------------------------------------------------------


def test_vorgabe_prueft() -> None:
    ergebnis = build_verify(TlsSettings())
    assert isinstance(ergebnis, ssl.SSLContext)
    assert ergebnis.verify_mode is ssl.CERT_REQUIRED


def test_abschalten_ist_moeglich_aber_ausdruecklich() -> None:
    assert build_verify(TlsSettings(verify=False)) is False


def test_fehlendes_ca_bundle_fliegt_auf(tmp_path: Path) -> None:
    # Kein stiller Rueckfall auf den Systemspeicher: ein Tippfehler im Pfad
    # wuerde sonst zu einem unerklaerlichen Verbindungsfehler.
    with pytest.raises(FileNotFoundError):
        build_verify(TlsSettings(ca_bundle=str(tmp_path / "gibtsnicht.pem")))


def test_fehlendes_client_zertifikat_fliegt_auf(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_verify(TlsSettings(client_cert=str(tmp_path / "gibtsnicht.pem")))


def test_vorhandenes_ca_bundle_wird_geladen(tmp_path: Path) -> None:
    # certifi liegt als Abhaengigkeit von httpx ohnehin bereit und ist ein
    # echtes PEM-Buendel - damit prueft der Test das Laden, nicht nur den Pfad.
    import certifi

    bundle = tmp_path / "eigenes.pem"
    bundle.write_text(Path(certifi.where()).read_text(encoding="utf-8"), encoding="utf-8")

    context = build_verify(TlsSettings(ca_bundle=str(bundle)))
    assert isinstance(context, ssl.SSLContext)
    assert context.get_ca_certs(), "Das Buendel wurde nicht geladen"


# --- Fehlererkennung ------------------------------------------------------------


def test_ssl_fehler_wird_durch_die_ursachenkette_erkannt() -> None:
    # So kommt der Fehler tatsaechlich an: httpx verpackt ihn in ConnectError.
    ursache = ssl.SSLCertVerificationError("unable to get local issuer certificate")
    verpackt = httpx.ConnectError("nope")
    verpackt.__cause__ = ursache
    assert is_ssl_error(verpackt)


def test_ein_gewoehnlicher_fehler_ist_kein_ssl_fehler() -> None:
    # Gegenprobe: sonst wuerde jede Panne den Zertifikatshinweis ausloesen.
    assert not is_ssl_error(httpx.ConnectError("Verbindung abgelehnt"))
    assert not is_ssl_error(ValueError("irgendwas"))


def test_endlose_ursachenkette_haengt_nicht() -> None:
    a = ValueError("a")
    b = ValueError("b")
    a.__cause__ = b
    b.__cause__ = a
    assert not is_ssl_error(a)


# --- Der Client -----------------------------------------------------------------


def test_client_meldet_eine_fehlende_zertifikatsdatei_verstaendlich(tmp_path: Path) -> None:
    from jira_timesheet_qt.i18n import load_locale

    # Ohne geladenes Sprachpaket liefert t() nur den Schluessel zurueck.
    load_locale("de")
    fehlt = tmp_path / "proxy-ca.pem"
    with pytest.raises(JiraClientError) as fehler:
        JiraClient(
            host="https://example.atlassian.net",
            email="a@b.de",
            token="x",
            tls=TlsSettings(ca_bundle=str(fehlt)),
        )
    assert str(fehlt) in str(fehler.value)


def test_client_prueft_ohne_angabe() -> None:
    client = JiraClient(host="https://example.atlassian.net", email="a@b.de", token="x")
    assert isinstance(client._verify, ssl.SSLContext)


def test_client_uebernimmt_das_abschalten() -> None:
    client = JiraClient(
        host="https://example.atlassian.net",
        email="a@b.de",
        token="x",
        tls=TlsSettings(verify=False),
    )
    assert client._verify is False


def test_tls_fehler_wird_zu_einer_meldung_mit_hinweis() -> None:
    from jira_timesheet_qt.i18n import load_locale

    load_locale("de")
    client = JiraClient(host="https://example.atlassian.net", email="a@b.de", token="x")

    verpackt = httpx.ConnectError("nope")
    verpackt.__cause__ = ssl.SSLCertVerificationError("unable to get local issuer certificate")

    meldung = str(client._as_client_error(verpackt))
    assert "CA-Bundle" in meldung
    # Und die Gegenprobe: ein anderer Fehler bekommt den Hinweis nicht.
    assert "CA-Bundle" not in str(client._as_client_error(httpx.ConnectError("abgelehnt")))


def test_jede_client_erzeugung_reicht_die_tls_angaben_durch() -> None:
    """Vier Erzeugungsorte, und einer war beim ersten Anlauf vergessen.

    Deshalb ueber den Syntaxbaum statt per Auge: Jeder Aufruf von JiraClient()
    im Quellcode muss ein `tls`-Argument tragen. Eine vergessene Stelle wuerde
    zwar pruefen (die Vorgabe ist an), aber ein eingetragenes CA-Bundle
    ignorieren - und dann scheitert genau ein Teil der Anwendung hinter dem
    Firmenproxy, waehrend der Rest laeuft.
    """
    ohne_tls: list[str] = []
    for datei in QUELLEN.rglob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = knoten.func.id if isinstance(knoten.func, ast.Name) else ""
            if name != "JiraClient":
                continue
            if not any(argument.arg == "tls" for argument in knoten.keywords):
                ohne_tls.append(f"{datei.relative_to(QUELLEN)}:{knoten.lineno}")
    assert ohne_tls == []

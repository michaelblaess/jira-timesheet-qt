"""TLS-Einstellungen fuer die Jira-Verbindung.

Bis v1.21.0 stand in jedem httpx-Client dieser Anwendung `verify=False` -
an acht Stellen, ohne Kommentar und ohne Schalter. Damit war die Pruefung des
Serverzertifikats vollstaendig abgeschaltet: Die Verbindung ist zwar
verschluesselt, aber niemand prueft mehr, mit wem eigentlich. Wer sich
dazwischenschaltet, faellt nicht auf, und Zugangsdaten laufen mit.

Der Grund dafuer ist gut nachvollziehbar - ein Firmenproxy, der TLS aufbricht,
legt sein eigenes Zertifikat vor, und ohne dessen Wurzelzertifikat bricht jede
Verbindung ab. Die Loesung ist aber, dieses Wurzelzertifikat bekannt zu machen,
nicht die Pruefung abzuschalten.

Public API:
    - `TlsSettings` - was die Anwendung dafuer braucht, ohne Bezug zur Ablage.
    - `build_verify()` - baut daraus den Wert fuer `httpx.AsyncClient(verify=)`.
    - `tls_from_settings()` - die Umrechnung aus den gespeicherten Einstellungen.
    - `is_ssl_error()` - erkennt einen TLS-Abbruch in der Ursachenkette.

Reihenfolge, in der eine CA gefunden wird:

1. Der in den Einstellungen gesetzte Pfad.
2. Die Umgebungsvariablen `SSL_CERT_FILE` und `REQUESTS_CA_BUNDLE`, die in
   Unternehmensumgebungen ueblicherweise schon gesetzt sind. Das erledigt
   `ssl.create_default_context()` von selbst.
3. Der Zertifikatsspeicher des Systems.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from pathlib import Path

from jira_timesheet_qt.models.settings import Settings


@dataclass(frozen=True)
class TlsSettings:
    """Die TLS-Angaben aus den Einstellungen.

    Bewusst eine eigene Dataclass und nicht `Settings` selbst: Der Kern soll
    die Ablage nicht kennen, und so laesst sich der Aufbau ohne
    Einstellungsdatei testen.

    Args:
        verify: Ob das Serverzertifikat geprueft wird. Aus heisst ungeschuetzt.
        ca_bundle: Pfad zu einer PEM-Datei mit Wurzelzertifikaten.
        client_cert: Pfad zum Client-Zertifikat, falls die Gegenstelle eines will.
        client_key: Pfad zum privaten Schluessel des Client-Zertifikats.
        client_key_password: Passwort des Schluessels, falls er verschluesselt ist.
    """

    verify: bool = True
    ca_bundle: str = ""
    client_cert: str = ""
    client_key: str = ""
    client_key_password: str = ""


def build_verify(settings: TlsSettings) -> ssl.SSLContext | bool:
    """Baut den Wert, den httpx als `verify` erwartet.

    Args:
        settings:
            Die TLS-Angaben.

    Returns:
        `False`, wenn die Pruefung ausdruecklich abgeschaltet ist. Sonst ein
        `SSLContext` mit dem angegebenen Wurzelzertifikat und, falls gesetzt,
        dem Client-Zertifikat.

    Raises:
        FileNotFoundError:
            Wenn ein angegebener Pfad nicht existiert. Das ist Absicht - ein
            stillschweigender Rueckfall auf den Systemspeicher wuerde einen
            Tippfehler im Pfad in einen unerklaerlichen Verbindungsfehler
            verwandeln.
    """

    if not settings.verify:
        return False

    ca = settings.ca_bundle.strip()
    if ca and not Path(ca).is_file():
        raise FileNotFoundError(ca)

    # Ohne cafile liest create_default_context SSL_CERT_FILE bzw.
    # REQUESTS_CA_BUNDLE aus der Umgebung und faellt sonst auf den
    # Systemspeicher zurueck.
    context = ssl.create_default_context(cafile=ca or None)

    cert = settings.client_cert.strip()
    if not cert:
        return context

    if not Path(cert).is_file():
        raise FileNotFoundError(cert)
    key = settings.client_key.strip()
    if key and not Path(key).is_file():
        raise FileNotFoundError(key)

    # load_cert_chain vertraegt keyfile=None und password=None - dann steckt
    # der Schluessel in derselben Datei bzw. ist unverschluesselt.
    context.load_cert_chain(
        certfile=cert,
        keyfile=key or None,
        password=settings.client_key_password or None,
    )
    return context


def is_ssl_error(error: BaseException) -> bool:
    """Prueft, ob ein Fehler von der Zertifikatspruefung kommt.

    httpx verpackt TLS-Fehler in `httpx.ConnectError`, deren Ursache im
    `__cause__` steckt. Deshalb wird die Kette mitgeprueft.

    Args:
        error:
            Der aufgetretene Fehler.

    Returns:
        True, wenn irgendwo in der Ursachenkette ein `ssl.SSLError` steht.
    """

    aktuell: BaseException | None = error
    gesehen: set[int] = set()
    while aktuell is not None and id(aktuell) not in gesehen:
        gesehen.add(id(aktuell))
        if isinstance(aktuell, ssl.SSLError) or "SSL" in type(aktuell).__name__:
            return True
        aktuell = aktuell.__cause__ or aktuell.__context__
    return False


def tls_from_settings(settings: Settings) -> TlsSettings:
    """Zieht die TLS-Angaben aus den gespeicherten Einstellungen.

    An einer Stelle, damit die vier Erzeugungsorte des Jira-Clients nicht je
    ihre eigene Umrechnung fuehren - genau so ist frueher an einem davon das
    Setzen vergessen worden.

    Args:
        settings:
            Die geladenen Einstellungen.

    Returns:
        Die Angaben in der Form, die `build_verify()` erwartet.
    """
    return TlsSettings(
        verify=settings.verify_ssl,
        ca_bundle=settings.ca_bundle,
        client_cert=settings.client_cert,
        client_key=settings.client_key,
        client_key_password=settings.client_key_password,
    )

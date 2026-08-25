"""Stellt eine Lizenzdatei aus. Laeuft nur beim Herausgeber.

    python assets/make_license.py anwender@example.com

Der private Schluessel wird NICHT im Repo gesucht. Sein Ort kommt aus der
Umgebungsvariablen JIRA_TIMESHEET_SIGNING_KEY, sonst aus dem Vorgabepfad
unten. Geht er verloren, sind alle bisher ausgestellten Lizenzen wertlos -
eine Sicherung an zweiter Stelle ist Pflicht.

Die erzeugte Datei geht an den Anwender. Er waehlt sie im
Registrierungsdialog aus oder fuegt ihren Inhalt dort ein.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from QAppFramework.registration import sign, verify

from jira_timesheet_qt.ui.registration import PUBLIC_KEY

VORGABE_SCHLUESSEL = Path.home() / ".jira-timesheet-qt-keys" / "signing-key.hex"


def schluessel_pfad() -> Path:
    """Wo der private Schluessel liegt."""
    aus_umgebung = os.environ.get("JIRA_TIMESHEET_SIGNING_KEY")
    return Path(aus_umgebung) if aus_umgebung else VORGABE_SCHLUESSEL


def main() -> int:
    """Erzeugt die Lizenzdatei und prueft sie gleich gegen den oeffentlichen Schluessel."""
    zerleger = argparse.ArgumentParser(description="Stellt eine Lizenzdatei aus.")
    zerleger.add_argument("email", help="E-Mail-Adresse des Anwenders")
    zerleger.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Zieldatei (Vorgabe: <mail>.lic im aktuellen Verzeichnis)",
    )
    argumente = zerleger.parse_args()

    pfad = schluessel_pfad()
    if not pfad.is_file():
        print(f"Privater Schluessel nicht gefunden: {pfad}", file=sys.stderr)
        print(
            "Ort ueber JIRA_TIMESHEET_SIGNING_KEY setzen, oder die Datei dorthin legen.",
            file=sys.stderr,
        )
        return 1

    privat = bytes.fromhex(pfad.read_text(encoding="utf-8").strip())
    lizenz = sign(argumente.email, privat)

    # Gegenprobe mit dem Schluessel, den die Anwendung wirklich mitbringt.
    # Ohne sie faellt ein vertauschtes Schluesselpaar erst beim Anwender auf.
    if not verify(lizenz, PUBLIC_KEY):
        print(
            "Die erzeugte Lizenz besteht die Pruefung NICHT - der private Schluessel\n"
            "passt nicht zu dem oeffentlichen, den die Anwendung mitbringt.",
            file=sys.stderr,
        )
        return 2

    ziel = argumente.out or Path(f"{argumente.email.replace('@', '_at_')}.lic")
    ziel.write_text(lizenz.as_text(), encoding="utf-8", newline="\n")
    print(f"Lizenz fuer {lizenz.email} geschrieben nach {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

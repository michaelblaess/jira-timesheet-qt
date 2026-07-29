"""Gemeinsame Vorbereitungen fuer alle Tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Qt ohne Bildschirm betreiben. Muss VOR dem ersten Qt-Import gesetzt sein,
# sonst sucht Qt einen X-Server und bricht in der CI ab.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402 - muss nach der Zeile oben stehen


@pytest.fixture(autouse=True)
def _isolated_qsettings(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Verlegt die QSettings des Hauptfensters pro Test in eine eigene Ini.

    Ohne das schreibt das Hauptfenster Groesse, Aufteilung, die Sichtbarkeit
    des Meldungsfensters und den Gruppieren-Schalter in die echte
    Windows-Registry - und liest sie beim naechsten Lauf zurueck. Tests
    haengen dann davon ab, wie zuletzt jemand das Fenster verlassen hat.

    WICHTIG (belegt 27.07.2026): der fruehere Weg ueber setDefaultFormat +
    setPath ISOLIERT AUF WINDOWS NICHT. Der Konstruktor
    QSettings("org", "app") bleibt trotzdem im NativeFormat und liest die
    Registry (`iso.format()` == NativeFormat). Die Tests lasen also in
    Wahrheit die echten Nutzereinstellungen - ein latenter Fehler, den die
    Geometrie-Tests nie aufdeckten, weil sie keinen konkreten Wert pruefen.

    Wirksam ist nur, den Namen `QSettings` IM Modul durch eine Fabrik zu
    ersetzen, die eine isolierte Ini liefert. Pro Test ein eigenes
    Verzeichnis, damit sich die Tests auch untereinander nicht ueber
    persistierte Zustaende beeinflussen (ein Test, der die Gruppierung
    einschaltet, darf den naechsten nicht erben).
    """
    from jira_timesheet_qt.models import settings as settings_module
    from jira_timesheet_qt.models.settings import Settings
    from jira_timesheet_qt.ui import main_window

    directory = tmp_path_factory.mktemp("qsettings")
    ini_path = str(directory / "window.ini")

    def _isolated(*_args: object, **_kwargs: object) -> QSettings:
        return QSettings(ini_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(main_window, "QSettings", _isolated)

    # Auch die JSON-Einstellungsdatei pro Test verlegen. Ohne das schreibt jeder
    # Test, der ein Fenster schliesst (closeEvent -> save) oder Settings.save()
    # aufruft, in die ECHTE ~/.jira-timesheet-qt/settings.json - und kann dort
    # sogar den Jira-Zugang ueberschreiben. Ein Host-only-Fenster hat so einmal
    # E-Mail und Token in der echten Datei geleert.
    config_dir = directory / "config"
    config_dir.mkdir()
    monkeypatch.setattr(Settings, "SETTINGS_DIR", config_dir)
    monkeypatch.setattr(Settings, "SETTINGS_FILE", config_dir / "settings.json")
    # Legacy-TUI-Datei ins Leere zeigen lassen, sonst liest ein Test echte Werte.
    monkeypatch.setattr(settings_module, "LEGACY_SETTINGS_FILE", config_dir / "legacy-absent.json")
    return directory

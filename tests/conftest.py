"""Gemeinsame Vorbereitungen fuer alle Tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Qt ohne Bildschirm betreiben. Muss VOR dem ersten Qt-Import gesetzt sein,
# sonst sucht Qt einen X-Server und bricht in der CI ab.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402 - muss nach der Zeile oben stehen


@pytest.fixture(autouse=True, scope="session")
def _isolated_qsettings(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Verlegt QSettings in eine Datei unter tmp.

    Ohne das schreibt das Hauptfenster Groesse, Aufteilung und die
    Sichtbarkeit des Meldungsfensters in die echte Windows-Registry - und
    liest sie beim naechsten Lauf zurueck. Tests haengen dann davon ab, wie
    zuletzt jemand das Fenster verlassen hat.

    Genau das ist am 26.07.2026 passiert: ein Skript zum Erzeugen der
    Bildschirmfotos hatte das Meldungsfenster eingeblendet, danach schlug
    test_toggle_switches_visibility fehl.
    """
    directory = tmp_path_factory.mktemp("qsettings")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(directory))
    return directory

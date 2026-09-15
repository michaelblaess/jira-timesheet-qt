"""Tastenkuerzel des Hauptfensters muessen wirklich ausloesen.

Bis v0.12.0 standen F5, Strg+N, Strg+E, Strg+P, Strg+, und F1 zweimal im
Fenster: als Menueaktion aus menu.json und als eigener QShortcut. Qt meldet
dann "Ambiguous shortcut overload" und fuehrt keines von beiden aus. Der
Vergleich der Menueaktionen untereinander (test_kuerzel_ist_eindeutig)
konnte das nicht sehen, und ein Test, der nur die Registrierung prueft,
haette die Wirkung nicht belegt - deshalb wird hier gedrueckt.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode

# Taste -> Methode, die sie ausloesen soll.
KUERZEL = {
    "F5": "reload_current",
    "Ctrl+N": "action_new_manual",
    "Ctrl+Q": "close",
    "Ctrl+E": "export_file",
    "Ctrl+P": "print_preview",
    "Ctrl+,": "open_settings",
    "F1": "open_about",
    "Ctrl+L": "toggle_log",
}


def _zaehler(aufrufe: Counter[str], name: str) -> Callable[..., None]:
    def aufruf(_self: MainWindow, *_args: object, **_kwargs: object) -> None:
        aufrufe[name] += 1

    return aufruf


@pytest.fixture
def fenster_mit_zaehlern(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[MainWindow, Counter[str]]]:
    """Ein aktives Hauptfenster, dessen Zielmethoden nur mitzaehlen.

    Die Methoden werden VOR dem Fensterbau ersetzt: Menue und Kuerzel binden
    sie beim Aufbau. Danach wird das Fenster wirklich geschlossen und
    freigegeben - ein offen gebliebenes aktives Fenster hat die Tests in
    test_team_ui.py rot gemacht, die nach dieser Datei laufen.
    """
    aufrufe: Counter[str] = Counter()
    for name in set(KUERZEL.values()):
        monkeypatch.setattr(MainWindow, name, _zaehler(aufrufe, name))
    fenster = MainWindow(Settings(), Mode.DARK)
    fenster.show()
    fenster.activateWindow()
    assert QTest.qWaitForWindowActive(fenster, 2000), "Fenster wurde nicht aktiv"
    yield fenster, aufrufe
    # Das Loslassen der Buchstabentaste traegt Strg noch als gedrueckt, und
    # QGuiApplication merkt sich das. Danach schaltet selectRow() in jedem
    # spaeteren Test die Auswahl um, statt sie zu setzen.
    QTest.keyRelease(fenster, Qt.Key.Key_Control)
    QApplication.processEvents()
    assert QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier
    # close ist hier ersetzt - die Qt-Methode direkt aufrufen.
    QWidget.close(fenster)
    fenster.deleteLater()
    QApplication.processEvents()


@pytest.mark.parametrize(("taste", "methode"), KUERZEL.items(), ids=list(KUERZEL))
def test_die_taste_loest_genau_einmal_aus(
    fenster_mit_zaehlern: tuple[MainWindow, Counter[str]], taste: str, methode: str
) -> None:
    fenster, aufrufe = fenster_mit_zaehlern
    QTest.keySequence(fenster, QKeySequence(taste))
    QApplication.processEvents()
    assert aufrufe[methode] == 1, (taste, dict(aufrufe))


def test_keine_taste_liegt_auf_menue_und_eigenem_kuerzel(qapp: QApplication) -> None:
    fenster = MainWindow(Settings(), Mode.DARK)
    halter: dict[str, list[str]] = {}
    for aktion in fenster.findChildren(QAction):
        for folge in aktion.shortcuts():
            halter.setdefault(folge.toString(), []).append(f"QAction {aktion.text()}")
    for kuerzel in fenster.findChildren(QShortcut):
        halter.setdefault(kuerzel.key().toString(), []).append("QShortcut")
    doppelt = {taste: wer for taste, wer in halter.items() if len(wer) > 1}
    assert not doppelt, doppelt

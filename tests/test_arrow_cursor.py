"""Tabellen zeigen den Pfeil, nicht den Text-Cursor (Michael, 24.09.2026)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QWidget

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui import main_window
from jira_timesheet_qt.ui.settings_dialog import SettingsDialog
from jira_timesheet_qt.ui.theme import Mode


def _ohne_pfeil(root: QWidget) -> list[str]:
    """Ansichten, deren Flaeche den Cursor nur erbt oder einen anderen traegt."""
    fehlend = []
    for view in root.findChildren(QAbstractItemView):
        viewport = view.viewport()
        # WA_SetCursor unterscheidet "ausdruecklich gesetzt" von "geerbt" - geerbt
        # meldet ebenfalls den Pfeil, und genau das war der Fehler.
        if not viewport.testAttribute(Qt.WidgetAttribute.WA_SetCursor) or (
            viewport.cursor().shape() != Qt.CursorShape.ArrowCursor
        ):
            fehlend.append(f"{type(view).__name__}:{view.objectName()}")
    return fehlend


def test_hauptfenster(qapp: QApplication) -> None:
    fenster = main_window.MainWindow(Settings(), Mode.DARK)
    assert fenster.findChildren(QAbstractItemView)
    assert _ohne_pfeil(fenster) == []


def test_einstellungen(qapp: QApplication) -> None:
    dialog = SettingsDialog(Settings())
    assert _ohne_pfeil(dialog) == []

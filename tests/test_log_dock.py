"""Tests fuer das Meldungsfenster und die einheitlichen Feldbreiten."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.log_dock import Level, LogDock
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.settings_dialog import FIELD_WIDTH, SettingsDialog
from jira_timesheet_qt.ui.theme import Mode


class TestLogDock:
    def test_writes_with_timestamp(self, qapp: QApplication) -> None:
        dock = LogDock()
        dock.write("Erste Meldung")
        text = dock.plain_text()
        assert "Erste Meldung" in text
        # Zeitstempel als HH:MM:SS am Zeilenanfang.
        assert text.split()[0].count(":") == 2

    def test_keeps_the_order(self, qapp: QApplication) -> None:
        dock = LogDock()
        for i in range(3):
            dock.write(f"Meldung {i}")
        lines = dock.plain_text().splitlines()
        assert "Meldung 0" in lines[0]
        assert "Meldung 2" in lines[2]

    def test_clear_empties_it(self, qapp: QApplication) -> None:
        dock = LogDock()
        dock.write("etwas")
        dock.clear()
        assert dock.line_count == 0

    @pytest.mark.parametrize("level", list(Level))
    def test_every_level_is_writable(self, qapp: QApplication, level: Level) -> None:
        dock = LogDock()
        dock.write("Meldung", level)
        assert "Meldung" in dock.plain_text()

    def test_markup_in_the_message_is_escaped(self, qapp: QApplication) -> None:
        """Eine Fehlermeldung kann HTML enthalten - etwa eine Proxy-Seite."""
        dock = LogDock()
        dock.write("<b>fett</b> & <script>böse</script>")
        text = dock.plain_text()
        assert "<b>fett</b>" in text
        assert "<script>böse</script>" in text

    def test_old_lines_are_dropped(self, qapp: QApplication) -> None:
        """Ein langer Lauf darf den Speicher nicht unbegrenzt füllen."""
        dock = LogDock()
        for i in range(LogDock.MAX_LINES + 50):
            dock.write(f"Zeile {i}")
        assert dock.line_count <= LogDock.MAX_LINES


class TestLogInWindow:
    def test_hidden_at_first_start(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.show()
        # Erst nach dem Anzeigen des Fensters ist die Frage aussagekraeftig:
        # ein hide() davor haelt nicht, sobald noch etwas geschrieben wird.
        assert not window._log.isVisible()

    def test_setting_decides_the_start_state(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(log_visible=True), Mode.DARK)
        window.show()
        assert window._log.isVisible()

    def test_toggle_is_remembered(self, qapp: QApplication, tmp_path, monkeypatch) -> None:
        """Der Zustand ueberlebt den naechsten Start."""
        monkeypatch.setattr(Settings, "SETTINGS_DIR", tmp_path)
        monkeypatch.setattr(Settings, "SETTINGS_FILE", tmp_path / "settings.json")
        window = MainWindow(Settings(), Mode.DARK)
        window.show()
        window.toggle_log()
        assert Settings.load().log_visible is True

    def test_toggle_switches_visibility(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.show()
        window.toggle_log()
        assert window._log.isVisible()
        window.toggle_log()
        assert not window._log.isVisible()

    def test_status_messages_land_in_the_log(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window._set_status("Etwas ist schiefgegangen", "error")
        assert "Etwas ist schiefgegangen" in window._log.plain_text()

    def test_failed_load_is_recorded(self, qapp: QApplication, monkeypatch) -> None:
        """Der Grund eines Fehlschlags muss im Verlauf nachlesbar bleiben."""
        window = MainWindow(Settings(), Mode.DARK)
        monkeypatch.setattr(window, "open_settings", lambda: None)
        window.load_month()
        assert "Zugang unvollständig" in window._log.plain_text()


class TestFieldWidths:
    def test_all_inputs_share_one_width(self, qapp: QApplication) -> None:
        """Uneinheitliche Feldbreiten lassen den Dialog unruhig wirken."""
        dialog = SettingsDialog(Settings())
        fields = [
            *dialog.findChildren(QLineEdit),
            *dialog.findChildren(QSpinBox),
            *dialog.findChildren(QComboBox),
        ]
        # findChildren liefert auch das interne "qt_spinbox_lineedit" jeder
        # Zahlenbox mit - das ist ein Kind, kein eigenes Feld.
        widths = {f.width() for f in fields if f.objectName() != "qt_spinbox_lineedit"}
        assert widths == {FIELD_WIDTH}, widths

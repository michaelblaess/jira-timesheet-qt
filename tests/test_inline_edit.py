"""Tests fuer die Inline-Bearbeitung manueller Eintraege in Tabelle und Baum."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from jira_timesheet_qt.models.export_column import default_columns
from jira_timesheet_qt.models.timesheet import WorklogEntry
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.grid_columns import build_columns
from jira_timesheet_qt.ui.timesheet_model import TimesheetModel, apply_manual_edit
from jira_timesheet_qt.ui.timesheet_tree_model import TimesheetTreeModel

_KEYS = [c.key for c in build_columns(default_columns())]
_SUMMARY_COL = _KEYS.index("description")
_HOURS_COL = _KEYS.index("hours")
_DATE_COL = _KEYS.index("date")


def _manual_entry() -> WorklogEntry:
    return WorklogEntry(
        date=date(2026, 7, 1), ticket="", summary="alt", author="Ich",
        budget="", hours=1.0, manual=True, manual_id=7,
    )


class TestApplyManualEdit:
    def test_hours_parse_german_comma(self) -> None:
        entry = _manual_entry()
        assert apply_manual_edit(entry, "hours", "2,5") is True
        assert entry.hours == 2.5

    def test_summary_is_stripped(self) -> None:
        entry = _manual_entry()
        assert apply_manual_edit(entry, "description", "  neuer Text  ") is True
        assert entry.summary == "neuer Text"

    def test_invalid_hours_rejected(self) -> None:
        entry = _manual_entry()
        assert apply_manual_edit(entry, "hours", "keine Zahl") is False
        assert entry.hours == 1.0  # unveraendert

    def test_zero_hours_rejected(self) -> None:
        assert apply_manual_edit(_manual_entry(), "hours", "0") is False

    def test_empty_summary_rejected(self) -> None:
        assert apply_manual_edit(_manual_entry(), "description", "   ") is False

    def test_unknown_column_rejected(self) -> None:
        assert apply_manual_edit(_manual_entry(), "author", "X") is False


class TestFlatModelEditing:
    def _model(self) -> TimesheetModel:
        model = TimesheetModel()
        model.set_timesheet(demo_timesheet())
        return model

    def _manual_row(self, model: TimesheetModel) -> int:
        return next(r for r in range(model.rowCount()) if model.entry_at(r).manual)  # type: ignore[union-attr]

    def _jira_row(self, model: TimesheetModel) -> int:
        return next(r for r in range(model.rowCount()) if not model.entry_at(r).manual)  # type: ignore[union-attr]

    def test_manual_cells_are_editable(self, qapp: QApplication) -> None:
        model = self._model()
        row = self._manual_row(model)
        for col in (_SUMMARY_COL, _HOURS_COL):
            assert model.flags(model.index(row, col)) & Qt.ItemFlag.ItemIsEditable
        # Datum bleibt gesperrt (verschoebe den Eintrag zwischen Tagen).
        assert not (model.flags(model.index(row, _DATE_COL)) & Qt.ItemFlag.ItemIsEditable)

    def test_jira_rows_are_not_editable(self, qapp: QApplication) -> None:
        model = self._model()
        row = self._jira_row(model)
        assert not (model.flags(model.index(row, _SUMMARY_COL)) & Qt.ItemFlag.ItemIsEditable)

    def test_setdata_updates_and_emits(self, qapp: QApplication) -> None:
        model = self._model()
        row = self._manual_row(model)
        captured: list[WorklogEntry] = []
        model.manual_edited.connect(captured.append)
        assert model.setData(model.index(row, _HOURS_COL), "3,5", Qt.ItemDataRole.EditRole) is True
        assert model.entry_at(row).hours == 3.5  # type: ignore[union-attr]
        assert len(captured) == 1

    def test_setdata_rejects_jira_row(self, qapp: QApplication) -> None:
        model = self._model()
        row = self._jira_row(model)
        assert model.setData(model.index(row, _SUMMARY_COL), "x", Qt.ItemDataRole.EditRole) is False

    def test_manual_color_applies_only_to_manual_rows(self, qapp: QApplication) -> None:
        model = self._model()
        model.set_manual_color(QColor("#ff0000"))
        manual = model.index(self._manual_row(model), _SUMMARY_COL)
        jira = model.index(self._jira_row(model), _SUMMARY_COL)
        assert model.data(manual, Qt.ItemDataRole.ForegroundRole) == QColor("#ff0000")
        assert model.data(jira, Qt.ItemDataRole.ForegroundRole) is None

    def test_manual_color_none_disables_coloring(self, qapp: QApplication) -> None:
        model = self._model()
        model.set_manual_color(QColor("#ff0000"))
        model.set_manual_color(None)
        manual = model.index(self._manual_row(model), _SUMMARY_COL)
        assert model.data(manual, Qt.ItemDataRole.ForegroundRole) is None


class TestTreeModelEditing:
    def _model(self) -> TimesheetTreeModel:
        model = TimesheetTreeModel()
        model.set_timesheet(demo_timesheet())
        return model

    def _manual_index(self, model: TimesheetTreeModel) -> QModelIndex:
        # Eltern-Index fuer rowCount/index MUSS Spalte 0 sein (Qt-Konvention).
        for g in range(model.rowCount()):
            group = model.index(g, 0)
            for r in range(model.rowCount(group)):
                child = model.index(r, _SUMMARY_COL, group)
                entry = model.entry_at_index(child)
                if entry is not None and entry.manual:
                    return child
        raise AssertionError("kein manueller Eintrag in den Demodaten")

    def test_manual_child_is_editable(self, qapp: QApplication) -> None:
        model = self._model()
        assert model.flags(self._manual_index(model)) & Qt.ItemFlag.ItemIsEditable

    def test_group_row_is_not_editable(self, qapp: QApplication) -> None:
        model = self._model()
        group = model.index(0, _SUMMARY_COL)
        assert not (model.flags(group) & Qt.ItemFlag.ItemIsEditable)

    def test_setdata_updates_and_emits(self, qapp: QApplication) -> None:
        model = self._model()
        index = self._manual_index(model)
        captured: list[WorklogEntry] = []
        model.manual_edited.connect(captured.append)
        assert model.setData(index, "geänderter Text", Qt.ItemDataRole.EditRole) is True
        assert model.entry_at_index(index).summary == "geänderter Text"  # type: ignore[union-attr]
        assert len(captured) == 1

    def test_manual_color_applies_to_manual_child_only(self, qapp: QApplication) -> None:
        model = self._model()
        model.set_manual_color(QColor("#ff0000"))
        manual = self._manual_index(model)
        group = model.index(0, _SUMMARY_COL)
        assert model.data(manual, Qt.ItemDataRole.ForegroundRole) == QColor("#ff0000")
        # Gruppenzeilen bekommen keine Einfaerbung.
        assert model.data(group, Qt.ItemDataRole.ForegroundRole) is None

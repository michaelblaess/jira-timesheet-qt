"""Tests fuer FillColumn: Titel fuellt die Restbreite, jede Spaltenkante folgt der Maus."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHeaderView, QTableWidget, QTableWidgetItem

from jira_timesheet_qt.ui.fill_column import FILL_MIN, FillColumn

TITEL = 1


@pytest.fixture
def tabelle(qapp: QApplication) -> Iterator[tuple[QTableWidget, FillColumn]]:
    table = QTableWidget(3, 4)
    table.setHorizontalHeaderLabels(["Ticket", "Titel", "Typ", "Status"])
    for row in range(3):
        for column, text in enumerate((f"ABC-{row}", "Ein Beispieltitel", "Story", "In Arbeit")):
            table.setItem(row, column, QTableWidgetItem(text))
    columns = FillColumn(table, TITEL)
    table.resize(900, 300)
    table.show()
    QTest.qWait(20)
    columns.autosize()
    yield table, columns
    table.hide()


def _rechter_rand(table: QTableWidget) -> int:
    header = table.horizontalHeader()
    return sum(header.sectionSize(s) for s in range(header.count()))


def _ziehe(table: QTableWidget, section: int, dx: int) -> int:
    """Zieht die rechte Kante einer Spalte mit der Maus und liefert, wie weit sie gefolgt ist."""
    header = table.horizontalHeader()
    viewport = header.viewport()
    x = header.sectionViewportPosition(section) + header.sectionSize(section) - 1
    y = header.height() // 2
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y))
    step = 5 if dx > 0 else -5
    for d in range(step, dx + step, step):
        QTest.mouseMove(viewport, QPoint(x + d, y))
    edge = header.sectionViewportPosition(section) + header.sectionSize(section) - 1
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x + dx, y))
    return edge - x


class TestFuellspalte:
    def test_alle_spalten_sind_ziehbar(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, _columns = tabelle
        header = table.horizontalHeader()
        assert {header.sectionResizeMode(s) for s in range(header.count())} == {QHeaderView.ResizeMode.Interactive}

    def test_titel_fuellt_die_restbreite(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, _columns = tabelle
        assert _rechter_rand(table) == table.viewport().width()

    @pytest.mark.parametrize("section", [0, TITEL, 2])
    def test_kante_folgt_der_maus(self, tabelle: tuple[QTableWidget, FillColumn], section: int) -> None:
        # Mit Stretch blieb die Kante rechts vom Titel stehen, und die Kante des
        # Titels liess sich gar nicht greifen.
        table, _columns = tabelle
        assert _ziehe(table, section, 40) == 40

    def test_breiter_werden_fuellt_nach(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, _columns = tabelle
        table.resize(1300, 300)
        QTest.qWait(20)
        assert _rechter_rand(table) == table.viewport().width()

    def test_schmaler_werden_endet_an_der_untergrenze(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, _columns = tabelle
        table.resize(200, 300)
        QTest.qWait(20)
        assert table.horizontalHeader().sectionSize(TITEL) == FILL_MIN

    def test_gezogene_breite_uebersteht_neuladen(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, columns = tabelle
        _ziehe(table, 2, 40)
        breite = table.horizontalHeader().sectionSize(2)
        columns.autosize()
        assert table.horizontalHeader().sectionSize(2) == breite

    def test_nach_dem_ziehen_bleibt_keine_luecke(self, tabelle: tuple[QTableWidget, FillColumn]) -> None:
        table, _columns = tabelle
        _ziehe(table, 2, -30)
        assert _rechter_rand(table) == table.viewport().width()

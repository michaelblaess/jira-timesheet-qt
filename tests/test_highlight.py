"""Tests fuer die Such-Hervorhebung und den Innenabstand der Zellen."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.cell_delegate import CellDelegate
from jira_timesheet_qt.ui.demo import demo_timesheet
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.theme import Mode

_CELL = QRect(0, 0, 200, 30)


def _painted_text_bounds(
    text: str,
    alignment: Qt.AlignmentFlag,
    *,
    needle: str = "",
) -> tuple[int, int]:
    """Zeichnet eine Zelle und misst, wo der Text tatsaechlich beginnt und endet.

    Der einzige belastbare Weg zu einer Aussage ueber den Innenabstand: die
    Zelle wirklich malen und die Pixel auswerten. Eine Zusicherung ueber
    Konstanten oder Rechtecke wuerde nur die eigene Rechnung wiederholen.

    Args:
        text:
            Der Zellinhalt.
        alignment:
            Ausrichtung der Zelle (wie sie die TextAlignmentRole liefert).
        needle:
            Suchbegriff - leer zeichnet ueber den schnellen Weg, gesetzt ueber
            das QTextDocument.

    Returns:
        Erste und letzte Bildspalte mit Text, jeweils bezogen auf die Zelle.
    """
    model = QStandardItemModel(1, 1)
    item = QStandardItem(text)
    item.setTextAlignment(alignment)
    model.setItem(0, 0, item)

    delegate = CellDelegate()
    delegate.set_needle(needle)

    pixmap = QPixmap(_CELL.width(), _CELL.height())
    pixmap.fill(QColor("white"))
    option = QStyleOptionViewItem()
    option.rect = _CELL
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
    option.palette.setColor(option.palette.ColorRole.Text, QColor("black"))

    painter = QPainter(pixmap)
    delegate.paint(painter, option, model.index(0, 0))
    painter.end()

    image = pixmap.toImage()
    columns = [
        x
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y) != QColor("white")
    ]
    assert columns, "Die Zelle blieb leer - der Text wurde gar nicht gezeichnet."
    return min(columns), max(columns)


class TestHighlightHtml:
    def test_without_needle_returns_escaped_text(self) -> None:
        assert CellDelegate.highlight_html("PROJ-101", "") == "PROJ-101"

    def test_escapes_html_special_characters(self) -> None:
        assert CellDelegate.highlight_html("<b> & </b>", "") == "&lt;b&gt; &amp; &lt;/b&gt;"

    def test_wraps_a_match_in_a_span(self) -> None:
        result = CellDelegate.highlight_html("PROJ-101", "101")
        assert "<span" in result
        assert "101</span>" in result
        # Der uebrige Text bleibt erhalten.
        assert result.startswith("PROJ-")

    def test_match_is_case_insensitive(self) -> None:
        result = CellDelegate.highlight_html("Beispiel Advisory", "beispiel")
        assert "<span" in result
        # Die Original-Gross-/Kleinschreibung des Treffers bleibt erhalten.
        assert ">Beispiel</span>" in result

    def test_no_match_leaves_text_unmarked(self) -> None:
        assert CellDelegate.highlight_html("PROJ-101", "xyz") == "PROJ-101"


class TestZellenAbstand:
    """Der Zelltext darf nicht an der Spaltenkante kleben."""

    def test_rechtsbuendige_zelle_haelt_abstand_zur_kante(self, qapp: QApplication) -> None:
        _, right = _painted_text_bounds("7,50", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Fester Mindestwert, NICHT die Konstante: gegen CELL_PADDING_RIGHT zu
        # pruefen hiesse, die eigene Rechnung zu wiederholen - der Test bestuende
        # dann auch bei einem Innenabstand von null. Ohne den Abstand endet die
        # Zahl rund drei Pixel vor der Kante, in der letzten Spalte also
        # unmittelbar am Fensterrand.
        assert _CELL.right() - right >= 8

    def test_linksbuendige_zelle_beginnt_am_nativen_rand(self, qapp: QApplication) -> None:
        """Links bleibt alles wie gehabt - sonst fluchtet der Text nicht mit der Kopfzeile."""
        option = QStyleOptionViewItem()
        option.rect = _CELL
        native = QApplication.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, option, None
        )
        left, _ = _painted_text_bounds("Beispiel", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        assert left - native.left() <= 1

    def test_suchbegriff_verschiebt_den_text_nicht(self, qapp: QApplication) -> None:
        """Beide Zeichenwege nutzen dasselbe Rechteck - beim Tippen springt nichts."""
        plain = _painted_text_bounds("Beispiel", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        marked = _painted_text_bounds(
            "Beispiel",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            needle="spie",
        )
        assert abs(plain[0] - marked[0]) <= 1
        assert abs(plain[1] - marked[1]) <= 1


class TestSearchWiring:
    def test_search_sets_the_needle(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_search_changed("ABC")
        assert window._cell_delegate._needle == "ABC"
        # Der Filter des Proxys folgt derselben Eingabe.
        assert window._proxy.filterRegularExpression().pattern() != ""

    def test_clearing_search_clears_the_needle(self, qapp: QApplication) -> None:
        window = MainWindow(Settings(), Mode.DARK)
        window.set_timesheet(demo_timesheet())
        window._on_search_changed("ABC")
        window._on_search_changed("")
        assert window._cell_delegate._needle == ""

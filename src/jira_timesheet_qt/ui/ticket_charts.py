"""Diagramme ueber der Ticket-Tabelle, selbst gezeichnet mit QPainter.

Bewusst OHNE QtCharts: das Modul steht unter GPL oder kommerzieller Lizenz
und darf in einem Apache-2.0-Repo nicht verwendet werden. QtDataVisualization
und QtGraphs ebenso. Zulaessig waeren PyQtGraph (MIT) oder Matplotlib (BSD) -
fuer ein paar Balken und eine Kurve lohnt keine zusaetzliche Abhaengigkeit,
und Kalender- und Jahresansicht zeichnen hier ohnehin schon selbst.

Drei Fragen, drei Bilder:

1. Zulauf gegen Abgang je Monat - waechst der Bestand oder schrumpft er?
2. Bestand kumuliert - dieselbe Aussage als Kurve ueber die Zeit.
3. Altersverteilung - wie viel liegt wie lange?
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.ticket_board import FOOTNOTE, Statistics

from .theme import Mode, palette_for

# Hoehe der Zeichenflaeche. Reicht fuer eine lesbare Skala, ohne der Tabelle
# den Platz zu nehmen - die Diagramme sind Beiwerk, nicht der Inhalt.
CHART_HEIGHT = 130

# Rand um die Zeichenflaeche: links fuer die Skala, unten fuer die
# Beschriftung, oben fuer den Titel.
MARGIN_LEFT = 34
MARGIN_RIGHT = 6
MARGIN_TOP = 18
MARGIN_BOTTOM = 18


class _Chart(QWidget):
    """Gemeinsames Geruest: Titel, Rahmen, Achse, Hilfslinien."""

    def __init__(self, title: str, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._mode = mode
        self.setMinimumHeight(CHART_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        self.update()

    def _plot_rect(self) -> QRectF:
        """Die eigentliche Zeichenflaeche ohne Raender."""
        return QRectF(
            MARGIN_LEFT,
            MARGIN_TOP,
            max(1.0, self.width() - MARGIN_LEFT - MARGIN_RIGHT),
            max(1.0, self.height() - MARGIN_TOP - MARGIN_BOTTOM),
        )

    def _draw_frame(self, painter: QPainter, top_value: float) -> QRectF:
        """Zeichnet Titel, Grundlinie und zwei Hilfslinien.

        Args:
            painter:
                Der aktive Zeichner.
            top_value:
                Der groesste darzustellende Wert - bestimmt die Skala.

        Returns:
            Die Zeichenflaeche fuer die Daten.
        """
        colors = palette_for(self._mode)
        rect = self._plot_rect()

        font = QFont(self.font())
        font.setPointSizeF(max(6.5, font.pointSizeF() - 1.5))
        painter.setFont(font)

        painter.setPen(QPen(QColor(colors.text_secondary)))
        painter.drawText(
            QRectF(MARGIN_LEFT, 0, rect.width(), MARGIN_TOP),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._title,
        )

        # Hilfslinien bei 0, der Haelfte und dem Hoechstwert. Mehr wuerde bei
        # dieser Hoehe nur Streifen erzeugen.
        grid = QPen(QColor(colors.border))
        grid.setWidthF(1.0)
        painter.setPen(grid)
        metrics = QFontMetricsF(font)
        for share in (0.0, 0.5, 1.0):
            y = rect.bottom() - rect.height() * share
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            label = f"{top_value * share:.0f}"
            painter.setPen(QPen(QColor(colors.text_tertiary)))
            painter.drawText(
                QPointF(MARGIN_LEFT - 4 - metrics.horizontalAdvance(label), y + 3), label
            )
            painter.setPen(grid)
        return rect

    def _draw_empty(self, painter: QPainter) -> None:
        """Hinweis, wenn es nichts zu zeichnen gibt."""
        colors = palette_for(self._mode)
        painter.setPen(QPen(QColor(colors.text_tertiary)))
        painter.drawText(
            self.rect(),
            int(Qt.AlignmentFlag.AlignCenter),
            "keine Daten",
        )


class FlowChart(_Chart):
    """Zulauf gegen Abgang je Monat als Balkenpaare."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Zulauf / Abgang je Monat", mode, parent)
        self._stats: Statistics | None = None

    def set_statistics(self, stats: Statistics | None) -> None:
        """Uebernimmt die Zahlen und zeichnet neu."""
        self._stats = stats
        self.setToolTip(
            "Blau: neu hinzugekommen. Grün: erledigt.\n"
            "Ist der blaue Balken höher, wächst der Bestand.\n\n" + FOOTNOTE
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Balkenpaare."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        months = self._stats.months if self._stats is not None else []
        if not months:
            self._draw_empty(painter)
            return

        colors = palette_for(self._mode)
        top = max(1.0, float(max(max(m.inflow, m.outflow) for m in months)))
        rect = self._draw_frame(painter, top)

        slot = rect.width() / len(months)
        bar = max(2.0, min(9.0, slot / 2.6))
        painter.setPen(Qt.PenStyle.NoPen)
        for index, month in enumerate(months):
            center = rect.left() + slot * (index + 0.5)
            for value, color, offset in (
                (month.inflow, colors.accent, -bar * 0.55),
                (month.outflow, colors.green, bar * 0.55),
            ):
                height = rect.height() * value / top
                painter.setBrush(QColor(color))
                painter.drawRect(
                    QRectF(center + offset - bar / 2, rect.bottom() - height, bar, height)
                )

        # Nur den ersten und letzten Monat beschriften - alle nebeneinander
        # ergaeben bei dieser Breite einen Brei.
        painter.setPen(QPen(QColor(colors.text_tertiary)))
        baseline = rect.bottom() + MARGIN_BOTTOM - 5
        painter.drawText(QPointF(rect.left(), baseline), months[0].month)
        if len(months) > 1:
            label = months[-1].month
            width = QFontMetricsF(painter.font()).horizontalAdvance(label)
            painter.drawText(QPointF(rect.right() - width, baseline), label)


class StockChart(_Chart):
    """Kumulierter Bestand als Kurve."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Bestand kumuliert", mode, parent)
        self._stats: Statistics | None = None

    def set_statistics(self, stats: Statistics | None) -> None:
        """Uebernimmt die Zahlen und zeichnet neu."""
        self._stats = stats
        self.setToolTip(
            "Offene Tickets über die Zeit. Eine steigende Kurve heißt: "
            "es kommt mehr herein als heraus.\n\n" + FOOTNOTE
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Kurve."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        months = self._stats.months if self._stats is not None else []
        if not months:
            self._draw_empty(painter)
            return

        colors = palette_for(self._mode)
        top = max(1.0, float(max(m.cumulative for m in months)))
        rect = self._draw_frame(painter, top)

        step = rect.width() / max(1, len(months) - 1)
        points = [
            QPointF(
                rect.left() + step * index,
                rect.bottom() - rect.height() * month.cumulative / top,
            )
            for index, month in enumerate(months)
        ]

        # Flaeche unter der Kurve dezent fuellen - macht die Richtung auf
        # einen Blick lesbar, ohne die Linie zu ueberdecken.
        area = QPolygonF([QPointF(points[0].x(), rect.bottom()), *points])
        area.append(QPointF(points[-1].x(), rect.bottom()))
        fill = QColor(colors.accent)
        fill.setAlpha(48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPolygon(area)

        pen = QPen(QColor(colors.accent))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))

        painter.setPen(QPen(QColor(colors.text_tertiary)))
        baseline = rect.bottom() + MARGIN_BOTTOM - 5
        painter.drawText(QPointF(rect.left(), baseline), months[0].month)
        if len(months) > 1:
            label = months[-1].month
            width = QFontMetricsF(painter.font()).horizontalAdvance(label)
            painter.drawText(QPointF(rect.right() - width, baseline), label)


class AgeChart(_Chart):
    """Altersverteilung der offenen Tickets als Balken."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Liegezeit der offenen Tickets", mode, parent)
        self._stats: Statistics | None = None

    def set_statistics(self, stats: Statistics | None) -> None:
        """Uebernimmt die Zahlen und zeichnet neu."""
        self._stats = stats
        self.setToolTip(
            "Wie viele Tickets wie lange unverändert liegen, in Arbeitstagen.\n"
            "Ein schwerer rechter Rand heißt: der Bestand ist alt.\n\n"
            "\"Offen\" heißt hier: nicht in Jiras Kategorie Fertig. Die Liste "
            "darüber zeigt zusätzlich die Abschluss-Status, die Jira bereits "
            "als fertig zählt - deshalb steht dort eine höhere Zahl."
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Klassen."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        buckets = self._stats.buckets if self._stats is not None else []
        if not buckets or not any(b.count for b in buckets):
            self._draw_empty(painter)
            return

        colors = palette_for(self._mode)
        top = max(1.0, float(max(b.count for b in buckets)))
        rect = self._draw_frame(painter, top)

        # Von frisch nach alt einfaerben. Die Farbe traegt hier eine Aussage,
        # deshalb feste Werte statt Theme-Farben - eine Ampel muss ueberall
        # dieselbe sein.
        tones = (colors.green, colors.accent, colors.orange, colors.red)
        slot = rect.width() / len(buckets)
        bar = min(26.0, slot * 0.55)
        metrics = QFontMetricsF(painter.font())
        baseline = rect.bottom() + MARGIN_BOTTOM - 5

        for index, bucket in enumerate(buckets):
            center = rect.left() + slot * (index + 0.5)
            height = rect.height() * bucket.count / top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tones[min(index, len(tones) - 1)]))
            painter.drawRect(QRectF(center - bar / 2, rect.bottom() - height, bar, height))

            painter.setPen(QPen(QColor(colors.text_secondary)))
            value = str(bucket.count)
            painter.drawText(
                QPointF(center - metrics.horizontalAdvance(value) / 2, rect.bottom() - height - 3),
                value,
            )
            painter.setPen(QPen(QColor(colors.text_tertiary)))
            painter.drawText(
                QPointF(center - metrics.horizontalAdvance(bucket.label) / 2, baseline),
                bucket.label,
            )


class ChartPanel(QWidget):
    """Einklappbarer Streifen mit den drei Diagrammen.

    Standardmaessig zu: die Diagramme sind Beiwerk, die Liste ist der Inhalt.
    Die Zahlen werden erst beim ersten Aufklappen geholt - ein Abruf, den
    niemand sehen will, muss auch nicht laufen.
    """

    statistics_requested = Signal()

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._requested = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._toggle = QToolButton()
        self._toggle.setObjectName("ChartToggle")
        self._toggle.setText("Auswertung")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setAutoRaise(True)
        self._toggle.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)

        charts = QHBoxLayout()
        charts.setSpacing(12)
        self._flow = FlowChart(mode)
        self._stock = StockChart(mode)
        self._age = AgeChart(mode)
        for chart in (self._flow, self._stock, self._age):
            charts.addWidget(chart, 1)
        body.addLayout(charts)

        self._note = QLabel(FOOTNOTE)
        self._note.setObjectName("ChartNote")
        self._note.setWordWrap(True)
        body.addWidget(self._note)

        self._body.setVisible(False)
        outer.addWidget(self._body)

    def set_statistics(self, stats: Statistics | None) -> None:
        """Verteilt die Zahlen auf die drei Diagramme."""
        for chart in (self._flow, self._stock, self._age):
            chart.set_statistics(stats)

    def apply_mode(self, mode: Mode) -> None:
        """Uebernimmt ein anderes Erscheinungsbild."""
        self._mode = mode
        for chart in (self._flow, self._stock, self._age):
            chart.apply_mode(mode)

    def invalidate(self) -> None:
        """Vergisst, dass die Zahlen schon geholt wurden.

        Nach einem neuen Abruf der Liste sind sie veraltet - beim naechsten
        Aufklappen werden sie erneut angefordert.
        """
        self._requested = False
        if self._toggle.isChecked():
            self._request()

    def _on_toggled(self, expanded: bool) -> None:
        """Klappt auf oder zu und holt beim ersten Mal die Zahlen."""
        self._body.setVisible(expanded)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        if expanded:
            self._request()

    def _request(self) -> None:
        """Fordert die Zahlen an, aber hoechstens einmal je Stand."""
        if self._requested:
            return
        self._requested = True
        self.statistics_requested.emit()

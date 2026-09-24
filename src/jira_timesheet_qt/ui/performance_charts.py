"""Diagramme des Performance-Boosters, selbst gezeichnet mit QPainter.

Aus demselben Grund wie ticket_charts ohne QtCharts (Lizenz). Das Geruest
(Titel, Skala, Hilfslinien) kommt von dort.

1. Verlauf - erledigte und erstellte Tickets kumuliert, die Vorperiode gestrichelt.
2. Durchlaufzeit - Anzahl Tickets je Klasse aktiver Arbeitstage.
3. Ticketgroessen - Verteilung der gebuchten Stunden, "klein" hervorgehoben.
4. Rollenprofil - geschrieben, umgesetzt, geschlossen.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from jira_timesheet_qt.services.performance import (
    PerformanceReport,
    cumulative_days,
    cumulative_done,
    cycle_buckets,
    size_buckets,
)

from .theme import Mode, palette_for
from .ticket_charts import MARGIN_BOTTOM, MARGIN_LEFT, MARGIN_TOP, _Chart


def _scale_top(highest: int) -> float:
    """Obergrenze der Skala fuer ganze Zahlen.

    Mit etwas Luft, damit die Zahl ueber der hoechsten Saeule nicht in den
    Titel laeuft, und gerade, damit die Mittellinie eine ganze Zahl traegt -
    sonst stuende bei einer Obergrenze von 1 zweimal "0" an der Skala.
    """
    top = max(2, math.ceil(highest * 1.2))
    return float(top + top % 2)


def _label_edges(chart: _Chart, painter: QPainter, rect: QRectF, left: str, right: str) -> None:
    """Beschriftet Anfang und Ende der x-Achse."""
    colors = palette_for(chart._mode)
    painter.setPen(QPen(QColor(colors.text_tertiary)))
    baseline = rect.bottom() + MARGIN_BOTTOM - 5
    painter.drawText(QPointF(rect.left(), baseline), left)
    width = QFontMetricsF(painter.font()).horizontalAdvance(right)
    painter.drawText(QPointF(rect.right() - width, baseline), right)


class _ReportChart(_Chart):
    """Ein Diagramm, das einen Bericht zeigt."""

    def __init__(self, title: str, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        # Der Titel steht als Ueberschrift der Karte (PerformanceView), nicht
        # klein im Diagramm - die Zeile darueber bleibt fuer die Legende frei.
        super().__init__("", mode, parent)
        self.card_title = title
        self._report: PerformanceReport | None = None
        self.setMinimumHeight(120)

    def set_report(self, report: PerformanceReport | None) -> None:
        """Uebernimmt den Bericht und zeichnet neu."""
        self._report = report
        self.update()

    def _draw_bars(self, painter: QPainter, buckets: list[tuple[str, int, str]]) -> None:
        """Zeichnet beschriftete Saeulen. Je Klasse (Beschriftung, Anzahl, Farbe)."""
        colors = palette_for(self._mode)
        top = _scale_top(max(count for _, count, _ in buckets))
        rect = self._draw_frame(painter, top)
        slot = rect.width() / len(buckets)
        bar = min(26.0, slot * 0.55)
        metrics = QFontMetricsF(painter.font())
        baseline = rect.bottom() + MARGIN_BOTTOM - 5
        for index, (label, count, tone) in enumerate(buckets):
            center = rect.left() + slot * (index + 0.5)
            height = rect.height() * count / top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tone))
            if height > 0:
                painter.drawRoundedRect(QRectF(center - bar / 2, rect.bottom() - height, bar, height), 2.5, 2.5)
            painter.setPen(QPen(QColor(colors.text_secondary)))
            value = str(count)
            painter.drawText(QPointF(center - metrics.horizontalAdvance(value) / 2, rect.bottom() - height - 3), value)
            painter.setPen(QPen(QColor(colors.text_tertiary)))
            painter.drawText(QPointF(center - metrics.horizontalAdvance(label) / 2, baseline), label)


class CourseChart(_ReportChart):
    """Erledigte und erstellte Tickets kumuliert, mit der Vorperiode dahinter."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Erledigt und erstellt, kumuliert", mode, parent)
        self.setToolTip(
            "Erledigt: Tickets der Person, die im Zeitraum fertig wurden, aufsummiert.\n"
            "Grün, wenn es mindestens so viele sind wie in der Vorperiode, sonst rot.\n"
            "Erstellt: Tickets, die die Person selbst angelegt hat - der Zulauf.\n"
            "Gestrichelt: erledigt in der Vorperiode."
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Kurven und eine kleine Legende."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        report = self._report
        if report is None or not (report.tickets or report.prior_tickets or report.created):
            self._draw_empty(painter)
            return

        colors = palette_for(self._mode)
        current = cumulative_done(report.tickets, report.period)
        prior = cumulative_done(report.prior_tickets, report.prior_period)
        created = cumulative_days(report.created, report.period)
        top = _scale_top(max(current[-1], prior[-1], created[-1]))
        rect = self._draw_frame(painter, top)

        def points(series: list[int]) -> list[QPointF]:
            step = rect.width() / max(1, len(series) - 1)
            return [
                QPointF(rect.left() + step * index, rect.bottom() - rect.height() * value / top)
                for index, value in enumerate(series)
            ]

        dashed = QPen(QColor(colors.text_tertiary))
        dashed.setStyle(Qt.PenStyle.DashLine)
        dashed.setWidthF(1.2)
        painter.setPen(dashed)
        painter.drawPolyline(QPolygonF(points(prior)))

        line = points(current)
        tone = QColor(colors.green if current[-1] >= prior[-1] else colors.red)
        area = QPolygonF([QPointF(line[0].x(), rect.bottom()), *line, QPointF(line[-1].x(), rect.bottom())])
        fill = QColor(tone)
        fill.setAlpha(48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPolygon(area)
        pen = QPen(tone)
        pen.setWidthF(1.8)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(line))

        created_pen = QPen(QColor(colors.purple))
        created_pen.setWidthF(1.6)
        painter.setPen(created_pen)
        painter.drawPolyline(QPolygonF(points(created)))

        self._draw_legend(painter, rect, [("erledigt", tone.name()), ("erstellt", colors.purple)])
        _label_edges(self, painter, rect, f"{report.period.start:%d.%m.}", f"{report.period.end:%d.%m.%Y}")

    def _draw_legend(self, painter: QPainter, rect: QRectF, entries: list[tuple[str, str]]) -> None:
        """Kurze Legende rechts in der Titelzeile."""
        colors = palette_for(self._mode)
        metrics = QFontMetricsF(painter.font())
        x = rect.right()
        y = MARGIN_TOP / 2
        for label, tone in reversed(entries):
            x -= metrics.horizontalAdvance(label)
            painter.setPen(QPen(QColor(colors.text_secondary)))
            painter.drawText(QPointF(x, y + 4), label)
            x -= 16
            pen = QPen(QColor(tone))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, y), QPointF(x + 12, y))
            x -= 12


class CycleChart(_ReportChart):
    """Verteilung der Durchlaufzeit in Klassen aktiver Arbeitstage."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Durchlaufzeit (Arbeitstage aktiv)", mode, parent)
        self.setToolTip(
            "Wie viele erledigte Tickets wie lange in einem aktiven Status standen.\n"
            "Wartezeiten bei Abnahme oder Autor zählen nicht mit.\n"
            "Rot: über der Schwelle für lange Tickets. Nie aktiv: direkt geschlossen."
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Klassen."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        report = self._report
        buckets = cycle_buckets(report.tickets, report.config.long_days) if report else []
        if not buckets or not any(count for _, count, _ in buckets):
            self._draw_empty(painter)
            return
        colors = palette_for(self._mode)
        self._draw_bars(
            painter,
            [
                (label, count, colors.red if long else (colors.text_tertiary if index == 0 else colors.purple))
                for index, (label, count, long) in enumerate(buckets)
            ],
        )


class SizeChart(_ReportChart):
    """Verteilung der Ticketgroessen in gebuchten Stunden."""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Ticketgrößen (insgesamt gebucht)", mode, parent)
        self.setToolTip(
            "Wie viele erledigte Tickets wie viel gebuchte Zeit trugen.\n"
            "Rot: unter der Schwelle für kleine Tickets.\n"
            "0 h: gar nicht gebucht - zählt nicht als klein."
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet die Klassen."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        report = self._report
        buckets = size_buckets(report.tickets, report.config.small_hours) if report else []
        if not buckets or not any(count for _, count, _ in buckets):
            self._draw_empty(painter)
            return
        colors = palette_for(self._mode)
        self._draw_bars(
            painter,
            [
                (label, count, colors.red if small else (colors.text_tertiary if index == 0 else colors.purple))
                for index, (label, count, small) in enumerate(buckets)
            ],
        )


class ProfileChart(_ReportChart):
    """Rollenprofil: schreibt, setzt um oder schliesst jemand eher Tickets?"""

    def __init__(self, mode: Mode = Mode.DARK, parent: QWidget | None = None) -> None:
        super().__init__("Rollenprofil", mode, parent)
        self.setToolTip(
            "Geschrieben: selbst angelegte Tickets.\n"
            "Umgesetzt: zugewiesene Tickets, die fertig wurden.\n"
            "Geschlossen: Tickets, die die Person selbst in einen Fertig-Status gezogen hat,\n"
            "egal wem sie zugewiesen waren.\n"
            "Der Strich zeigt den Wert der Vorperiode."
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt-Schreibweise
        """Zeichnet drei waagerechte Balken mit Anteil und Vorperiode."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        report = self._report
        if report is None:
            self._draw_empty(painter)
            return
        now, before = report.current, report.prior
        rows: list[tuple[str, int | None, int | None]] = [
            ("Geschrieben", now.created, before.created),
            ("Umgesetzt", now.done, before.done),
            ("Geschlossen", now.closed, before.closed),
        ]
        if not any(value for _, value, _ in rows):
            self._draw_empty(painter)
            return

        colors = palette_for(self._mode)
        font = painter.font()
        font.setPointSizeF(max(6.5, font.pointSizeF() - 1.5))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        painter.setPen(QPen(QColor(colors.text_secondary)))
        painter.drawText(
            QRectF(MARGIN_LEFT, 0, self.width(), MARGIN_TOP),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._title,
        )

        total = sum(value for _, value, _ in rows if value is not None) or 1
        top = max([1] + [v for _, value, prior in rows for v in (value or 0, prior or 0)])
        label_width = max(metrics.horizontalAdvance(label) for label, _, _ in rows) + 10
        left = 8 + label_width
        right = self.width() - 70
        area = QRectF(left, MARGIN_TOP + 4, max(1.0, right - left), max(1.0, self.height() - MARGIN_TOP - 10))
        slot = area.height() / len(rows)
        tones = (colors.purple, colors.green, colors.accent)
        for index, (label, value, prior) in enumerate(rows):
            center = area.top() + slot * (index + 0.5)
            height = min(18.0, slot * 0.55)
            text_y = center + metrics.ascent() / 2 - 1
            painter.setPen(QPen(QColor(colors.text_secondary)))
            painter.drawText(QPointF(8, text_y), label)
            if value is None:
                painter.setPen(QPen(QColor(colors.text_tertiary)))
                painter.drawText(QPointF(left, text_y), "nicht ermittelbar")
                continue
            width = area.width() * value / top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tones[index]))
            if width > 0:
                painter.drawRoundedRect(QRectF(left, center - height / 2, width, height), 2.5, 2.5)
            if prior is not None:
                marker = left + area.width() * prior / top
                painter.setPen(QPen(QColor(colors.text_primary), 2.0))
                painter.drawLine(QPointF(marker, center - height / 2 - 3), QPointF(marker, center + height / 2 + 3))
            painter.setPen(QPen(QColor(colors.text_secondary)))
            share = round(100 * value / total)
            painter.drawText(QPointF(left + width + 6, text_y), f"{value} ({share} %)")

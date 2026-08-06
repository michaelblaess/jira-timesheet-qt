"""Zell-Delegate der Liste: Innenabstand rechts und Hervorhebung des Suchbegriffs.

Zwei Aufgaben, ein Zeichenweg:

1. Jede Zelle bekommt rechts einen zusaetzlichen Innenabstand. Qt gibt dem
   Zelltext nur wenige Pixel Rand - in einer rechtsbuendigen Zahlenspalte klebt
   die Zahl damit unmittelbar an der Spaltenkante, und in der letzten Spalte am
   Fensterrand. Das ist schwer zu lesen. Links bleibt der native Abstand
   unangetastet, sonst fluchtet der Zelltext nicht mehr mit der Kopfzeile.
2. Der aktuelle Suchbegriff wird in der Zelle farblich hervorgehoben. Dafuer
   wird die Zelle als QTextDocument (Rich Text) gerendert - das kanonische
   Qt-Muster. Wichtig: NIE echte Rich-Text-Widgets pro Zelle verwenden (das
   bricht bei vielen Zeilen ein), sondern pro paint() ein frisches Dokument.
   Die View malt ohnehin nur die sichtbaren Zellen.

Beide Faelle zeichnen in dasselbe Text-Rechteck, damit der Text beim Tippen im
Suchfeld nicht springt.
"""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

# Warmes Gelb mit dunklem Text - lesbar auf hellen wie dunklen (auch ausgewaehlten)
# Zeilen, unabhaengig vom Erscheinungsbild.
_MATCH_BACKGROUND = "#ffd24a"
_MATCH_FOREGROUND = "#1c1f24"

# Zusaetzlicher Rand rechts in jeder Zelle, in Pixeln. Nur rechts: der linke
# Rand kommt vom Stil und haelt den Zelltext in einer Flucht mit der Kopfzeile.
CELL_PADDING_RIGHT = 10

AnyIndex = QModelIndex | QPersistentModelIndex


class CellDelegate(QStyledItemDelegate):
    """Zeichnet Zelltext mit Rand rechts und hebt Treffer des Suchbegriffs hervor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._needle = ""

    def set_needle(self, needle: str) -> None:
        """Setzt den hervorzuhebenden Suchbegriff (leer = keine Hervorhebung)."""
        self._needle = needle

    @staticmethod
    def highlight_html(text: str, needle: str) -> str:
        """Baut das Zell-HTML: Treffer werden in ein farbiges span gewickelt.

        Args:
            text:
                Der anzuzeigende Zelltext (unmaskiert).
            needle:
                Der Suchbegriff. Leer -> nur maskierter Text ohne Hervorhebung.

        Returns:
            HTML-Zeichenkette mit maskiertem Text und markierten Treffern.
        """
        escaped = html.escape(text)
        if not needle:
            return escaped
        pattern = re.escape(needle)
        return re.sub(
            f"({pattern})",
            rf'<span style="background-color:{_MATCH_BACKGROUND}; '
            rf'color:{_MATCH_FOREGROUND};">\1</span>',
            escaped,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _text_color(opt: QStyleOptionViewItem) -> QColor:
        """Farbe des Zelltextes, wie der Stil sie waehlen wuerde.

        Beruecksichtigt Auswahl, deaktivierte Zeilen und ein Fenster ohne Fokus.
        Die Farbe eines Eintrags (Soll-Ist-Ampel, manueller Eintrag) steckt zu
        diesem Zeitpunkt bereits in der Palette - initStyleOption hat sie aus
        der ForegroundRole uebernommen.
        """
        if not (opt.state & QStyle.StateFlag.State_Enabled):
            group = QPalette.ColorGroup.Disabled
        elif not (opt.state & QStyle.StateFlag.State_Active):
            group = QPalette.ColorGroup.Inactive
        else:
            group = QPalette.ColorGroup.Normal
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        return opt.palette.color(group, role)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: AnyIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()

        text = opt.text
        # Hintergrund, Auswahl und Fokusrahmen zeichnet der Stil ueber die volle
        # Zellbreite - nur der Text bekommt gleich weniger Platz. Wuerde man
        # stattdessen das ganze Zell-Rechteck verkleinern, bliebe rechts ein
        # heller Streifen in jeder ausgewaehlten Zeile stehen.
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not text:
            return

        rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget
        ).adjusted(0, 0, -CELL_PADDING_RIGHT, 0)
        if rect.width() <= 0:
            return

        alignment = opt.displayAlignment
        # Wie die native Zelle rechts mit "..." kuerzen. Ein sichtbarer Treffer
        # bleibt markiert; liegt der Treffer im abgeschnittenen Teil, zeigt die
        # Zelle nur "..." - die Zeile ist trotzdem gefiltert.
        elided = QFontMetrics(opt.font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        color = self._text_color(opt)

        if not self._needle or self._needle.lower() not in text.lower():
            painter.save()
            painter.setFont(opt.font)
            painter.setPen(color)
            painter.drawText(rect, int(alignment), elided)
            painter.restore()
            return

        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(opt.font)
        text_option = QTextOption(alignment)
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        doc.setDefaultTextOption(text_option)
        inner = self.highlight_html(elided, self._needle)
        doc.setHtml(f'<span style="color:{color.name()};">{inner}</span>')
        doc.setTextWidth(rect.width())

        painter.save()
        offset_y = rect.top() + max(0.0, (rect.height() - doc.size().height()) / 2)
        painter.translate(rect.left(), offset_y)
        doc.drawContents(painter, QRectF(0, 0, float(rect.width()), float(rect.height())))
        painter.restore()

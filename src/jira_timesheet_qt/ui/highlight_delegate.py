"""Zell-Delegate, der den aktuellen Suchbegriff in der Tabelle farblich hervorhebt.

Der Standard-Delegate zeichnet nur einfachen Text. Um eine Teilzeichenkette
innerhalb einer Zelle einzufaerben, wird die Zelle als QTextDocument (Rich Text)
gerendert - das kanonische Qt-Muster. Wichtig: NIE echte Rich-Text-Widgets pro
Zelle verwenden (das bricht bei vielen Zeilen ein), sondern pro paint() ein
frisches QTextDocument. Die View malt ohnehin nur die sichtbaren Zellen.
"""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPalette, QTextDocument, QTextOption
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

AnyIndex = QModelIndex | QPersistentModelIndex


class HighlightDelegate(QStyledItemDelegate):
    """Hebt Treffer des aktuellen Suchbegriffs in der Zelle hervor."""

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

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: AnyIndex) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole)
        # Ohne Suchbegriff oder ohne Treffer in DIESER Zelle: normal zeichnen.
        if (
            not self._needle
            or not isinstance(text, str)
            or self._needle.lower() not in text.lower()
        ):
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()

        # Hintergrund, Auswahl und Fokus vom Stil zeichnen lassen, aber ohne Text -
        # den uebernimmt gleich das QTextDocument.
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        base_role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        base_color = opt.palette.color(base_role).name()

        align = index.data(Qt.ItemDataRole.TextAlignmentRole)
        alignment = Qt.AlignmentFlag(int(align)) if align is not None else Qt.AlignmentFlag.AlignLeft

        pad = 8
        width = max(0, opt.rect.width() - 2 * pad)

        # Wie die native Zelle rechts mit "..." kuerzen. Ein sichtbarer Treffer
        # bleibt markiert; liegt der Treffer im abgeschnittenen Teil, zeigt die
        # Zelle nur "..." - die Zeile ist trotzdem gefiltert.
        elided = QFontMetrics(opt.font).elidedText(text, Qt.TextElideMode.ElideRight, width)

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        text_option = QTextOption(alignment)
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        doc.setDefaultTextOption(text_option)
        inner = self.highlight_html(elided, self._needle)
        doc.setHtml(f'<span style="color:{base_color};">{inner}</span>')
        doc.setTextWidth(width)

        painter.save()
        offset_y = opt.rect.top() + max(0.0, (opt.rect.height() - doc.size().height()) / 2)
        painter.translate(opt.rect.left() + pad, offset_y)
        doc.drawContents(painter, QRectF(0, 0, width, float(opt.rect.height())))
        painter.restore()

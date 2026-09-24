"""Pfeil statt Text-Cursor ueber Tabellen und Listen.

Die Tabellen setzen selbst keinen Cursor und erben ihn nur. Michael sah
ueber ihnen dauerhaft den Text-Cursor (24.09.2026), obwohl Qt fuer die
Flaeche unter der Maus den Pfeil meldet - gemessen per widgetAt. Die
Ursache ist nicht belegt. Ein ausdruecklich gesetzter Pfeil macht die
Flaeche unabhaengig davon, was vorher unter der Maus lag.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QWidget


def use_arrow_cursor(root: QWidget) -> int:
    """Setzt den Pfeil auf die Anzeigeflaeche aller Tabellen, Baeume und Listen unter root.

    Ein Editor fuer die Inline-Bearbeitung bringt seinen eigenen Text-Cursor
    mit und ist davon nicht betroffen.

    Args:
        root:
            Fenster oder Dialog.

    Returns:
        Wie viele Ansichten den Pfeil bekommen haben.
    """
    views = root.findChildren(QAbstractItemView)
    for view in views:
        view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
    return len(views)

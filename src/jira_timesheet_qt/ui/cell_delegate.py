"""Zell-Delegate - liegt in QAppFramework.

Er steht dort, weil jede Tabelle jeder Anwendung ihn braucht: ohne ihn gibt Qt
dem Zelltext vier Bildpunkte bis zur Spaltenkante. Die Namen hier bleiben, weil
sie an mehreren Stellen und in den Tests stehen.
"""

from __future__ import annotations

from QAppFramework.cell import CELL_PADDING_RIGHT as CELL_PADDING_RIGHT
from QAppFramework.cell import CellDelegate as _CellDelegate

__all__ = ["CELL_PADDING_RIGHT", "CellDelegate"]


class CellDelegate(_CellDelegate):
    """Der Delegate der Bibliothek unter dem hier ueblichen Namen."""

    def set_needle(self, needle: str) -> None:
        """Setzt den hervorzuhebenden Suchbegriff (leer = keine Hervorhebung)."""
        self.setze_suchbegriff(needle)

    @staticmethod
    def highlight_html(text: str, needle: str) -> str:
        """Baut das Zell-HTML: Treffer werden in ein farbiges span gewickelt."""
        return _CellDelegate.hervorhebung(text, needle)

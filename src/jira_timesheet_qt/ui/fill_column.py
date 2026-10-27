"""Eine Spalte fuellt die Restbreite, und trotzdem bleibt jede Spalte ziehbar.

QHeaderView.Stretch fuellt zwar, taugt aber nicht zum Ziehen. Die rechte Kante
der gestreckten Spalte laesst sich gar nicht greifen. Und zieht man eine Spalte
rechts davon breiter, nimmt Qt den Platz der gestreckten Spalte weg: die
gezogene Kante bleibt stehen, statt der Maus zu folgen (Michael, 27.10.2026,
im Reiter "Neue Tickets").

Hier sind alle Spalten Interactive. Die Fuellspalte bekommt die freie Breite,
wenn sich die Ansicht in der Breite aendert oder neu befuellt wird, aber nie
waehrend jemand zieht. Untergrenze ist ihre zuletzt gezogene Breite, sonst
eine Vorgabe. Gezogene Breiten der anderen Spalten ueberstehen ein Neuladen.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QHeaderView, QTableView

# Untergrenze der Fuellspalte, solange niemand an ihr gezogen hat.
FILL_MIN = 160
# Innenabstand des Delegates, den resizeColumnsToContents nicht kennt.
CONTENT_PADDING = 16


class FillColumn(QObject):
    """Haelt eine Spalte auf Restbreite und merkt sich gezogene Breiten."""

    def __init__(self, view: QTableView, column: int, minimum: int = FILL_MIN) -> None:
        super().__init__(view)
        self._view = view
        self._column = column
        self._floor = minimum
        self._dragged: dict[int, int] = {}
        self._adjusting = False
        header = self._header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionResized.connect(self._on_resized)
        view.viewport().installEventFilter(self)
        header.viewport().installEventFilter(self)

    def _header(self) -> QHeaderView:
        return self._view.horizontalHeader()

    def autosize(self) -> None:
        """Spalten nach Inhalt, gezogene Breiten bleiben stehen, danach fuellen."""
        header = self._header()
        self._adjusting = True
        try:
            self._view.resizeColumnsToContents()
            for section in range(header.count()):
                if section in self._dragged:
                    header.resizeSection(section, self._dragged[section])
                elif section != self._column:
                    header.resizeSection(section, header.sectionSize(section) + CONTENT_PADDING)
        finally:
            self._adjusting = False
        self.fill()

    def fill(self, grow_only: bool = False) -> None:
        """Gibt der Fuellspalte die freie Breite, mindestens ihre Untergrenze.

        Mit grow_only waechst sie nur in eine Luecke hinein und schrumpft nicht.
        """
        header = self._header()
        if self._column >= header.count():
            return
        others = sum(
            header.sectionSize(section)
            for section in range(header.count())
            if section != self._column and not header.isSectionHidden(section)
        )
        target = max(self._floor, self._view.viewport().width() - others)
        current = header.sectionSize(self._column)
        if target == current or (grow_only and target < current):
            return
        self._adjusting = True
        try:
            header.resizeSection(self._column, target)
        finally:
            self._adjusting = False

    def _on_resized(self, section: int, _old: int, new: int) -> None:
        # Waehrend des Ziehens nichts nachfuellen, sonst folgt die Kante der Maus nicht.
        if self._adjusting or new <= 0:
            return
        if section == self._column:
            self._floor = new
        else:
            self._dragged[section] = new

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Fuellt nach, wenn die Ansicht breiter oder schmaler wird oder ein Ziehen endet.

        Nur die Breite zaehlt. Zieht jemand eine Spalte breiter, erscheint die
        waagrechte Bildlaufleiste und der Viewport wird niedriger. Fuellte das
        nach, sprange der Titel mitten im Ziehen zurueck.
        """
        if isinstance(event, QResizeEvent) and event.size().width() != event.oldSize().width():
            self.fill()
        elif event.type() == QEvent.Type.MouseButtonRelease:
            # Nach dem Ziehen eine entstandene Luecke schliessen, aber nichts wegnehmen.
            self.fill(grow_only=True)
        return super().eventFilter(obj, event)

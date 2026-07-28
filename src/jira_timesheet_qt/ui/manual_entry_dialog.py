"""Dialog zum Erfassen und Bearbeiten manueller Zeiten.

Entspricht dem "Manuelle Zeit erfassen"-Dialog der TUI: Datum, Ticket,
Beschreibung, Kunde und Aufwand. Der Aufwand wird tolerant geparst
(3h 30m, 3:30, 3,5). Die Persistenz liegt ausserhalb - der Dialog liefert nur
einen ManualEntry zurueck.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.services.hours_parser import parse_hours
from jira_timesheet_qt.services.manual_entry_service import ManualEntry

FIELD_WIDTH = 320


class ManualEntryDialog(QDialog):
    """Erfasst oder bearbeitet einen manuellen Zeiteintrag."""

    def __init__(
        self,
        *,
        customers: Sequence[str],
        default_customer: str,
        entry: ManualEntry | None = None,
        default_date: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entry = entry
        self._result: ManualEntry | None = None
        self.setWindowTitle("Manuellen Eintrag bearbeiten" if entry else "Manuelle Zeit erfassen")
        self.setSizeGripEnabled(True)
        self.setMinimumWidth(480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(24, 22, 24, 12)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        start = entry.entry_date if entry else (default_date or date.today())
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.date.setDate(QDate(start.year, start.month, start.day))
        self.date.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Datum"), self.date)

        self.ticket = QLineEdit(entry.ticket if entry else "")
        self.ticket.setFixedWidth(FIELD_WIDTH)
        self.ticket.setPlaceholderText("z.B. PROJ-0 (optional)")
        form.addRow(self._label("Ticket"), self.ticket)

        self.summary = QLineEdit(entry.summary if entry else "")
        self.summary.setFixedWidth(FIELD_WIDTH)
        self.summary.setPlaceholderText("Kurze Beschreibung der Tätigkeit")
        form.addRow(self._label("Beschreibung"), self.summary)

        self.customer = QComboBox()
        self.customer.setEditable(True)
        self.customer.setView(QListView())
        self.customer.setFixedWidth(FIELD_WIDTH)
        self.customer.addItems(list(customers))
        self.customer.setCurrentText(entry.customer if entry else default_customer)
        form.addRow(self._label("Kunde"), self.customer)

        self.hours = QLineEdit(self._format_hours(entry.hours) if entry else "")
        self.hours.setFixedWidth(FIELD_WIDTH)
        self.hours.setPlaceholderText("z.B. 3h 30m, 3:30 oder 3,5")
        form.addRow(self._label("Aufwand"), self.hours)

        outer.addWidget(body)
        outer.addWidget(self._buttons())

    # --- Ergebnis -------------------------------------------------------

    def result_entry(self) -> ManualEntry | None:
        """Liefert den erfassten Eintrag (nur nach erfolgreichem Speichern)."""
        return self._result

    def _on_save(self) -> None:
        """Prueft die Eingaben und schliesst den Dialog bei Erfolg."""
        entry = self._build_entry()
        if entry is None:
            QMessageBox.warning(
                self,
                "Ungültiger Aufwand",
                "Bitte den Aufwand angeben, z.B. „3h 30m“, „3:30“ oder „3,5“.",
            )
            self.hours.setFocus()
            return
        self._result = entry
        self.accept()

    def _build_entry(self) -> ManualEntry | None:
        """Baut den Eintrag aus den Feldern; None bei ungueltigem Aufwand.

        Bewusst ohne UI-Rueckmeldung - so ist die Validierung ohne blockierenden
        Dialog testbar.
        """
        hours = parse_hours(self.hours.text())
        if hours is None:
            return None
        qdate = self.date.date()
        return ManualEntry(
            entry_date=date(qdate.year(), qdate.month(), qdate.day()),
            ticket=self.ticket.text().strip(),
            summary=self.summary.text().strip(),
            customer=self.customer.currentText().strip(),
            hours=hours,
            entry_id=self._entry.entry_id if self._entry else 0,
        )

    # --- Bausteine ------------------------------------------------------

    @staticmethod
    def _format_hours(hours: float) -> str:
        """Stellt Stunden fuer die Bearbeitung als Dezimalzahl dar (Komma)."""
        return f"{hours:.2f}".replace(".", ",")

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SettingsLabel")
        label.setMinimumWidth(110)
        return label

    def _buttons(self) -> QWidget:
        row = QWidget()
        row.setObjectName("DialogButtons")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(24, 14, 24, 16)
        layout.setSpacing(10)
        layout.addStretch(1)

        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

        save = QPushButton("Speichern")
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        layout.addWidget(save)
        return row

"""Einstellungen der Anwendung.

Bewusst kein QTabWidget: dessen Reiter sind eines der auffaelligsten Merkmale
einer Standard-Qt-Anwendung. Stattdessen eine schmale Liste links und die
Seiten in einem QStackedWidget - dasselbe Muster wie im Hauptfenster.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.models.export_column import ExportColumn, default_label
from jira_timesheet_qt.models.settings import (
    DEFAULT_DAY_OVER_COLOR,
    DEFAULT_DAY_UNDER_COLOR,
    Settings,
    normalize_color,
)
from jira_timesheet_qt.services.cache_service import CACHE_DIR
from jira_timesheet_qt.services.manual_entry_service import DB_FILE
from jira_timesheet_qt.ui.jira_worker import BudgetFieldWorker
from jira_timesheet_qt.ui.theme import ACCENT_LABELS, SCALES

# Einheitliche Breite aller Eingabefelder. Ohne das richtet sich jedes Feld
# nach seinem Inhalt, und die rechte Kante wirkt zerfranst.
FIELD_WIDTH = 240

# Kommalisten brauchen mehr Platz: "Fertig fuer Entwicklung, Offen" passt in
# ein Feld von 240 Pixeln nicht einmal zur Haelfte hinein. Die Ticket-Seite
# nimmt deshalb bewusst zwei Kanten in Kauf - schmale Zahlenfelder, breite
# Textfelder - statt Listen anzuzeigen, die man nicht lesen kann.
WIDE_FIELD_WIDTH = 2 * FIELD_WIDTH

# Bundeslaender fuer die Feiertagsberechnung.
_STATES = (
    ("BW", "Baden-Württemberg"),
    ("BY", "Bayern"),
    ("BE", "Berlin"),
    ("BB", "Brandenburg"),
    ("HB", "Bremen"),
    ("HH", "Hamburg"),
    ("HE", "Hessen"),
    ("MV", "Mecklenburg-Vorpommern"),
    ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"),
    ("RP", "Rheinland-Pfalz"),
    ("SL", "Saarland"),
    ("SN", "Sachsen"),
    ("ST", "Sachsen-Anhalt"),
    ("SH", "Schleswig-Holstein"),
    ("TH", "Thüringen"),
)


def _split(raw: str) -> list[str]:
    """Zerlegt eine Kommaliste, leere Eintraege entfallen."""
    return [part.strip() for part in raw.split(",") if part.strip()]


class SettingsDialog(QDialog):
    """Dialog zum Bearbeiten der Einstellungen.

    Bekommt die aktuellen Einstellungen, gibt bei Annahme die geaenderten
    zurueck. Gespeichert wird ausserhalb - der Dialog kennt keine Dateipfade.
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        # Faden fuer die Budget-Feld-Autoerkennung (ein Netzwerkaufruf).
        self._detect_worker: BudgetFieldWorker | None = None
        self.setWindowTitle("Einstellungen")
        # Die Breite folgt dem breitesten Feld: Seitenleiste, Beschriftung und
        # ein Textfeld von WIDE_FIELD_WIDTH muessen nebeneinander passen. Bei
        # 720 lief die Ticket-Seite rechts aus dem Dialog heraus.
        self.setMinimumSize(820, 520)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("SettingsNav")
        self._nav.setFixedWidth(180)
        self._nav.addItems(
            ["Zugang", "Arbeitszeit", "Tickets", "Export", "Spalten", "Darstellung", "Speicherort"]
        )
        self._nav.setCurrentRow(0)
        body.addWidget(self._nav)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._page_access())
        self._pages.addWidget(self._page_worktime())
        self._pages.addWidget(self._page_tickets())
        self._pages.addWidget(self._page_export())
        self._pages.addWidget(self._page_columns())
        self._pages.addWidget(self._page_appearance())
        self._pages.addWidget(self._page_storage())
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        body.addWidget(self._pages, 1)

        outer.addLayout(body, 1)
        outer.addWidget(self._buttons())

        # Der Import-Knopf gehoert zur Zugang-Seite und wird nur dort gezeigt.
        self._nav.currentRowChanged.connect(self._update_import_visibility)
        self._update_import_visibility(self._nav.currentRow())

        # Wird der Dialog geschlossen, waehrend die Autoerkennung laeuft, erst auf
        # den Faden warten - sonst zerstoert Qt ihn im Lauf.
        self.finished.connect(self._await_detect_worker)

    # --- Seiten ---------------------------------------------------------

    def _page_access(self) -> QWidget:
        page, form = self._page("Zugang zu Jira")

        self.host = QLineEdit(self._settings.jira_host)
        self.host.setFixedWidth(FIELD_WIDTH)
        self.host.setPlaceholderText("https://deine-firma.atlassian.net")
        form.addRow(self._label("Jira-Host"), self.host)

        self.email = QLineEdit(self._settings.email)
        self.email.setFixedWidth(FIELD_WIDTH)
        self.email.setPlaceholderText("vorname.nachname@firma.de")
        form.addRow(self._label("E-Mail"), self.email)

        self.token = QLineEdit(self._settings.jira_token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setFixedWidth(FIELD_WIDTH)
        self.token.setPlaceholderText("API-Token von id.atlassian.com")
        form.addRow(self._label("Token"), self.token)

        self.legacy = QCheckBox("Data Center statt Cloud (Bearer-Token, ältere API)")
        self.legacy.setChecked(self._settings.use_legacy_api)
        form.addRow(self._label(""), self.legacy)

        self.proxy = QLineEdit(self._settings.proxy_url)
        self.proxy.setFixedWidth(FIELD_WIDTH)
        self.proxy.setPlaceholderText("http://proxy:8080 - leer lässt die Umgebung entscheiden")
        form.addRow(self._label("Proxy"), self.proxy)

        self.budget_field = QLineEdit(self._settings.budget_field)
        self.budget_field.setFixedWidth(FIELD_WIDTH)
        self.budget_field.setPlaceholderText("customfield_XXXXX")
        budget_row = QWidget()
        budget_layout = QHBoxLayout(budget_row)
        budget_layout.setContentsMargins(0, 0, 0, 0)
        budget_layout.setSpacing(8)
        budget_layout.addWidget(self.budget_field)
        self.detect_budget = QPushButton("Automatisch ermitteln")
        self.detect_budget.setProperty("variant", "secondary")
        self.detect_budget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detect_budget.setToolTip(
            "Sucht in Jira (Cloud) das Custom-Feld mit 'budget' im Namen und trägt es hier ein."
        )
        self.detect_budget.clicked.connect(self._detect_budget_field)
        # Die Autoerkennung nutzt die Cloud-API - im Data-Center-Modus abgeschaltet.
        self.detect_budget.setEnabled(not self.legacy.isChecked())
        self.legacy.toggled.connect(lambda checked: self.detect_budget.setEnabled(not checked))
        budget_layout.addWidget(self.detect_budget)
        budget_layout.addStretch(1)
        form.addRow(self._label("Budget-Feld"), budget_row)

        form.addRow(
            self._hint(
                "Der Token wird unverschlüsselt in der Einstellungsdatei abgelegt. "
                "Wer Zugriff auf das Benutzerprofil hat, kann ihn lesen."
            )
        )
        return page

    def _update_import_visibility(self, row: int) -> None:
        """Zeigt den Import-Knopf nur auf der Zugang-Seite (erste Zeile)."""
        if self._import_button is not None:
            self._import_button.setVisible(row == 0)

    def _import_legacy_access(self) -> None:
        """Fuellt Zugangs- und Berechnungsfelder aus der Textual-TUI.

        Uebernommen wird erst in die Felder - gespeichert wird wie ueberall
        erst beim Klick auf "Speichern".
        """
        data = Settings.legacy_access()
        if data is None:
            QMessageBox.information(
                self,
                "Import",
                "Es wurde keine Einstellungsdatei der jira-timesheet-TUI gefunden.",
            )
            return

        # Zugang
        self.host.setText(str(data["jira_host"]))
        self.email.setText(str(data["email"]))
        self.token.setText(str(data["jira_token"]))
        self.legacy.setChecked(bool(data["use_legacy_api"]))
        self.proxy.setText(str(data["proxy_url"]))
        self.budget_field.setText(str(data["budget_field"]))

        # Berechnung / Arbeitszeit
        self.hours_per_day.setValue(float(data["hours_per_day"]))
        self.max_yearly.setValue(float(data["max_yearly_hours"]))
        self.hourly_rate.setValue(float(data["hourly_rate"]))
        self.vat_rate.setValue(float(data["vat_rate"]))
        state_index = self.state.findData(str(data["federal_state"]))
        if state_index >= 0:
            self.state.setCurrentIndex(state_index)

        QMessageBox.information(
            self,
            "Import",
            "Zugang und Berechnung (Stundensatz, MwSt, Arbeitszeit) aus "
            "jira-timesheet wurden übernommen.\nZum Sichern auf 'Speichern' klicken.",
        )

    # --- Budget-Feld automatisch ermitteln ------------------------------

    def _detect_budget_field(self) -> None:
        """Ermittelt das Budget-Custom-Field aus den aktuellen Zugangsfeldern.

        Liest Host/E-Mail/Token/Proxy aus den Eingabefeldern (damit auch frisch
        Eingetipptes greift) und startet den Netzwerkaufruf in einem Faden - der
        Dialog bleibt bedienbar.
        """
        if self._detect_worker is not None and self._detect_worker.isRunning():
            return
        host = self.host.text().strip().rstrip("/")
        email = self.email.text().strip()
        token = self.token.text().strip()
        proxy = self.proxy.text().strip()
        if not host or not email or not token:
            QMessageBox.warning(
                self, "Budget-Feld ermitteln", "Bitte zuerst Host, E-Mail und Token eintragen."
            )
            return

        self.detect_budget.setEnabled(False)
        self.detect_budget.setText("Ermittle ...")
        worker = BudgetFieldWorker(host, email, token, proxy, self)
        worker.found.connect(self._on_budget_found)
        worker.failed.connect(self._on_budget_failed)
        worker.finished.connect(self._on_detect_finished)
        self._detect_worker = worker
        worker.start()

    def _reset_detect_button(self) -> None:
        """Setzt den Knopf zurueck (Beschriftung und - je nach Modus - aktiv)."""
        self.detect_budget.setText("Automatisch ermitteln")
        self.detect_budget.setEnabled(not self.legacy.isChecked())

    def _on_detect_finished(self) -> None:
        """Gibt die Faden-Referenz frei, sobald er durch ist."""
        self._detect_worker = None

    def _on_budget_found(self, matches: list[tuple[str, str]]) -> None:
        """Uebernimmt den ersten Treffer und meldet das Ergebnis."""
        self._reset_detect_button()
        if not matches:
            QMessageBox.warning(
                self, "Budget-Feld ermitteln", "Kein Custom-Feld mit 'budget' im Namen gefunden."
            )
            return
        field_id, field_name = matches[0]
        self.budget_field.setText(field_id)
        if len(matches) == 1:
            QMessageBox.information(
                self, "Budget-Feld ermitteln", f"Budget-Feld gefunden: {field_name} ({field_id})"
            )
        else:
            listing = "\n".join(f"- {name} ({fid})" for fid, name in matches)
            QMessageBox.warning(
                self,
                "Budget-Feld ermitteln",
                f"Mehrere Treffer - der erste wurde übernommen:\n{listing}",
            )

    def _on_budget_failed(self, message: str) -> None:
        """Meldet einen Fehler der Autoerkennung."""
        self._reset_detect_button()
        QMessageBox.critical(self, "Budget-Feld ermitteln", message)

    def _await_detect_worker(self, _result: int) -> None:
        """Wartet beim Schliessen auf einen noch laufenden Erkennungs-Faden."""
        if self._detect_worker is not None and self._detect_worker.isRunning():
            self._detect_worker.wait(3000)

    def _page_worktime(self) -> QWidget:
        page, form = self._page("Arbeitszeit")

        self.hours_per_day = QDoubleSpinBox()
        self.hours_per_day.setRange(0.5, 24.0)
        self.hours_per_day.setSingleStep(0.5)
        self.hours_per_day.setDecimals(1)
        self.hours_per_day.setSuffix(" h")
        self.hours_per_day.setValue(self._settings.hours_per_day)
        self.hours_per_day.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Stunden pro Tag"), self.hours_per_day)

        self.max_yearly = QDoubleSpinBox()
        self.max_yearly.setRange(0.0, 5000.0)
        self.max_yearly.setSingleStep(10.0)
        self.max_yearly.setDecimals(1)
        self.max_yearly.setSuffix(" h")
        self.max_yearly.setValue(self._settings.max_yearly_hours)
        self.max_yearly.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Jahresbudget"), self.max_yearly)

        self.hourly_rate = QDoubleSpinBox()
        self.hourly_rate.setRange(0.0, 100000.0)
        self.hourly_rate.setSingleStep(5.0)
        self.hourly_rate.setDecimals(2)
        self.hourly_rate.setSuffix(" €")
        self.hourly_rate.setValue(self._settings.hourly_rate)
        self.hourly_rate.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Stundensatz"), self.hourly_rate)

        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0.0, 100.0)
        self.vat_rate.setSingleStep(1.0)
        self.vat_rate.setDecimals(1)
        self.vat_rate.setSuffix(" %")
        self.vat_rate.setValue(self._settings.vat_rate)
        self.vat_rate.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("MwSt-Satz"), self.vat_rate)

        self.vacation = QSpinBox()
        self.vacation.setRange(0, 90)
        self.vacation.setSuffix(" Tage")
        self.vacation.setValue(self._settings.vacation_days)
        self.vacation.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Urlaubstage"), self.vacation)

        self.state = self._combo()
        for code, name in _STATES:
            self.state.addItem(name, code)
        index = self.state.findData(self._settings.federal_state)
        self.state.setCurrentIndex(max(0, index))
        form.addRow(self._label("Bundesland"), self.state)
        form.addRow(self._hint("Bestimmt, welche Feiertage als arbeitsfrei gelten."))
        return page

    def _page_tickets(self) -> QWidget:
        page, form = self._page("Ticket-Ansichten")

        form.addRow(
            self._hint(
                "Die Ansicht gruppiert deine Tickets danach, wer gerade am Zug ist. Trage "
                "hier ein, welcher Status deiner Jira-Instanz zu welcher Gruppe gehört - "
                "mehrere durch Komma getrennt, genau so geschrieben wie im Ticket. Die "
                "grauen Beispiele sind erfunden und zeigen nur die Form. Bleiben die Felder "
                "leer, ordnet die Anwendung grob nach der Jira-Statuskategorie zu."
            )
        )

        self.board_active = self._wide_edit(
            self._settings.board_active_status, "In Bearbeitung, Im Review"
        )
        form.addRow(self._label("Ich bin dran"), self.board_active)

        self.board_backlog = self._wide_edit(
            self._settings.board_backlog_status, "Bereit, Eingeplant"
        )
        form.addRow(self._label("Backlog"), self.board_backlog)

        self.board_acceptance = self._wide_edit(
            self._settings.board_acceptance_status, "Wartet auf Freigabe, Beim Fachbereich"
        )
        form.addRow(self._label("Andere sind dran"), self.board_acceptance)

        self.board_handback = self._wide_edit(
            self._settings.board_handback_status, "Ausgeliefert, Zur Bewertung"
        )
        form.addRow(self._label("Rückgabe"), self.board_handback)
        form.addRow(
            self._hint(
                "Ausgeliefert, wartet auf Bewertung. Bei fremdem Autor gehört das Ticket "
                "zurückgegeben; bist du selbst der Autor, bleibt es bei dir."
            )
        )

        self.board_closing = self._wide_edit(
            self._settings.board_closing_status, "Zur Abnahme, Doku offen"
        )
        form.addRow(self._label("Abschluss offen"), self.board_closing)
        form.addRow(
            self._hint(
                "Status, die Jira als fertig zählt, obwohl noch etwas zu tun ist. Ohne "
                "diesen Eintrag fallen solche Tickets komplett aus der Ansicht."
            )
        )

        self.board_priorities = self._wide_edit(
            self._settings.board_priorities, "Blocker, Kritisch, Hoch, Mittel, Niedrig"
        )
        form.addRow(self._label("Prioritäten"), self.board_priorities)
        form.addRow(self._hint("Rangfolge, dringendstes zuerst. Leer = Reihenfolge aus Jira."))

        self.board_window = QSpinBox()
        self.board_window.setRange(0, 3650)
        self.board_window.setSuffix(" Tage")
        self.board_window.setValue(self._settings.board_window_days)
        self.board_window.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Zeitfenster"), self.board_window)
        form.addRow(
            self._hint(
                "Nur für \"Relevante Tickets\". 0 = kein Fenster - dann wird die Liste "
                "schnell zum Archiv statt zum Arbeitsvorrat."
            )
        )

        self.board_stale = QSpinBox()
        self.board_stale.setRange(0, 3650)
        self.board_stale.setSuffix(" Tage")
        self.board_stale.setValue(self._settings.board_stale_days)
        self.board_stale.setFixedWidth(FIELD_WIDTH)
        form.addRow(self._label("Verwaist ab"), self.board_stale)

        self.board_threshold_active = self._threshold(self._settings.board_threshold_active)
        form.addRow(self._label("Schwelle: ich dran"), self.board_threshold_active)

        self.board_threshold_acceptance = self._threshold(
            self._settings.board_threshold_acceptance
        )
        form.addRow(self._label("Schwelle: andere"), self.board_threshold_acceptance)

        self.board_threshold_closing = self._threshold(self._settings.board_threshold_closing)
        form.addRow(self._label("Schwelle: Abschluss"), self.board_threshold_closing)
        form.addRow(
            self._hint(
                "Ab so vielen ARBEITSTAGEN ohne Änderung UND ohne gebuchte Stunde landet ein "
                "Ticket im Pile of Shame. 0 schaltet die Rolle davon frei. Die Zahlen sind "
                "eine Setzung, keine Messung - zu klein gewählt trifft der Hinweis alles und "
                "sagt dann nichts mehr."
            )
        )
        return page

    def _wide_edit(self, values: list[str], placeholder: str = "") -> QLineEdit:
        """Ein breites Eingabefeld fuer eine Kommaliste.

        Args:
            values:
                Die bereits gesetzten Werte.
            placeholder:
                Beispielhafte Eingabe. Bewusst mit erfundenen Statusnamen - die
                echten kennt nur die jeweilige Jira-Instanz, und die Namen einer
                fremden Instanz gehoeren nicht in ein oeffentliches Repo.

        Returns:
            Das vorbereitete Eingabefeld.
        """
        edit = QLineEdit(", ".join(values))
        edit.setPlaceholderText(placeholder)
        # Der Objektname allein reichte NICHT: die Seite steht auf
        # FieldsStayAtSizeHint, also bleibt das Feld ohne ausdrueckliche Breite
        # auf seiner Wunschbreite stehen - schmaler noch als die Zahlenfelder
        # darunter. Die Mindestbreite ist deshalb die eigentliche Wirkung.
        edit.setObjectName("ExpandingField")
        edit.setMinimumWidth(WIDE_FIELD_WIDTH)
        return edit

    @staticmethod
    def _threshold(value: float) -> QDoubleSpinBox:
        """Ein Feld fuer eine Schwelle in Arbeitstagen."""
        box = QDoubleSpinBox()
        box.setRange(0.0, 999.0)
        box.setSingleStep(5.0)
        box.setDecimals(0)
        box.setSuffix(" Arbeitstage")
        box.setValue(value)
        box.setFixedWidth(FIELD_WIDTH)
        return box

    def _page_export(self) -> QWidget:
        page, form = self._page("Export")
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.logo_path = QLineEdit(self._settings.logo_path)
        self.logo_path.setObjectName("ExpandingField")
        self.logo_path.setPlaceholderText("Pfad zu einer Logo-Grafik (PNG/JPG) fuer Excel und PDF")
        logo_row = QWidget()
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(8)
        logo_layout.addWidget(self.logo_path, 1)
        browse = QPushButton("Durchsuchen ...")
        browse.setProperty("variant", "secondary")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._browse_logo)
        logo_layout.addWidget(browse)
        form.addRow(self._label("Logo-Pfad"), logo_row)

        self.show_target = QCheckBox("Soll-Stunden im Excel-/PDF-Export anzeigen")
        self.show_target.setChecked(self._settings.show_target_hours_in_export)
        form.addRow(self._label(""), self.show_target)

        self.show_ticket_links = QCheckBox("Ticket-Links im Excel-/PDF-Export anzeigen")
        self.show_ticket_links.setChecked(self._settings.show_ticket_links_in_export)
        form.addRow(self._label(""), self.show_ticket_links)

        self.default_customer = QLineEdit(self._settings.default_customer)
        self.default_customer.setFixedWidth(FIELD_WIDTH)
        self.default_customer.setPlaceholderText("Vertrieb")
        form.addRow(self._label("Standard-Kunde"), self.default_customer)

        self.customers = QPlainTextEdit("\n".join(self._settings.customers))
        self.customers.setFixedHeight(110)
        form.addRow(self._label("Kunden-Auswahl"), self.customers)
        form.addRow(self._hint("Ein Kunde pro Zeile. Das ist die Auswahlliste im Dialog fuer manuelle Zeiten."))
        return page

    def _browse_logo(self) -> None:
        """Oeffnet einen Datei-Dialog fuer die Logo-Grafik und uebernimmt die Wahl."""
        current = self.logo_path.text().strip()
        start = current or str(Path.home())
        chosen, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Logo-Grafik wählen",
            start,
            "Bilder (*.png *.jpg *.jpeg *.bmp);;Alle Dateien (*)",
        )
        if chosen:
            self.logo_path.setText(chosen)

    def _page_columns(self) -> QWidget:
        page, form = self._page("Spalten")
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow(
            self._hint(
                "Anzeige steuert die Listenansicht, Export die Excel- und PDF-Datei. Die "
                "Bezeichnung gilt fuer den Export; leer gelassen gilt die Standard-Bezeichnung."
            )
        )
        form.addRow(self._columns_header())

        # (key, Anzeige-Checkbox, Export-Checkbox, Bezeichnungs-Feld) je Spalte.
        self._column_rows: list[tuple[str, QCheckBox, QCheckBox, QLineEdit]] = []
        for column in self._settings.export_columns:
            form.addRow(self._column_row(column))
        return page

    def _columns_header(self) -> QWidget:
        """Kopfzeile ueber den Spalten-Reihen (Anzeige | Export | Bezeichnung)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        spacer = QLabel("")
        spacer.setFixedWidth(120)
        layout.addWidget(spacer)
        for text in ("Anzeige", "Export"):
            head = QLabel(text)
            head.setObjectName("SidebarSection")
            head.setFixedWidth(64)
            layout.addWidget(head)
        caption = QLabel("Bezeichnung im Export")
        caption.setObjectName("SidebarSection")
        layout.addWidget(caption, 1)
        return row

    def _column_row(self, column: ExportColumn) -> QWidget:
        """Baut eine Zeile fuer eine konfigurierbare Spalte."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        name = QLabel(default_label(column.key) or column.key)
        name.setFixedWidth(120)
        layout.addWidget(name)

        visible = QCheckBox()
        visible.setChecked(column.visible)
        visible.setFixedWidth(64)
        layout.addWidget(visible)

        enabled = QCheckBox()
        enabled.setChecked(column.enabled)
        enabled.setFixedWidth(64)
        layout.addWidget(enabled)

        label = QLineEdit(column.label)
        label.setObjectName("ExpandingField")
        label.setPlaceholderText(default_label(column.key))
        layout.addWidget(label, 1)

        self._column_rows.append((column.key, visible, enabled, label))
        return row

    def _page_appearance(self) -> QWidget:
        page, form = self._page("Darstellung")

        self.theme = self._combo()
        self.theme.addItem("Wie das Betriebssystem", "system")
        self.theme.addItem("Dunkel", "dark")
        self.theme.addItem("Hell", "light")
        index = self.theme.findData(self._settings.theme)
        self.theme.setCurrentIndex(max(0, index))
        form.addRow(self._label("Erscheinungsbild"), self.theme)

        # Akzentfarbe - vordefinierte Werte mit gutem Kontrast in Hell und Dunkel.
        self.accent = self._combo()
        for key in sorted(ACCENT_LABELS, key=lambda k: ACCENT_LABELS[k]):
            self.accent.addItem(ACCENT_LABELS[key], key)
        accent_index = self.accent.findData(self._settings.accent)
        self.accent.setCurrentIndex(max(0, accent_index))
        form.addRow(self._label("Akzentfarbe"), self.accent)

        # Oberflaechen-Zoom - skaliert alle Schriftgroessen (auch per Ctrl +/-/0).
        self.ui_scale = self._combo()
        for percent in SCALES:
            self.ui_scale.addItem(f"{percent} %", percent)
        scale_index = self.ui_scale.findData(self._settings.ui_scale)
        self.ui_scale.setCurrentIndex(max(0, scale_index))
        form.addRow(self._label("Zoom"), self.ui_scale)

        self.mark_manual = QCheckBox("Manuell erfasste Zeiten hervorheben")
        self.mark_manual.setChecked(self._settings.mark_manual_entries)
        form.addRow(self._label(""), self.mark_manual)

        # Farbe, in der manuelle Eintraege in der Liste eingefaerbt werden.
        self._manual_color_value = normalize_color(self._settings.manual_entry_color)
        self.manual_color = QPushButton()
        self.manual_color.setFixedWidth(FIELD_WIDTH)
        self.manual_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_color.clicked.connect(self._pick_manual_color)
        self._update_manual_color_button()
        self.mark_manual.toggled.connect(self.manual_color.setEnabled)
        self.manual_color.setEnabled(self.mark_manual.isChecked())
        form.addRow(self._label("Markierungsfarbe"), self.manual_color)

        # Soll-Ist-Ampel der Tagessummen: ueber Soll gruen, unter Soll rot.
        self.color_day_totals = QCheckBox("Tagessummen nach Soll-Ist einfärben")
        self.color_day_totals.setChecked(self._settings.color_day_totals)
        form.addRow(self._label(""), self.color_day_totals)

        self._day_over_value = normalize_color(self._settings.day_over_color, DEFAULT_DAY_OVER_COLOR)
        self.day_over_color = QPushButton()
        self.day_over_color.setFixedWidth(FIELD_WIDTH)
        self.day_over_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.day_over_color.clicked.connect(self._pick_day_over_color)
        self._style_color_button(self.day_over_color, self._day_over_value)
        form.addRow(self._label("Farbe über Soll"), self.day_over_color)

        self._day_under_value = normalize_color(self._settings.day_under_color, DEFAULT_DAY_UNDER_COLOR)
        self.day_under_color = QPushButton()
        self.day_under_color.setFixedWidth(FIELD_WIDTH)
        self.day_under_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.day_under_color.clicked.connect(self._pick_day_under_color)
        self._style_color_button(self.day_under_color, self._day_under_value)
        form.addRow(self._label("Farbe unter Soll"), self.day_under_color)

        for widget in (self.day_over_color, self.day_under_color):
            self.color_day_totals.toggled.connect(widget.setEnabled)
            widget.setEnabled(self.color_day_totals.isChecked())

        form.addRow(self._hint("Ein Wechsel wirkt sofort, ohne Neustart."))
        return page

    def _pick_manual_color(self) -> None:
        """Oeffnet den Farbwaehler fuer die Markierungsfarbe manueller Eintraege."""
        chosen = QColorDialog.getColor(
            QColor(f"#{self._manual_color_value}"), self, "Markierungsfarbe"
        )
        if chosen.isValid():
            self._manual_color_value = normalize_color(chosen.name().lstrip("#"))
            self._update_manual_color_button()

    def _update_manual_color_button(self) -> None:
        """Zeigt die aktuelle Markierungsfarbe als Flaeche samt Hex-Wert."""
        self._style_color_button(self.manual_color, self._manual_color_value)

    @staticmethod
    def _style_color_button(button: QPushButton, hex_value: str) -> None:
        """Malt eine Farbflaeche samt Hex-Wert auf einen Farbwaehler-Knopf."""
        color = QColor(f"#{hex_value}")
        text_color = "#000000" if color.lightnessF() > 0.6 else "#ffffff"
        button.setText(f"#{hex_value}")
        button.setStyleSheet(
            f"background-color: #{hex_value}; color: {text_color}; "
            f"border: 1px solid {color.darker(130).name()}; border-radius: 4px; padding: 6px;"
        )

    def _pick_day_over_color(self) -> None:
        """Farbwaehler fuer Tagessummen ueber Soll (gruen)."""
        chosen = QColorDialog.getColor(QColor(f"#{self._day_over_value}"), self, "Farbe ueber Soll")
        if chosen.isValid():
            self._day_over_value = normalize_color(chosen.name().lstrip("#"))
            self._style_color_button(self.day_over_color, self._day_over_value)

    def _pick_day_under_color(self) -> None:
        """Farbwaehler fuer Tagessummen unter Soll (rot)."""
        chosen = QColorDialog.getColor(QColor(f"#{self._day_under_value}"), self, "Farbe unter Soll")
        if chosen.isValid():
            self._day_under_value = normalize_color(chosen.name().lstrip("#"))
            self._style_color_button(self.day_under_color, self._day_under_value)

    def _page_storage(self) -> QWidget:
        page, form = self._page("Speicherort")
        # Anders als bei den Eingabeseiten sollen die Pfad-Zeilen die volle
        # Breite fuellen - nur so stehen die "Oeffnen"-Knoepfe buendig
        # rechts untereinander statt an jeder Pfadlaenge ausgerichtet.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for caption, path in (
            ("Einstellungen", Settings.SETTINGS_FILE),
            ("Protokoll", Settings.SETTINGS_DIR / "app.log"),
            ("Zwischenspeicher", CACHE_DIR),
            ("Manuelle Zeiten", DB_FILE),
            ("Zustimmung", Settings.SETTINGS_DIR / "disclaimer.json"),
        ):
            form.addRow(self._label(caption), self._path_row(path))
        form.addRow(
            self._hint("Ein Klick öffnet den Ordner. Die Anwendung überschreibt diese Dateien beim Speichern.")
        )
        return page

    # --- Bausteine ------------------------------------------------------

    def _page(self, title: str) -> tuple[QWidget, QFormLayout]:
        """Baut eine Seite mit Ueberschrift und liefert ihr Formular."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("SettingsHeading")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        # Felder wachsen NICHT mit der Dialogbreite - sonst haetten die
        # Textfelder eine andere Kante als die Zahlenfelder daneben.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        layout.addLayout(form)
        layout.addStretch(1)
        return page, form

    @staticmethod
    def _combo() -> QComboBox:
        """Auswahlliste, deren aufgeklapptes Feld dem Stylesheet folgt.

        Ohne ein ausdrueckliches QListView zeichnet Qt das Popup mit einem
        eigenen View, der die ::item-Regeln ignoriert - die Auswahl erscheint
        dann im Systemblau statt in der Akzentfarbe.
        """
        combo = QComboBox()
        combo.setView(QListView())
        combo.setFixedWidth(FIELD_WIDTH)
        return combo

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SettingsLabel")
        label.setMinimumWidth(120)
        return label

    @staticmethod
    def _hint(text: str) -> QLabel:
        hint = QLabel(text)
        hint.setObjectName("SettingsHint")
        hint.setWordWrap(True)
        return hint

    def _path_row(self, path: Path) -> QWidget:
        """Zeigt einen Pfad an und oeffnet ihn auf Klick im Dateimanager."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        value = QLabel(str(path))
        value.setObjectName("SettingsPath")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(value, 1)

        button = QPushButton("Öffnen")
        button.setProperty("variant", "secondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._open_path(path))
        layout.addWidget(button)
        return row

    @staticmethod
    def _open_path(path: Path) -> None:
        """Oeffnet das Verzeichnis des Pfads im Dateimanager."""
        target = path if path.is_dir() else path.parent
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _buttons(self) -> QWidget:
        row = QWidget()
        row.setObjectName("DialogButtons")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(24, 14, 24, 16)
        layout.setSpacing(10)

        # Import-Knopf unten links - nur, wenn die Textual-TUI hier einen
        # Zugang hinterlassen hat. Sichtbar gesteuert ueber die aktive Seite.
        self._import_button: QPushButton | None = None
        if Settings.legacy_access() is not None:
            self._import_button = QPushButton("Einstellungen aus jira-timesheet (TUI) übernehmen")
            self._import_button.setProperty("variant", "secondary")
            self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._import_button.clicked.connect(self._import_legacy_access)
            layout.addWidget(self._import_button)

        layout.addStretch(1)

        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

        save = QPushButton("Speichern")
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        layout.addWidget(save)
        return row

    # --- Ergebnis -------------------------------------------------------

    def result_settings(self) -> Settings:
        """Liefert die Einstellungen mit den Werten aus dem Dialog."""
        s = self._settings
        s.jira_host = self.host.text().strip().rstrip("/")
        s.email = self.email.text().strip()
        s.jira_token = self.token.text().strip()
        s.use_legacy_api = self.legacy.isChecked()
        s.proxy_url = self.proxy.text().strip()
        s.budget_field = self.budget_field.text().strip()
        s.hours_per_day = self.hours_per_day.value()
        s.max_yearly_hours = self.max_yearly.value()
        s.hourly_rate = self.hourly_rate.value()
        s.vat_rate = self.vat_rate.value()
        s.vacation_days = self.vacation.value()
        s.federal_state = str(self.state.currentData())
        s.logo_path = self.logo_path.text().strip()
        s.show_target_hours_in_export = self.show_target.isChecked()
        s.show_ticket_links_in_export = self.show_ticket_links.isChecked()
        s.default_customer = self.default_customer.text().strip() or "Vertrieb"
        s.board_active_status = _split(self.board_active.text())
        s.board_backlog_status = _split(self.board_backlog.text())
        s.board_acceptance_status = _split(self.board_acceptance.text())
        s.board_handback_status = _split(self.board_handback.text())
        s.board_closing_status = _split(self.board_closing.text())
        s.board_priorities = _split(self.board_priorities.text())
        s.board_window_days = self.board_window.value()
        s.board_stale_days = self.board_stale.value()
        s.board_threshold_active = self.board_threshold_active.value()
        s.board_threshold_acceptance = self.board_threshold_acceptance.value()
        s.board_threshold_closing = self.board_threshold_closing.value()
        s.customers = self._customers_from_input()
        s.export_columns = [
            ExportColumn(
                key=key,
                label=label.text().strip() or default_label(key),
                enabled=enabled.isChecked(),
                visible=visible.isChecked(),
            )
            for key, visible, enabled, label in self._column_rows
        ]
        s.theme = str(self.theme.currentData())
        s.accent = str(self.accent.currentData())
        s.ui_scale = int(self.ui_scale.currentData())
        s.mark_manual_entries = self.mark_manual.isChecked()
        s.manual_entry_color = self._manual_color_value
        s.color_day_totals = self.color_day_totals.isChecked()
        s.day_over_color = self._day_over_value
        s.day_under_color = self._day_under_value
        return s

    def _customers_from_input(self) -> list[str]:
        """Liest die Kundenliste (ein Kunde je Zeile); leer -> bisherige Liste."""
        names = [line.strip() for line in self.customers.toPlainText().splitlines() if line.strip()]
        return names or list(self._settings.customers)

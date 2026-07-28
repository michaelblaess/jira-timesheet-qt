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
from jira_timesheet_qt.models.settings import Settings, normalize_color
from jira_timesheet_qt.services.cache_service import CACHE_DIR
from jira_timesheet_qt.services.manual_entry_service import DB_FILE
from jira_timesheet_qt.ui.theme import ACCENT_LABELS

# Einheitliche Breite aller Eingabefelder. Ohne das richtet sich jedes Feld
# nach seinem Inhalt, und die rechte Kante wirkt zerfranst.
FIELD_WIDTH = 240

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


class SettingsDialog(QDialog):
    """Dialog zum Bearbeiten der Einstellungen.

    Bekommt die aktuellen Einstellungen, gibt bei Annahme die geaenderten
    zurueck. Gespeichert wird ausserhalb - der Dialog kennt keine Dateipfade.
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Einstellungen")
        self.setMinimumSize(720, 520)
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
        self._nav.addItems(["Zugang", "Arbeitszeit", "Export", "Spalten", "Darstellung", "Speicherort"])
        self._nav.setCurrentRow(0)
        body.addWidget(self._nav)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._page_access())
        self._pages.addWidget(self._page_worktime())
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
        form.addRow(self._label("Budget-Feld"), self.budget_field)

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
        """Fuellt die Zugangsfelder aus der Einstellungsdatei der Textual-TUI.

        Uebernommen werden nur die Jira-Zugangsdaten und erst in die Felder -
        gespeichert wird wie ueberall erst beim Klick auf "Speichern".
        """
        access = Settings.legacy_access()
        if access is None:
            QMessageBox.information(
                self,
                "Import",
                "Es wurde keine Einstellungsdatei der jira-timesheet-TUI gefunden.",
            )
            return

        self.host.setText(str(access["jira_host"]))
        self.email.setText(str(access["email"]))
        self.token.setText(str(access["jira_token"]))
        self.legacy.setChecked(bool(access["use_legacy_api"]))
        self.proxy.setText(str(access["proxy_url"]))
        self.budget_field.setText(str(access["budget_field"]))
        QMessageBox.information(
            self,
            "Import",
            "Der Jira-Zugang aus jira-timesheet wurde übernommen.\n"
            "Zum Sichern auf „Speichern“ klicken.",
        )

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

    def _page_export(self) -> QWidget:
        page, form = self._page("Export")
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.logo_path = QLineEdit(self._settings.logo_path)
        self.logo_path.setObjectName("ExpandingField")
        self.logo_path.setPlaceholderText("Pfad zu einer Logo-Grafik (PNG/JPG) fuer Excel und PDF")
        form.addRow(self._label("Logo-Pfad"), self.logo_path)

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
        """Zeigt die aktuelle Farbe als Flaeche samt Hex-Wert auf dem Knopf."""
        hex_value = self._manual_color_value
        color = QColor(f"#{hex_value}")
        text_color = "#000000" if color.lightnessF() > 0.6 else "#ffffff"
        self.manual_color.setText(f"#{hex_value}")
        self.manual_color.setStyleSheet(
            f"background-color: #{hex_value}; color: {text_color}; "
            f"border: 1px solid {color.darker(130).name()}; border-radius: 4px; padding: 6px;"
        )

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
            self._import_button = QPushButton("Zugang aus jira-timesheet (TUI) übernehmen")
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
        s.budget_field = self.budget_field.text().strip() or "customfield_XXXXX"
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
        s.mark_manual_entries = self.mark_manual.isChecked()
        s.manual_entry_color = self._manual_color_value
        return s

    def _customers_from_input(self) -> list[str]:
        """Liest die Kundenliste (ein Kunde je Zeile); leer -> bisherige Liste."""
        names = [line.strip() for line in self.customers.toPlainText().splitlines() if line.strip()]
        return names or list(self._settings.customers)

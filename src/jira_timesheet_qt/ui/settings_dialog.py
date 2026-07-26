"""Einstellungen der Anwendung.

Bewusst kein QTabWidget: dessen Reiter sind eines der auffaelligsten Merkmale
einer Standard-Qt-Anwendung. Stattdessen eine schmale Liste links und die
Seiten in einem QStackedWidget - dasselbe Muster wie im Hauptfenster.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.cache_service import CACHE_DIR
from jira_timesheet_qt.services.manual_entry_service import DB_FILE

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("SettingsNav")
        self._nav.setFixedWidth(180)
        self._nav.addItems(["Zugang", "Arbeitszeit", "Darstellung", "Speicherort"])
        self._nav.setCurrentRow(0)
        body.addWidget(self._nav)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._page_access())
        self._pages.addWidget(self._page_worktime())
        self._pages.addWidget(self._page_appearance())
        self._pages.addWidget(self._page_storage())
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        body.addWidget(self._pages, 1)

        outer.addLayout(body, 1)
        outer.addWidget(self._buttons())

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

    def _page_appearance(self) -> QWidget:
        page, form = self._page("Darstellung")

        self.theme = self._combo()
        self.theme.addItem("Wie das Betriebssystem", "system")
        self.theme.addItem("Dunkel", "dark")
        self.theme.addItem("Hell", "light")
        index = self.theme.findData(self._settings.theme)
        self.theme.setCurrentIndex(max(0, index))
        form.addRow(self._label("Erscheinungsbild"), self.theme)

        self.mark_manual = QCheckBox("Manuell erfasste Zeiten hervorheben")
        self.mark_manual.setChecked(self._settings.mark_manual_entries)
        form.addRow(self._label(""), self.mark_manual)

        form.addRow(self._hint("Ein Wechsel wirkt sofort, ohne Neustart."))
        return page

    def _page_storage(self) -> QWidget:
        page, form = self._page("Speicherort")
        for caption, path in (
            ("Einstellungen", Settings.SETTINGS_FILE),
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
        button.setProperty("variant", "ghost")
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
        s.vacation_days = self.vacation.value()
        s.federal_state = str(self.state.currentData())
        s.theme = str(self.theme.currentData())
        s.mark_manual_entries = self.mark_manual.isChecked()
        return s

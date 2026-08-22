"""Einstellungen der Anwendung.

Bewusst kein QTabWidget: dessen Reiter sind eines der auffaelligsten Merkmale
einer Standard-Qt-Anwendung. Stattdessen eine schmale Liste links und die
Seiten in einem QStackedWidget - dasselbe Muster wie im Hauptfenster.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
from QAppFramework.einstellungen import FELDBREITE, BasisEinstellungenDialog, Darstellung
from QAppFramework.theme import Modus

from jira_timesheet_qt.models.export_column import ExportColumn, default_label
from jira_timesheet_qt.models.settings import (
    Settings,
)
from jira_timesheet_qt.services.cache_service import CACHE_DIR
from jira_timesheet_qt.services.manual_entry_service import DB_FILE
from jira_timesheet_qt.services.team import (
    AccountCandidate,
    Roster,
    TeamMember,
    from_storage,
    merge_accounts,
    to_storage,
)
from jira_timesheet_qt.ui.jira_worker import BudgetFieldWorker
from jira_timesheet_qt.ui.team_worker import TeamSearchWorker

# Einheitliche Breite aller Eingabefelder. Ohne das richtet sich jedes Feld
# nach seinem Inhalt, und die rechte Kante wirkt zerfranst.
# Eine Breite fuer alle Felder - die der Bibliothek. Sonst haetten die
# eigenen Seiten eine andere rechte Kante als die Darstellungs-Seite.
FIELD_WIDTH = FELDBREITE

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


class SettingsDialog(BasisEinstellungenDialog):
    """Dialog zum Bearbeiten der Einstellungen.

    Bekommt die aktuellen Einstellungen, gibt bei Annahme die geaenderten
    zurueck. Gespeichert wird ausserhalb - der Dialog kennt keine Dateipfade.
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        # Alles, was eigene_seiten() braucht, MUSS vor super().__init__ stehen:
        # der Konstruktor der Basis ruft den Haken auf.
        self._settings = settings
        # Faden fuer die Budget-Feld-Autoerkennung (ein Netzwerkaufruf).
        self._detect_worker: BudgetFieldWorker | None = None
        super().__init__(
            Darstellung(
                modus=Modus(settings.theme) if settings.theme in {m.value for m in Modus} else Modus.SYSTEM,
                akzent=settings.accent,
                zoom=settings.ui_scale,
            ),
            parent,
        )
        # Die Mindestbreite der Bibliothek reicht fuer ihre eigenen Felder. Die
        # Statusfelder auf der Ticket-Seite sind doppelt so breit - gemessen
        # ragte das breiteste 17 Bildpunkte heraus.
        self.setMinimumWidth(WIDE_FIELD_WIDTH + 400)
        # Wird der Dialog geschlossen, waehrend die Autoerkennung laeuft, erst
        # auf den Faden warten - sonst zerstoert Qt ihn im Lauf.
        self.finished.connect(self._await_detect_worker)

    def eigene_seiten(self) -> Sequence[tuple[str, QWidget]]:
        """Die sechs Seiten dieser Anwendung.

        Darstellung und Speicherort kommen aus der Bibliothek und haengen sich
        dahinter. Was auf der Darstellungs-Seite zusaetzlich steht - Markierung
        und Soll-Ist-Ampel -, liefert darstellung_erweitern().
        """
        return [
            ("Zugang", self._page_access()),
            ("Arbeitszeit", self._page_worktime()),
            ("Tickets", self._page_tickets()),
            ("Mein Team", self._page_team()),
            ("Export", self._page_export()),
            ("Spalten", self._page_columns()),
        ]

    def uebernehmen(self) -> None:
        """Liest die eigenen Felder aus. Die Basis ruft das beim Speichern."""
        self.result_settings()

    def speicherorte(self) -> list[tuple[str, Path]]:
        return [
            ("Einstellungen", Settings.SETTINGS_FILE),
            ("Protokoll", Settings.SETTINGS_DIR / "app.log"),
            ("Zwischenspeicher", CACHE_DIR),
            ("Manuelle Zeiten", DB_FILE),
            ("Zustimmung", Settings.SETTINGS_DIR / "disclaimer.json"),
        ]

    # --- Seiten ---------------------------------------------------------

    def _page_access(self) -> QWidget:
        page, form = self.seite("Zugang zu Jira")

        self.host = QLineEdit(self._settings.jira_host)
        self.host.setFixedWidth(FIELD_WIDTH)
        self.host.setPlaceholderText("https://deine-firma.atlassian.net")
        form.addRow(self.beschriftung("Jira-Host"), self.host)

        self.email = QLineEdit(self._settings.email)
        self.email.setFixedWidth(FIELD_WIDTH)
        self.email.setPlaceholderText("vorname.nachname@firma.de")
        form.addRow(self.beschriftung("E-Mail"), self.email)

        self.token = QLineEdit(self._settings.jira_token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setFixedWidth(FIELD_WIDTH)
        self.token.setPlaceholderText("API-Token von id.atlassian.com")
        form.addRow(self.beschriftung("Token"), self.token)

        self.legacy = QCheckBox("Data Center statt Cloud (Bearer-Token, ältere API)")
        self.legacy.setChecked(self._settings.use_legacy_api)
        form.addRow(self.beschriftung(""), self.legacy)

        self.proxy = QLineEdit(self._settings.proxy_url)
        self.proxy.setFixedWidth(FIELD_WIDTH)
        self.proxy.setPlaceholderText("http://proxy:8080 - leer lässt die Umgebung entscheiden")
        form.addRow(self.beschriftung("Proxy"), self.proxy)

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
        form.addRow(self.beschriftung("Budget-Feld"), budget_row)

        form.addRow(
            self.hinweis(
                "Der Token wird unverschlüsselt in der Einstellungsdatei abgelegt. "
                "Wer Zugriff auf das Benutzerprofil hat, kann ihn lesen."
            )
        )

        self._import_button = self._import_knopf()
        if self._import_button is not None:
            form.addRow(self.beschriftung(""), self._import_button)
        return page

    def _import_knopf(self) -> QPushButton | None:
        """Uebernahme aus der Textual-Fassung - nur, wenn die hier etwas hinterlassen hat.

        Stand bis 0.7.2 unten links in der Knopfzeile und wurde je nach Seite
        ein- und ausgeblendet. Die Knopfzeile kommt jetzt aus der Bibliothek,
        und inhaltlich gehoert der Knopf ohnehin dorthin, wo die Zugangsdaten
        stehen.
        """
        if Settings.legacy_access() is None:
            return None
        knopf = QPushButton("Einstellungen aus jira-timesheet (TUI) übernehmen")
        knopf.setProperty("variant", "secondary")
        knopf.setCursor(Qt.CursorShape.PointingHandCursor)
        knopf.clicked.connect(self._import_legacy_access)
        return knopf

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
        """Wartet beim Schliessen auf noch laufende Hintergrund-Faeden.

        Betrifft die Budget-Feld-Erkennung UND die Personensuche: beide
        koennen laenger laufen als der Dialog offen bleibt, und Qt zerstoert
        einen QThread nicht gefahrlos, solange er noch arbeitet.

        Args:
            _result:
                Der Rueckgabewert des Dialogs, hier ohne Bedeutung.
        """
        if self._detect_worker is not None and self._detect_worker.isRunning():
            self._detect_worker.wait(3000)
        if self._team_worker is not None and self._team_worker.isRunning():
            self._team_worker.wait(3000)

    def _page_worktime(self) -> QWidget:
        page, form = self.seite("Arbeitszeit")

        self.hours_per_day = QDoubleSpinBox()
        self.hours_per_day.setRange(0.5, 24.0)
        self.hours_per_day.setSingleStep(0.5)
        self.hours_per_day.setDecimals(1)
        self.hours_per_day.setSuffix(" h")
        self.hours_per_day.setValue(self._settings.hours_per_day)
        self.hours_per_day.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Stunden pro Tag"), self.hours_per_day)

        self.max_yearly = QDoubleSpinBox()
        self.max_yearly.setRange(0.0, 5000.0)
        self.max_yearly.setSingleStep(10.0)
        self.max_yearly.setDecimals(1)
        self.max_yearly.setSuffix(" h")
        self.max_yearly.setValue(self._settings.max_yearly_hours)
        self.max_yearly.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Jahresbudget"), self.max_yearly)

        self.hourly_rate = QDoubleSpinBox()
        self.hourly_rate.setRange(0.0, 100000.0)
        self.hourly_rate.setSingleStep(5.0)
        self.hourly_rate.setDecimals(2)
        self.hourly_rate.setSuffix(" €")
        self.hourly_rate.setValue(self._settings.hourly_rate)
        self.hourly_rate.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Stundensatz"), self.hourly_rate)

        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0.0, 100.0)
        self.vat_rate.setSingleStep(1.0)
        self.vat_rate.setDecimals(1)
        self.vat_rate.setSuffix(" %")
        self.vat_rate.setValue(self._settings.vat_rate)
        self.vat_rate.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("MwSt-Satz"), self.vat_rate)

        self.vacation = QSpinBox()
        self.vacation.setRange(0, 90)
        self.vacation.setSuffix(" Tage")
        self.vacation.setValue(self._settings.vacation_days)
        self.vacation.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Urlaubstage"), self.vacation)

        self.state = self.auswahl()
        for code, name in _STATES:
            self.state.addItem(name, code)
        index = self.state.findData(self._settings.federal_state)
        self.state.setCurrentIndex(max(0, index))
        form.addRow(self.beschriftung("Bundesland"), self.state)
        form.addRow(self.hinweis("Bestimmt, welche Feiertage als arbeitsfrei gelten."))
        return page

    def _page_tickets(self) -> QWidget:
        page, form = self.seite("Ticket-Ansichten")

        form.addRow(
            self.hinweis(
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
        form.addRow(self.beschriftung("Ich bin dran"), self.board_active)

        self.board_backlog = self._wide_edit(
            self._settings.board_backlog_status, "Bereit, Eingeplant"
        )
        form.addRow(self.beschriftung("Backlog"), self.board_backlog)

        self.board_acceptance = self._wide_edit(
            self._settings.board_acceptance_status, "Wartet auf Freigabe, Beim Fachbereich"
        )
        form.addRow(self.beschriftung("Andere sind dran"), self.board_acceptance)

        self.board_handback = self._wide_edit(
            self._settings.board_handback_status, "Ausgeliefert, Zur Bewertung"
        )
        form.addRow(self.beschriftung("Live, Test offen"), self.board_handback)
        form.addRow(
            self.hinweis(
                "Produktiv gesetzt und wartet auf den Test durch den Autor. Ist der Autor "
                "jemand anderes, gehört das Ticket zurückgegeben - bist du es selbst, liegt "
                "der Ball bei dir, und die Ansicht sortiert es zu \"Ich bin dran\"."
            )
        )

        self.board_closing = self._wide_edit(
            self._settings.board_closing_status, "Zur Übergabe, Deployment offen"
        )
        form.addRow(self.beschriftung("Übergabe"), self.board_closing)
        form.addRow(
            self.hinweis(
                "Das wichtigste Feld. Status, die Jira als fertig zählt, obwohl das Ticket "
                "noch auf die Live-Setzung wartet - ohne diesen Eintrag tauchen sie in "
                "keiner Liste auf."
            )
        )

        self.board_done = self._wide_edit(
            self._settings.board_done_status, "Erledigt, Abgeschlossen"
        )
        form.addRow(self.beschriftung("Abgeschlossen"), self.board_done)
        form.addRow(
            self.hinweis(
                "Wirklich fertig. Reiner Kontrollblick: diese Tickets erscheinen ohne "
                "Handlungsbedarf und ohne Schwelle, damit sichtbar bleibt, was formal noch "
                "bei dir hängt."
            )
        )

        self.board_priorities = self._wide_edit(
            self._settings.board_priorities, "Blocker, Kritisch, Hoch, Mittel, Niedrig"
        )
        form.addRow(self.beschriftung("Prioritäten"), self.board_priorities)
        form.addRow(self.hinweis("Rangfolge, dringendstes zuerst. Leer = Reihenfolge aus Jira."))

        self.board_window = QSpinBox()
        self.board_window.setRange(0, 3650)
        self.board_window.setSuffix(" Tage")
        self.board_window.setValue(self._settings.board_window_days)
        self.board_window.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Zeitfenster"), self.board_window)
        form.addRow(
            self.hinweis(
                "Nur für \"Meine Aktivitäten\". 0 = kein Fenster - dann wird die Liste "
                "schnell zum Archiv statt zum Arbeitsvorrat."
            )
        )

        self.board_stale = QSpinBox()
        self.board_stale.setRange(0, 3650)
        self.board_stale.setSuffix(" Tage")
        self.board_stale.setValue(self._settings.board_stale_days)
        self.board_stale.setFixedWidth(FIELD_WIDTH)
        form.addRow(self.beschriftung("Verwaist ab"), self.board_stale)

        self.board_threshold_active = self._threshold(self._settings.board_threshold_active)
        form.addRow(self.beschriftung("Schwelle: ich dran"), self.board_threshold_active)

        self.board_threshold_acceptance = self._threshold(
            self._settings.board_threshold_acceptance
        )
        form.addRow(self.beschriftung("Schwelle: andere"), self.board_threshold_acceptance)

        self.board_threshold_closing = self._threshold(self._settings.board_threshold_closing)
        form.addRow(self.beschriftung("Schwelle: Übergabe"), self.board_threshold_closing)
        form.addRow(
            self.hinweis(
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

    def _page_team(self) -> QWidget:
        page, form = self.seite("Mein Team")

        form.addRow(
            self.hinweis(
                "Merke dir Kolleginnen und Kollegen, deren Ticketstand du im Reiter "
                "\"Mein Team\" ansehen willst. Suche nach dem <b>Namen</b>, nicht nach der "
                "Mailadresse: viele Konten geben ihre Adresse nicht heraus, und ein Mensch "
                "kann mehrere Konten haben. Alle Treffer zu einer Person werden gemeinsam "
                "übernommen."
            )
        )

        self.team_query = QLineEdit()
        self.team_query.setPlaceholderText("Nachname")
        self.team_query.setFixedWidth(FIELD_WIDTH)
        # Enter sucht - sonst muss man für jede Suche zur Maus greifen.
        self.team_query.returnPressed.connect(self._team_search)

        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.team_query)
        self.team_search_button = QPushButton("Suchen")
        self.team_search_button.setProperty("variant", "secondary")
        self.team_search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.team_search_button.clicked.connect(self._team_search)
        search_layout.addWidget(self.team_search_button)
        search_layout.addStretch(1)
        form.addRow(self.beschriftung("Suchen"), search_row)

        self.team_hits = QTableWidget(0, 4)
        self.team_hits.setHorizontalHeaderLabels(["Name", "Mail", "offen", "zuletzt"])
        self.team_hits.verticalHeader().setVisible(False)
        self.team_hits.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # ExtendedSelection, NICHT MultiSelection: bei MultiSelection ist ein
        # Klick auf eine bereits ausgewaehlte Zeile ein Abwaehlen. Da nach der
        # Suche die oberste Zeile vorgewaehlt ist, haette der Griff zum
        # wahrscheinlichsten Treffer ihn gerade wieder abgewaehlt.
        self.team_hits.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.team_hits.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.team_hits.setMinimumHeight(170)
        self.team_hits.setMinimumWidth(WIDE_FIELD_WIDTH)
        # Mehrfachauswahl mit Absicht (Strg oder Umschalt): fuehrt eine Person
        # mehrere Konten, muss man alle gemeinsam uebernehmen koennen. Die
        # Reihenfolge stammt aus dem Kern - das juengste Konto steht oben,
        # nicht das groesste.
        form.addRow(self.beschriftung("Treffer"), self.team_hits)

        self.team_status = self.hinweis("")
        form.addRow(self.team_status)

        self.team_name = QLineEdit()
        self.team_name.setPlaceholderText("Wie im Reiter angezeigt")
        self.team_name.setFixedWidth(FIELD_WIDTH)

        add_row = QWidget()
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(8)
        add_layout.addWidget(self.team_name)
        self.team_add_button = QPushButton("Übernehmen")
        self.team_add_button.setProperty("variant", "secondary")
        self.team_add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.team_add_button.clicked.connect(self._team_add)
        add_layout.addWidget(self.team_add_button)
        add_layout.addStretch(1)
        form.addRow(self.beschriftung("Anzeigename"), add_row)
        form.addRow(
            self.hinweis(
                "Leer lassen übernimmt den Namen aus Jira. Jira führt denselben Menschen "
                "aber gern in mehreren Schreibweisen - wie jemand genannt werden möchte, "
                "entscheidet nicht das Verzeichnis."
            )
        )

        self.team_roster_list = QListWidget()
        self.team_roster_list.setMinimumHeight(120)
        self.team_roster_list.setMinimumWidth(WIDE_FIELD_WIDTH)
        form.addRow(self.beschriftung("Merkliste"), self.team_roster_list)

        self.team_remove_button = QPushButton("Entfernen")
        self.team_remove_button.setProperty("variant", "secondary")
        self.team_remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.team_remove_button.clicked.connect(self._team_remove)
        form.addRow(self.team_remove_button)

        self._roster: Roster = from_storage(self._settings.team_members)
        self._hits: list[AccountCandidate] = []
        self._team_worker: TeamSearchWorker | None = None
        self._refresh_roster()
        return page

    # --- Mein Team ------------------------------------------------------

    def _team_search(self) -> None:
        """Startet die Personensuche im Hintergrund."""
        query = self.team_query.text().strip()
        if not query:
            return
        if not (self.host.text().strip() and self.email.text().strip() and self.token.text()):
            self.team_status.setText(
                "Dafür fehlt der Jira-Zugang. Trage ihn unter \"Zugang\" ein."
            )
            return
        if self._team_worker is not None and self._team_worker.isRunning():
            return

        self.team_search_button.setEnabled(False)
        self.team_status.setText("Suche läuft ...")

        # Die Suche nimmt den Zugang aus den FELDERN, nicht aus den
        # gespeicherten Einstellungen: wer den Zugang gerade erst eingetragen
        # hat, soll nicht erst speichern und den Dialog neu oeffnen muessen.
        settings = self._settings_for_search()
        self._team_worker = TeamSearchWorker(settings, query, self)
        self._team_worker.finished_ok.connect(self._team_hits_ready)
        self._team_worker.failed.connect(self._team_search_failed)
        self._team_worker.start()

    def _settings_for_search(self) -> Settings:
        """Baut die Zugangsdaten aus den aktuellen Eingabefeldern."""
        settings = Settings.load()
        settings.jira_host = self.host.text().strip()
        settings.email = self.email.text().strip()
        settings.jira_token = self.token.text()
        settings.proxy_url = self.proxy.text().strip()
        settings.use_legacy_api = self.legacy.isChecked()
        return settings

    def _team_hits_ready(self, hits: object) -> None:
        """Zeigt die gefundenen Konten an.

        Args:
            hits:
                Die Kandidaten aus dem Faden, bereits sortiert.
        """
        self.team_search_button.setEnabled(True)
        self._hits = list(hits) if isinstance(hits, list) else []
        self.team_hits.setRowCount(len(self._hits))
        for row, candidate in enumerate(self._hits):
            stamp = candidate.last_touch.strftime("%d.%m.%Y") if candidate.last_touch else ""
            # Leer statt "0" oder "-", wenn der Abruf des Kontos scheiterte:
            # eine Null waere eine Behauptung, die niemand geprueft hat.
            offen = "" if candidate.open_count is None else str(candidate.open_count)
            for column, text in enumerate(
                (candidate.display_name, candidate.email, offen, stamp)
            ):
                self.team_hits.setItem(row, column, QTableWidgetItem(text))
        self.team_hits.resizeColumnsToContents()

        if not self._hits:
            self.team_status.setText("Kein Konto zu diesem Namen gefunden.")
            return
        self.team_status.setText(
            f"{len(self._hits)} Konten gefunden. Wähle alle aus, die zu derselben Person "
            "gehören - das oberste ist das zuletzt benutzte."
        )
        self.team_hits.selectRow(0)

    def _team_search_failed(self, message: str) -> None:
        """Meldet eine gescheiterte Suche, ohne den Dialog anzuhalten."""
        self.team_search_button.setEnabled(True)
        self.team_status.setText(f"Suche gescheitert: {message}")

    def _team_add(self) -> None:
        """Uebernimmt die ausgewaehlten Konten als eine Person."""
        rows = sorted({index.row() for index in self.team_hits.selectedIndexes()})
        chosen = [self._hits[row] for row in rows if 0 <= row < len(self._hits)]
        if not chosen:
            self.team_status.setText("Kein Konto ausgewählt.")
            return

        wanted = self.team_name.text().strip()
        known = {
            account_id
            for existing in self._roster.members
            for account_id in existing.account_ids
        }
        # Ein Konto, das bereits einer ANDEREN Person zugeordnet ist, waere
        # doppelt in der Merkliste - dieselben Tickets erschienen dann unter
        # zwei Namen. Nur beim Erweitern derselben Person ist es erwuenscht.
        target = self._roster.find(wanted) if wanted else None
        fremd = [
            candidate
            for candidate in chosen
            if candidate.account_id in known
            and (target is None or candidate.account_id not in target.account_ids)
        ]
        if fremd:
            self.team_status.setText(
                "Mindestens eines dieser Konten gehört schon zu einer Person in der "
                "Merkliste. Entferne sie dort erst, oder trage denselben Anzeigenamen ein."
            )
            return

        member = merge_accounts(chosen, name=wanted)
        existing = self._roster.find(member.display_name)
        if existing is None:
            self._roster.members.append(member)
        else:
            # Gleicher Name, weitere Konten: vereinigen statt ersetzen. Wer
            # spaeter ein viertes Konto derselben Person findet, soll es
            # dazulegen koennen, ohne die schon gefundenen zu verlieren.
            merged = list(existing.account_ids) + [
                account_id
                for account_id in member.account_ids
                if account_id not in existing.account_ids
            ]
            member = TeamMember(
                display_name=member.display_name,
                account_ids=tuple(merged),
                email=member.email or existing.email,
                avatar_url=member.avatar_url or existing.avatar_url,
            )
            self._roster.members[self._roster.members.index(existing)] = member

        self._refresh_roster()
        self.team_name.clear()
        # Suchbegriff ist verbraucht, der Fokus geht zurueck ins Feld: der
        # naechste Name laesst sich sofort tippen. Die Trefferliste bleibt
        # bewusst stehen - faellt einem hinterher auf, dass ein weiteres Konto
        # zu derselben Person gehoert, ist es noch da.
        self.team_query.clear()
        self.team_query.setFocus()
        konten = "1 Konto" if len(member.account_ids) == 1 else f"{len(member.account_ids)} Konten"
        self.team_status.setText(f"{member.display_name} übernommen ({konten}).")

    def _team_remove(self) -> None:
        """Nimmt die ausgewaehlte Person aus der Merkliste."""
        item = self.team_roster_list.currentItem()
        if item is None:
            return
        name = str(item.data(Qt.ItemDataRole.UserRole))
        chosen = self._roster.find(name)
        if chosen is None:
            return
        self._roster.members.remove(chosen)
        self._refresh_roster()
        self.team_status.setText(f"{name} entfernt.")

    def _refresh_roster(self) -> None:
        """Schreibt die Merkliste neu in die Anzeige."""
        self.team_roster_list.clear()
        for member in self._roster.members:
            konten = "1 Konto" if len(member.account_ids) == 1 else f"{len(member.account_ids)} Konten"
            item = QListWidgetItem(f"{member.display_name}  ({konten})")
            item.setData(Qt.ItemDataRole.UserRole, member.display_name)
            self.team_roster_list.addItem(item)
        self.team_remove_button.setEnabled(bool(self._roster.members))

    def _page_export(self) -> QWidget:
        page, form = self.seite("Export")
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
        form.addRow(self.beschriftung("Logo-Pfad"), logo_row)

        self.show_target = QCheckBox("Soll-Stunden im Excel-/PDF-Export anzeigen")
        self.show_target.setChecked(self._settings.show_target_hours_in_export)
        form.addRow(self.beschriftung(""), self.show_target)

        self.show_ticket_links = QCheckBox("Ticket-Links im Excel-/PDF-Export anzeigen")
        self.show_ticket_links.setChecked(self._settings.show_ticket_links_in_export)
        form.addRow(self.beschriftung(""), self.show_ticket_links)

        self.default_customer = QLineEdit(self._settings.default_customer)
        self.default_customer.setFixedWidth(FIELD_WIDTH)
        self.default_customer.setPlaceholderText("Vertrieb")
        form.addRow(self.beschriftung("Standard-Kunde"), self.default_customer)

        self.customers = QPlainTextEdit("\n".join(self._settings.customers))
        self.customers.setFixedHeight(110)
        form.addRow(self.beschriftung("Kunden-Auswahl"), self.customers)
        form.addRow(self.hinweis("Ein Kunde pro Zeile. Das ist die Auswahlliste im Dialog fuer manuelle Zeiten."))
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
        page, form = self.seite("Spalten")
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow(
            self.hinweis(
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

    def darstellung_erweitern(self, form: QFormLayout) -> None:
        """Markierung und Soll-Ist-Ampel - sie gehoeren fuer den Anwender zur
        Darstellung, kennt aber nur diese Anwendung.

        Erscheinungsbild, Akzentfarbe und Zoom stehen darueber und kommen aus
        der Bibliothek.
        """
        self.mark_manual = QCheckBox("Manuell erfasste Zeiten hervorheben")
        self.mark_manual.setChecked(self._settings.mark_manual_entries)
        form.addRow(self.beschriftung(""), self.mark_manual)

        # Farbe, in der manuelle Eintraege in der Liste eingefaerbt werden.
        self.manual_color = self.farbknopf(self._settings.manual_entry_color, "Markierungsfarbe")
        self.mark_manual.toggled.connect(self.manual_color.setEnabled)
        self.manual_color.setEnabled(self.mark_manual.isChecked())
        form.addRow(self.beschriftung("Markierungsfarbe"), self.manual_color)

        # Soll-Ist-Ampel der Tagessummen: ueber Soll gruen, unter Soll rot.
        self.color_day_totals = QCheckBox("Tagessummen nach Soll-Ist einfärben")
        self.color_day_totals.setChecked(self._settings.color_day_totals)
        form.addRow(self.beschriftung(""), self.color_day_totals)

        self.day_over_color = self.farbknopf(self._settings.day_over_color, "Farbe über Soll")
        form.addRow(self.beschriftung("Farbe über Soll"), self.day_over_color)

        self.day_under_color = self.farbknopf(self._settings.day_under_color, "Farbe unter Soll")
        form.addRow(self.beschriftung("Farbe unter Soll"), self.day_under_color)

        for widget in (self.day_over_color, self.day_under_color):
            self.color_day_totals.toggled.connect(widget.setEnabled)
            widget.setEnabled(self.color_day_totals.isChecked())

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
        s.board_done_status = _split(self.board_done.text())
        s.team_members = to_storage(self._roster)
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
        # Erscheinungsbild, Akzentfarbe und Zoom kommen aus der Bibliothek.
        s.theme = self.darstellung.modus.value
        s.accent = self.darstellung.akzent
        s.ui_scale = self.darstellung.zoom
        s.mark_manual_entries = self.mark_manual.isChecked()
        s.manual_entry_color = self.farbe_von(self.manual_color)
        s.color_day_totals = self.color_day_totals.isChecked()
        s.day_over_color = self.farbe_von(self.day_over_color)
        s.day_under_color = self.farbe_von(self.day_under_color)
        return s

    def _customers_from_input(self) -> list[str]:
        """Liest die Kundenliste (ein Kunde je Zeile); leer -> bisherige Liste."""
        names = [line.strip() for line in self.customers.toPlainText().splitlines() if line.strip()]
        return names or list(self._settings.customers)

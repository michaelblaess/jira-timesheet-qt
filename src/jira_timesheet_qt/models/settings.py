"""Persistierte Benutzereinstellungen."""

from __future__ import annotations

import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jira_timesheet_qt.models.export_column import ExportColumn, default_columns, parse_columns

logger = logging.getLogger(__name__)

# Markierungsfarbe manueller Eintraege als RRGGBB (ohne fuehrendes #).
DEFAULT_MANUAL_COLOR = "FF0000"

# Vorbelegte Kundenliste - der Benutzer pflegt sie in den Einstellungen.
DEFAULT_CUSTOMERS = ("Vertrieb", "Corporate")

_HEX_COLOR = re.compile(r"^[0-9A-Fa-f]{6}$")
_RGB_TRIPLE = re.compile(r"^(\d{1,3})\s*[,;/ ]\s*(\d{1,3})\s*[,;/ ]\s*(\d{1,3})$")


def normalize_color(value: str, fallback: str = DEFAULT_MANUAL_COLOR) -> str:
    """Normalisiert eine Farbeingabe auf RRGGBB (Grossbuchstaben).

    Akzeptiert "#RRGGBB", "RRGGBB", die Kurzform "#RGB" sowie ein
    RGB-Tripel wie "255,0,0". Bei ungueltiger Eingabe kommt der Fallback
    zurueck - eine kaputte Farbe darf den Export nie sprengen.

    Args:
        value:
            Die Benutzereingabe.
        fallback:
            Rueckgabewert bei ungueltiger Eingabe.

    Returns:
        Farbe als sechsstelliger Hex-String ohne fuehrendes Doppelkreuz.
    """
    raw = (value or "").strip().lstrip("#").strip()
    if _HEX_COLOR.match(raw):
        return raw.upper()

    if len(raw) == 3 and _HEX_COLOR.match(raw * 2):
        return "".join(ch * 2 for ch in raw).upper()

    match = _RGB_TRIPLE.match(raw)
    if match is not None:
        parts = [int(g) for g in match.groups()]
        if all(0 <= p <= 255 for p in parts):
            return "".join(f"{p:02X}" for p in parts)

    return fallback


# Themen der Oberflaeche. "system" folgt der Einstellung des Betriebssystems.
THEMES = ("system", "dark", "light")
DEFAULT_THEME = "system"

# Einstellungsdatei der aelteren Textual-TUI "jira-timesheet". Die Feldnamen
# sind identisch, deshalb lassen sich die Werte ohne Umbau uebernehmen - der
# Anwender soll Host, Token und Co. nicht erneut eingeben muessen.
LEGACY_SETTINGS_FILE: Path = Path.home() / ".jira-timesheet" / "settings.json"

# Zugangsfelder, die der Import-Knopf im Einstellungsdialog uebernimmt. Bewusst
# nur der Jira-Zugang - Arbeitszeit und Darstellung bleiben unangetastet, damit
# ein bewusster Klick keine schon getroffenen Entscheidungen ueberschreibt.
ACCESS_FIELDS = (
    "jira_host",
    "email",
    "jira_token",
    "use_legacy_api",
    "proxy_url",
    "budget_field",
)

# Berechnungs-/Arbeitszeitfelder der TUI (Reiter "Berechnung"). Werden beim
# Import aus der TUI mit uebernommen - sonst fehlen Stundensatz/MwSt und Netto/
# Brutto bleiben leer.
CALC_FIELDS = (
    "federal_state",
    "hours_per_day",
    "max_yearly_hours",
    "hourly_rate",
    "vat_rate",
    "vacation_days",
)

# Kernfelder des Zugangs: sind ALLE drei leer, gilt der Zugang als
# unkonfiguriert. Grundlage fuer den Datenverlust-Schutz beim Speichern.
_ACCESS_CORE = ("jira_host", "email", "jira_token")


@dataclass
class Settings:
    """Einstellungen gespeichert in ~/.jira-timesheet-qt/settings.json."""

    theme: str = DEFAULT_THEME
    accent: str = "orange"
    # Oberflaechen-Zoom in Prozent (skaliert alle Schriftgroessen).
    ui_scale: int = 100
    language: str = "de"
    jira_host: str = ""
    jira_token: str = ""
    email: str = ""
    use_legacy_api: bool = False
    proxy_url: str = ""
    logo_path: str = ""
    last_date_from: str = ""
    last_date_to: str = ""
    # In der GUI beim ersten Start ausgeblendet: die Statuszeile zeigt den
    # letzten Stand, der Verlauf wird nur bei Bedarf gebraucht.
    log_visible: bool = False
    budget_field: str = "customfield_XXXXX"
    federal_state: str = "SN"
    hours_per_day: float = 8.0
    max_yearly_hours: float = 1720.0
    show_target_hours_in_export: bool = False
    show_ticket_links_in_export: bool = False
    hourly_rate: float = 0.0
    vat_rate: float = 19.0
    year: int = 0
    vacation_days: int = 30
    config_collapsed: bool = False
    search_history: list[str] = field(default_factory=list)
    # Manuell gezogene Spaltenbreiten der Liste, Schluessel ist der Spaltenindex.
    column_widths: dict[str, int] = field(default_factory=dict)
    # Konfiguration der Export-Spalten (aktiv + Bezeichnung).
    export_columns: list[ExportColumn] = field(default_factory=default_columns)
    mark_manual_entries: bool = True
    manual_entry_color: str = DEFAULT_MANUAL_COLOR
    default_customer: str = "Vertrieb"
    # Zuletzt im Speichern-Dialog gewaehltes Verzeichnis.
    last_export_dir: str = ""
    # Auswahlliste fuer das Kunden-Feld im Dialog fuer manuelle Zeiten.
    customers: list[str] = field(default_factory=lambda: list(DEFAULT_CUSTOMERS))

    SETTINGS_DIR: Path = Path.home() / ".jira-timesheet-qt"
    SETTINGS_FILE: Path = SETTINGS_DIR / "settings.json"

    _FIELDS = (
        "theme",
        "accent",
        "ui_scale",
        "language",
        "jira_host",
        "jira_token",
        "email",
        "use_legacy_api",
        "proxy_url",
        "logo_path",
        "last_date_from",
        "last_date_to",
        "log_visible",
        "budget_field",
        "federal_state",
        "hours_per_day",
        "max_yearly_hours",
        "show_target_hours_in_export",
        "show_ticket_links_in_export",
        "hourly_rate",
        "vat_rate",
        "year",
        "vacation_days",
        "config_collapsed",
        "search_history",
        "column_widths",
        "export_columns",
        "mark_manual_entries",
        "manual_entry_color",
        "default_customer",
        "customers",
        "last_export_dir",
    )

    def to_dict(self) -> dict[str, object]:
        """Konvertiert die Einstellungen in ein Dictionary fuer JSON."""
        data: dict[str, object] = {name: getattr(self, name) for name in self._FIELDS}
        # Spalten sind Dataclasses - fuer JSON in Dicts wandeln.
        data["export_columns"] = [column.to_dict() for column in self.export_columns]
        return data

    @staticmethod
    def load() -> Settings:
        """Laedt die Einstellungen aus der JSON-Datei.

        Fehlt die eigene Datei, wird beim ersten Start einmalig die
        Einstellungsdatei der aelteren Textual-TUI uebernommen, sofern
        vorhanden - so muss der Jira-Zugang nicht erneut eingegeben werden.
        Gibt Default-Einstellungen zurueck bei Fehler.
        """
        data = Settings._read_json(Settings.SETTINGS_FILE)
        if data is None:
            # Keine eigene Datei - beim ersten Start komplett aus der Textual-TUI
            # uebernehmen, sofern vorhanden.
            legacy = Settings._read_json(LEGACY_SETTINGS_FILE)
            settings = Settings._from_dict(legacy) if legacy is not None else Settings()
            source = "TUI-Datei" if legacy is not None else "Vorgaben"
            logger.info("Erststart ohne eigene Einstellungsdatei - geladen aus: %s", source)
            return settings

        settings = Settings._from_dict(data)
        has_access = bool(settings.jira_host or settings.email or settings.jira_token)
        logger.info(
            "Einstellungen geladen aus %s (Jira-Zugang: %s)",
            Settings.SETTINGS_FILE,
            "vorhanden" if has_access else "LEER",
        )
        return settings

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        """Liest eine JSON-Datei defensiv; None bei Fehlen oder Fehler.

        Rueckgabe ist bewusst ``dict[str, Any]`` - der Inhalt kommt aus JSON,
        und die Feld-Parser unten pruefen jeden Wert einzeln.
        """
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Datei %s konnte nicht gelesen werden: %s", path, exc)
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> Settings:
        """Baut Einstellungen aus einem Dictionary (defensiv, mit Vorgaben)."""
        try:
            return Settings(
                theme=Settings._parse_theme(data.get("theme")),
                accent=str(data.get("accent", "orange")),
                ui_scale=int(data.get("ui_scale", 100)),
                language=data.get("language", "de"),
                jira_host=data.get("jira_host", ""),
                jira_token=data.get("jira_token", ""),
                email=data.get("email", ""),
                use_legacy_api=bool(data.get("use_legacy_api", False)),
                proxy_url=data.get("proxy_url", ""),
                logo_path=data.get("logo_path", ""),
                last_date_from=data.get("last_date_from", ""),
                last_date_to=data.get("last_date_to", ""),
                log_visible=bool(data.get("log_visible", False)),
                budget_field=data.get("budget_field", "customfield_XXXXX"),
                federal_state=data.get("federal_state", "SN"),
                hours_per_day=data.get("hours_per_day", 8.0),
                max_yearly_hours=data.get("max_yearly_hours", 1720.0),
                show_target_hours_in_export=bool(data.get("show_target_hours_in_export", False)),
                show_ticket_links_in_export=bool(data.get("show_ticket_links_in_export", False)),
                hourly_rate=data.get("hourly_rate", 0.0),
                vat_rate=data.get("vat_rate", 19.0),
                year=data.get("year", 0),
                vacation_days=data.get("vacation_days", 30),
                config_collapsed=bool(data.get("config_collapsed", False)),
                search_history=[str(x) for x in data.get("search_history", []) if isinstance(x, str)],
                column_widths=Settings._parse_column_widths(data.get("column_widths")),
                export_columns=parse_columns(data.get("export_columns")),
                mark_manual_entries=bool(data.get("mark_manual_entries", True)),
                manual_entry_color=normalize_color(str(data.get("manual_entry_color", DEFAULT_MANUAL_COLOR))),
                default_customer=str(data.get("default_customer", "Vertrieb")),
                customers=Settings._parse_customers(data.get("customers")),
                last_export_dir=str(data.get("last_export_dir", "")),
            )
        except Exception as exc:
            logger.warning("Settings konnten nicht aufgebaut werden: %s", exc)
            return Settings()

    @staticmethod
    def legacy_available() -> bool:
        """Meldet, ob eine Einstellungsdatei der Textual-TUI existiert."""
        return LEGACY_SETTINGS_FILE.is_file()

    @staticmethod
    def legacy_access() -> dict[str, Any] | None:
        """Liefert Zugangs- UND Berechnungsfelder aus der Textual-TUI.

        Bewusst lesend und ohne Seiteneffekt: der Einstellungsdialog fuellt
        damit seine Felder, uebernommen wird erst beim Speichern. Neben dem
        Jira-Zugang kommen die Berechnungsfelder mit (Stundensatz, MwSt,
        Arbeitszeit) - sonst blieben Netto/Brutto leer.

        Returns:
            Ein Dictionary der Felder, oder None ohne Legacy-Datei.
        """
        legacy = Settings._read_json(LEGACY_SETTINGS_FILE)
        if legacy is None:
            return None
        source = Settings._from_dict(legacy)
        return {name: getattr(source, name) for name in (*ACCESS_FIELDS, *CALC_FIELDS)}

    @staticmethod
    def _parse_theme(raw: object) -> str:
        """Nimmt nur bekannte Themen an, sonst die Vorgabe.

        Aeltere Dateien aus der TUI koennen einen Textual-Theme-Namen
        enthalten (z.B. "brotkasten") - der ergibt hier keinen Sinn.
        """
        value = str(raw) if raw is not None else ""
        return value if value in THEMES else DEFAULT_THEME

    @staticmethod
    def _parse_customers(raw: object) -> list[str]:
        """Liest die Kundenliste defensiv; leere Eintraege fliegen raus."""
        if not isinstance(raw, list):
            return list(DEFAULT_CUSTOMERS)
        names = [str(item).strip() for item in raw if str(item).strip()]
        return names or list(DEFAULT_CUSTOMERS)

    @staticmethod
    def _parse_column_widths(raw: object) -> dict[str, int]:
        """Liest die gespeicherten Spaltenbreiten defensiv aus dem JSON."""
        if not isinstance(raw, dict):
            return {}
        return {str(key): int(value) for key, value in raw.items() if isinstance(value, int) and value > 0}

    def save(self) -> None:
        """Speichert die Einstellungen in die JSON-Datei.

        Vor dem Schreiben greift ein Datenverlust-Schutz: Wuerde dieser Vorgang
        einen zuvor gesetzten Jira-Zugang leeren, wird das als Fehler geloggt
        (mit Aufrufpfad) und die vorhandenen Werte werden bewahrt.
        """
        try:
            Settings.SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            data = self.to_dict()
            Settings._guard_access_loss(data)
            Settings.SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Settings konnten nicht gespeichert werden: %s", exc)

    @staticmethod
    def _guard_access_loss(data: dict[str, Any]) -> None:
        """Bewahrt einen vorhandenen Jira-Zugang vor dem Leerschreiben.

        Sind Host, E-Mail UND Token im zu schreibenden Datensatz leer, die
        bereits gespeicherte Datei hatte sie aber, gilt das als Fehler: WARNUNG
        samt Aufrufpfad (Stacktrace) ins Log, und die vorhandenen Zugangsfelder
        werden aus der alten Datei uebernommen. So verliert niemand seine
        muehsam eingegebenen Werte, und der Ausloeser bleibt im Log auffindbar.

        Args:
            data:
                Der zu schreibende Datensatz; wird bei Bedarf in-place ergaenzt.
        """
        writing_empty = not any(str(data.get(field_name, "")).strip() for field_name in _ACCESS_CORE)
        if not writing_empty:
            return
        previous = Settings._read_json(Settings.SETTINGS_FILE)
        if previous is None:
            return
        had_access = any(str(previous.get(field_name, "")).strip() for field_name in _ACCESS_CORE)
        if not had_access:
            return

        logger.warning(
            "DATENVERLUST VERHINDERT: Speichern haette den Jira-Zugang geleert. "
            "Vorhandene Werte wurden bewahrt. Aufrufpfad:\n%s",
            "".join(traceback.format_stack()),
        )
        for name in ACCESS_FIELDS:
            if name in previous:
                data[name] = previous[name]

"""Spaltenkonfiguration fuer die Stundenzettel-Exporte (Excel/PDF).

Der Benutzer kann pro Spalte festlegen, ob sie exportiert wird und wie sie
heisst. Die Reihenfolge ist fest und entspricht dem gewachsenen Layout des
Stundenzettels.
"""

from __future__ import annotations

from dataclasses import dataclass

# Schluessel der Beschreibungs-Spalte. Sie ist die Flex-Spalte und bekommt die
# Breite, die die uebrigen aktiven Spalten uebrig lassen.
DESCRIPTION_KEY = "description"


@dataclass
class ExportColumn:
    """Eine konfigurierbare Spalte.

    ``visible`` steuert die Anzeige in der Listenansicht, ``enabled`` den
    Export nach Excel und PDF - beides ist bewusst getrennt schaltbar.
    """

    key: str
    label: str
    enabled: bool = True
    visible: bool = True

    def to_dict(self) -> dict[str, object]:
        """Serialisiert die Spalte fuer settings.json."""
        return {"key": self.key, "label": self.label, "enabled": self.enabled, "visible": self.visible}


@dataclass(frozen=True)
class ColumnDefault:
    """Unveraenderliche Vorgaben einer Spalte (Bezeichnung und Breiten)."""

    key: str
    label: str
    excel_width: float
    pdf_width: float


# Reihenfolge und Vorgaben wie im abgestimmten Muster-Stundenzettel.
# excel_width in Excel-Zeicheneinheiten, pdf_width in Millimetern (A4 quer).
COLUMN_DEFAULTS: tuple[ColumnDefault, ...] = (
    ColumnDefault("week", "KW", 5.0, 10.0),
    ColumnDefault("weekday", "Tag", 6.0, 10.0),
    ColumnDefault("date", "Datum", 11.0, 16.0),
    ColumnDefault("ticket", "Ticket", 12.0, 24.0),
    ColumnDefault(DESCRIPTION_KEY, "Beschreibung", 100.0, 100.0),
    ColumnDefault("customer", "Kunde", 20.0, 30.0),
    ColumnDefault("hours", "Aufwand (h)", 12.0, 25.0),
    ColumnDefault("day_hours", "Tagessumme (h)", 15.0, 25.0),
)

_DEFAULTS_BY_KEY = {c.key: c for c in COLUMN_DEFAULTS}

# Gesamtbreite der PDF-Tabelle: A4 quer (297 mm) minus 2 x 10 mm Rand.
PDF_TABLE_WIDTH = 277.0
# Untergrenzen, damit die Flex-Spalte nie auf 0 zusammenfaellt.
MIN_PDF_DESCRIPTION_WIDTH = 40.0
MIN_EXCEL_DESCRIPTION_WIDTH = 30.0


def default_columns() -> list[ExportColumn]:
    """Liefert die Vorgabe-Spaltenliste (alle aktiv, Standard-Bezeichnungen)."""
    return [ExportColumn(key=c.key, label=c.label, enabled=True, visible=True) for c in COLUMN_DEFAULTS]


def default_label(key: str) -> str:
    """Standard-Bezeichnung einer Spalte, leer bei unbekanntem Schluessel."""
    entry = _DEFAULTS_BY_KEY.get(key)
    return entry.label if entry is not None else ""


def excel_width(key: str) -> float:
    """Excel-Spaltenbreite einer Spalte."""
    entry = _DEFAULTS_BY_KEY.get(key)
    return entry.excel_width if entry is not None else 12.0


def pdf_width(key: str) -> float:
    """PDF-Spaltenbreite einer Spalte in Millimetern."""
    entry = _DEFAULTS_BY_KEY.get(key)
    return entry.pdf_width if entry is not None else 20.0


def parse_columns(raw: object) -> list[ExportColumn]:
    """Liest die Spaltenkonfiguration defensiv aus dem JSON.

    Unbekannte Schluessel werden verworfen, fehlende Spalten aus den Defaults
    ergaenzt - so tauchen spaeter hinzugefuegte Spalten automatisch auf, ohne
    dass eine bestehende settings.json von Hand nachgezogen werden muss.
    """
    stored: dict[str, ExportColumn] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            if key not in _DEFAULTS_BY_KEY:
                continue
            label = str(item.get("label", "")).strip() or default_label(key)
            stored[key] = ExportColumn(
                key=key,
                label=label,
                enabled=bool(item.get("enabled", True)),
                visible=bool(item.get("visible", True)),
            )

    return [
        stored.get(c.key, ExportColumn(key=c.key, label=c.label, enabled=True, visible=True)) for c in COLUMN_DEFAULTS
    ]


def visible_keys(columns: list[ExportColumn]) -> list[str]:
    """Schluessel der in der Listenansicht sichtbaren Spalten, in Reihenfolge."""
    return [c.key for c in columns if c.visible]


def pdf_column_widths(columns: list[ExportColumn]) -> list[float]:
    """Berechnet die PDF-Breiten der aktiven Spalten.

    Die Beschreibungs-Spalte fuellt den Rest der Tabellenbreite. Ist sie nicht
    aktiv, werden die uebrigen Spalten proportional auf die volle Breite
    gestreckt, damit die Tabelle keinen Rand frei laesst.
    """
    active = [c for c in columns if c.enabled]
    if not active:
        return []

    fixed = sum(pdf_width(c.key) for c in active if c.key != DESCRIPTION_KEY)
    has_description = any(c.key == DESCRIPTION_KEY for c in active)

    if has_description:
        rest = max(MIN_PDF_DESCRIPTION_WIDTH, PDF_TABLE_WIDTH - fixed)
        return [rest if c.key == DESCRIPTION_KEY else pdf_width(c.key) for c in active]

    scale = PDF_TABLE_WIDTH / fixed if fixed > 0 else 1.0
    return [pdf_width(c.key) * scale for c in active]

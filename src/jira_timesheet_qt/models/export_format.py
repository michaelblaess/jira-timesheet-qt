"""Die Ausgabeformate des Stundenzettel-Exports.

Ein Format ist hier nur seine Kennung, seine Dateiendung und die
i18n-Schluessel seiner Beschriftungen. Welcher Dienst schreibt, steht
bewusst NICHT hier - so kennen Oberflaeche und Dienste dieselbe Liste, ohne
dass das Modell von den Exportern abhaengt.

Public API:
    - `ExportFormat` - ein Format.
    - `EXCEL` / `PDF` / `JSON` / `MARKDOWN` - die einzelnen Formate.
    - `EXPORT_FORMATS` - alle Formate in der Reihenfolge des Dialogs.
    - `DEFAULT_FORMAT` - das vorausgewaehlte Format.
    - `format_for_suffix()` / `format_for_path()` - Endung auf Format.
    - `swap_suffix()` - Dateiname auf ein anderes Format umstellen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class ExportFormat:
    """Ein Ausgabeformat des Exports.

    Attributes:
        key: Interne Kennung, taucht in Logmeldungen und Tests auf.
        suffix: Die Dateiendung mit fuehrendem Punkt, immer klein.
        filter_key: i18n-Schluessel des Eintrags im Filter-Auswahlfeld.
        name_key: i18n-Schluessel des kurzen Namens fuer Meldungen.
    """

    key: str
    suffix: str
    filter_key: str
    name_key: str


EXCEL = ExportFormat("excel", ".xlsx", "save_dialog.filter_excel", "format.excel")
PDF = ExportFormat("pdf", ".pdf", "save_dialog.filter_pdf", "format.pdf")
JSON = ExportFormat("json", ".json", "save_dialog.filter_json", "format.json")
MARKDOWN = ExportFormat("markdown", ".md", "save_dialog.filter_markdown", "format.markdown")

EXPORT_FORMATS: tuple[ExportFormat, ...] = (EXCEL, PDF, JSON, MARKDOWN)
"""Alle Formate in der Reihenfolge, in der sie im Dialog stehen.

Erst die beiden Formate zum Abgeben (Excel, PDF), dann die beiden zum
Weiterverarbeiten (JSON, Markdown).
"""

DEFAULT_FORMAT: ExportFormat = EXPORT_FORMATS[0]
"""Das beim Oeffnen des Dialogs vorausgewaehlte Format."""

_BY_SUFFIX: dict[str, ExportFormat] = {f.suffix: f for f in EXPORT_FORMATS}
_BY_KEY: dict[str, ExportFormat] = {f.key: f for f in EXPORT_FORMATS}


def format_for_suffix(suffix: str) -> ExportFormat | None:
    """Sucht das Format zu einer Dateiendung.

    Args:
        suffix: Die Endung, mit oder ohne fuehrenden Punkt, Gross-/Kleinschreibung egal.

    Returns:
        Das Format, oder None wenn die Endung zu keinem gehoert.
    """

    raw = suffix.strip().lower()
    if raw and not raw.startswith("."):
        raw = f".{raw}"
    return _BY_SUFFIX.get(raw)


def format_for_path(path: Path | str) -> ExportFormat | None:
    """Sucht das Format zur Endung eines Pfades.

    Args:
        path: Der Pfad oder Dateiname.

    Returns:
        Das Format, oder None wenn die Endung zu keinem gehoert.
    """

    return format_for_suffix(Path(path).suffix)


def format_for_key(key: str) -> ExportFormat | None:
    """Sucht das Format zu seiner Kennung.

    Args:
        key: Die Kennung, z.B. "excel".

    Returns:
        Das Format, oder None bei unbekannter Kennung.
    """

    return _BY_KEY.get(key.strip().lower())


def suggested_name(target: ExportFormat, date_from: date, date_to: date, now: datetime | None = None) -> str:
    """Baut den vorgeschlagenen Dateinamen fuer ein Format.

    Die Regel steht hier und NUR hier. Sie stand vorher in jedem Exporter
    einzeln - beim Zusammenlegen des Exports waeren daraus fuenf fast gleiche
    Zeilen geworden, die beim naechsten Wunsch alle nachgezogen werden muessten.

    Args:
        target: Das Ausgabeformat, es liefert die Endung.
        date_from: Erster Tag des Zeitraums.
        date_to: Letzter Tag des Zeitraums.
        now: Zeitpunkt fuer den Zeitstempel. None nimmt die aktuelle Zeit -
            ein Test setzt ihn fest, statt gegen die Uhr zu pruefen.

    Returns:
        Der Dateiname, ohne Verzeichnis.
    """

    stempel = now if now is not None else datetime.now()
    return f"Stundenzettel_{date_from:%Y-%m-%d}_{date_to:%Y-%m-%d}_{stempel:%Y%m%d_%H%M%S}{target.suffix}"


def swap_suffix(filename: str, target: ExportFormat) -> str:
    """Stellt einen Dateinamen auf ein anderes Format um.

    Traegt der Name schon die Endung eines bekannten Formats, wird sie
    ersetzt. Jede andere Endung bleibt stehen und die neue tritt dahinter -
    aus "Bericht v1.2" wird also "Bericht v1.2.md" und nicht "Bericht v1.md".
    Was der Anwender getippt hat, geht dabei nie verloren.

    Args:
        filename: Der aktuelle Dateiname ohne Verzeichnis.
        target: Das Format, auf das umgestellt wird.

    Returns:
        Der Dateiname mit der Endung des Zielformats.
    """

    name = filename.strip()
    if not name:
        return name
    current = Path(name).suffix
    if current.lower() == target.suffix:
        return name
    if current.lower() in _BY_SUFFIX:
        return f"{name[: -len(current)]}{target.suffix}"
    return f"{name}{target.suffix}"

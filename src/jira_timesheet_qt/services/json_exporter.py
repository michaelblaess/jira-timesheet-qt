"""JSON-Export - der Stundenzettel als maschinenlesbarer Datensatz.

Anders als Excel, PDF und Markdown ist dieser Export bewusst NICHT an die
Spaltenkonfiguration gebunden: er schreibt jedes Feld, das ein Eintrag traegt.
Wer JSON waehlt, will weiterverarbeiten, und eine abgeschaltete Spalte im
Ausdruck ist kein Grund, ihm Daten vorzuenthalten.

Die Datei traegt eine `fassung`. Kommt ein Feld hinzu, bleibt sie stehen -
hochgezogen wird sie nur, wenn sich die Bedeutung vorhandener Felder aendert.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from jira_timesheet_qt.models.export_format import JSON, suggested_name
from jira_timesheet_qt.models.timesheet import Timesheet, WorklogEntry

FASSUNG = 1
"""Fassung des Dateiformats. Siehe Modul-Beschreibung."""


class JsonExporter:
    """Schreibt den Stundenzettel als JSON-Datei."""

    def __init__(self, jira_host: str = "", hours_per_day: float = 8.0, default_customer: str = "") -> None:
        """Nimmt die Angaben entgegen, die nicht im Stundenzettel selbst stehen.

        Args:
            jira_host: Basisadresse von Jira, fuer die Ticket-Verweise.
            hours_per_day: Sollstunden je Arbeitstag.
            default_customer: Kunde fuer Eintraege ohne eigenen Kunden.
        """

        self._jira_host = jira_host.rstrip("/")
        self._hours_per_day = hours_per_day
        self._default_customer = default_customer

    @staticmethod
    def suggested_filename(timesheet: Timesheet) -> str:
        """Liefert einen vorgeschlagenen Dateinamen fuer den Speichern-Dialog.

        Args:
            timesheet: Der zu exportierende Stundenzettel.

        Returns:
            Der Dateiname, ohne Verzeichnis.
        """

        return suggested_name(JSON, timesheet.date_from, timesheet.date_to)

    def export(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]] | None = None,
        target_hours: float = 0.0,
        output_dir: str = "",
        output_path: str = "",
    ) -> str:
        """Exportiert den Stundenzettel als .json Datei.

        Args:
            timesheet: Der zu exportierende Stundenzettel.
            missing_days: Tage ohne Buchung mit ihrem Grund.
            target_hours: Sollstunden des Zeitraums, 0 wenn sie nicht mit sollen.
            output_dir: Zielverzeichnis, wenn kein vollstaendiger Pfad vorliegt.
            output_path: Vollstaendiger Zielpfad, z.B. aus dem Speichern-Dialog.

        Returns:
            Der geschriebene Pfad, absolut.
        """

        if output_path:
            filepath = output_path
        else:
            if not output_dir:
                output_dir = str(Path.home() / "Desktop")
            filepath = os.path.join(output_dir, self.suggested_filename(timesheet))

        daten = self._build(timesheet, missing_days or [], target_hours)
        ziel = Path(filepath)
        # newline="\n" - sonst uebersetzt Windows jedes \n in CRLF.
        ziel.write_text(
            json.dumps(daten, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return str(ziel.resolve())

    def _build(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]],
        target_hours: float,
    ) -> dict[str, object]:
        """Baut den Datensatz, der geschrieben wird.

        Args:
            timesheet: Der Stundenzettel.
            missing_days: Tage ohne Buchung mit ihrem Grund.
            target_hours: Sollstunden des Zeitraums.

        Returns:
            Der vollstaendige Datensatz als Abbildung.
        """

        return {
            "fassung": FASSUNG,
            "erzeugt_am": datetime.now().isoformat(timespec="seconds"),
            "entwickler": timesheet.developer,
            "email": timesheet.email,
            "zeitraum": {
                "von": timesheet.date_from.isoformat(),
                "bis": timesheet.date_to.isoformat(),
            },
            "summen": {
                "gesamt_stunden": round(timesheet.total_hours, 2),
                "arbeitstage": timesheet.working_days,
                "durchschnitt_stunden": round(timesheet.average_hours, 2),
                "soll_stunden": round(target_hours, 2),
                "differenz_stunden": round(timesheet.total_hours - target_hours, 2) if target_hours > 0 else None,
                "stunden_pro_tag": self._hours_per_day,
            },
            "jira_host": self._jira_host,
            "tage": [
                {
                    "datum": tag.date.isoformat(),
                    "stunden": round(tag.total_hours, 2),
                    "eintraege": [self._entry(eintrag) for eintrag in tag.entries],
                }
                for tag in timesheet.days
            ],
            "fehlende_tage": [{"datum": d.isoformat(), "grund": grund} for d, grund in missing_days],
        }

    def _entry(self, entry: WorklogEntry) -> dict[str, object]:
        """Wandelt einen Eintrag in seine JSON-Form.

        Args:
            entry: Der Eintrag.

        Returns:
            Alle Felder des Eintrags, Datum als ISO-Text.
        """

        daten: dict[str, object] = dict(asdict(entry))
        daten["date"] = entry.date.isoformat()
        daten["customer"] = entry.customer or self._default_customer
        if self._jira_host and entry.ticket:
            daten["url"] = f"{self._jira_host}/browse/{entry.ticket}"
        return daten

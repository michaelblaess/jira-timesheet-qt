"""Markdown-Export - der Stundenzettel als Tabelle zum Weiterreichen.

Gleiche Spalten und gleiche Zeilenlogik wie der PDF-Export (siehe
`export_rows`), nur eben als Text. Gedacht fuer Tickets, Mails und Doku, wo
eine angehaengte Datei stoert.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from jira_timesheet_qt.models.export_column import ExportColumn, default_columns
from jira_timesheet_qt.models.export_format import MARKDOWN, suggested_name
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.services.export_rows import entry_values, gap_values

# Spalten mit Zahlen stehen rechts - in Markdown ueber den Doppelpunkt in der
# Trennzeile.
_RIGHT_ALIGNED = frozenset({"hours", "day_hours"})


class MarkdownExporter:
    """Schreibt den Stundenzettel als Markdown-Datei."""

    def __init__(
        self,
        jira_host: str = "",
        hours_per_day: float = 8.0,
        show_ticket_links: bool = False,
        columns: list[ExportColumn] | None = None,
        default_customer: str = "",
        mark_manual: bool = True,
    ) -> None:
        """Nimmt die Angaben entgegen, die nicht im Stundenzettel selbst stehen.

        Args:
            jira_host: Basisadresse von Jira, fuer die Ticket-Verweise.
            hours_per_day: Sollstunden je Arbeitstag.
            show_ticket_links: Ticketnummern als Verweis nach Jira schreiben.
            columns: Die Spaltenkonfiguration, None fuer die Vorgabe.
            default_customer: Kunde fuer Eintraege ohne eigenen Kunden.
            mark_manual: Manuell erfasste Eintraege kennzeichnen.
        """

        self._jira_host = jira_host.rstrip("/")
        self._hours_per_day = hours_per_day
        self._show_ticket_links = show_ticket_links
        self._default_customer = default_customer
        self._mark_manual = mark_manual
        source = columns if columns is not None else default_columns()
        self._columns = [c for c in source if c.enabled]

    @staticmethod
    def suggested_filename(timesheet: Timesheet) -> str:
        """Liefert einen vorgeschlagenen Dateinamen fuer den Speichern-Dialog.

        Args:
            timesheet: Der zu exportierende Stundenzettel.

        Returns:
            Der Dateiname, ohne Verzeichnis.
        """

        return suggested_name(MARKDOWN, timesheet.date_from, timesheet.date_to)

    def export(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]] | None = None,
        target_hours: float = 0.0,
        output_dir: str = "",
        output_path: str = "",
    ) -> str:
        """Exportiert den Stundenzettel als .md Datei.

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

        text = self.render(timesheet, missing_days or [], target_hours)
        ziel = Path(filepath)
        # newline="\n" - sonst uebersetzt Windows jedes \n in CRLF.
        ziel.write_text(text, encoding="utf-8", newline="\n")
        return str(ziel.resolve())

    def render(
        self,
        timesheet: Timesheet,
        missing_days: list[tuple[date, str]] | None = None,
        target_hours: float = 0.0,
    ) -> str:
        """Baut den Markdown-Text, ohne ihn zu schreiben.

        Args:
            timesheet: Der zu exportierende Stundenzettel.
            missing_days: Tage ohne Buchung mit ihrem Grund.
            target_hours: Sollstunden des Zeitraums.

        Returns:
            Der vollstaendige Text, mit abschliessendem Zeilenumbruch.
        """

        zeilen = self._header(timesheet, target_hours)
        zeilen += self._table(timesheet, missing_days or [])
        return "\n".join(zeilen) + "\n"

    def _header(self, timesheet: Timesheet, target_hours: float) -> list[str]:
        """Baut Titel und Kopfdaten.

        Args:
            timesheet: Der Stundenzettel.
            target_hours: Sollstunden des Zeitraums.

        Returns:
            Die Zeilen des Kopfes, mit Leerzeile am Ende.
        """

        zeilen = [
            "# Stundenzettel",
            "",
            f"- **Entwickler:** {timesheet.developer}",
            f"- **Zeitraum:** {timesheet.date_from:%d.%m.%Y} - {timesheet.date_to:%d.%m.%Y}",
            f"- **Gesamt:** {timesheet.total_hours:.2f} h",
        ]
        if target_hours > 0:
            diff = timesheet.total_hours - target_hours
            vorzeichen = "+" if diff >= 0 else ""
            zeilen.append(f"- **Soll:** {target_hours:.0f} h  |  **Differenz:** {vorzeichen}{diff:.2f} h")
        zeilen.append("")
        return zeilen

    def _table(self, timesheet: Timesheet, missing_days: list[tuple[date, str]]) -> list[str]:
        """Baut die Tabelle aus Buchungen und Luecken.

        Args:
            timesheet: Der Stundenzettel.
            missing_days: Tage ohne Buchung mit ihrem Grund.

        Returns:
            Die Zeilen der Tabelle.
        """

        if not self._columns:
            return []

        trenner = ["---:" if c.key in _RIGHT_ALIGNED else "---" for c in self._columns]
        zeilen = [
            self._row([c.label for c in self._columns]),
            self._row(trenner, escape=False),
        ]

        tage = {tag.date: tag for tag in timesheet.days}
        luecken = dict(missing_days)
        for d in sorted(set(tage) | set(luecken)):
            if d in luecken and d not in tage:
                zeilen.append(self._row(gap_values(self._columns, d, luecken[d])))
                continue
            tag = tage[d]
            for index, eintrag in enumerate(tag.entries):
                werte = entry_values(self._columns, eintrag, tag, index == 0, self._default_customer)
                zeilen.append(self._row(self._decorate(werte, eintrag.ticket, eintrag.manual)))
        return zeilen

    def _decorate(self, values: list[str], ticket: str, manual: bool) -> list[str]:
        """Setzt Ticket-Verweis und Kennzeichnung manueller Eintraege.

        Args:
            values: Die Zellwerte in Spaltenreihenfolge.
            ticket: Die Ticketnummer des Eintrags.
            manual: True, wenn der Eintrag von Hand erfasst wurde.

        Returns:
            Die Zellwerte, ergaenzt um Verweis und Kennzeichnung.
        """

        ergebnis = list(values)
        for index, spalte in enumerate(self._columns):
            if spalte.key != "ticket" or not ergebnis[index]:
                continue
            if self._show_ticket_links and self._jira_host and ticket:
                ergebnis[index] = f"[{ergebnis[index]}]({self._jira_host}/browse/{ticket})"
            if manual and self._mark_manual:
                # Kursiv statt Farbe - Markdown kennt keine Zellfarbe.
                ergebnis[index] = f"*{ergebnis[index]}*"
        return ergebnis

    @staticmethod
    def _row(values: list[str], escape: bool = True) -> str:
        """Setzt Zellwerte zu einer Markdown-Tabellenzeile zusammen.

        Args:
            values: Die Zellwerte in Spaltenreihenfolge.
            escape: Senkrechte Striche in den Werten maskieren. Fuer die
                Trennzeile abschalten, deren Striche gehoeren zur Syntax.

        Returns:
            Die fertige Zeile.
        """

        trenner = " | "
        zellen = [v.replace("|", "\\|").replace("\n", " ") if escape else v for v in values]
        return f"| {trenner.join(zellen)} |"

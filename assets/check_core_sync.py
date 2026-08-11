"""Vergleicht den fachlichen Kern mit dem der Textual-Fassung.

Der Kern wurde beim Anlegen dieses Projekts aus jira-timesheet KOPIERT, nicht
eingebunden. Es gibt also keine Verbindung: eine Aenderung dort kommt hier
nicht an, und umgekehrt. Das ist gewollt, solange die GUI die TUI ersetzen
soll - es darf nur nicht unbemerkt bleiben.

Dieses Skript macht die Abweichungen sichtbar. Package-Name und Datenpfad
werden vor dem Vergleich angeglichen, weil sie sich zwangslaeufig
unterscheiden.

Aufruf:
    python assets/check_core_sync.py [pfad-zu-jira-timesheet]

Rueckgabe:
    0 = kein Unterschied ausser den bekannten
    1 = es gibt Abweichungen (Liste auf der Ausgabe)
    2 = die Textual-Fassung wurde nicht gefunden
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
QT_SRC = HERE / "src" / "jira_timesheet_qt"

# Dateien, die aus der Textual-Fassung stammen.
#
# Die drei Kern-Pakete standen bis zum 11.08.2026 NICHT in dieser Liste,
# obwohl sie den groessten geteilten Teil ausmachen. Der Reiter "Mein Team"
# lief deshalb ueber Wochen unbemerkt auseinander - 138 Zeilen in
# ticket_board, das ganze Paket team fehlte hier komplett. Ein Abgleich, der
# den Kern auslaesst, meldet "alles gleich" und belegt damit nichts.
SHARED = (
    "i18n.py",
    "models/export_column.py",
    "models/settings.py",
    "models/timesheet.py",
    "services/anonymizer.py",
    "services/cache_service.py",
    "services/duration.py",
    "services/excel_exporter.py",
    "services/holiday_service.py",
    "services/jira_client.py",
    "services/manual_entry_service.py",
    "services/pdf_exporter.py",
    "services/timesheet_service.py",
    # Ticket-Ansichten: der fachliche Kern, UI-frei und in beiden Fassungen
    # wortgleich.
    "services/ticket_board/__init__.py",
    "services/ticket_board/config.py",
    "services/ticket_board/models.py",
    "services/ticket_board/queries.py",
    "services/ticket_board/rules.py",
    "services/ticket_board/stats.py",
    # Mein Team: Merkliste und Kontoauswahl.
    "services/team/__init__.py",
    "services/team/models.py",
    "services/team/roster.py",
    # Ticket-Bericht.
    "services/ticket_report/__init__.py",
    "services/ticket_report/adf.py",
    "services/ticket_report/lifecycle.py",
    "services/ticket_report/render.py",
    "services/ticket_report/style.py",
    "services/ticket_report/viewmodel.py",
)

# Bewusst abweichend (anderer Datenpfad, kein Retro-Theme, Export-Verzeichnis).
# Wird gemeldet, gilt aber nicht als Fehler.
EXPECTED_DIFFERENT = {"models/settings.py"}

DEFAULT_TUI = HERE.parent / "jira-timesheet"


def normalise(text: str) -> list[str]:
    """Gleicht Package-Name und Datenpfad an, damit nur Inhalt uebrig bleibt."""
    text = text.replace("jira_timesheet_qt", "jira_timesheet")
    text = text.replace("jira-timesheet-qt", "jira-timesheet")
    return [line.rstrip() for line in text.splitlines()]


def main(argv: list[str]) -> int:
    """Vergleicht beide Faelle und meldet die Abweichungen."""
    tui_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_TUI
    tui_src = tui_root / "src" / "jira_timesheet"
    if not tui_src.is_dir():
        print(f"Textual-Fassung nicht gefunden: {tui_src}", file=sys.stderr)
        print("Aufruf: python assets/check_core_sync.py <pfad-zu-jira-timesheet>", file=sys.stderr)
        return 2

    unexpected: list[str] = []
    for name in SHARED:
        here, there = QT_SRC / name, tui_src / name
        if not there.is_file():
            print(f"  {name}: in der Textual-Fassung nicht vorhanden")
            unexpected.append(name)
            continue

        mine = normalise(here.read_text(encoding="utf-8"))
        theirs = normalise(there.read_text(encoding="utf-8"))
        if mine == theirs:
            print(f"  {name}: gleich")
            continue

        changed = sum(1 for line in difflib.unified_diff(theirs, mine, n=0) if line[:1] in "+-")
        if name in EXPECTED_DIFFERENT:
            print(f"  {name}: {changed} Zeilen abweichend (bekannt, gewollt)")
        else:
            print(f"  {name}: {changed} Zeilen abweichend  <-- NEU")
            unexpected.append(name)

    print()
    if unexpected:
        print(f"{len(unexpected)} Datei(en) laufen auseinander: {', '.join(unexpected)}")
        print("Unterschied ansehen mit:")
        print(f"  diff -u {tui_src / unexpected[0]} {QT_SRC / unexpected[0]}")
        return 1

    print("Kern deckungsgleich (bis auf die bekannten Stellen).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

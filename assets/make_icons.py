"""Erzeugt die Symbole der Oberflaeche als SVG.

Warum ueberhaupt eigene Symbole: Unicode-Glyphen wie ⚙ oder ◐ werden unter
Windows als farbige Emoji gerendert - verwaschen, nicht einfaerbbar und in
jeder Schriftart anders. Qt-Standardsymbole wiederum sehen je nach Stil und
Betriebssystem verschieden aus.

QSS kennt kein currentColor, deshalb wird jedes Symbol je Erscheinungsbild in
einer eigenen Farbe geschrieben.

Aufruf:  python assets/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "jira_timesheet_qt" / "resources" / "icons"

# Strichfarbe je Erscheinungsbild - entspricht text_secondary aus theme.py.
COLORS = {"dark": "#9ba3b0", "light": "#5f6775"}

# Strichgrafiken im 24er-Raster, bewusst schlicht und gleich stark.
PATHS: dict[str, str] = {
    "chevron-left": '<path d="M15 6 L9 12 L15 18"/>',
    "chevron-right": '<path d="M9 6 L15 12 L9 18"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11 L12 16.5"/><path d="M12 7.6 L12 8"/>',
    # Schieberegler statt Zahnrad: ein Zahnrad aus Kreis plus Strahlen ist von
    # der Sonne nicht zu unterscheiden, wenn beide nebeneinander stehen.
    "settings": (
        '<path d="M4 7 L14 7 M18 7 L20 7 M4 12 L8 12 M12 12 L20 12 M4 17 L15 17 M19 17 L20 17"/>'
        '<circle cx="16" cy="7" r="2.1"/><circle cx="10" cy="12" r="2.1"/><circle cx="17" cy="17" r="2.1"/>'
    ),
    # Erscheinungsbild: Mond fuer den Wechsel ins Dunkle, Sonne ins Helle.
    "moon": '<path d="M20 14.5 A8.5 8.5 0 1 1 9.5 4 A6.6 6.6 0 0 0 20 14.5 Z"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2.4 L12 4.4 M12 19.6 L12 21.6 M2.4 12 L4.4 12 M19.6 12 L21.6 12'
        ' M5.1 5.1 L6.5 6.5 M17.5 17.5 L18.9 18.9'
        ' M18.9 5.1 L17.5 6.5 M6.5 17.5 L5.1 18.9"/>'
    ),
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.4 15.4 L20 20"/>',
    # Manuelle Zeit erfassen: Pluszeichen.
    "plus": '<path d="M12 5 L12 19 M5 12 L19 12"/>',
    # Protokoll/Verlauf: ein Fenster mit Textzeilen - klar abgesetzt vom
    # Schieberegler-Symbol der Einstellungen (Zeilen mit Kreisen).
    "log": (
        '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/>'
        '<path d="M6.8 9 L14 9 M6.8 12.5 L17.2 12.5 M6.8 16 L11.5 16"/>'
    ),
    "refresh": (
        '<path d="M20 12 A8 8 0 1 1 17.3 6.1"/>'
        '<path d="M20.4 3.4 L20.4 8.2 L15.6 8.2" stroke-linejoin="round"/>'
    ),
}

# Kleinere Symbole fuer Auswahllisten und Zahlenfelder, eigenes Raster.
SMALL_PATHS: dict[str, tuple[int, str]] = {
    "chevron-down": (12, '<path d="M2.5 4.5 L6 8 L9.5 4.5"/>'),
    "chevron-up": (12, '<path d="M2.5 7.5 L6 4 L9.5 7.5"/>'),
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    'viewBox="0 0 {size} {size}" fill="none" stroke="{color}" stroke-width="{width}" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>\n'
)


def main() -> None:
    """Schreibt alle Symbole in beiden Farben."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    for variant, color in COLORS.items():
        for name, body in PATHS.items():
            path = OUT_DIR / f"{name}-{variant}.svg"
            path.write_text(
                _TEMPLATE.format(size=24, color=color, width=1.7, body=body),
                encoding="utf-8",
            )
            written += 1

        for name, (size, body) in SMALL_PATHS.items():
            path = OUT_DIR / f"{name}-{variant}.svg"
            path.write_text(
                _TEMPLATE.format(size=size, color=color, width=1.6, body=body),
                encoding="utf-8",
            )
            written += 1

    print(f"{written} Symbole in {OUT_DIR}")


if __name__ == "__main__":
    main()

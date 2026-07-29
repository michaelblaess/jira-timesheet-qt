"""Designsprache der Anwendung: Farben, die QPalette und das duenne Struktur-QSS.

Erscheinungsbild-Entscheidung E1 (27.07.2026): klassischer Fusion-Look. Die
Steuerelemente (Schaltflaechen, Eingaben, Tabelle, Combo, Zahlenfelder, Kalender,
Bildlaufleiste) bleiben nativ - Fusion zeichnet sie ueber die QPalette. Nur die
strukturellen Flaechen der Anwendung (Kopfzeile, Seitenleiste, Detailbereich,
Summenleiste, Statuszeile, Dialoge) und die Typografie werden per QSS gesetzt.

So ist die Anwendung leicht verstaendlich, plattformnah und wartungsarm - kein
Riesen-QSS, das jede Qt-Vorgabe nachbaut. Details siehe docs/qt-grundlagen.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from PySide6.QtGui import QColor, QPalette


class Mode(StrEnum):
    """Verfuegbare Erscheinungsbilder."""

    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class Palette:
    """Farbwerte eines Erscheinungsbilds.

    Wird von der QPalette (native Steuerelemente), vom Struktur-QSS und von den
    selbstgezeichneten Ansichten (Kalender, Jahr) gemeinsam genutzt.
    """

    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_elevated: str
    border: str
    border_hover: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    accent: str
    accent_hover: str
    accent_subtle: str
    green: str
    orange: str
    red: str
    purple: str
    shadow: str


# Konservative Palette: gedeckte Graustufen, ruhiger Stahlblau-Akzent. Reihenfolge
# der Flaechen nach Helligkeit: bg_primary (Fenster) - bg_secondary (Panels) -
# bg_tertiary (Tabelle/Base) - bg_elevated (Schaltflaechen).
DARK = Palette(
    bg_primary="#1f2226",
    bg_secondary="#23262b",
    bg_tertiary="#26292e",
    bg_elevated="#2f333a",
    border="#3a3f47",
    border_hover="#4a505a",
    text_primary="#e2e5ea",
    text_secondary="#9aa2ad",
    text_tertiary="#6f7680",
    accent="#ff922b",
    accent_hover="#ffa94d",
    accent_subtle="rgba(255, 146, 43, 0.20)",
    green="#5a9e83",
    orange="#c39a52",
    red="#c96f6f",
    purple="#8f83b0",
    shadow="rgba(0, 0, 0, 0.4)",
)

LIGHT = Palette(
    bg_primary="#f4f5f7",
    bg_secondary="#f0f1f4",
    bg_tertiary="#ffffff",
    bg_elevated="#eceef1",
    border="#d3d7dd",
    border_hover="#b9bec6",
    text_primary="#1c1f24",
    text_secondary="#5f6773",
    text_tertiary="#8b929e",
    accent="#e8590c",
    accent_hover="#fd7e14",
    accent_subtle="rgba(232, 89, 12, 0.14)",
    green="#2f8f6b",
    orange="#b0791f",
    red="#b64a4a",
    purple="#6f5fa0",
    shadow="rgba(0, 0, 0, 0.10)",
)

# Radien nur noch fuer die wenigen strukturellen Flaechen mit eigenem Rahmen.
RADIUS_SM = 4
RADIUS_MD = 6


@dataclass(frozen=True)
class Accent:
    """Ein Akzentfarben-Satz (Grundton, Hover, transparente Flaeche)."""

    accent: str
    accent_hover: str
    accent_subtle: str


# Vordefinierte Akzentfarben, je (dunkel, hell) und auf guten Kontrast in beiden
# Erscheinungsbildern abgestimmt. Schluessel bleiben stabil (Serialisierung),
# der Anzeigename steht in ACCENT_LABELS.
ACCENTS: dict[str, tuple[Accent, Accent]] = {
    "orange": (
        Accent("#ff922b", "#ffa94d", "rgba(255, 146, 43, 0.20)"),
        Accent("#e8590c", "#fd7e14", "rgba(232, 89, 12, 0.14)"),
    ),
    "blau": (
        Accent("#4dabf7", "#74c0fc", "rgba(77, 171, 247, 0.20)"),
        Accent("#1c7ed6", "#1971c2", "rgba(28, 126, 214, 0.14)"),
    ),
    "gruen": (
        Accent("#51cf66", "#69db7c", "rgba(81, 207, 102, 0.20)"),
        Accent("#2f9e44", "#37b24d", "rgba(47, 158, 68, 0.14)"),
    ),
    "tuerkis": (
        Accent("#22b8cf", "#3bc9db", "rgba(34, 184, 207, 0.20)"),
        Accent("#0c8599", "#1098ad", "rgba(12, 133, 153, 0.14)"),
    ),
    "violett": (
        Accent("#b197fc", "#d0bfff", "rgba(177, 151, 252, 0.20)"),
        Accent("#7048e8", "#7950f2", "rgba(112, 72, 232, 0.14)"),
    ),
}

# Anzeigenamen (alphabetisch sortiert vom Aufrufer).
ACCENT_LABELS: dict[str, str] = {
    "blau": "Blau",
    "gruen": "Grün",
    "orange": "Orange",
    "tuerkis": "Türkis",
    "violett": "Violett",
}

DEFAULT_ACCENT = "orange"
# Aktive Akzentfarbe - global, weil das Erscheinungsbild app-weit gilt (wie das
# Stylesheet). set_accent wird beim Start und beim Speichern der Einstellungen
# aufgerufen, bevor Palette und QSS neu gebaut werden.
_current_accent = DEFAULT_ACCENT


def set_accent(name: str) -> None:
    """Setzt die aktive Akzentfarbe (faellt bei unbekanntem Namen auf Orange)."""
    global _current_accent
    _current_accent = name if name in ACCENTS else DEFAULT_ACCENT


def current_accent() -> str:
    """Name der aktiven Akzentfarbe."""
    return _current_accent


# Verfuegbare Oberflaechen-Zoomstufen (Prozent).
SCALES: tuple[int, ...] = (80, 90, 100, 110, 125, 150, 175, 200)
DEFAULT_SCALE = 100
_current_scale = DEFAULT_SCALE


def set_scale(percent: int) -> None:
    """Setzt den Oberflaechen-Zoom (Prozent, auf gueltige Werte begrenzt)."""
    global _current_scale
    _current_scale = min(SCALES[-1], max(SCALES[0], int(percent)))


def current_scale() -> int:
    """Aktive Zoomstufe in Prozent."""
    return _current_scale


def _apply_scale(qss: str) -> str:
    """Skaliert alle font-size-Angaben (px) im QSS mit dem aktiven Zoom.

    So laesst sich die ganze Oberflaeche vergroessern, ohne jede Groesse einzeln
    zu pflegen - auch die selbstgezeichneten Ansichten ziehen mit, weil sie ihre
    Schrift vom (per QSS gesetzten) Widget-Font ableiten.
    """
    if _current_scale == 100:
        return qss
    factor = _current_scale / 100.0
    return re.sub(
        r"font-size:\s*(\d+)px",
        lambda m: f"font-size: {max(1, round(int(m.group(1)) * factor))}px",
        qss,
    )


def palette_for(mode: Mode) -> Palette:
    """Liefert die Farbwerte zum Erscheinungsbild - mit der aktiven Akzentfarbe."""
    base = DARK if mode is Mode.DARK else LIGHT
    variant = ACCENTS.get(_current_accent, ACCENTS[DEFAULT_ACCENT])[0 if mode is Mode.DARK else 1]
    return replace(
        base,
        accent=variant.accent,
        accent_hover=variant.accent_hover,
        accent_subtle=variant.accent_subtle,
    )


def build_palette(mode: Mode) -> QPalette:
    """Baut die QPalette, mit der Fusion alle nativen Steuerelemente faerbt.

    Args:
        mode:
            Gewaehltes Erscheinungsbild.

    Returns:
        Eine vollstaendig gesetzte QPalette (Fenster, Basis, Text, Knoepfe,
        Auswahl, deaktivierte Zustaende).
    """
    p = palette_for(mode)
    pal = QPalette()

    def c(value: str) -> QColor:
        return QColor(value)

    pal.setColor(QPalette.ColorRole.Window, c(p.bg_primary))
    pal.setColor(QPalette.ColorRole.WindowText, c(p.text_primary))
    pal.setColor(QPalette.ColorRole.Base, c(p.bg_tertiary))
    pal.setColor(QPalette.ColorRole.AlternateBase, c(p.bg_secondary))
    pal.setColor(QPalette.ColorRole.ToolTipBase, c(p.bg_elevated))
    pal.setColor(QPalette.ColorRole.ToolTipText, c(p.text_primary))
    pal.setColor(QPalette.ColorRole.Text, c(p.text_primary))
    pal.setColor(QPalette.ColorRole.Button, c(p.bg_elevated))
    pal.setColor(QPalette.ColorRole.ButtonText, c(p.text_primary))
    pal.setColor(QPalette.ColorRole.BrightText, c("#ffffff"))
    pal.setColor(QPalette.ColorRole.Highlight, c(p.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, c("#ffffff"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, c(p.text_tertiary))
    pal.setColor(QPalette.ColorRole.Link, c(p.accent_hover))

    disabled = QPalette.ColorGroup.Disabled
    pal.setColor(disabled, QPalette.ColorRole.Text, c(p.text_tertiary))
    pal.setColor(disabled, QPalette.ColorRole.ButtonText, c(p.text_tertiary))
    pal.setColor(disabled, QPalette.ColorRole.WindowText, c(p.text_tertiary))
    pal.setColor(disabled, QPalette.ColorRole.Highlight, c(p.border))
    pal.setColor(disabled, QPalette.ColorRole.HighlightedText, c(p.text_secondary))
    return pal


def build_qss(mode: Mode, font_sans: str, font_mono: str) -> str:
    """Erzeugt das duenne Struktur-Stylesheet.

    Nur strukturelle Flaechen und Typografie. Alle Steuerelemente bleiben nativ
    (Fusion + QPalette).

    Args:
        mode:
            Gewaehltes Erscheinungsbild.
        font_sans:
            Schriftfamilie der Oberflaeche.
        font_mono:
            Schriftfamilie fuer Zahlen, Vorgangsschluessel und Zeiten.

    Returns:
        QSS als Zeichenkette, direkt fuer setStyleSheet geeignet.
    """
    p = palette_for(mode)
    # Leere Familie bedeutet: keine passende Schrift gefunden - dann die
    # Angabe weglassen, damit Qt seine Standardschrift nimmt.
    sans_rule = f'font-family: "{font_sans}";' if font_sans else ""
    mono_rule = f'font-family: "{font_mono}";' if font_mono else ""
    return _apply_scale(f"""
/* ---------------------------------------------------------------- Grundlage */
QWidget {{
    {sans_rule}
    font-size: 13px;
}}

/* Ohne das faerbt die Fensterfarbe jedes Label auf abweichenden Flaechen ein. */
QLabel {{
    background: transparent;
}}

QToolTip {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 1px solid {p.border};
    padding: 6px 10px;
}}

/* ---------------------------------------------------------- Menue + Toolbar */
/* Ohne einen vollstaendigen Block uebernimmt QStyleSheetStyle das Menue (weil
   app-weit ein Stylesheet gesetzt ist) und zeichnet das Icon eines gehoverten
   Eintrags nicht mehr. Deshalb hier komplett und theme-konsistent. */
QMenuBar {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
    padding: 2px 6px;
}}

QMenuBar::item {{
    background: transparent;
    color: {p.text_primary};
    padding: 5px 10px;
    border-radius: {RADIUS_SM}px;
}}

QMenuBar::item:selected {{
    background-color: {p.bg_tertiary};
}}

QMenuBar::item:pressed {{
    background-color: {p.accent_subtle};
    color: {p.accent};
}}

QMenu {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: {RADIUS_MD}px;
    padding: 5px;
}}

QMenu::item {{
    /* Links Platz fuer das Icon reservieren - sonst kann es beim Hover
       verschwinden. */
    padding: 6px 28px 6px 34px;
    border-radius: {RADIUS_SM}px;
    color: {p.text_primary};
}}

QMenu::item:selected {{
    background-color: {p.accent_subtle};
    color: {p.accent};
}}

QMenu::item:disabled {{
    color: {p.text_tertiary};
}}

QMenu::separator {{
    height: 1px;
    background-color: {p.border};
    margin: 5px 10px;
}}

QMenu::icon {{
    padding-left: 10px;
}}

QToolBar {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
    padding: 3px 6px;
    spacing: 2px;
}}

QToolBar::separator {{
    background-color: {p.border};
    width: 1px;
    margin: 4px 6px;
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 5px;
}}

QToolButton:hover {{
    background-color: {p.bg_tertiary};
}}

QToolButton:pressed, QToolButton:checked {{
    background-color: {p.accent_subtle};
}}

/* ---------------------------------------------- Monat und Suche in der Toolbar */
/* Die Blaetter-Knoepfe sollen immer als Knoepfe erkennbar sein, nicht erst beim
   Hover - deshalb sichtbarer Rahmen und Flaeche. */
#MonthNavButton {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SM}px;
    padding: 4px 10px;
}}

#MonthNavButton:hover {{
    background-color: {p.bg_tertiary};
    border-color: {p.text_tertiary};
}}

#MonthNavButton:pressed {{
    background-color: {p.accent_subtle};
    border-color: {p.accent};
}}

#ToolbarMonth {{
    font-size: 15px;
    font-weight: 700;
    color: {p.text_primary};
    padding: 0 6px;
}}

#ToolbarSearch {{
    min-height: 22px;
}}

/* --------------------------------------------------- Ansichts-Reiter (wie TUI) */
#ViewTabs {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
}}

#ViewTabs::tab {{
    background: transparent;
    color: {p.text_secondary};
    padding: 8px 18px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    font-weight: 600;
}}

#ViewTabs::tab:hover {{
    color: {p.text_primary};
}}

#ViewTabs::tab:selected {{
    color: {p.accent};
    border-bottom: 2px solid {p.accent};
    font-weight: 700;
}}

/* ---------------------------------------------------------------- Trennlinie */
#Divider {{
    background-color: {p.border};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QSplitter::handle {{
    background-color: {p.border};
}}

/* Trenn-/Griffleiste des Meldungsfensters (QDockWidget). Ohne eigene Regel ist
   sie im hellen Erscheinungsbild kaum zu sehen. */
QMainWindow::separator {{
    background-color: {p.text_tertiary};
    width: 5px;
    height: 5px;
}}

QMainWindow::separator:hover {{
    background-color: {p.accent};
}}

/* Listen-/Baumansicht etwas groesser als die Grundschrift - bessere Lesbarkeit
   in der (gruppierten) Liste. */
QTreeView, QTableView {{
    font-size: 14px;
}}

/* ----------------------------------------------------- Detail-Dialog (modal) */
/* Kopf-Banner wie im Info-Dialog: abgesetzte Flaeche, border-bottom als Trennlinie. */
#DetailBanner {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
}}

#DetailBannerTicket {{
    color: {p.text_primary};
    font-size: 16px;
    font-weight: 800;
}}

#DetailBannerSummary {{
    color: {p.text_secondary};
    font-size: 13px;
}}

#DetailDialogLabel {{
    color: {p.text_tertiary};
    font-size: 12px;
    font-weight: 700;
}}

#DetailDialogValue {{
    color: {p.text_primary};
    font-size: 13px;
}}

#DetailDialogLink {{
    color: {p.accent};
    font-size: 12px;
}}

/* -------------------------------------------------------------- Leerzustand */
/* Lesbare Karte ueber dem formatfuellenden Hintergrundbild. */
#EmptyCard {{
    background-color: {p.bg_secondary};
    border: 1px solid {p.border};
    border-radius: 12px;
}}

#EmptyTitle {{
    color: {p.text_primary};
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}}

#EmptyText {{
    color: {p.text_tertiary};
    font-size: 13px;
    background: transparent;
}}

/* --------------------------------------------------------- Summenleiste */
/* Sitzt in der QStatusBar - deren Rahmen genuegt, kein eigener border-top. */
#SummaryBar {{
    background-color: {p.bg_secondary};
}}

/* Gerahmtes Panel je Kennzahl - leicht eingesenkt gegen die Leiste. */
#SummaryPanel {{
    background-color: {p.bg_tertiary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SM}px;
}}

#SummaryStatLabel {{
    color: {p.text_tertiary};
    font-size: 14px;
    background: transparent;
    border: none;
}}

#SummaryStatValue {{
    color: {p.text_primary};
    font-size: 14px;
    font-weight: 700;
    background: transparent;
    border: none;
}}

/* ------------------------------------------------------------ Statuszeile */
QStatusBar {{
    background-color: {p.bg_secondary};
    border-top: 1px solid {p.border};
}}

QStatusBar::item {{
    border: none;
}}

#StatusBar {{
    background: transparent;
    color: {p.text_tertiary};
    font-size: 12px;
}}

#StatusBar[state="error"] {{
    color: {p.red};
}}

#StatusBar[state="busy"] {{
    color: {p.accent_hover};
}}

/* ------------------------------------------------------------------ Toast */
#Toast {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border_hover};
    border-radius: {RADIUS_MD}px;
}}

#ToastText {{
    color: {p.text_primary};
    font-size: 15px;
    font-weight: 600;
    background: transparent;
    border: none;
}}

#ToastIcon {{
    background: transparent;
    border: none;
}}

/* ------------------------------------------------------------------ Dialoge */
#DialogButtons {{
    background-color: {p.bg_secondary};
    border-top: 1px solid {p.border};
}}

#SettingsNav {{
    background-color: {p.bg_secondary};
    border: none;
    border-right: 1px solid {p.border};
    padding: 14px 8px;
    outline: 0;
}}

#SettingsNav::item {{
    padding: 9px 12px;
    border-radius: {RADIUS_SM}px;
    color: {p.text_secondary};
    font-weight: 600;
}}

#SettingsNav::item:hover {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
}}

#SettingsNav::item:selected {{
    background-color: {p.accent_subtle};
    color: {p.accent};
}}

#SettingsHeading {{
    font-size: 17px;
    font-weight: 700;
    color: {p.text_primary};
}}

#SettingsLabel {{
    color: {p.text_secondary};
    font-weight: 600;
}}

#SettingsHint {{
    color: {p.text_tertiary};
    font-size: 12px;
}}

#SettingsPath {{
    color: {p.text_secondary};
    {mono_rule}
    font-size: 12px;
}}

/* ------------------------------------------------------- Haftungshinweis */
#DisclaimerTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {p.text_primary};
}}

#DisclaimerSection {{
    font-size: 13px;
    font-weight: 700;
    color: {p.text_primary};
    padding-top: 4px;
}}

#DisclaimerText {{
    color: {p.text_secondary};
    font-size: 13px;
}}

#DisclaimerScroll {{
    background-color: {p.bg_secondary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_MD}px;
    padding: 14px;
}}

#DisclaimerScroll > QWidget > QWidget {{
    background-color: {p.bg_secondary};
}}

/* ------------------------------------------------------------------- Info */
#AboutBanner {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
}}

#AboutName {{
    font-size: 26px;
    font-weight: 800;
    color: {p.text_primary};
}}

#AboutBannerText {{
    color: {p.text_secondary};
    font-size: 13px;
}}

/* Versionsplakette in der Akzentfarbe - der einzige farbige Punkt oben. */
#AboutBadge {{
    background-color: {p.accent};
    color: #ffffff;
    {mono_rule}
    font-size: 12px;
    font-weight: 700;
    padding: 3px 12px;
    border-radius: 9px;
}}

#AboutFacts {{
    color: {p.text_tertiary};
    font-size: 12px;
}}

#AboutText {{
    color: {p.text_secondary};
    font-size: 13px;
}}

#AboutQuote {{
    color: {p.text_secondary};
    font-size: 13px;
    font-style: italic;
}}

#AboutQuoteAuthor {{
    color: {p.text_tertiary};
    font-size: 12px;
    padding-top: 6px;
}}

#AboutLink {{
    font-size: 12px;
}}

#AboutLink a {{
    color: {p.accent_hover};
    text-decoration: none;
}}

/* --------------------------------------------------------- Meldungsfenster */
#LogView {{
    background-color: {p.bg_tertiary};
    border: none;
    {mono_rule}
    font-size: 12px;
    padding: 8px 12px;
}}

#LogButtons {{
    background-color: {p.bg_secondary};
    border-top: 1px solid {p.border};
}}
""")

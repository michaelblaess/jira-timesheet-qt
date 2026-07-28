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

from dataclasses import dataclass
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


def palette_for(mode: Mode) -> Palette:
    """Liefert die Farbwerte zum Erscheinungsbild."""
    return DARK if mode is Mode.DARK else LIGHT


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
    return f"""
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

/* ------------------------------------------------------------------ Kopfzeile */
#Header {{
    background-color: {p.bg_secondary};
    border-bottom: 1px solid {p.border};
}}

#HeaderTitle {{
    font-size: 19px;
    font-weight: 700;
    color: {p.text_primary};
}}

#HeaderSubtitle {{
    font-size: 12px;
    color: {p.text_tertiary};
}}

/* ---------------------------------------------------------------- Seitenleiste */
#Sidebar {{
    background-color: {p.bg_secondary};
    border-right: 1px solid {p.border};
}}

#SidebarSection {{
    color: {p.text_tertiary};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 12px;
}}

/* NavButton ist ein eigenes Widget, kein normaler Knopf - flach als Navi-Eintrag. */
#Sidebar NavButton {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
    color: {p.text_secondary};
}}

#Sidebar NavButton:hover {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
}}

#Sidebar NavButton[active="true"] {{
    background-color: {p.accent_subtle};
    color: {p.accent};
    font-weight: 700;
}}

#SidebarTotalLabel {{
    color: {p.text_tertiary};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}

#SidebarTotalValue {{
    color: {p.text_primary};
    {mono_rule}
    font-size: 22px;
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

/* ------------------------------------------------------------ Detailbereich */
#DetailPanel {{
    background-color: {p.bg_secondary};
    border-left: 1px solid {p.border};
}}

#DetailKey {{
    color: {p.text_primary};
    {mono_rule}
    font-size: 15px;
    font-weight: 700;
}}

#DetailSummary {{
    color: {p.text_secondary};
    font-size: 13px;
}}

#DetailLabel {{
    color: {p.text_tertiary};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}

#DetailValue {{
    color: {p.text_primary};
    font-size: 13px;
}}

#DetailValueMono {{
    color: {p.text_primary};
    {mono_rule}
    font-size: 13px;
}}

/* -------------------------------------------------------------- Leerzustand */
#EmptyTitle {{
    color: {p.text_primary};
    font-size: 17px;
    font-weight: 700;
}}

#EmptyText {{
    color: {p.text_tertiary};
    font-size: 13px;
}}

/* --------------------------------------------------------- Summenleiste */
#SummaryBar {{
    background-color: {p.bg_secondary};
    border-top: 1px solid {p.border};
}}

#SummaryStatLabel {{
    color: {p.text_tertiary};
    font-size: 12px;
}}

#SummaryStatValue {{
    color: {p.text_primary};
    font-size: 12px;
    font-weight: 700;
}}

#SummarySep {{
    color: {p.border};
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
"""

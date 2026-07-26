"""Designsprache der Anwendung: Farben, Masse und das daraus erzeugte QSS.

Die Werte stammen aus dem PRECISION-Design-System der GitHub-Pages-Seiten
(docs/css/precision.css in jira-timesheet), damit Web-Auftritt und Anwendung
zusammengehoeren.

Alles Sichtbare wird hier gestylt. Qt-Vorgaben bleiben nirgends stehen - ein
ungestyltes Widget verraet sofort das Toolkit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """Verfuegbare Erscheinungsbilder."""

    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class Palette:
    """Farbwerte eines Erscheinungsbilds."""

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


DARK = Palette(
    bg_primary="#0f1114",
    bg_secondary="#171a1f",
    bg_tertiary="#1e2228",
    bg_elevated="#242930",
    border="#2a2f38",
    border_hover="#3d4450",
    text_primary="#e8ecf1",
    text_secondary="#9ba3b0",
    text_tertiary="#6b7280",
    accent="#3b82f6",
    accent_hover="#60a5fa",
    accent_subtle="rgba(59, 130, 246, 0.14)",
    green="#34d399",
    orange="#fbbf24",
    red="#f87171",
    purple="#a78bfa",
    shadow="rgba(0, 0, 0, 0.4)",
)

LIGHT = Palette(
    bg_primary="#ffffff",
    bg_secondary="#f8f9fb",
    bg_tertiary="#f1f3f6",
    bg_elevated="#ffffff",
    border="#e2e5ea",
    border_hover="#c8cdd5",
    text_primary="#111318",
    text_secondary="#5f6775",
    text_tertiary="#8b929e",
    accent="#2563eb",
    accent_hover="#3b82f6",
    accent_subtle="rgba(37, 99, 235, 0.10)",
    green="#059669",
    orange="#d97706",
    red="#dc2626",
    purple="#7c3aed",
    shadow="rgba(0, 0, 0, 0.10)",
)

# Radien und Abstaende (Pixel), aus precision.css uebernommen.
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 16


def palette_for(mode: Mode) -> Palette:
    """Liefert die Farbwerte zum Erscheinungsbild."""
    return DARK if mode is Mode.DARK else LIGHT


def build_qss(mode: Mode, font_sans: str, font_mono: str) -> str:
    """Erzeugt das komplette Stylesheet.

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
    background-color: {p.bg_primary};
    color: {p.text_primary};
    {sans_rule}
    font-size: 13px;
    /* Qt zeichnet sonst gepunktete Fokusrahmen im Stil von 2005. */
    outline: 0;
}}

QToolTip {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
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

#Sidebar NavButton {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_MD}px;
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
    color: {p.accent_hover};
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

/* --------------------------------------------------------------- Schaltflaechen */
QPushButton {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_MD}px;
    padding: 8px 16px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {p.bg_elevated};
    border-color: {p.border_hover};
}}

QPushButton:pressed {{
    background-color: {p.bg_secondary};
}}

QPushButton:disabled {{
    color: {p.text_tertiary};
    border-color: {p.border};
}}

QPushButton[variant="primary"] {{
    background-color: {p.accent};
    border-color: {p.accent};
    color: #ffffff;
}}

QPushButton[variant="primary"]:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: none;
    padding: 7px 10px;
    color: {p.text_secondary};
}}

QPushButton[variant="ghost"]:hover {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
}}

/* ---------------------------------------------------------------- Eingaben */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background-color: {p.bg_tertiary};
    border: 1px solid {p.border};
    border-radius: {RADIUS_MD}px;
    padding: 8px 12px;
    selection-background-color: {p.accent};
    selection-color: #ffffff;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus {{
    border-color: {p.accent};
    background-color: {p.bg_elevated};
}}

QLineEdit::placeholder {{
    color: {p.text_tertiary};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {p.bg_elevated};
    border: 1px solid {p.border};
    border-radius: {RADIUS_MD}px;
    padding: 4px;
    selection-background-color: {p.accent_subtle};
    selection-color: {p.text_primary};
}}

/* ------------------------------------------------------------------ Tabelle */
QTableView {{
    background-color: {p.bg_primary};
    alternate-background-color: {p.bg_secondary};
    border: none;
    gridline-color: transparent;
    selection-background-color: {p.accent_subtle};
    selection-color: {p.text_primary};
}}

QTableView::item {{
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid {p.border};
}}

QTableView::item:selected {{
    background-color: {p.accent_subtle};
    color: {p.text_primary};
}}

QHeaderView {{
    background-color: {p.bg_primary};
}}

QHeaderView::section {{
    background-color: {p.bg_primary};
    color: {p.text_tertiary};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 9px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-align: left;
}}

QHeaderView::section:hover {{
    color: {p.text_secondary};
}}

QTableView QTableCornerButton::section {{
    background-color: {p.bg_primary};
    border: none;
}}

/* -------------------------------------------------------------- Bildlaufleiste */
/* Schmal und ohne Pfeiltasten - die Qt-Vorgabe ist unverkennbar. */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {p.border_hover};
    border-radius: 5px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p.text_tertiary};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {p.border_hover};
    border-radius: 5px;
    min-width: 32px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p.text_tertiary};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
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

/* ---------------------------------------------------------------- Trennlinie */
#Divider {{
    background-color: {p.border};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QSplitter::handle {{
    background-color: {p.border};
    width: 1px;
}}

QSplitter::handle:hover {{
    background-color: {p.accent};
}}
"""

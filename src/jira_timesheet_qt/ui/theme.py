"""Erscheinungsbild - Bruecke auf QAppFramework.

Farbwerte, Palette, die Grundregeln des Stylesheets sowie Erscheinungsbild,
Akzentfarbe und Zoom stehen in QAppFramework. Sie standen bis 0.7.2 hier, und
zwar zugleich in SiteHammer - zwei Staende derselben Sache, die auseinander
liefen.

Was hier bleibt, ist die eigene Handschrift dieser Anwendung: Monatsleiste,
Detailfenster, Summenleiste, Statuszeile, Toast und die Ansichten des
Ticket-Bretts. Dazu die Namen, unter denen die Anwendung das alles kennt -
Mode, Palette, palette_for, build_qss und die uebrigen. Sie an ueber hundert
Stellen umzubenennen brachte nichts ausser Risiko.

Wer eine Regel sucht, die hier nicht steht: sie kommt aus der Bibliothek und
gilt fuer alle Anwendungen. Wer sie dort aendert, aendert sie ueberall - genau
das ist der Zweck.
"""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtGui import QPalette
from QAppFramework.theme import (
    ACCENTS,
    DARK,
    DEFAULT_ACCENT,
    DEFAULT_ZOOM,
    LIGHT,
    RADIUS_MD,
    RADIUS_SM,
    ZOOM_LEVELS,
    Accent,
    Colors,
    accent_names,
)
from QAppFramework.theme import accent as current_accent
from QAppFramework.theme import build_palette as _baue_palette
from QAppFramework.theme import build_stylesheet as _baue_qss
from QAppFramework.theme import colors as _farben
from QAppFramework.theme import scale as _skaliere
from QAppFramework.theme import set_accent as set_accent
from QAppFramework.theme import set_zoom as set_scale
from QAppFramework.theme import zoom as current_scale


class Mode(StrEnum):
    """Verfuegbare Erscheinungsbilder.

    Bewusst weiter ein eigenes Enum statt des Modus der Bibliothek: die
    Ansichten dieser Anwendung kennen nur hell und dunkel. Welches von beiden
    bei der Einstellung 'System' gilt, loest der Einstiegspunkt beim Start auf.
    """

    DARK = "dark"
    LIGHT = "light"


# Die Anwendung nennt die Farbwerte 'Palette' und die Zoomstufen 'Scales' -
# alles andere heisst in der Bibliothek inzwischen genauso und kommt direkt
# aus dem Import.
Palette = Colors
ACCENT_LABELS: dict[str, str] = accent_names("de")
SCALES = ZOOM_LEVELS
DEFAULT_SCALE = DEFAULT_ZOOM

__all__ = [
    "ACCENTS",
    "ACCENT_LABELS",
    "DARK",
    "DEFAULT_ACCENT",
    "DEFAULT_SCALE",
    "LIGHT",
    "SCALES",
    "Accent",
    "Mode",
    "Palette",
    "build_palette",
    "build_qss",
    "current_accent",
    "current_scale",
    "palette_for",
    "set_accent",
    "set_scale",
]



def palette_for(mode: Mode) -> Palette:
    """Die Farbwerte zum Erscheinungsbild, mit der aktiven Akzentfarbe."""
    return _farben(dunkel=mode is Mode.DARK)


def build_palette(mode: Mode) -> QPalette:
    """Die QPalette, mit der Fusion alle nativen Steuerelemente faerbt."""
    return _baue_palette(palette_for(mode))


def build_qss(mode: Mode, font_sans: str, font_mono: str) -> str:
    """Das Stylesheet: die Grundregeln der Bibliothek, dann die eigenen.

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
    # Angabe weglassen, damit Qt seine Standardschrift nimmt. Ein Gattungsname
    # wie "sans-serif" waere keine Familie und ergaebe Kaestchen.
    sans_rule = f'font-family: "{font_sans}";' if font_sans else ""
    mono_rule = f'font-family: "{font_mono}";' if font_mono else ""
    eigenes = f"""
    QWidget {{ {sans_rule} }}
    QMenuBar::item:pressed {{ background-color: {p.accent_subtle}; color: {p.accent}; }}
    #MonthNavButton {{ background-color: {p.bg_elevated}; border: 1px solid {p.border}; border-radius: {RADIUS_SM}px; padding: 4px 10px; }}
    #MonthNavButton:hover {{ background-color: {p.bg_tertiary}; border-color: {p.text_tertiary}; }}
    #MonthNavButton:pressed {{ background-color: {p.accent_subtle}; border-color: {p.accent}; }}
    #ToolbarMonth {{ font-size: 15px; font-weight: 700; color: {p.text_primary}; padding: 0 6px; }}
    #ToolbarSearch {{ min-height: 22px; }}
    QSplitter#BoardSplitter::handle {{ background-color: {p.bg_secondary}; border-top: 1px solid {p.border}; border-bottom: 1px solid {p.border}; height: 7px; }}
    QSplitter#BoardSplitter::handle:hover {{ background-color: {p.accent_subtle}; }}
    QMainWindow::separator:hover {{ background-color: {p.accent}; }}
    QTreeView, QTableView {{ font-size: 14px; }}
    #DetailBanner {{ background-color: {p.bg_secondary}; border-bottom: 1px solid {p.border}; }}
    #DetailBannerTicket {{ color: {p.text_primary}; font-size: 16px; font-weight: 800; }}
    #DetailBannerSummary {{ color: {p.text_secondary}; font-size: 13px; }}
    #DetailDialogLabel {{ color: {p.text_tertiary}; font-size: 12px; font-weight: 700; }}
    #DetailDialogValue {{ color: {p.text_primary}; font-size: 13px; }}
    #DetailDialogLink {{ color: {p.accent}; font-size: 12px; }}
    #SummaryBar {{ background-color: {p.bg_secondary}; }}
    #SummaryPanel {{ background-color: {p.bg_tertiary}; border: 1px solid {p.border}; border-radius: {RADIUS_SM}px; }}
    #SummaryStatLabel {{ color: {p.text_tertiary}; font-size: 14px; background: transparent; border: none; }}
    #SummaryStatValue {{ color: {p.text_primary}; font-size: 14px; font-weight: 700; background: transparent; border: none; }}
    #StatusBar {{ background: transparent; color: {p.text_tertiary}; font-size: 12px; }}
    #StatusBar[state="error"] {{ color: {p.red}; }}
    #StatusBar[state="busy"] {{ color: {p.accent_hover}; }}
    #AnonBadge {{ background-color: {p.orange}; color: #ffffff; font-size: 11px; font-weight: 700; border-radius: {RADIUS_SM}px; }}
    #Toast {{ background-color: {p.bg_elevated}; border: 1px solid {p.border_hover}; border-radius: {RADIUS_MD}px; }}
    #ToastText {{ color: {p.text_primary}; font-size: 15px; font-weight: 600; background: transparent; border: none; }}
    #ToastIcon {{ background: transparent; border: none; }}
    #LogView {{ background-color: {p.bg_tertiary}; border: none; {mono_rule} font-size: 12px; padding: 8px 12px; }}
    #LogButtons {{ background-color: {p.bg_secondary}; border-top: 1px solid {p.border}; }}
    """
    # Der eigene Teil muss durch dieselbe Zoom-Skalierung wie der der
    # Bibliothek - sonst bleibt er als einziger auf fester Groesse.
    return _baue_qss(p) + _skaliere(eigenes)

"""Datengetriebenes Menuesystem: Struktur aus JSON/DB, Verhalten aus Code.

Die Struktur (welche Menues/Aktionen wo) kommt aus einer JSON- oder DB-Quelle und
wird zur Laufzeit gebaut - nie statisch. Verhalten liegt in der CommandRegistry,
verbunden nur ueber eine Command-ID. Ein MenuBuilder rendert aus DERSELBEN
Definition natives Menue UND Toolbar (eine QAction pro Command, von Qt synchron
gehalten). Details in docs/qt-menues.md.
"""

from __future__ import annotations

from jira_timesheet_qt.ui.menu.builder import MenuBuilder
from jira_timesheet_qt.ui.menu.registry import Command, CommandRegistry
from jira_timesheet_qt.ui.menu.schema import MenuDefinition, MenuNode, load_menu, missing_commands

__all__ = [
    "Command",
    "CommandRegistry",
    "MenuBuilder",
    "MenuDefinition",
    "MenuNode",
    "load_menu",
    "missing_commands",
]

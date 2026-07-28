"""Typisiertes Schema der Menue-Definition (JSON/DB -> validierter Knotenbaum).

Ein Menue ist ein Baum aus Knoten mit kleinem, geschlossenem Typ-Satz. Struktur-
knoten (menu, group, separator) tragen nur Layout; das Blatt (action/nav-item)
traegt NUR eine command-ID - nie einen Callable. pydantic validiert beim Laden,
damit eine kaputte Definition laut beim Start scheitert, nicht mit halber UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal[
    "menubar",
    "menu",
    "submenu",
    "action",
    "separator",
    "section",
    "group",
    "toolbar",
    "nav-item",
]


class MenuNode(BaseModel):
    """Ein Knoten im Menuebaum."""

    id: str
    type: NodeType
    # Beschriftung als i18n-Schluessel (nicht als Literal). Bei Trennern leer.
    title: str | None = None
    # Logisches Icon-Token (z.B. "mdi6.content-save"), nie ein Dateipfad.
    icon: str | None = None
    # Die Command-ID - der EINZIGE Link zum Verhalten (aus der Registry).
    command: str | None = None
    # Portabler Shortcut: "Ctrl+S" oder "StandardKey.Save" (plattformkorrekt).
    shortcut: str | None = None
    checkable: bool = False
    checked: bool = False
    # Name der QActionGroup fuer sich gegenseitig ausschliessende Umschalter.
    group: str | None = None
    # Sichtbarkeits-/Aktivierungs-Ausdruck (Whitelist-Grammatik, kein eval).
    when: str | None = None
    enabled_when: str | None = None
    # RBAC-Gate: der Teilbaum entsteht nur, wenn das Recht vorliegt.
    permission: str | None = None
    # Auf welchen Oberflaechen dieser Knoten erscheint.
    surfaces: list[str] = Field(default_factory=lambda: ["menu"])
    children: list[MenuNode] = Field(default_factory=list)

    def walk(self) -> list[MenuNode]:
        """Liefert diesen Knoten und alle Nachkommen (Tiefensuche)."""
        result = [self]
        for child in self.children:
            result.extend(child.walk())
        return result


class MenuDefinition(BaseModel):
    """Vollstaendige Menue-Definition einer Anwendung."""

    schema_version: int
    menubar: MenuNode

    def command_ids(self) -> set[str]:
        """Alle referenzierten Command-IDs im Baum."""
        return {node.command for node in self.menubar.walk() if node.command}


def load_menu(path: Path) -> MenuDefinition:
    """Laedt und validiert eine Menue-Definition aus einer JSON-Datei.

    Args:
        path:
            Pfad zur JSON-Datei.

    Returns:
        Die validierte Definition.

    Raises:
        pydantic.ValidationError:
            Wenn die Struktur nicht zum Schema passt.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return MenuDefinition.model_validate(data)


def missing_commands(definition: MenuDefinition, registered: set[str]) -> set[str]:
    """Command-IDs, die im Menue referenziert, aber nicht registriert sind.

    Der Referenz-Check, der scheitern kann: ein Menue, das auf einen Command
    zeigt, den niemand registriert hat.
    """
    return definition.command_ids() - registered

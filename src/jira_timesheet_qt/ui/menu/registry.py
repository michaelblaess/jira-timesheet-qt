"""Command-Registry: das Verhalten hinter den Command-IDs.

Die JSON-Struktur kennt nur Command-IDs; was ein Command TUT, liegt hier -
entkoppelt von jedem Menue. Die Registry besitzt die EINE QAction pro Command,
die der Builder lazy erzeugt und ueber alle Oberflaechen (Menue, Toolbar,
Kontextmenue) wiederverwendet - Qt haelt sie automatisch synchron.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtGui import QAction


@dataclass
class Command:
    """Ein Benutzer-Kommando: Verhalten plus Zustandsabfragen."""

    id: str
    # Das Verhalten - der einzige Ort, an dem ein Callable steht. Der Rueckgabe-
    # wert wird ignoriert (object statt None, damit z.B. QWidget.close -> bool passt).
    run: Callable[[], object]
    # i18n-Schluessel als Rueckfall, wenn der Knoten keinen Titel setzt.
    text_key: str = ""
    is_enabled: Callable[[], bool] = field(default=lambda: True)
    is_checked: Callable[[], bool] | None = None
    # Die EINE QAction, vom Builder lazy erzeugt und ueberall wiederverwendet.
    action: QAction | None = None


class CommandRegistry:
    """Haelt die Commands einer Anwendung, adressiert ueber ihre ID."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Registriert ein Command. Doppelte IDs sind ein Fehler."""
        if command.id in self._commands:
            raise ValueError(f"doppelte Command-ID: {command.id}")
        self._commands[command.id] = command

    def get(self, command_id: str) -> Command:
        """Liefert ein Command oder wirft KeyError mit sprechender Meldung."""
        try:
            return self._commands[command_id]
        except KeyError:
            raise KeyError(f"Menue verweist auf unbekanntes Command: {command_id}") from None

    def ids(self) -> set[str]:
        """Alle registrierten Command-IDs."""
        return set(self._commands)

    def refresh(self, command_id: str) -> None:
        """Gleicht Enabled/Checked der QAction mit dem aktuellen Zustand ab."""
        command = self.get(command_id)
        if command.action is None:
            return
        command.action.setEnabled(command.is_enabled())
        if command.is_checked is not None:
            command.action.setChecked(command.is_checked())

    def refresh_all(self) -> None:
        """Gleicht alle Commands ab (z.B. beim Oeffnen eines Menues)."""
        for command_id in self._commands:
            self.refresh(command_id)

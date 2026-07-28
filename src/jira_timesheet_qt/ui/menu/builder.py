"""MenuBuilder: baut aus der Definition native Qt-Oberflaechen.

Laeuft den validierten Baum fuer eine gegebene Oberflaeche (surface) ab und
materialisiert QMenuBar/QMenu (menu) oder QToolBar (toolbar) - aus DERSELBEN
Definition. Jedes Blatt holt die geteilte QAction aus der Registry, sodass ein
Command in Menue UND Toolbar dieselbe (von Qt synchron gehaltene) Instanz ist.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import QMenu, QMenuBar, QToolBar, QWidget

from jira_timesheet_qt.ui.menu.registry import CommandRegistry
from jira_timesheet_qt.ui.menu.schema import MenuNode


class MenuBuilder:
    """Erzeugt Menue und Toolbar aus einer Menue-Definition."""

    def __init__(
        self,
        registry: CommandRegistry,
        owner: QObject,
        tr: Callable[[str], str] | None = None,
        icon_loader: Callable[[str], QIcon] | None = None,
        has_permission: Callable[[str], bool] | None = None,
    ) -> None:
        """
        Args:
            registry:
                Die Command-Registry mit dem Verhalten.
            owner:
                QObject, das die erzeugten QActions/Gruppen besitzt (Lebensdauer).
            tr:
                i18n-Uebersetzer (Schluessel -> Text). Default: unveraendert.
            icon_loader:
                Laedt ein Icon aus einem logischen Token. Default: leeres Icon.
            has_permission:
                RBAC-Pruefung (Recht -> bool). Default: alles erlaubt.
        """
        self._registry = registry
        self._owner = owner
        self._tr = tr or (lambda key: key)
        self._icon = icon_loader or (lambda _name: QIcon())
        self._has_permission = has_permission or (lambda _perm: True)
        self._groups: dict[str, QActionGroup] = {}

    # --- Oberflaechen ---------------------------------------------------

    def build_menubar(self, node: MenuNode, parent: QWidget | None = None) -> QMenuBar:
        """Baut die Menueleiste."""
        bar = QMenuBar(parent)
        for child in self._visible(node.children, surface="menu"):
            if child.type in ("menu", "submenu"):
                # Menue an die Bar parenten, damit findChild/Q-Objektsuche greift.
                bar.addMenu(self._build_menu(child, bar))
        return bar

    def build_toolbar(self, node: MenuNode, parent: QWidget | None = None) -> QToolBar:
        """Baut eine Toolbar aus allen Aktionen mit surface 'toolbar'.

        Zwischen den Top-Level-Menues wird ein Trenner gesetzt, damit die
        Gruppierung der Menueleiste erhalten bleibt.
        """
        toolbar = QToolBar(parent)
        first = True
        for menu in self._visible(node.children, surface="toolbar"):
            actions = [
                self._action(a)
                for a in self._toolbar_actions(menu)
            ]
            if not actions:
                continue
            if not first:
                toolbar.addSeparator()
            for action in actions:
                toolbar.addAction(action)  # dieselbe QAction wie im Menue
            first = False
        return toolbar

    # --- Aufbau ---------------------------------------------------------

    def _build_menu(self, node: MenuNode, parent: QWidget | None) -> QMenu:
        menu = QMenu(self._tr(node.title or ""), parent)
        menu.setObjectName(node.id)  # fuer headless-Tests
        for child in self._visible(node.children, surface="menu"):
            if child.type == "separator":
                menu.addSeparator()
            elif child.type == "section":
                menu.addSection(self._tr(child.title or ""))
            elif child.type in ("menu", "submenu"):
                menu.addMenu(self._build_menu(child, parent))
            elif child.type == "group":
                for action_node in self._visible(child.children, surface="menu"):
                    menu.addAction(self._action(action_node))
            elif child.type == "action":
                menu.addAction(self._action(child))
        # Beim Oeffnen Enabled/Checked frisch abgleichen.
        menu.aboutToShow.connect(self._registry.refresh_all)
        return menu

    def _action(self, node: MenuNode) -> QAction:
        if node.command is None:
            raise ValueError(f"Aktionsknoten ohne command: {node.id}")
        command = self._registry.get(node.command)
        if command.action is None:
            action = QAction(self._owner)
            action.setText(self._tr(node.title or command.text_key))
            action.triggered.connect(lambda _checked=False, c=command: c.run())
            command.action = action
        action = command.action

        if node.icon:
            action.setIcon(self._icon(node.icon))
        if node.shortcut:
            action.setShortcut(self._key(node.shortcut))
        if node.checkable or command.is_checked is not None:
            action.setCheckable(True)
            action.setChecked(command.is_checked() if command.is_checked else node.checked)
        action.setEnabled(command.is_enabled())
        if node.group:
            group = self._groups.setdefault(node.group, QActionGroup(self._owner))
            group.setExclusive(True)
            group.addAction(action)
        return action

    @staticmethod
    def _key(spec: str) -> QKeySequence:
        """Portabler Shortcut: 'StandardKey.Save' oder ein Literal wie 'Ctrl+S'."""
        if spec.startswith("StandardKey."):
            name = spec.split(".", 1)[1]
            return QKeySequence(getattr(QKeySequence.StandardKey, name))
        return QKeySequence(spec)

    def _toolbar_actions(self, menu: MenuNode) -> list[MenuNode]:
        """Alle Aktionsknoten unter einem Menue, die auf der Toolbar erscheinen."""
        result: list[MenuNode] = []
        for node in menu.walk():
            if node.type == "action" and "toolbar" in node.surfaces and self._passes(node):
                result.append(node)
        return result

    def _visible(self, nodes: list[MenuNode], *, surface: str) -> list[MenuNode]:
        """Filtert Knoten nach Recht, Oberflaeche und when-Ausdruck."""
        visible: list[MenuNode] = []
        for node in nodes:
            if not self._passes(node):
                continue
            # Nur Blaetter werden nach surface gefiltert; Container immer durch.
            if node.type in ("action", "nav-item") and surface not in node.surfaces:
                continue
            visible.append(node)
        return visible

    def _passes(self, node: MenuNode) -> bool:
        """Recht (RBAC) fuer einen Knoten vorhanden?"""
        return not node.permission or self._has_permission(node.permission)

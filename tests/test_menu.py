"""Tests fuer das datengetriebene Menuesystem (Schema, Registry, Builder)."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.ui.main_window import MainWindow
from jira_timesheet_qt.ui.menu import (
    Command,
    CommandRegistry,
    MenuBuilder,
    MenuDefinition,
    MenuNode,
    missing_commands,
)
from jira_timesheet_qt.ui.theme import Mode


def _defn(children: list[MenuNode]) -> MenuDefinition:
    return MenuDefinition(
        schema_version=1,
        menubar=MenuNode(id="root.menubar", type="menubar", children=children),
    )


def _registry(command_ids: list[str]) -> CommandRegistry:
    registry = CommandRegistry()
    for cid in command_ids:
        registry.register(Command(cid, run=lambda: None, text_key=cid))
    return registry


class TestSchema:
    def test_valid_tree_parses(self) -> None:
        node = MenuNode.model_validate(
            {"id": "act.x", "type": "action", "command": "x", "title": "X"}
        )
        assert node.type == "action" and node.command == "x"
        assert node.surfaces == ["menu"]  # Default

    def test_unknown_type_is_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MenuNode.model_validate({"id": "x", "type": "bogus"})

    def test_command_ids_collects_the_whole_tree(self) -> None:
        definition = _defn([
            MenuNode(id="menu.f", type="menu", title="F", children=[
                MenuNode(id="a1", type="action", command="one", title="1"),
                MenuNode(id="a2", type="action", command="two", title="2"),
            ]),
        ])
        assert definition.command_ids() == {"one", "two"}


class TestMissingCommands:
    def test_detects_unregistered_command(self) -> None:
        definition = _defn([
            MenuNode(id="menu.f", type="menu", title="F", children=[
                MenuNode(id="a1", type="action", command="known", title="1"),
                MenuNode(id="a2", type="action", command="ghost", title="2"),
            ]),
        ])
        assert missing_commands(definition, _registry(["known"]).ids()) == {"ghost"}


class TestBuilder:
    def _owner(self) -> QWidget:
        return QWidget()

    def test_menubar_structure_matches_definition(self, qapp: QApplication) -> None:
        definition = _defn([
            MenuNode(id="menu.file", type="menu", title="Datei", children=[
                MenuNode(id="a.new", type="action", command="file.new", title="Neu"),
                MenuNode(id="sep", type="separator"),
                MenuNode(id="a.quit", type="action", command="file.quit", title="Beenden"),
            ]),
        ])
        owner = self._owner()
        builder = MenuBuilder(_registry(["file.new", "file.quit"]), owner=owner)
        bar = builder.build_menubar(definition.menubar, owner)

        file_menu = bar.findChild(QMenu, "menu.file")
        assert file_menu is not None
        labels = [a.text() for a in file_menu.actions() if not a.isSeparator()]
        assert labels == ["Neu", "Beenden"]
        assert any(a.isSeparator() for a in file_menu.actions())

    def test_same_qaction_across_menu_and_toolbar(self, qapp: QApplication) -> None:
        definition = _defn([
            MenuNode(id="menu.file", type="menu", title="Datei", children=[
                MenuNode(id="a.save", type="action", command="file.save", title="Speichern",
                         surfaces=["menu", "toolbar"]),
            ]),
        ])
        owner = self._owner()
        registry = _registry(["file.save"])
        builder = MenuBuilder(registry, owner=owner)
        builder.build_menubar(definition.menubar, owner)
        builder.build_toolbar(definition.menubar, owner)
        # Eine QAction pro Command - dieselbe Instanz in beiden Oberflaechen.
        assert isinstance(registry.get("file.save").action, QAction)
        menu = builder.build_menubar(definition.menubar, owner).findChild(QMenu, "menu.file")
        assert menu is not None
        assert menu.actions()[0] is registry.get("file.save").action

    def test_toolbar_only_includes_toolbar_surface(self, qapp: QApplication) -> None:
        definition = _defn([
            MenuNode(id="menu.file", type="menu", title="Datei", children=[
                MenuNode(id="a.tb", type="action", command="c.tb", title="Auf Toolbar",
                         surfaces=["menu", "toolbar"]),
                MenuNode(id="a.menuonly", type="action", command="c.menu", title="Nur Menue",
                         surfaces=["menu"]),
            ]),
        ])
        owner = self._owner()
        builder = MenuBuilder(_registry(["c.tb", "c.menu"]), owner=owner)
        toolbar = builder.build_toolbar(definition.menubar, owner)
        texts = [a.text() for a in toolbar.actions() if not a.isSeparator()]
        assert texts == ["Auf Toolbar"]

    def test_group_actions_are_exclusive_and_checkable(self, qapp: QApplication) -> None:
        definition = _defn([
            MenuNode(id="menu.v", type="menu", title="Ansicht", children=[
                MenuNode(id="grp", type="group", children=[
                    MenuNode(id="a.l", type="action", command="v.l", title="Liste",
                             checkable=True, checked=True, group="views"),
                    MenuNode(id="a.c", type="action", command="v.c", title="Kalender",
                             checkable=True, group="views"),
                ]),
            ]),
        ])
        owner = self._owner()
        registry = _registry(["v.l", "v.c"])
        builder = MenuBuilder(registry, owner=owner)
        builder.build_menubar(definition.menubar, owner)
        act_l = registry.get("v.l").action
        act_c = registry.get("v.c").action
        assert act_l is not None and act_l.isCheckable()
        assert act_l.actionGroup() is act_c.actionGroup()
        assert act_l.actionGroup().isExclusive()

    def test_permission_drops_subtree(self, qapp: QApplication) -> None:
        definition = _defn([
            MenuNode(id="menu.admin", type="menu", title="Admin", permission="is.admin",
                     children=[
                         MenuNode(id="a.x", type="action", command="c.x", title="X"),
                     ]),
        ])
        owner = self._owner()
        builder = MenuBuilder(_registry(["c.x"]), owner=owner, has_permission=lambda _p: False)
        bar = builder.build_menubar(definition.menubar, owner)
        assert bar.findChild(QMenu, "menu.admin") is None


class TestRealAppMenu:
    def test_every_menu_command_is_registered(self, qapp: QApplication) -> None:
        """Die echte menu.json und die MainWindow-Registry sind deckungsgleich."""
        window = MainWindow(Settings(), Mode.DARK)
        assert missing_commands(window._menu_definition, window._commands.ids()) == set()

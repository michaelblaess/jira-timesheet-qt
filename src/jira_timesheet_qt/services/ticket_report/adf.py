"""Atlassian Document Format (ADF) nach Plaintext.

Jira Cloud liefert Beschreibung und Kommentare als verschachteltes JSON, nicht
als Text. Diese Funktionen ziehen daraus lesbaren Fliesstext, damit der Inhalt
im Terminal und im Kontext eines LLM ankommt.
"""

from __future__ import annotations

import re
from typing import Any

# Blockelemente, nach denen ein Zeilenumbruch gehoert.
_BLOCK_TYPES = frozenset(
    {"paragraph", "heading", "listItem", "codeBlock", "blockquote", "rule", "panel", "tableRow"}
)
_LIST_TYPES = frozenset({"bulletList", "orderedList", "table"})


def to_text(node: Any) -> str:
    """Wandelt einen ADF-Knoten rekursiv in Plaintext.

    Args:
        node:
            ADF-Dokument, Teilbaum oder None.

    Returns:
        Plaintext mit Zeilenumbruechen an Blockgrenzen.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node

    node_type = node.get("type")
    attrs = node.get("attrs") or {}

    if node_type == "text":
        return str(node.get("text", ""))
    if node_type == "hardBreak":
        return "\n"
    if node_type == "mention":
        return "@" + str(attrs.get("text", "")).lstrip("@")
    if node_type == "emoji":
        return str(attrs.get("shortName", ""))
    if node_type in ("inlineCard", "blockCard"):
        return str(attrs.get("url", ""))
    if node_type == "media":
        # Bild/Datei - der eigentliche Inhalt steckt im Anhang.
        return f"[Bild: {attrs.get('id', 'unbekannt')}]"
    if node_type == "rule":
        return "\n---\n"

    parts = [to_text(child) for child in (node.get("content") or [])]
    text = "".join(parts)

    if node_type in _BLOCK_TYPES or node_type in _LIST_TYPES:
        text += "\n"

    return text


def clean(text: str) -> str:
    """Kollabiert Leerzeilenwueste, die beim ADF-Flatten entsteht."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def field_to_text(value: Any) -> str:
    """Rendert ein beliebiges Jira-Feld als Text.

    Deckt die drei Formen ab, in denen Felder ankommen: ADF-Dokument,
    Objekt mit Anzeigenamen (Status, User, Prioritaet) und Liste davon.
    """
    if value is None:
        return "-"
    if isinstance(value, dict):
        if "content" in value or value.get("type") == "doc":
            return clean(to_text(value))
        for key in ("displayName", "name", "value"):
            if key in value:
                return str(value[key])
        return str(value)
    if isinstance(value, list):
        rendered = [field_to_text(item) for item in value]
        return ", ".join(part for part in rendered if part and part != "-") or "-"
    return str(value)

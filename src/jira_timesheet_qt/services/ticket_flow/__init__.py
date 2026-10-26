"""Ticketfluss: wer wem Tickets gibt, als Stern um eine Person.

Oberflaechenfrei - die Qt-Schicht folgt in ui/ticket_flow_*.
Plan und Entscheidungen in PLAN-ticketfluss.md.
"""

from __future__ import annotations

from .edges import DEFAULT_CONTACTS, DEFAULT_SPOKES, FlowData, build_star, extract_flow, ticket_edges, top_contacts
from .loader import CHANGELOG_CHUNK, CHANGELOG_CONCURRENCY, FlowLoad, FlowSource, HistoryStore, load_flow
from .models import EDGE_HANDOVER, EDGE_KINDS, EDGE_ORDER, FlowEdge, FlowStar, Person, Spoke
from .period import (
    DEFAULT_FLOW_PERIOD,
    FLOW_1M,
    FLOW_3M,
    FLOW_12M,
    FLOW_ALL,
    FLOW_PERIODS,
    FLOW_YTD,
    flow_since,
)
from .queries import FLOW_FIELDS, flow_jqls

__all__ = [
    "CHANGELOG_CHUNK",
    "CHANGELOG_CONCURRENCY",
    "DEFAULT_FLOW_PERIOD",
    "DEFAULT_CONTACTS",
    "DEFAULT_SPOKES",
    "EDGE_HANDOVER",
    "EDGE_KINDS",
    "EDGE_ORDER",
    "FLOW_12M",
    "FLOW_1M",
    "FLOW_3M",
    "FLOW_ALL",
    "FLOW_FIELDS",
    "FLOW_PERIODS",
    "FLOW_YTD",
    "FlowData",
    "FlowEdge",
    "FlowLoad",
    "FlowSource",
    "FlowStar",
    "HistoryStore",
    "Person",
    "Spoke",
    "build_star",
    "extract_flow",
    "flow_jqls",
    "flow_since",
    "load_flow",
    "ticket_edges",
    "top_contacts",
]

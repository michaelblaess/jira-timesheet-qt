"""Ticket-Ansichten "Meine Tickets" und "Relevante Tickets".

Der Kern ist bewusst abhaengigkeitsfrei (reine Standardbibliothek) und kennt
keinen Jira-Client: die aufrufende Anwendung holt die Antworten der API
selbst und reicht sie herein. So laesst sich derselbe Code in der
Textual-Oberflaeche, in der Qt-Oberflaeche und im Terminal verwenden.

Typischer Ablauf:

    from jira_timesheet_qt.services.ticket_board import (
        BoardConfig, assigned_jql, build_board, pending_worklog_keys,
    )

    issues = client.search(assigned_jql())          # Grundladung, eine Abfrage
    board = build_board(issues, config, account_id=me, browse_base=host)

    keys = pending_worklog_keys(board, config)      # nur die Auffaelligen
    worklogs = {k: client.worklog_info(k) for k in keys}
    board = build_board(issues, config, account_id=me, browse_base=host,
                        worklogs=worklogs)          # jetzt mit Pile of Shame

Der zweite Durchgang ist bewusst getrennt: Worklogs kosten einen Abruf je
Ticket, und ohne sie laesst sich die Pile-of-Shame-Bedingung nicht pruefen.
Dann bleibt der Marker ungesetzt, statt geraten zu werden.
"""

from __future__ import annotations

from .config import (
    BLOCKER_PHRASES,
    DEFAULT_PRIORITIES,
    DEFAULT_STALE_DAYS,
    DEFAULT_THRESHOLDS,
    DEFAULT_WINDOW_DAYS,
    GROUP_ORDER,
    BoardConfig,
)
from .models import Board, Group, Marker, Role, Ticket, WorklogInfo
from .queries import (
    FIELDS,
    STATS_FIELDS,
    AccountIdError,
    assigned_jql,
    check_account_id,
    closing_jql,
    history_jql,
    relevant_jql,
)
from .rules import (
    build_board,
    is_blocked,
    markers_for,
    parse_ts,
    pending_worklog_keys,
    sort_tickets,
    to_ticket,
    workdays_between,
)
from .stats import FOOTNOTE, AgeBucket, MonthValue, Statistics, build_statistics

__all__ = [
    "BLOCKER_PHRASES",
    "DEFAULT_PRIORITIES",
    "DEFAULT_STALE_DAYS",
    "DEFAULT_THRESHOLDS",
    "DEFAULT_WINDOW_DAYS",
    "FIELDS",
    "FOOTNOTE",
    "GROUP_ORDER",
    "STATS_FIELDS",
    "AccountIdError",
    "AgeBucket",
    "Board",
    "BoardConfig",
    "Group",
    "Marker",
    "MonthValue",
    "Role",
    "Statistics",
    "Ticket",
    "WorklogInfo",
    "assigned_jql",
    "build_board",
    "build_statistics",
    "check_account_id",
    "closing_jql",
    "history_jql",
    "is_blocked",
    "markers_for",
    "parse_ts",
    "pending_worklog_keys",
    "relevant_jql",
    "sort_tickets",
    "to_ticket",
    "workdays_between",
]

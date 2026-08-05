"""Abruf der Ticket-Ansichten in einem Hintergrund-Thread.

Wie beim Stundenzettel: QThread mit eigener asyncio-Schleife, keine
Widget-Zugriffe, Ergebnisse ausschliesslich ueber Signale.

Hier laeuft die Verdrahtung zwischen Client und Kern. Der Client kennt die
Auswertung nicht, der Kern kennt keinen Client - dieser Faden bringt beide
zusammen. Das ist die einzige Stelle, die beide Seiten sieht.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Sequence

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.ticket_board import (
    DEFAULT_PRIORITIES,
    FIELDS,
    AccountIdError,
    Board,
    BoardConfig,
    Role,
    WorklogInfo,
    assigned_jql,
    build_board,
    closing_jql,
    parse_ts,
    pending_worklog_keys,
    relevant_jql,
)

# Die beiden Ansichten. Der Wert wandert unveraendert in die Einstellungen,
# deshalb sind es Zeichenketten und keine Aufzaehlung.
MODE_ASSIGNED = "assigned"
MODE_RELEVANT = "relevant"


def config_from(settings: Settings) -> BoardConfig:
    """Baut die Kern-Konfiguration aus den Benutzereinstellungen.

    Diese Uebersetzung liegt bewusst in der Oberflaechen-Schicht: der Kern
    soll die Einstellungen nicht kennen, und die Einstellungen nicht den
    Kern. Der Verdrahtungspunkt gehoert dorthin, wo ohnehin beide Seiten
    zusammenkommen.

    Args:
        settings:
            Die geladenen Benutzereinstellungen.

    Returns:
        Die Konfiguration fuer den Kern. Nicht gesetzte Schwellen (0) fehlen
        im Ergebnis - diese Rolle erzeugt dann keinen Pile of Shame.
    """
    thresholds: dict[Role, float] = {}
    for role, value in (
        (Role.ACTIVE, settings.board_threshold_active),
        (Role.ACCEPTANCE, settings.board_threshold_acceptance),
        (Role.CLOSING, settings.board_threshold_closing),
    ):
        if value > 0:
            thresholds[role] = float(value)

    return BoardConfig(
        active_status=tuple(settings.board_active_status),
        backlog_status=tuple(settings.board_backlog_status),
        handback_status=tuple(settings.board_handback_status),
        acceptance_status=tuple(settings.board_acceptance_status),
        closing_status=tuple(settings.board_closing_status),
        priorities=(
            tuple(settings.board_priorities)
            if settings.board_priorities
            else DEFAULT_PRIORITIES
        ),
        stale_days=settings.board_stale_days,
        window_days=settings.board_window_days,
        thresholds=thresholds,
    )


class TicketBoardWorker(QThread):
    """Holt eine Ticket-Ansicht und baut sie ueber den Kern auf."""

    finished_ok = Signal(object)
    failed = Signal(str)
    # Zwei Kanaele, bewusst getrennt: die Statuszeile hat Platz fuer einen
    # kurzen Satz, das Meldungsfenster fuer alles. Die JQL-Ausdruecke gehoeren
    # ins Meldungsfenster - dort kann man sie zum Nachvollziehen kopieren, in
    # der Statuszeile schoben sie nur alles andere weg.
    progress = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        config: BoardConfig,
        mode: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._config = config
        self._mode = mode

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            board = asyncio.run(self._fetch())
        except AccountIdError:
            # Ohne eigene Kennung sind die Quellen "bearbeitet" und
            # "erwaehnt" nicht abfragbar. Das betrifft nur den Legacy-Modus.
            self.failed.emit(
                "Die Ansicht braucht die eigene Benutzerkennung. "
                "Im Legacy-Modus (Data Center) steht sie nicht zur Verfügung."
            )
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(board)

    def _jqls(self, account_id: str) -> Sequence[str]:
        """Baut die Ausdruecke der gewaehlten Ansicht.

        Args:
            account_id:
                Die eigene Kennung, erst innerhalb der Sitzung bekannt.

        Returns:
            Die auszufuehrenden JQL-Ausdruecke.
        """
        if self._mode == MODE_RELEVANT:
            return [relevant_jql(account_id, self._config.window_days)]
        # Die Abschluss-Status fallen durch "statusCategory != Done" hindurch
        # und brauchen deshalb eine zweite Abfrage.
        return [assigned_jql(), closing_jql(self._config.closing_status)]

    def _phase(self, text: str) -> None:
        """Meldet einen Zwischenstand in beide Kanaele.

        Die eigenen Phasentexte sind kurz genug fuer die Statuszeile und
        gehoeren zugleich in den Verlauf.

        Args:
            text:
                Der Zwischenstand.
        """
        self.progress.emit(text)
        self.log.emit(text)

    async def _fetch(self) -> Board:
        """Holt die Rohantworten und baut daraus die Ansicht."""
        settings = self._settings
        self._phase("Verbinde mit Jira ...")

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            # Der Client meldet ausfuehrlich, inklusive der Ausdruecke.
            on_log=self.log.emit,
        )

        account_id, issues = await client.fetch_issues(self._jqls, FIELDS)
        now = dt.datetime.now(dt.UTC)
        board = build_board(
            issues,
            self._config,
            now,
            account_id=account_id,
            browse_base=settings.jira_host,
        )
        self._phase(f"{board.count} Tickets aufbereitet")

        if self._mode != MODE_ASSIGNED:
            # Fremde Tickets gehoeren nicht in den eigenen Pile of Shame -
            # der zweite, teure Durchgang entfaellt.
            return board

        keys = pending_worklog_keys(board, self._config)
        if not keys:
            return board

        self._phase(f"Buchungslage von {len(keys)} auffälligen Tickets wird geprüft ...")
        stats = await client.fetch_worklog_stats(keys)
        worklogs = {
            key: WorklogInfo(count=count, last=parse_ts(started))
            for key, (count, started) in stats.items()
        }
        return build_board(
            issues,
            self._config,
            now,
            account_id=account_id,
            browse_base=settings.jira_host,
            worklogs=worklogs,
        )

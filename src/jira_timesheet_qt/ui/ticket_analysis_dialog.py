"""Dialog "Ticket-Analyse".

Ablauf: Ticket-Key oder Jira-Link eingeben, Analyse laufen lassen, Bericht als
eine HTML-Datei speichern. Die Datei laeuft offline und laesst sich
weitergeben.

Der Abruf laeuft im Hintergrund-Faden (``TicketReportWorker``), damit die
Oberflaeche waehrenddessen bedienbar bleibt.
"""

from __future__ import annotations

import contextlib
import re
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jira_timesheet_qt.i18n import t
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.ticket_lifecycle import TicketLifecycleData
from jira_timesheet_qt.services.ticket_report import build_report, write_report
from jira_timesheet_qt.ui.jira_worker import TicketReportWorker

# Ticket-Keys lassen sich aus jedem Jira-Link ziehen - meist wird die volle
# URL aus dem Browser kopiert.
KEY_PATTERN = re.compile(r"([A-Z][A-Z0-9]+-\d+)")


def ticket_key(reference: str) -> str:
    """Zieht den Ticket-Key aus einem Key oder einer beliebigen Jira-URL.

    Args:
        reference:
            Key wie "ABC-123" oder ein Link darauf.

    Returns:
        Der erkannte Ticket-Key, oder ein leerer String.
    """
    match = KEY_PATTERN.search(reference.strip().upper())
    return match.group(1) if match else ""


class TicketAnalysisDialog(QDialog):
    """Fragt ein Ticket ab und schreibt den Bericht als HTML-Datei."""

    def __init__(
        self, settings: Settings, parent: QWidget | None = None, ticket: str = ""
    ) -> None:
        """Baut den Dialog.

        Args:
            settings:
                Zugangsdaten und zuletzt genutztes Zielverzeichnis.
            parent:
                Elternfenster.
            ticket:
                Vorbelegung des Eingabefelds, z.B. aus dem Kontextmenue.
        """
        super().__init__(parent)
        self._settings = settings
        self._worker: TicketReportWorker | None = None
        self._data: TicketLifecycleData | None = None

        self.setWindowTitle(t("ticket_report.title"))
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(t("ticket_report.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(t("ticket_report.field_label")))
        self._input = QLineEdit()
        self._input.setPlaceholderText(t("ticket_report.placeholder"))
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_start)
        row.addWidget(self._input, 1)
        layout.addLayout(row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)

        buttons = QDialogButtonBox()
        self._start_button = QPushButton(t("ticket_report.btn_analyse"))
        self._start_button.setDefault(True)
        self._start_button.setEnabled(False)
        self._start_button.clicked.connect(self._on_start)
        buttons.addButton(self._start_button, QDialogButtonBox.ButtonRole.AcceptRole)

        close_button = QPushButton(t("binding.close"))
        close_button.clicked.connect(self.reject)
        buttons.addButton(close_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

        # Erst ganz zum Schluss vorbelegen: setText loest textChanged aus, und
        # der Handler fasst den Knopf an - vor dessen Aufbau gaebe das einen
        # AttributeError.
        if ticket:
            self._input.setText(ticket)

    # -- Eingabe --------------------------------------------------------
    def _on_text_changed(self, text: str) -> None:
        """Schaltet den Knopf frei, sobald ein Key erkennbar ist."""
        key = ticket_key(text)
        self._start_button.setEnabled(bool(key))
        self._status.setText(t("ticket_report.recognised").format(ticket=key) if key else "")

    # -- Abruf ----------------------------------------------------------
    def _on_start(self) -> None:
        """Startet den Abruf im Hintergrund."""
        key = ticket_key(self._input.text())
        if not key:
            return
        if not self._settings.jira_host or not self._settings.jira_token:
            QMessageBox.warning(
                self,
                t("ticket_report.title"),
                t("ticket_report.settings_missing"),
            )
            return

        self._set_busy(True)
        self._status.setText(t("ticket_report.progress_fetch").format(ticket=key))

        worker = TicketReportWorker(self._settings, key, self)
        worker.progress.connect(self._status.setText)
        worker.log.connect(self._forward_log)
        worker.finished_ok.connect(self._on_data)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._set_busy(False))
        self._worker = worker
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        """Sperrt die Eingabe waehrend des Abrufs."""
        self._input.setEnabled(not busy)
        self._start_button.setEnabled(not busy and bool(ticket_key(self._input.text())))

    def _on_failed(self, message: str) -> None:
        """Zeigt einen Fehler aus dem Hintergrund-Faden."""
        self._status.setText("")
        QMessageBox.critical(self, t("ticket_report.title"), message)

    # -- Ergebnis -------------------------------------------------------
    def _forward_log(self, text: str) -> None:
        """Reicht ausfuehrliche Meldungen ans Meldungsfenster weiter.

        Der Dialog hat nur eine einzeilige Anzeige. Die JQL-Ausdruecke des
        Clients gehoeren in den Verlauf des Hauptfensters, wo man sie zum
        Nachvollziehen kopieren kann.

        Args:
            text:
                Die Meldung.
        """
        writer = getattr(self.parent(), "log_message", None)
        if callable(writer):
            writer(text)

    def _on_data(self, data: TicketLifecycleData) -> None:
        """Baut den Bericht und fragt nach dem Speicherort."""
        self._data = data
        key = data.key or ticket_key(self._input.text())
        self._status.setText(t("ticket_report.building").format(ticket=key))

        try:
            report = build_report(
                data.issue,
                data.changelog,
                data.comments,
                f"{self._settings.jira_host.rstrip('/')}/browse",
                titles=data.titles,
            )
        except Exception as exc:  # noqa: BLE001 - der Dialog darf nie mitsterben
            self._on_failed(f"{type(exc).__name__}: {exc}")
            return

        start_dir = self._settings.last_export_dir or str(Path.home() / "Desktop")
        suggested = str(Path(start_dir) / f"{report.key}.html")
        target, _filter = QFileDialog.getSaveFileName(
            self,
            t("ticket_report.save_title"),
            suggested,
            t("ticket_report.filter_html"),
        )
        if not target:
            self._status.setText(t("ticket_report.cancelled"))
            return

        path = write_report(report, target)
        self._settings.last_export_dir = str(path.parent)
        self._settings.save()
        self._status.setText(t("ticket_report.written").format(path=path))
        # Der Bericht ist zum Ansehen da - also gleich aufmachen.
        with contextlib.suppress(Exception):
            webbrowser.open(path.resolve().as_uri())

        QMessageBox.information(
            self,
            t("ticket_report.title"),
            t("ticket_report.done").format(ticket=report.key, path=path),
        )
        self.accept()

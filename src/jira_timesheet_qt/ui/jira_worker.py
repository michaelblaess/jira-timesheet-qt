"""Abruf der Worklogs in einem Hintergrund-Thread.

Entscheidung E2 des Plans: QThread statt qasync. Der Client ist zwar async,
aber es geht um wenige Netzwerkaufrufe pro Abruf - dafuer reicht ein
Arbeitsfaden, der eine eigene asyncio-Schleife oeffnet. Das spart ein
zusaetzliches Paket und haelt die Qt-Ereignisschleife unberuehrt.

Der Faden darf keine Widgets anfassen. Ergebnisse gehen ausschliesslich ueber
Signale zurueck, die Qt in den Hauptfaden zustellt.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime

from PySide6.QtCore import QObject, QThread, Signal

from jira_timesheet_qt.i18n import t
from jira_timesheet_qt.models.settings import Settings
from jira_timesheet_qt.models.ticket_lifecycle import TicketLifecycleData
from jira_timesheet_qt.models.timesheet import Timesheet
from jira_timesheet_qt.services.jira_client import JiraClient, JiraClientError
from jira_timesheet_qt.services.manual_entry_service import ManualEntryService
from jira_timesheet_qt.services.ssl_support import TlsSettings, tls_from_settings
from jira_timesheet_qt.services.ticket_preview import (
    BASE_FIELDS,
    IssuePreviewCache,
    TicketPreviewData,
    field_value_text,
    image_sources,
    parse_issue,
    resolve_field_ids,
    rewrite_images,
    seconds_value,
)
from jira_timesheet_qt.services.ticket_report import lifecycle
from jira_timesheet_qt.services.timesheet_service import TimesheetService


class WorklogWorker(QThread):
    """Holt die Worklogs eines Zeitraums und baut den Stundenzettel."""

    finished_ok = Signal(object)
    failed = Signal(str)
    # Kurzer Stand fuer die Statuszeile, ausfuehrliches fuer das
    # Meldungsfenster. Ohne die Trennung landet ein JQL-Ausdruck in der
    # Statuszeile und schiebt alles andere weg.
    progress = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        date_from: date,
        date_to: date,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._from = date_from
        self._to = date_to

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            timesheet = asyncio.run(self._fetch())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(timesheet)

    async def _fetch(self) -> Timesheet:
        """Holt die Eintraege und mischt die manuell erfassten Zeiten dazu."""
        settings = self._settings
        self.progress.emit("Verbinde mit Jira ...")

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            budget_field=settings.budget_field,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            tls=tls_from_settings(settings),
            on_log=self.log.emit,
        )
        entries = await client.get_worklogs(self._from, self._to)
        self.progress.emit(f"{len(entries)} Einträge aus Jira erhalten")

        manual = ManualEntryService().worklogs_between(self._from, self._to, author=settings.email)
        if manual:
            entries = [*entries, *manual]
            self.progress.emit(f"{len(manual)} manuell erfasste Einträge ergänzt")

        return TimesheetService.build_timesheet(
            entries=entries,
            developer=settings.email or "Unbekannt",
            email=settings.email,
            date_from=self._from,
            date_to=self._to,
        )


class TicketReportWorker(QThread):
    """Holt die Rohdaten eines Tickets fuer die Ticket-Analyse.

    Der Abruf dauert je nach Ticketgroesse ein bis mehrere Sekunden - er
    gehoert deshalb wie der Worklog-Abruf in einen eigenen Faden.
    """

    finished_ok = Signal(object)
    failed = Signal(str)
    # Kurzer Stand fuer die Statuszeile, ausfuehrliches fuer das
    # Meldungsfenster. Ohne die Trennung landet ein JQL-Ausdruck in der
    # Statuszeile und schiebt alles andere weg.
    progress = Signal(str)
    log = Signal(str)

    def __init__(self, settings: Settings, key: str, parent: QObject | None = None) -> None:
        """Merkt sich Zugang und Ticket.

        Args:
            settings:
                Zugangsdaten aus den Einstellungen.
            key:
                Ticket-Key, z.B. "ABC-123".
            parent:
                Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._key = key

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            data = asyncio.run(self._fetch())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished_ok.emit(data)

    async def _fetch(self) -> TicketLifecycleData:
        """Holt Issue, Aenderungsprotokoll und Kommentare."""
        settings = self._settings
        self.progress.emit(t("ticket_report.progress_fetch").format(ticket=self._key))

        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            tls=tls_from_settings(settings),
            on_log=self.log.emit,
        )
        daten = await client.get_ticket_lifecycle(self._key)

        # Titel der nur im Text erwaehnten Tickets nachreichen - ein Aufruf
        # fuer alle, damit die Karten im Bericht nicht nur den Key zeigen.
        leben = lifecycle.from_raw(daten.issue, daten.changelog, daten.comments)
        offen = [key for key in leben.mentioned if key not in leben.titles]
        if offen:
            daten.titles = await client.get_ticket_summaries(offen)
        return daten


class BudgetFieldWorker(QThread):
    """Ermittelt das Budget-Custom-Field ueber die Jira-Cloud-API.

    Laeuft im Hintergrund, damit der Einstellungsdialog waehrend des einen
    Netzwerkaufrufs nicht einfriert. Ergebnis ist eine Liste von
    (field_id, field_name)-Tupeln - leer, wenn kein Feld passt.
    """

    found = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        host: str,
        email: str,
        token: str,
        proxy: str = "",
        tls: TlsSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._email = email
        self._token = token
        self._proxy = proxy
        # Auch die Autoerkennung geht ueber TLS. Ohne die Angaben liefe sie
        # hinter einem Firmenproxy in einen Zertifikatsfehler, waehrend der
        # eigentliche Abruf laeuft - und niemand verstuende warum.
        self._tls = tls or TlsSettings()

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            matches = asyncio.run(self._detect())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - jede Netz-/Parse-Panne gemeldet, nie stiller Tod
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.found.emit(matches)

    async def _detect(self) -> list[tuple[str, str]]:
        """Fragt die Custom-Fields ab (Cloud-Modus, Autoerkennung nur dort)."""
        client = JiraClient(
            host=self._host,
            email=self._email,
            token=self._token,
            legacy=False,
            proxy=self._proxy,
            tls=self._tls,
        )
        return await client.detect_budget_field("budget")


class TicketPreviewWorker(QThread):
    """Holt ein Ticket fuer die Vorschau im Stundenzettel.

    Mit gemerktem Stand fragt der Faden zuerst nur updated und die gebuchte
    Zeit ab. Sind beide unveraendert, meldet er unchanged und spart den vollen
    Abruf samt HTML. Die gebuchte Zeit steht dabei ausdruecklich mit drin -
    ohne Beleg, dass eine neue Buchung auch updated aendert, verlassen wir uns
    nicht darauf. Das Ergebnis schreibt der Faden selbst in den Cache, damit
    die Oberflaeche keine Datei anfasst.
    """

    finished_ok = Signal(object)
    unchanged = Signal(str)
    failed = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        settings: Settings,
        key: str,
        cache: IssuePreviewCache,
        cached: TicketPreviewData | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Merkt sich Zugang, Ticket und Cache.

        Args:
            settings:
                Zugangsdaten und die Namen der Zusatzfelder.
            key:
                Ticket-Key, z.B. "ABC-123".
            cache:
                Der Cache des aktuellen Jira-Hosts.
            cached:
                Der gemerkte Stand, oder None fuer einen vollen Abruf.
            parent:
                Qt-Elternobjekt.
        """
        super().__init__(parent)
        self._settings = settings
        self._key = key
        self._cache = cache
        self._cached = cached

    def run(self) -> None:
        """Laeuft im Hintergrund-Thread."""
        try:
            data = asyncio.run(self._fetch())
        except JiraClientError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - der Faden darf nie unbemerkt sterben
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            if data is None:
                self.unchanged.emit(self._key)
            else:
                self.finished_ok.emit(data)

    async def _fetch(self) -> TicketPreviewData | None:
        """Prueft den Stand, holt bei Bedarf das Ticket und merkt es sich."""
        settings = self._settings
        client = JiraClient(
            host=settings.jira_host,
            email=settings.email,
            token=settings.jira_token,
            legacy=settings.use_legacy_api,
            proxy=settings.proxy_url,
            tls=tls_from_settings(settings),
            on_log=self.log.emit,
        )
        if self._cached is not None:
            stand = (await client.get_issue(self._key, ["updated", "timespent"])).get("fields") or {}
            if (
                field_value_text(stand.get("updated")) == self._cached.updated
                and seconds_value(stand.get("timespent")) == self._cached.time_spent_seconds
            ):
                return None

        names = list(settings.preview_extra_fields)
        ids = self._cache.load_field_ids(names) if names else {}
        if ids is None:
            ids = resolve_field_ids(await client.get_fields(), names)
            self._cache.save_field_ids(names, ids)
            fehlend = [name for name in names if name not in ids]
            if fehlend:
                self.log.emit(f"Vorschau: diese Felder kennt Jira nicht: {', '.join(fehlend)}")

        raw = await client.get_issue(self._key, [*BASE_FIELDS, *ids.values()], rendered=True)
        data = parse_issue(raw, ids, datetime.now())
        data = await self._load_images(client, data)
        self._cache.save(data)
        return data

    async def _load_images(self, client: JiraClient, data: TicketPreviewData) -> TicketPreviewData:
        """Holt die Bilder der Beschreibung in den Cache und setzt die Adressen um.

        Die Anhaenge brauchen eine Anmeldung, QTextBrowser laedt sie deshalb
        nie selbst. Ein Bild, das nicht kommt, kostet nur sich selbst: es
        wird zu einem kurzen Hinweis statt eines kaputten Symbols.
        """
        quellen = image_sources(data.description_html, self._settings.jira_host)
        lokal: dict[str, str] = {}
        grenze = asyncio.Semaphore(4)

        async def holen(src: str) -> None:
            async with grenze:
                try:
                    inhalt, typ = await client.get_attachment(src)
                except Exception as exc:  # noqa: BLE001 - ein fehlendes Bild bricht die Vorschau nicht ab
                    self.log.emit(f"Vorschau {data.key}: ein Bild wurde nicht geladen ({type(exc).__name__})")
                    return
                name = self._cache.save_image(data.key, src, inhalt, typ)
                if name is not None:
                    lokal[src] = name

        await asyncio.gather(*(holen(src) for src in quellen))
        return replace(data, description_html=rewrite_images(data.description_html, lokal), images=lokal)

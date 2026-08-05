"""Jira REST API Client fuer Worklog-Abfragen.

Unterstuetzt zwei Modi:
- Cloud (Default): REST v3, Basic-Auth (Mail + API-Token), native JQL
  (worklogAuthor/worklogDate), nextPageToken-Pagination, Matching ueber accountId.
- Data Center / Server (Legacy): REST v2, Bearer-PAT, ScriptRunner-JQL
  (issueFunction in workLogged), Matching ueber author.name.
Der Modus wird ueber das Flag ``legacy`` gewaehlt.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from jira_timesheet_qt.i18n import t
from jira_timesheet_qt.models.ticket_lifecycle import TicketLifecycleData
from jira_timesheet_qt.models.timesheet import WorklogEntry

logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    """Fehler bei der Jira-Kommunikation."""


class JiraClient:
    """Async Client fuer die Jira REST API (Cloud v3 oder Data Center v2)."""

    def __init__(
        self,
        host: str,
        email: str,
        token: str,
        budget_field: str = "",
        legacy: bool = False,
        proxy: str = "",
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        """Initialisiert den Client.

        Args:
            host:
                Basis-URL der Jira-Instanz (Cloud: https://xxx.atlassian.net).
            email:
                Cloud-Modus: Atlassian-Login-Mail fuer Basic-Auth.
                Legacy-Modus: Benutzername, nach dem die Worklogs gefiltert werden.
            token:
                Cloud-Modus: API-Token (id.atlassian.com). Legacy-Modus: PAT.
            budget_field:
                Custom-Field-ID des Budget-Felds.
            legacy:
                True = alte Data-Center-Methode (v2, Bearer, issueFunction).
            proxy:
                Optionale Proxy-URL (z.B. Corporate-Proxy,
                "http://host:port"). Leer = kein expliziter Proxy; httpx
                liest dann weiterhin HTTP(S)_PROXY aus der Umgebung.
            on_log:
                Optionaler Callback fuer Log-Ausgaben.
        """
        self._host = host.rstrip("/")
        self._email = email
        self._token = token
        self._budget_field = budget_field
        self._legacy = legacy
        self._proxy = proxy.strip()
        self._log = on_log or (lambda _: None)
        # Cloud-Modus: accountId des angemeldeten Benutzers (fuer Matching).
        self._account_id = ""

    async def get_worklogs(
        self,
        date_from: date,
        date_to: date,
    ) -> list[WorklogEntry]:
        """Holt alle Worklogs des Benutzers in einem Zeitraum.

        Args:
            date_from:
                Erster Tag des Zeitraums (inklusive).
            date_to:
                Letzter Tag des Zeitraums (inklusive).

        Returns:
            Liste der Worklog-Eintraege, sortiert nach Datum und Ticket.
        """
        fields = (
            "worklog,summary,status,issuetype,components,labels,priority,"
            "resolution,assignee,created,updated,timespent"
        )
        # Das Budget-Feld nur anfordern, wenn eine Custom-Field-ID gesetzt ist -
        # ein leerer Wert wuerde die Feldliste mit einem Komma abschliessen.
        if self._budget_field:
            fields = f"{fields},{self._budget_field}"

        if self._legacy:
            # Data Center: ScriptRunner-Funktion, sucht ab (date_from - 1 Tag).
            search_from = date_from - timedelta(days=1)
            jql = f'issueFunction in workLogged("after {search_from:%Y/%m/%d} by {self._email}")'
        else:
            # Cloud: native JQL ueber den angemeldeten Benutzer.
            jql = (
                f'worklogAuthor = currentUser() '
                f'AND worklogDate >= "{date_from:%Y-%m-%d}" '
                f'AND worklogDate <= "{date_to:%Y-%m-%d}"'
            )

        self._log(t("jira.jql", jql=jql))
        self._log(t("jira.connecting", host=self._host))

        entries: list[WorklogEntry] = []

        # Basic-Auth nur im Cloud-Modus ueber httpx; Legacy nutzt Bearer-Header.
        auth = None if self._legacy else (self._email, self._token)

        async with httpx.AsyncClient(
            verify=False,
            timeout=60.0,
            follow_redirects=True,
            auth=auth,
            proxy=self._proxy or None,
        ) as client:
            if not self._legacy:
                self._account_id = await self._fetch_account_id(client)

            issues = await self._search_issues(client, jql, fields)
            self._log(t("jira.issues_found", count=len(issues)))

            for issue in issues:
                issue_entries = await self._extract_worklogs(
                    client,
                    issue,
                    date_from,
                    date_to,
                )
                entries.extend(issue_entries)

        self._log(t("jira.worklogs_found", count=len(entries)))
        entries.sort(key=lambda e: (e.date, e.ticket))
        return entries

    async def get_ticket_lifecycle(self, key: str) -> TicketLifecycleData:
        """Holt Issue, Aenderungsprotokoll und Kommentare eines Tickets.

        Grundlage der Ticket-Analyse. Das Aenderungsprotokoll kommt ueber den
        eigenen, blaetterbaren Endpunkt - verlaesslicher als expand=changelog
        am Issue, das bei langen Historien abschneidet.

        Args:
            key:
                Ticket-Key, z.B. "ABC-123".

        Returns:
            Die drei Rohantworten der API.
        """
        version = "2" if self._legacy else "3"
        base = f"{self._host}/rest/api/{version}/issue/{key}"

        async with httpx.AsyncClient(
            verify=False,
            timeout=60.0,
            follow_redirects=True,
            auth=None if self._legacy else (self._email, self._token),
            proxy=self._proxy or None,
        ) as client:
            response = await client.get(base, headers=self._headers())
            self._check_response(response, base)
            issue: dict[str, Any] = response.json()

            changelog: list[dict[str, Any]] = []
            start = 0
            while True:
                url = f"{base}/changelog"
                params = {"startAt": start, "maxResults": 100}
                response = await client.get(url, params=params, headers=self._headers())
                self._check_response(response, url)
                page = response.json()
                values: list[dict[str, Any]] = page.get("values", [])
                changelog += values
                if page.get("isLast", True) or not values:
                    break
                start += len(values)

            url = f"{base}/comment"
            params = {"maxResults": 200}
            response = await client.get(url, params=params, headers=self._headers())
            self._check_response(response, url)
            comments: list[dict[str, Any]] = response.json().get("comments", [])

        self._log(
            f"{key}: {len(changelog)} Änderungen, {len(comments)} Kommentare gelesen"
        )
        return TicketLifecycleData(issue=issue, changelog=changelog, comments=comments)

    async def get_ticket_summaries(self, keys: list[str]) -> dict[str, str]:
        """Holt die Titel mehrerer Tickets in einem Aufruf.

        Fuer die im Kommentartext erwaehnten Tickets - Parent und echte
        Verknuepfungen bringen ihren Titel schon im Issue-JSON mit.

        Args:
            keys:
                Ticket-Keys, z.B. ["ABC-123", "ABC-456"].

        Returns:
            Zuordnung Key -> Titel. Nicht lesbare Tickets fehlen einfach.
        """
        if not keys:
            return {}

        version = "2" if self._legacy else "3"
        jql = "key in (" + ",".join(sorted(set(keys))) + ")"
        url = f"{self._host}/rest/api/{version}/search/jql"
        params = {"jql": jql, "fields": "summary", "maxResults": len(set(keys))}

        titles: dict[str, str] = {}
        try:
            async with httpx.AsyncClient(
                verify=False,
                timeout=30.0,
                follow_redirects=True,
                auth=None if self._legacy else (self._email, self._token),
                proxy=self._proxy or None,
            ) as client:
                response = await client.get(url, params=params, headers=self._headers())
                self._check_response(response, url)
                for issue in response.json().get("issues", []):
                    key = str(issue.get("key", ""))
                    summary = str((issue.get("fields") or {}).get("summary", ""))
                    if key and summary:
                        titles[key] = summary
        except Exception:  # noqa: BLE001 - Titel sind Beiwerk, kein Grund zum Abbruch
            return titles
        return titles

    async def detect_budget_field(self, keyword: str = "budget") -> list[tuple[str, str]]:
        """Sucht Cloud-Custom-Fields, deren Name das Keyword enthaelt.

        Ruft /rest/api/3/field ab und filtert auf Custom-Fields, deren Name
        das Keyword (case-insensitive) enthaelt. Nur im Cloud-Modus sinnvoll.

        Args:
            keyword:
                Suchbegriff im Feldnamen (Default "budget").

        Returns:
            Liste von (field_id, field_name)-Tupeln der Treffer.
        """
        url = f"{self._host}/rest/api/3/field"
        keyword_lower = keyword.lower()
        matches: list[tuple[str, str]] = []

        async with httpx.AsyncClient(
            verify=False,
            timeout=30.0,
            follow_redirects=True,
            auth=(self._email, self._token),
            proxy=self._proxy or None,
        ) as client:
            response = await client.get(url, headers=self._headers())
            self._check_response(response, url)
            fields = response.json()

        if not isinstance(fields, list):
            return matches

        for field in fields:
            if not isinstance(field, dict) or not field.get("custom", False):
                continue
            field_id = str(field.get("id", ""))
            field_name = str(field.get("name", ""))
            if field_id and keyword_lower in field_name.lower():
                matches.append((field_id, field_name))

        return matches

    async def fetch_issues(
        self,
        build_jqls: Callable[[str], Sequence[str]],
        fields: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Fuehrt mehrere JQL-Suchen in EINER Sitzung aus.

        Fuer die Ticket-Ansichten. Der Client bleibt dabei ohne Kenntnis der
        Auswertung: er liefert die Rohantworten, die Regeln liegen in
        services.ticket_board.

        Die Ausdruecke kommen ueber eine Fabrik statt als fertige Liste, weil
        manche von ihnen die eigene accountId brauchen - und die steht erst
        fest, wenn die Sitzung offen ist.

        Args:
            build_jqls:
                Bekommt die eigene accountId und liefert die auszufuehrenden
                Ausdruecke. Leere werden uebersprungen, damit eine nicht
                konfigurierte Abfrage nichts kaputt macht.
            fields:
                Kommaliste der angeforderten Felder.

        Returns:
            Die eigene accountId und alle gefundenen Issues. Doppelte
            Schluessel bleiben enthalten - das Zusammenfassen macht der Kern.
        """
        auth = None if self._legacy else (self._email, self._token)
        issues: list[dict[str, Any]] = []
        account_id = ""

        async with httpx.AsyncClient(
            verify=False,
            timeout=60.0,
            follow_redirects=True,
            auth=auth,
            proxy=self._proxy or None,
        ) as client:
            if not self._legacy:
                account_id = await self._fetch_account_id(client)
                self._account_id = account_id
            for jql in build_jqls(account_id):
                if not jql.strip():
                    continue
                self._log(t("jira.jql", jql=jql))
                issues.extend(await self._search_issues(client, jql, fields))

        self._log(t("jira.issues_found", count=len(issues)))
        return account_id, issues

    async def fetch_worklog_stats(self, keys: Sequence[str]) -> dict[str, tuple[int, str]]:
        """Holt Anzahl und juengsten Startzeitpunkt der Buchungen je Ticket.

        Kostet einen Abruf je Ticket - deshalb wird die Liste vom Kern
        vorgefiltert und enthaelt nur die bereits auffaelligen Tickets.

        Args:
            keys:
                Die Ticketschluessel.

        Returns:
            Je Schluessel ein Paar aus Anzahl und juengstem Startzeitpunkt
            als ISO-Zeichenkette. Leer, wenn nie gebucht wurde. Tickets,
            deren Abruf scheitert, fehlen im Ergebnis - dann bleibt der
            Pile-of-Shame-Marker ungesetzt statt geraten.
        """
        if not keys:
            return {}

        api = "2" if self._legacy else "3"
        auth = None if self._legacy else (self._email, self._token)
        result: dict[str, tuple[int, str]] = {}

        async with httpx.AsyncClient(
            verify=False,
            timeout=60.0,
            follow_redirects=True,
            auth=auth,
            proxy=self._proxy or None,
        ) as client:
            for key in keys:
                url = f"{self._host}/rest/api/{api}/issue/{key}/worklog"
                try:
                    response = await client.get(
                        url, headers=self._headers(), params={"maxResults": 1000}
                    )
                except httpx.HTTPError as exc:
                    logger.warning("Worklogs von %s nicht abrufbar: %s", key, exc)
                    continue
                if response.status_code != 200:
                    logger.warning("Worklogs von %s: HTTP %s", key, response.status_code)
                    continue
                logs = response.json().get("worklogs", [])
                started = sorted(str(w.get("started", "")) for w in logs if w.get("started"))
                result[key] = (len(logs), started[-1] if started else "")

        return result

    async def _fetch_account_id(self, client: httpx.AsyncClient) -> str:
        """Ermittelt die accountId des angemeldeten Benutzers (Cloud-Modus).

        Args:
            client:
                Der HTTP-Client mit konfigurierter Basic-Auth.

        Returns:
            Die accountId als String (oder leer, falls nicht ermittelbar).
        """
        url = f"{self._host}/rest/api/3/myself"
        response = await client.get(url, headers=self._headers())
        self._check_response(response, url)
        data = response.json()
        account_id: str = data.get("accountId", "")
        return account_id

    async def _search_issues(
        self,
        client: httpx.AsyncClient,
        jql: str,
        fields: str,
    ) -> list[dict[str, Any]]:
        """Fuehrt die JQL-Suche aus und gibt alle Issues zurueck.

        Cloud nutzt /search/jql mit nextPageToken-Pagination, Legacy den
        klassischen /search-Endpoint mit einer maxResults-Seite.

        Args:
            client:
                Der HTTP-Client.
            jql:
                Die JQL-Abfrage.
            fields:
                Komma-separierte Feldliste.

        Returns:
            Liste der gefundenen Issues (rohe Dicts).
        """
        if self._legacy:
            return await self._search_issues_legacy(client, jql, fields)
        return await self._search_issues_cloud(client, jql, fields)

    async def _search_issues_cloud(
        self,
        client: httpx.AsyncClient,
        jql: str,
        fields: str,
    ) -> list[dict[str, Any]]:
        """JQL-Suche ueber den Cloud-Endpoint /rest/api/3/search/jql.

        Args:
            client:
                Der HTTP-Client.
            jql:
                Die JQL-Abfrage.
            fields:
                Komma-separierte Feldliste.

        Returns:
            Liste aller Issues ueber alle Seiten hinweg.
        """
        url = f"{self._host}/rest/api/3/search/jql"
        issues: list[dict[str, Any]] = []
        next_token: str | None = None

        while True:
            params: dict[str, str | int] = {"jql": jql, "fields": fields, "maxResults": 100}
            if next_token:
                params["nextPageToken"] = next_token

            response = await client.get(url, params=params, headers=self._headers())
            self._check_response(response, url)

            data = response.json()
            page: list[dict[str, Any]] = data.get("issues", [])
            issues.extend(page)

            if data.get("isLast", True):
                break
            next_token = data.get("nextPageToken")
            if not next_token:
                break

        return issues

    async def _search_issues_legacy(
        self,
        client: httpx.AsyncClient,
        jql: str,
        fields: str,
    ) -> list[dict[str, Any]]:
        """JQL-Suche ueber den klassischen Endpoint /rest/api/2/search.

        Args:
            client:
                Der HTTP-Client.
            jql:
                Die JQL-Abfrage.
            fields:
                Komma-separierte Feldliste.

        Returns:
            Liste der gefundenen Issues (eine Seite, maxResults=200).
        """
        url = f"{self._host}/rest/api/2/search"
        params: dict[str, str | int] = {"jql": jql, "fields": fields, "maxResults": 200}

        response = await client.get(url, params=params, headers=self._headers())
        self._check_response(response, url)

        data = response.json()
        issues: list[dict[str, Any]] = data.get("issues", [])
        return issues

    async def _extract_worklogs(
        self,
        client: httpx.AsyncClient,
        issue: dict[str, Any],
        date_from: date,
        date_to: date,
    ) -> list[WorklogEntry]:
        """Extrahiert die eigenen Worklogs aus einem Issue.

        Args:
            client:
                Der HTTP-Client (fuer Nachladen bei Pagination).
            issue:
                Das rohe Issue-Dict aus der Suche.
            date_from:
                Erster Tag des Zeitraums (inklusive).
            date_to:
                Letzter Tag des Zeitraums (inklusive).

        Returns:
            Liste der eigenen Worklog-Eintraege dieses Issues im Zeitraum.
        """
        issue_key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")

        budget_data = fields.get(self._budget_field)
        if budget_data and isinstance(budget_data, dict):
            budget = budget_data.get("value", t("jira.budget_unassigned"))
        else:
            budget = t("jira.budget_unassigned")

        status_obj = fields.get("status", {})
        issue_status = status_obj.get("name", "") if isinstance(status_obj, dict) else ""

        type_obj = fields.get("issuetype", {})
        issue_type = type_obj.get("name", "") if isinstance(type_obj, dict) else ""

        priority_obj = fields.get("priority", {})
        issue_priority = priority_obj.get("name", "") if isinstance(priority_obj, dict) else ""

        comp_list = fields.get("components", [])
        issue_components = ", ".join(c.get("name", "") for c in comp_list if isinstance(c, dict))

        label_list = fields.get("labels", [])
        issue_labels = ", ".join(label_list) if isinstance(label_list, list) else ""

        resolution_obj = fields.get("resolution", {})
        issue_resolution = resolution_obj.get("name", "") if isinstance(resolution_obj, dict) else ""

        assignee_obj = fields.get("assignee", {})
        issue_assignee = assignee_obj.get("displayName", "") if isinstance(assignee_obj, dict) else ""

        issue_created = fields.get("created", "")[:16].replace("T", " ") if fields.get("created") else ""
        issue_updated = fields.get("updated", "")[:16].replace("T", " ") if fields.get("updated") else ""

        timespent_sec = fields.get("timespent", 0) or 0
        total_logged_h = timespent_sec / 3600.0
        issue_total_logged = f"{total_logged_h:.2f}h" if timespent_sec > 0 else ""

        worklog_node = fields.get("worklog", {})
        max_results = worklog_node.get("maxResults", 0)
        total = worklog_node.get("total", 0)

        if max_results < total:
            worklogs = await self._fetch_all_worklogs(client, issue_key)
        else:
            worklogs = worklog_node.get("worklogs", [])

        entries: list[WorklogEntry] = []

        for wl in worklogs:
            author = wl.get("author", {})

            started_str = wl.get("started", "")[:10]
            try:
                started = datetime.strptime(started_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if not self._worklog_is_mine(author):
                continue
            if started < date_from or started > date_to:
                continue

            seconds = wl.get("timeSpentSeconds", 0)
            hours = seconds / 3600.0

            entries.append(
                WorklogEntry(
                    date=started,
                    ticket=issue_key,
                    summary=summary,
                    author=self._author_display(author),
                    budget=budget,
                    hours=hours,
                    status=issue_status,
                    issuetype=issue_type,
                    epic="",
                    components=issue_components,
                    labels=issue_labels,
                    priority=issue_priority,
                    resolution=issue_resolution,
                    assignee=issue_assignee,
                    created=issue_created,
                    updated=issue_updated,
                    total_logged=issue_total_logged,
                )
            )

        return entries

    def _worklog_is_mine(self, author: dict[str, Any]) -> bool:
        """Prueft, ob ein Worklog-Author der eigene Benutzer ist.

        Cloud: Vergleich ueber accountId; Legacy: ueber author.name == email.

        Args:
            author:
                Das author-Dict eines Worklogs.

        Returns:
            True, wenn das Worklog dem eigenen Benutzer gehoert.
        """
        if self._legacy:
            return bool(author.get("name", "") == self._email)
        # Cloud: ueber accountId matchen (zuverlaessig, DSGVO-konform).
        if not self._account_id:
            return True
        return bool(author.get("accountId", "") == self._account_id)

    @staticmethod
    def _author_display(author: dict[str, Any]) -> str:
        """Liefert den Anzeigenamen eines Worklog-Authors.

        Args:
            author:
                Das author-Dict eines Worklogs.

        Returns:
            displayName, sonst name, sonst leerer String.
        """
        display: str = author.get("displayName", "") or author.get("name", "")
        return display

    async def _fetch_all_worklogs(
        self,
        client: httpx.AsyncClient,
        issue_key: str,
    ) -> list[dict[str, Any]]:
        """Holt alle Worklogs eines Issues (bei Pagination > maxResults).

        Args:
            client:
                Der HTTP-Client.
            issue_key:
                Der Issue-Key (z.B. PROJ-1234).

        Returns:
            Liste der Worklog-Dicts (leer bei Fehler).
        """
        api = "2" if self._legacy else "3"
        url = f"{self._host}/rest/api/{api}/issue/{issue_key}/worklog"
        response = await client.get(url, headers=self._headers())

        if response.status_code != 200:
            logger.warning("Worklog-Abruf fuer %s fehlgeschlagen", issue_key)
            self._log(t("jira.worklog_fetch_failed", issue=issue_key))
            for line in self._describe_error(response, url):
                self._log(line)
            return []

        data = response.json()
        worklogs: list[dict[str, Any]] = data.get("worklogs", [])
        return worklogs

    def _check_response(self, response: httpx.Response, url: str) -> None:
        """Prueft die Antwort und wirft bei Nicht-200 einen JiraClientError.

        Schreibt vorher die vollstaendigen Fehlerdetails (Status, Ziel-URL,
        Atlassian-Auth-Header und Antwort-Body) ins Log-Panel, damit die
        Ursache eines 401/403 sichtbar wird. Die geworfene Exception bleibt
        kompakt fuer die Toast-Meldung.

        Args:
            response:
                Die HTTP-Antwort von Jira.
            url:
                Die angefragte URL (fuer die Diagnose-Ausgabe).
        """
        if response.status_code == 200:
            return

        for line in self._describe_error(response, url):
            self._log(line)

        if response.status_code == 401:
            raise JiraClientError(t("jira.login_failed"))

        raise JiraClientError(t("jira.api_error", status=response.status_code))

    def _describe_error(self, response: httpx.Response, url: str) -> list[str]:
        """Baut detaillierte Diagnose-Zeilen aus einer Fehler-Antwort.

        Wertet die Atlassian-spezifischen Auth-Header aus (CAPTCHA-Challenge,
        Seraph-Login-Grund) und extrahiert die Jira-Fehlermeldung aus dem
        JSON-Body bzw. einen gekuerzten Auszug bei Nicht-JSON-Antworten
        (z.B. HTML-Seiten von Proxy/WAF/Login).

        Args:
            response:
                Die fehlerhafte HTTP-Antwort.
            url:
                Die angefragte URL.

        Returns:
            Liste von Log-Zeilen (eine pro Detail).
        """
        method = response.request.method if response.request else "GET"
        lines = [
            t(
                "jira.error_status",
                status=response.status_code,
                reason=response.reason_phrase or "",
            ).rstrip(),
            t("jira.error_url", method=method, url=url),
        ]

        # Atlassian sendet bei verweigerter Auth aussagekraeftige Header
        denied = response.headers.get("X-Authentication-Denied-Reason")
        if denied:
            lines.append(t("jira.error_denied", reason=denied))
        seraph = response.headers.get("X-Seraph-LoginReason")
        if seraph and seraph.upper() != "OK":
            lines.append(t("jira.error_seraph", reason=seraph))

        content_type = response.headers.get("content-type", "")
        if "html" in content_type.lower():
            lines.append(t("jira.error_html_hint"))

        body = self._extract_body_message(response, content_type)
        if body:
            lines.append(t("jira.error_body", body=body))

        return lines

    @staticmethod
    def _extract_body_message(response: httpx.Response, content_type: str) -> str:
        """Liest die aussagekraeftigste Fehlermeldung aus dem Antwort-Body.

        Bei JSON werden Jiras ``errorMessages``/``errors`` bevorzugt, sonst
        der serialisierte JSON-Auszug. Bei Nicht-JSON wird der Text auf eine
        Zeile normalisiert und gekuerzt.

        Args:
            response:
                Die HTTP-Antwort.
            content_type:
                Der Content-Type-Header der Antwort.

        Returns:
            Eine einzeilige, auf 500 Zeichen gekuerzte Fehlermeldung.
        """
        max_len = 500

        if "application/json" in content_type.lower():
            try:
                data = response.json()
            except ValueError:
                return (response.text or "").strip()[:max_len]

            if isinstance(data, dict):
                messages: list[str] = []
                error_messages = data.get("errorMessages")
                if isinstance(error_messages, list):
                    messages.extend(str(m) for m in error_messages)
                errors = data.get("errors")
                if isinstance(errors, dict):
                    messages.extend(f"{key}: {value}" for key, value in errors.items())
                if messages:
                    return " | ".join(messages)[:max_len]
            return json.dumps(data, ensure_ascii=False)[:max_len]

        # Nicht-JSON (HTML-Fehlerseite, Plain-Text) auf eine Zeile reduzieren
        normalized = " ".join((response.text or "").split())
        return normalized[:max_len]

    def _headers(self) -> dict[str, str]:
        """HTTP Headers fuer Jira API Requests.

        Cloud-Modus: Basic-Auth uebernimmt httpx (auth=). Legacy-Modus:
        Bearer-PAT als Authorization-Header.

        Returns:
            Das Header-Dict.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",
        }
        if self._legacy:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

"""Anonymisiert Timesheet-Daten fuer Screenshots und Demos."""

from __future__ import annotations

import random
from dataclasses import replace

from jira_timesheet_qt.models.timesheet import Timesheet, TimesheetDay, WorklogEntry
from jira_timesheet_qt.services.ticket_board import Board, Group, Role, Ticket

# Zentrale Fake-Werte fuer den Anonymisierungs-Modus (Screenshots). Werden auch
# vom ConfigPanel-Header, der Log-Zensur und dem Detail-Dialog verwendet.
FAKE_EMAIL = "user@example.com"
FAKE_HOST = "https://jira.example.com"

_FAKE_PROJECTS = ["PROJ", "TASK", "FEAT", "DEV", "OPS", "INFRA", "WEB", "APP"]

_FAKE_SUMMARIES = [
    "Update user authentication flow",
    "Fix pagination in dashboard",
    "Refactor database connection pool",
    "Add export functionality",
    "Improve error handling",
    "Update dependencies to latest",
    "Fix responsive layout issues",
    "Implement caching layer",
    "Add unit tests for services",
    "Optimize API response time",
    "Fix memory leak in worker",
    "Update CI/CD pipeline",
    "Add logging and monitoring",
    "Refactor configuration module",
    "Implement retry logic",
    "Fix date formatting bug",
    "Add input validation",
    "Update documentation",
    "Performance optimization",
    "Security patch for auth module",
    "Implement search feature",
    "Fix timezone handling",
    "Add CSV export option",
    "Refactor event handling",
    "Update email templates",
    "Fix broken links in navigation",
    "Add dark mode support",
    "Implement webhook handler",
    "Fix concurrent access issue",
    "Add health check endpoint",
]

# Unmissverstaendlich erfundene Namen. Gaengige Nachnamen wie "Weber" oder
# "Schmidt" kollidieren in einer echten Instanz frueher oder spaeter mit einer
# realen Person - im Screenshot steht dann der Name eines Kollegen, obwohl
# anonymisiert wurde. Genau das ist an echten Daten aufgefallen.
_FAKE_AUTHORS = [
    "Mustermann, Max",
    "Musterfrau, Erika",
    "Beispiel, Bernd",
    "Muster, Martina",
    "Beispiel, Berta",
]

_FAKE_COMPONENTS = [
    "Frontend",
    "Backend",
    "API",
    "Database",
    "Infrastructure",
    "Security",
    "Testing",
    "DevOps",
    "UI/UX",
    "",
]

_FAKE_BUDGETS = [
    "Projekt Alpha",
    "Projekt Beta",
    "Wartung",
    "nicht zugeordnet",
]


def _strip_scheme(host: str) -> str:
    """Entfernt Schema und abschliessenden Schraegstrich eines Hosts."""
    host = host.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


def log_censor_map(email: str, host: str) -> dict[str, str]:
    """Baut die Ersetzungen fuer die Log-Zensur im Anonymisierungs-Modus.

    Bildet die echten Zugangswerte (E-Mail, Host mit und ohne Schema) auf die
    zentralen Dummy-Werte ab. Laengere Schluessel zuerst, damit z.B. der Host
    mit Schema vor dem blossen Hostnamen ersetzt wird.
    """
    pairs: dict[str, str] = {}
    host = host.strip()
    if host:
        pairs[host.rstrip("/")] = FAKE_HOST
        bare = _strip_scheme(host)
        if bare:
            pairs[bare] = _strip_scheme(FAKE_HOST)
    if email.strip():
        pairs[email.strip()] = FAKE_EMAIL
    # Laengste Schluessel zuerst - sonst zensiert der blosse Host den Host mit Schema.
    return dict(sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True))


def anonymize_timesheet(timesheet: Timesheet) -> Timesheet:
    """Erzeugt eine anonymisierte Kopie des Timesheets.

    Ticket-Keys, Beschreibungen, Autoren und Komponenten werden ersetzt.
    Stunden, Daten und Struktur bleiben erhalten.
    """
    rng = random.Random(42)
    ticket_map: dict[str, str] = {}
    summary_idx = 0

    anon_days: list[TimesheetDay] = []

    for day in timesheet.days:
        anon_entries: list[WorklogEntry] = []

        for entry in day.entries:
            if entry.ticket not in ticket_map:
                project = rng.choice(_FAKE_PROJECTS)
                num = len(ticket_map) + 1001
                ticket_map[entry.ticket] = f"{project}-{num}"

            anon_ticket = ticket_map[entry.ticket]
            anon_summary = _FAKE_SUMMARIES[summary_idx % len(_FAKE_SUMMARIES)]
            summary_idx += 1

            anon_entries.append(
                WorklogEntry(
                    date=entry.date,
                    ticket=anon_ticket,
                    summary=anon_summary,
                    author=rng.choice(_FAKE_AUTHORS),
                    budget=rng.choice(_FAKE_BUDGETS),
                    hours=entry.hours,
                    status=entry.status,
                    issuetype=entry.issuetype,
                    epic="",
                    components=rng.choice(_FAKE_COMPONENTS),
                    labels="",
                    priority=entry.priority,
                    resolution=entry.resolution,
                    assignee=rng.choice(_FAKE_AUTHORS),
                    created=entry.created,
                    updated=entry.updated,
                    total_logged=entry.total_logged,
                )
            )

        anon_days.append(TimesheetDay(date=day.date, entries=anon_entries))

    return Timesheet(
        developer=rng.choice(_FAKE_AUTHORS),
        email=FAKE_EMAIL,
        date_from=timesheet.date_from,
        date_to=timesheet.date_to,
        days=anon_days,
    )


# Neutrale Statusnamen je Rolle. Die echten Namen sind interne
# Prozessbezeichner des Betreibers und haben in einem Screenshot nichts
# verloren - anders als Stunden oder Liegezeiten, die nichts verraten.
_FAKE_STATUS: dict[Role, tuple[str, ...]] = {
    Role.ACTIVE: ("In Progress", "Implementing", "Analysing"),
    Role.BACKLOG: ("To Do", "Refined", "Planned"),
    Role.ACCEPTANCE: ("In Review", "In Acceptance", "Waiting"),
    Role.HANDBACK: ("In Validation", "Deployed"),
    Role.CLOSING: ("Closing", "Handover", "Approved"),
    Role.UNKNOWN: ("Status A", "Status B", "Status C"),
}


def anonymize_board(board: Board) -> Board:
    """Erzeugt eine anonymisierte Kopie einer Ticket-Ansicht.

    Ersetzt werden Ticketnummer, Titel, Autor, Bearbeiter, Statusname und die
    Verweis-URL. Erhalten bleibt alles, was keine Identitaet traegt und die
    Aussage des Bildes ausmacht: Rolle, Merkmale, Liegezeit, Prioritaet,
    Vorgangsart und die Gruppierung.

    Args:
        board:
            Die echte Ansicht.

    Returns:
        Eine neue Ansicht mit Dummy-Werten. Das Original bleibt unberuehrt,
        damit sich der Modus zurueckschalten laesst.
    """
    rng = random.Random(42)
    ticket_map: dict[str, str] = {}
    status_map: dict[str, str] = {}
    people: dict[str, str] = {}
    summary_index = 0

    def fake_key(real: str) -> str:
        if real not in ticket_map:
            project = rng.choice(_FAKE_PROJECTS)
            ticket_map[real] = f"{project}-{len(ticket_map) + 1001}"
        return ticket_map[real]

    def fake_status(real: str, role: Role) -> str:
        if real not in status_map:
            pool = _FAKE_STATUS.get(role) or _FAKE_STATUS[Role.UNKNOWN]
            status_map[real] = pool[len(status_map) % len(pool)]
        return status_map[real]

    def fake_person(real: str) -> str:
        if not real:
            return ""
        if real not in people:
            people[real] = _FAKE_AUTHORS[len(people) % len(_FAKE_AUTHORS)]
        return people[real]

    def copy_ticket(ticket: Ticket) -> Ticket:
        nonlocal summary_index
        key = fake_key(ticket.key)
        summary = _FAKE_SUMMARIES[summary_index % len(_FAKE_SUMMARIES)]
        summary_index += 1
        return replace(
            ticket,
            key=key,
            summary=summary,
            status=fake_status(ticket.status, ticket.role),
            reporter=fake_person(ticket.reporter),
            assignee=fake_person(ticket.assignee),
            url=f"{FAKE_HOST}/browse/{key}" if ticket.url else "",
        )

    groups = [
        Group(role=group.role, tickets=[copy_ticket(t) for t in group.tickets])
        for group in board.groups
    ]
    return Board(
        groups=groups,
        tickets=[t for g in groups for t in g.tickets],
        # Auch hier stehen echte Statusnamen - sie erscheinen im Hinweis der
        # Statusleiste.
        unknown_status=[
            fake_status(name, Role.UNKNOWN) for name in board.unknown_status
        ],
    )

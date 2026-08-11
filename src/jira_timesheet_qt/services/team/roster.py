"""Personen aus Jira-Antworten lesen und die Merkliste verwalten.

Kein Jira-Client, keine Oberflaeche - die aufrufende Anwendung holt die
Antworten und reicht sie herein, wie im Kern der Ticket-Ansichten auch.

Gemessene Grundlagen (10.08.2026, gegen die echte Instanz):

* Die **Mailadresse taugt nicht als Schluessel.** Von 63 Personen mit offenen
  Tickets gaben nur 46 ueberhaupt eine Adresse heraus. Ein Kollege hatte zwei
  Konten, das mit der Adresse trug null Tickets, das ohne trug hundertzwanzig.
* **Nicht sichtbar heisst nicht: nicht vorhanden.** Der direkte Abruf ueber
  ``/rest/api/3/user`` liefert dieselbe Auskunft wie die Suche, das eigene
  Konto gibt seine Adresse dabei sehr wohl heraus. Das leere Feld ist also
  eine Sichtbarkeitseinstellung im Profil.
* **Ueber das aktuelle Konto entscheidet das Datum, nicht die Anzahl.** Bei
  einem Kollegen trug das juengste Konto zwei Tickets und ein stillgelegtes
  achtzehn. Eine Trefferliste, die nach Menge sortiert, fuehrt hier in die
  Irre.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import Any

from ..ticket_board import AccountIdError, check_account_id, parse_ts
from .models import AccountCandidate, Roster, TeamMember

# Konten dieser Art sind Menschen. Anwendungskonten und Kundenportal-Konten
# tauchen in derselben Suche auf und gehoeren nicht in eine Team-Merkliste.
_HUMAN_ACCOUNT_TYPE = "atlassian"


def _text(source: Any, key: str) -> str:
    """Liest ein Textfeld defensiv aus einem Antwortstueck."""
    if not isinstance(source, dict):
        return ""
    value = source.get(key)
    return str(value) if value is not None else ""


def _avatar(source: Any) -> str:
    """Liest die groesste angebotene Avatar-URL, leer wenn keine da ist."""
    if not isinstance(source, dict):
        return ""
    urls = source.get("avatarUrls")
    if not isinstance(urls, dict) or not urls:
        return ""
    # Die Schluessel heissen "16x16" bis "48x48". Die groesste zuletzt.
    for size in ("48x48", "32x32", "24x24", "16x16"):
        if urls.get(size):
            return str(urls[size])
    return str(next(iter(urls.values())))


def parse_search(users: Iterable[Any]) -> list[AccountCandidate]:
    """Liest die Treffer einer Personensuche.

    Args:
        users:
            Die Antwort von ``/rest/api/3/user/search``.

    Returns:
        Die menschlichen, aktiven Konten. Konten mit unbrauchbarer Kennung
        werden uebergangen - sie liessen sich ohnehin nicht abfragen.
    """
    found: list[AccountCandidate] = []
    seen: set[str] = set()
    for user in users:
        if not isinstance(user, dict):
            continue
        if not user.get("active"):
            continue
        if _text(user, "accountType") != _HUMAN_ACCOUNT_TYPE:
            continue
        account_id = _text(user, "accountId")
        try:
            check_account_id(account_id)
        except AccountIdError:
            continue
        if account_id in seen:
            continue
        seen.add(account_id)
        found.append(
            AccountCandidate(
                account_id=account_id,
                display_name=_text(user, "displayName"),
                email=_text(user, "emailAddress"),
                avatar_url=_avatar(user),
            )
        )
    return found


def parse_people(issues: Iterable[Any]) -> list[AccountCandidate]:
    """Liest die Bearbeiter aus einer Suchantwort.

    Der Weg ueber den Ticketbestand kommt ohne die Benutzer-Schnittstelle aus
    und liefert deshalb auch dort Kennungen, wo die Personensuche nichts
    herausgibt. Das ``assignee``-Objekt fuehrt Kennung, Anzeigename, Avatar und
    - soweit sichtbar - die Mailadresse gleich mit.

    Args:
        issues:
            Die issues-Liste einer Suchantwort, angefordert mit dem Feld
            ``assignee``.

    Returns:
        Je Konto ein Eintrag, nach Anzeigename sortiert.
    """
    people: dict[str, AccountCandidate] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        assignee = (issue.get("fields") or {}).get("assignee")
        account_id = _text(assignee, "accountId")
        if not account_id or account_id in people:
            continue
        try:
            check_account_id(account_id)
        except AccountIdError:
            continue
        people[account_id] = AccountCandidate(
            account_id=account_id,
            display_name=_text(assignee, "displayName"),
            email=_text(assignee, "emailAddress"),
            avatar_url=_avatar(assignee),
        )
    return sorted(people.values(), key=lambda p: p.display_name.casefold())


def with_last_touch(
    candidate: AccountCandidate,
    issues: Sequence[Any],
) -> AccountCandidate:
    """Ergaenzt einen Kandidaten um sein juengstes Aenderungsdatum.

    Args:
        candidate:
            Das Konto.
        issues:
            Die Antwort auf ``last_touch_jql``, es genuegt der erste Treffer.

    Returns:
        Eine Kopie mit gesetztem ``last_touch``, oder None dort, wenn das
        Konto nie ein Ticket getragen hat.
    """
    stamp: dt.datetime | None = None
    if issues:
        first = issues[0]
        if isinstance(first, dict):
            stamp = parse_ts(_text(first.get("fields"), "updated"))
    return AccountCandidate(
        account_id=candidate.account_id,
        display_name=candidate.display_name,
        email=candidate.email,
        avatar_url=candidate.avatar_url,
        open_count=candidate.open_count,
        last_touch=stamp,
    )


def sort_candidates(candidates: Iterable[AccountCandidate]) -> list[AccountCandidate]:
    """Sortiert Kandidaten nach Aktualitaet, juengstes Konto zuerst.

    Ausdruecklich NICHT nach Ticketzahl: das aktuelle Konto ist nicht das
    groesste. Konten ohne jedes Ticket landen hinten, weil sie zwar existieren,
    aber nie benutzt wurden.
    """
    return sorted(
        candidates,
        key=lambda c: (
            c.last_touch is None,
            -(c.last_touch.timestamp() if c.last_touch else 0.0),
            c.display_name.casefold(),
        ),
    )


def merge_accounts(candidates: Sequence[AccountCandidate], name: str = "") -> TeamMember:
    """Fasst mehrere Konten zu einem Mitglied zusammen.

    Args:
        candidates:
            Die zugehoerigen Konten, in beliebiger Reihenfolge.
        name:
            Gewuenschter Anzeigename. Leer nimmt den des juengsten Kontos.

    Returns:
        Das Mitglied. Die Kennungen stehen in der Reihenfolge der Aktualitaet,
        damit das aktuelle Konto vorn steht.

    Raises:
        ValueError:
            Ohne Konten. Ein Mitglied ohne Kennung liesse sich nicht abfragen
            und wuerde als leere Liste erscheinen, die wie "nichts zu tun"
            aussieht.
    """
    ordered = sort_candidates(candidates)
    if not ordered:
        raise ValueError("Ein Mitglied braucht mindestens ein Konto")
    lead = ordered[0]
    return TeamMember(
        display_name=name.strip() or lead.display_name,
        account_ids=tuple(c.account_id for c in ordered),
        email=next((c.email for c in ordered if c.email), ""),
        avatar_url=next((c.avatar_url for c in ordered if c.avatar_url), ""),
    )


def to_storage(roster: Roster) -> list[dict[str, Any]]:
    """Wandelt die Merkliste in die Form, die in den Einstellungen liegt."""
    return [
        {
            "display_name": m.display_name,
            "account_ids": list(m.account_ids),
            "email": m.email,
            "avatar_url": m.avatar_url,
        }
        for m in roster.members
    ]


def from_storage(raw: Any) -> Roster:
    """Liest die Merkliste aus den Einstellungen.

    Defensiv: eine von Hand verdorbene Datei darf den Programmstart nicht
    verhindern. Unbrauchbare Eintraege werden uebergangen, nicht geraten.

    Args:
        raw:
            Der gespeicherte Wert, ueblicherweise eine Liste von Abbildungen.

    Returns:
        Die Merkliste, alphabetisch nach Anzeigename.
    """
    members: list[TeamMember] = []
    if not isinstance(raw, list):
        return Roster()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ids: list[str] = []
        for value in entry.get("account_ids") or []:
            try:
                ids.append(check_account_id(str(value)))
            except AccountIdError:
                continue
        name = str(entry.get("display_name") or "").strip()
        if not ids or not name:
            continue
        members.append(
            TeamMember(
                display_name=name,
                account_ids=tuple(ids),
                email=str(entry.get("email") or ""),
                avatar_url=str(entry.get("avatar_url") or ""),
            )
        )
    members.sort(key=lambda m: m.display_name.casefold())
    return Roster(members=members)

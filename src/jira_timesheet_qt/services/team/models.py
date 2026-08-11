"""Anzeigemodell der Merkliste "Mein Team".

Reine Datenklassen ohne Verhalten und ohne Kenntnis von Jira oder einer
Oberflaeche. Wer sie fuellt, steht in ``roster``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AccountCandidate:
    """Ein Konto, wie es die Personensuche liefert.

    Die Kandidatenliste ist kein Zwischenschritt, sondern die eigentliche
    Entscheidungshilfe: eine Person kann mehrere Konten fuehren, und weder
    Mailadresse noch Ticketzahl sagen zuverlaessig, welches das aktuelle ist.
    """

    account_id: str = ""
    display_name: str = ""
    email: str = ""
    """Leer, wenn das Profil die Adresse nicht herausgibt. Das heisst NICHT,
    dass keine existiert - jedes Konto braucht eine zum Anmelden. Nur zur
    Anzeige verwenden, nie als Schluessel."""

    avatar_url: str = ""
    open_count: int | None = None
    """None = noch nicht ermittelt, 0 = nachweislich keine offenen Tickets."""

    last_touch: dt.datetime | None = None
    """Aenderungszeitpunkt des juengsten Tickets dieses Kontos."""


@dataclass(frozen=True)
class TeamMember:
    """Eine Person der Merkliste.

    Traegt eine LISTE von Kennungen, nicht eine einzelne. Gemessen am
    10.08.2026: ein Kollege fuehrte drei aktive Konten, weil er im Lauf der
    Zeit von einem zum naechsten gewandert ist. Wer nur das juengste aufnimmt,
    verliert seine Vorgeschichte, wer nur das groesste nimmt, sieht die
    aktuelle Arbeit nicht.
    """

    display_name: str = ""
    """Wie die Person hier genannt wird. Ueberschreibt bewusst den
    Jira-Anzeigenamen: derselbe Mensch stand in der vermessenen Instanz unter
    drei verschiedenen Schreibweisen, und wie jemand genannt werden moechte,
    entscheidet nicht das Benutzerverzeichnis."""

    account_ids: tuple[str, ...] = ()
    email: str = ""
    avatar_url: str = ""

    def with_name(self, name: str) -> TeamMember:
        """Liefert eine Kopie mit geaendertem Anzeigenamen."""
        return TeamMember(
            display_name=name.strip() or self.display_name,
            account_ids=self.account_ids,
            email=self.email,
            avatar_url=self.avatar_url,
        )


@dataclass
class Roster:
    """Die gesamte Merkliste, in der Reihenfolge der Anzeige."""

    members: list[TeamMember] = field(default_factory=list)

    def find(self, name: str) -> TeamMember | None:
        """Sucht ein Mitglied ueber seinen Anzeigenamen."""
        needle = name.strip().casefold()
        for member in self.members:
            if member.display_name.strip().casefold() == needle:
                return member
        return None

"""JQL-Ausdruecke fuer die Ticket-Ansichten.

Was hier steht, ist gegen eine echte Jira-Cloud-Instanz gemessen und nicht
aus der Dokumentation abgeschrieben. Die Fallstricke im Einzelnen:

* ``issue in commentedBy(...)`` steht in der Autovervollstaendigung mancher
  Instanzen, liefert aber nichts oder HTTP 400. Nicht verwenden.
* ``currentUser()`` laesst sich NICHT als Argument einer Funktion
  verschachteln. ``issue in updatedBy(currentUser())`` ist ein Syntaxfehler,
  die accountId muss als Zeichenkette hinein.
* ``issue in updatedBy("<id>")`` erfasst auch eigene Kommentare. In einer
  Stichprobe waren 18 von 18 Tickets mit eigenem Kommentar enthalten.
* ``comment ~ "<id>"`` findet Erwaehnungen. Dass es nicht einfach alles
  trifft, ist allein durch die Gegenprobe belegt: dieselbe Abfrage mit einer
  erfundenen accountId liefert null Treffer. Diese Gegenprobe gehoert in den
  Test.
* Fuer Zeitreihen ist ``statuscategorychangedate`` zu verwenden, NICHT
  ``resolutiondate``. Letzteres war in der vermessenen Instanz nur bei der
  Haelfte der erledigten Tickets gesetzt - wer damit rechnet, halbiert den
  Durchsatz, ohne es zu merken.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Felder, die beide Ansichten brauchen. issuelinks nur fuer die
# Blockiert-Erkennung, die client-seitig laeuft.
FIELDS = (
    "summary,status,priority,issuetype,assignee,reporter,"
    "created,updated,statuscategorychangedate,issuelinks"
)

# Felder fuer die Auswertung - schlanker, weil nur Zeitpunkte gebraucht werden.
# "updated" gehoert dazu: ohne das Feld bleibt die Altersverteilung der
# offenen Tickets leer, und zwar lautlos. Genau so aufgefallen.
STATS_FIELDS = "created,updated,statuscategorychangedate,status,issuetype"

# Jira-accountIds bestehen aus Ziffern, Buchstaben, Doppelpunkt und
# Bindestrich. Alles andere wird abgelehnt, statt es in eine Abfrage zu
# kleben - eine Zeichenkette aus einer Fremdquelle gehoert nie ungeprueft
# in ein Ausdrucksfeld.
_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9:_.@-]{1,128}$")


class AccountIdError(ValueError):
    """Die uebergebene accountId taugt nicht fuer eine JQL-Abfrage."""


def check_account_id(account_id: str) -> str:
    """Prueft eine accountId, bevor sie in einen JQL-Ausdruck wandert.

    Args:
        account_id:
            Die Kennung aus /rest/api/3/myself.

    Returns:
        Die unveraenderte Kennung.

    Raises:
        AccountIdError:
            Wenn die Kennung leer ist oder unerlaubte Zeichen enthaelt.
    """
    value = (account_id or "").strip()
    if not _ACCOUNT_ID.match(value):
        raise AccountIdError("accountId enthaelt unerlaubte Zeichen")
    return value


def assignee_clause(account_ids: Sequence[str] = ()) -> str:
    """Baut die Bedingung auf den Bearbeiter.

    Ohne Kennungen bleibt es bei ``currentUser()``. Mit Kennungen wird ``IN``
    verwendet, und zwar auch bei einer einzigen - eine Person kann in einer
    Instanz mehrere Konten fuehren. Gemessen am 10.08.2026: ein Kollege hatte
    drei aktive Konten, deren Einzelsummen sich in der IN-Abfrage exakt
    addierten (1 + 3 + 10 = 14).

    Args:
        account_ids:
            Kennungen der gemeinten Person. Leer = der angemeldete Benutzer.

    Returns:
        Die fertige Bedingung.

    Raises:
        AccountIdError:
            Wenn eine der Kennungen unbrauchbar ist. Bewusst ein Abbruch und
            keine stille Auslassung - eine uebersprungene Kennung liefert ein
            unvollstaendiges Ergebnis, das wie ein vollstaendiges aussieht.
    """
    if not account_ids:
        return "assignee = currentUser()"
    names = ", ".join(f'"{check_account_id(a)}"' for a in account_ids)
    return f"assignee IN ({names})"


def assigned_jql(account_ids: Sequence[str] = ()) -> str:
    """Alle offenen Tickets, die einer Person zugewiesen sind.

    Args:
        account_ids:
            Kennungen der gemeinten Person. Leer = der angemeldete Benutzer.

    Returns:
        Der JQL-Ausdruck.
    """
    return (
        f"{assignee_clause(account_ids)} AND statusCategory != Done "
        "ORDER BY updated ASC"
    )


def closing_jql(statuses: tuple[str, ...], account_ids: Sequence[str] = ()) -> str:
    """Tickets in Status, die Jira als fertig zaehlt, obwohl Restarbeit bleibt.

    Diese Tickets faellt ein reiner Filter auf ``statusCategory != Done``
    komplett unter den Tisch. In der vermessenen Instanz war das die
    groesste Einzelgruppe ueberhaupt.

    Args:
        statuses:
            Die konfigurierten Abschluss-Status.
        account_ids:
            Kennungen der gemeinten Person. Leer = der angemeldete Benutzer.

    Returns:
        Der JQL-Ausdruck, oder ein leerer String ohne konfigurierte Status.
    """
    if not statuses:
        return ""
    names = ", ".join(f'"{s}"' for s in statuses if '"' not in s)
    if not names:
        return ""
    return (
        f"{assignee_clause(account_ids)} AND status IN ({names}) "
        "ORDER BY updated ASC"
    )


def relevant_jql(account_id: str, window_days: int = 0) -> str:
    """Offene Tickets mit Bezug zum Benutzer, die ihm nicht zugewiesen sind.

    Args:
        account_id:
            Die eigene accountId, geprueft ueber check_account_id.
        window_days:
            Nur Tickets, die in so vielen Tagen zuletzt geaendert wurden.
            0 = kein Zeitfenster.

    Returns:
        Der JQL-Ausdruck.

    Raises:
        AccountIdError:
            Bei einer unbrauchbaren Kennung.
    """
    ident = check_account_id(account_id)
    sources = (
        "reporter = currentUser()",
        "watcher = currentUser()",
        "worklogAuthor = currentUser()",
        f'issue in updatedBy("{ident}")',
        f'comment ~ "{ident}"',
    )
    parts = [
        "(" + " OR ".join(sources) + ")",
        "assignee != currentUser()",
        "statusCategory != Done",
    ]
    if window_days > 0:
        parts.append(f"updated >= -{int(window_days)}d")
    return " AND ".join(parts) + " ORDER BY updated DESC"


def history_jql() -> str:
    """Alle Tickets des Benutzers fuer die Auswertung, offen wie erledigt.

    Bewusst OHNE Parameter fuer fremde Kennungen. Die Auswertung zeigt
    Durchsatz je Monat, und das ist ueber eine andere Person eine
    Leistungskennzahl. Die Ansicht "Mein Team" zeigt deshalb keine Diagramme.
    Siehe auch ``last_touch_jql`` fuer den erlaubten Blick auf Fremde.

    Returns:
        Der JQL-Ausdruck.
    """
    return "assignee = currentUser() ORDER BY created ASC"


def last_touch_jql(account_id: str) -> str:
    """Zuletzt geaendertes Ticket eines Kontos, fuer die Kontoauswahl.

    Fuehrt eine Person mehrere Konten, entscheidet das Datum, welches das
    aktuelle ist - nicht die Anzahl der Tickets. Gemessen am 10.08.2026: das
    aktuelle Konto eines Kollegen trug zwei Tickets, ein stillgelegtes achtzehn.

    Args:
        account_id:
            Die zu pruefende Kennung.

    Returns:
        Der JQL-Ausdruck. Es genuegt, den ersten Treffer zu lesen.

    Raises:
        AccountIdError:
            Bei einer unbrauchbaren Kennung.
    """
    return f'assignee = "{check_account_id(account_id)}" ORDER BY updated DESC'

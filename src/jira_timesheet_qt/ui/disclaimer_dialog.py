"""Was diese Anwendung am Haftungshinweis ergaenzt.

Der Standardtext in QAppFramework beschreibt Werkzeuge, die fremde Systeme
abrufen und dabei Last erzeugen. Hier geht es um etwas anderes: um den Zugriff
auf Daten, die andere Personen betreffen koennen. Einleitung und Zusicherungen
sind deshalb eigene.

Der HAFTUNGSABSATZ steht nicht hier - er kommt fest aus der Bibliothek und soll
in jeder Anwendung gleich lauten.
"""

from __future__ import annotations

from QAppFramework.disclaimer import DISCLAIMER_VERSION, DisclaimerDialog, DisclaimerStore

__all__ = ["DISCLAIMER_VERSION", "DUTIES", "INTRO", "DisclaimerDialog", "DisclaimerStore"]

INTRO = (
    "Dieses Programm greift über die REST-API auf eine Jira-Instanz zu und liest dort "
    "Arbeitszeit-Buchungen aus. Welche Vorgänge und welche Worklogs dabei sichtbar werden, "
    "bestimmen allein die Berechtigungen Ihres Zugangs. Je nach Rechtevergabe können darunter "
    "auch Buchungen anderer Personen sein."
)

DUTIES: tuple[str, ...] = (
    "Sie setzen das Programm ausschließlich gegen Jira-Instanzen ein, für die Ihnen eine "
    "ausdrückliche Berechtigung des Betreibers vorliegt.",
    "Sie werten nur Daten aus, zu deren Einsicht und Verarbeitung Sie befugt sind. Werden Ihnen "
    "Buchungen anderer Personen angezeigt, prüfen Sie vor jeder weiteren Verwendung, ob Sie diese "
    "verarbeiten dürfen.",
    "Erzeugte Stundenzettel und Exporte können personenbezogene Daten enthalten. Für deren "
    "Weitergabe, Aufbewahrung und Löschung sind Sie verantwortlich.",
)

"""Desktop-GUI fuer Stundenzettel aus Jira-Worklogs."""

from __future__ import annotations

__version__ = "0.8.2"
__author__ = "Michael Blaess"
__year__ = "2026"
# Anzeigename der Anwendung - was in Fenstertitel, Info-Dialog und
# Absturzbericht steht. Bewusst der Werkzeugname und NICHT das deutsche Wort
# "Stundenzettel": das meint das erzeugte Dokument, nicht das Programm.
#
# Getrennt vom PAKETnamen (jira-timesheet-qt): der bleibt kleingeschrieben und
# mit Endung, weil an ihm Repo, Einstellungsordner, Befehl und PyPI-Name
# haengen. Fuer den Anwender ist das "-qt" ohne Bedeutung - er kennt nur diese
# eine Anwendung.
__app_name__ = "JIRA-Timesheet"

"""Ticket-Lebenszyklus als interaktiver Bericht in einer HTML-Datei.

Der Kern ist bewusst abhaengigkeitsfrei (reine Standardbibliothek) und kennt
keinen Jira-Client: die aufrufende Anwendung holt die drei Antworten der API
selbst und reicht sie herein. So laesst sich derselbe Code im Terminal, in
der Textual-Oberflaeche und in der Qt-Oberflaeche verwenden.

Typischer Aufruf:

    from ticket_report import build_report, write_report

    report = build_report(issue, changelog, comments, browse_base)
    pfad = write_report(report, "ABC-123.html")

Der Bericht selbst traegt interne Ticketdaten - die erzeugte Datei bleibt
lokal.
"""

from __future__ import annotations

from .render import build_html, write_report
from .viewmodel import Report
from .viewmodel import build as build_report

__all__ = ["Report", "build_html", "build_report", "write_report"]

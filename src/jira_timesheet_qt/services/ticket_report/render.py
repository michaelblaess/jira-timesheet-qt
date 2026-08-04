"""Erzeugt den Bericht als eine self-contained HTML-Datei.

Reine Standardbibliothek - kein Webserver, keine Vorlagensprache, keine
Fremdbibliothek. Das Ergebnis ist eine einzelne Datei, die sich per
Doppelklick oeffnen und per Mail weitergeben laesst.

Sicherheitsregel fuer dieses Modul: JEDER Wert, der aus Jira stammt, laeuft
durch ``e()``. Ein Ticket-Titel mit ``&`` oder ``<`` zerlegt sonst die Seite.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from html import escape

from .style import CSS
from .viewmodel import Marker, Report, Segment

# Farbwerte je Tonwert. Bestimmen die Akzentfarbe einer Komponente.
TONES = {
    "wait": "#7d8f86",
    "work": "#b04812",
    "done": "#0e7a52",
    "pine": "#0a5c3f",
    "clock": "#b04812",
    "warn": "#b42318",
    "mut": "#5a6b62",
}

# Bedienung der fertigen Datei: Marker anklicken, Ledger umschalten,
# arbeitsfreie Zeiten einblenden. Bewusst winzig und ohne Bibliothek.
SCRIPT = """
function toggleOff(b){
 var l=document.getElementById('offlayer');
 var on=l.classList.toggle('on');
 b.classList.toggle('act',on);
 b.textContent=on?b.dataset.labelOff:b.dataset.labelOn;
}
document.addEventListener('click',function(e){
 var d=e.target.closest('[data-detail]');
 if(d){
  document.getElementById('detailbox').outerHTML=PANELS[d.getAttribute('data-detail')];
  document.querySelectorAll('.mk').forEach(function(x){x.classList.remove('on')});
  d.classList.add('on');
  return;
 }
 var m=e.target.closest('[data-mode]');
 if(m){
  document.getElementById('peoplebox').innerHTML=LEDGERS[m.getAttribute('data-mode')];
  return;
 }
 var o=e.target.closest('[data-off]');
 if(o){toggleOff(o);}
});
"""


def e(value: object) -> str:
    """Maskiert einen Wert fuer die Ausgabe in HTML."""
    return escape(str(value), quote=True)


def _tone(name: str) -> str:
    """Liefert die CSS-Variablendefinition fuer einen Tonwert."""
    return f"--c:{TONES.get(name, TONES['mut'])}"


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------
def masthead(report: Report) -> str:
    """Dunkler Kopfbereich mit Kennzahlen."""
    stats = "".join(
        f'<div class="stat"><div class="k">{e(label)}</div><div class="v">{e(value)}</div></div>'
        for label, value in report.stats
    )
    return (
        '<div class="mast"><div class="mrow">'
        f'<div><p class="eyebrow">Ticket-Lebenszyklus</p><h1>{e(report.summary)}</h1></div>'
        f'<div class="idbox"><span class="idtag">'
        f'<a class="jlink" href="{e(report.url)}" target="_blank">{e(report.key)}</a>'
        f"  ·  {e(report.issue_type)}</span>"
        f'<span class="pill">{e(report.status)}</span></div>'
        f'</div><div class="stats">{stats}</div></div>'
    )


def _marker(marker: Marker) -> str:
    """Ein anklickbarer Punkt auf der Zeitachse."""
    side = "up" if marker.above else "dn"
    edge = " el" if marker.pct < 8 else (" er" if marker.pct > 92 else "")
    status = " st" if marker.is_status else ""
    # Unter der Achse liegen Band, Dauer und Tagesmarken - der Stiel muss
    # daran vorbei, sonst schreibt sich die Beschriftung darueber.
    stem = f'<div class="stem" style="height:{26 if marker.above else 70}px"></div>'
    count = f'<span class="cnt">×{marker.count}</span>' if marker.count > 1 else ""
    dot = f'<div style="position:relative"><div class="dot"></div>{count}</div>'

    label = ""
    if marker.show_label:
        chip = (
            f'<div><span class="chip">{e(marker.status_target)}</span></div>'
            if marker.is_status
            else ""
        )
        text = (
            f'<div class="clk">{marker.when:%d.%m. %H:%M}</div>'
            f'<div class="lab">{e(marker.label)}</div>'
        )
        label = text + chip if marker.above else chip + text

    # Ueber der Achse: Beschriftung, Stiel, Punkt. Darunter gespiegelt.
    inner = (label + stem + dot) if marker.above else (dot + stem + label)
    return (
        f'<button class="mk {side}{edge}{status}" data-detail="{e(marker.key)}" '
        f'style="left:{marker.pct:.3f}%;{_tone(marker.tone)}">{inner}</button>'
    )


def rail(report: Report) -> str:
    """Massstabsgetreue Achse mit Statusband, Tagesmarken und Markern."""
    offs = "".join(
        f'<div class="off" style="left:{left:.3f}%;width:{width:.3f}%"></div>'
        for left, width in report.offhours
    )
    lines = "".join(
        f'<div class="phaseline" style="left:{m.pct:.3f}%;{_tone(m.tone)}"></div>'
        for m in report.markers
        if m.is_status
    )
    segs = "".join(
        f'<div class="seg{" long" if s.long else ""}" '
        f'style="left:{s.left:.3f}%;width:{s.width:.3f}%;{_tone(s.tone)}">'
        f'<span>{e(s.status) if s.width > 6 else ""}</span></div>'
        for s in report.segments
    )
    labs = "".join(
        f'<div class="sl{" long" if s.long else ""}" '
        f'style="left:{s.left + s.width / 2:.3f}%;transform:translateX(-50%)">'
        f"{e(s.gross)}</div>"
        for s in report.segments
        if s.width > 9
    )
    days = "".join(
        f'<div class="day" style="left:{left:.3f}%">{e(text)}</div>'
        for left, text in _day_ticks(report)
    )
    markers = "".join(_marker(m) for m in report.markers)

    return (
        '<div class="railbox"><div class="rail">'
        f'<div class="offlayer" id="offlayer">{offs}</div>{lines}'
        f'<div class="axis"></div><div class="band">{segs}</div>'
        f'<div class="seglab">{labs}</div><div class="days">{days}</div>'
        f"{markers}</div></div>"
    )


def _day_ticks(report: Report) -> list[tuple[float, str]]:
    """Rechnet die Tagesgrenzen auf Achsenpositionen um."""
    if not report.markers:
        return []
    start = report.created
    last = max(m.when for m in report.markers)
    end = max(last, dt.datetime.now(tz=start.tzinfo))
    span = (end - start).total_seconds() or 1

    # Bei langen Laufzeiten wuerden taegliche Marken zu einem Brei verschmelzen.
    tage = span / 86400
    if tage <= 16:
        schritt, monatlich = 1, False
    elif tage <= 70:
        schritt, monatlich = 7, False
    else:
        schritt, monatlich = 1, True

    ticks: list[tuple[float, str]] = []
    day = (start + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        if monatlich:
            if day.day == 1:
                ticks.append(((day - start).total_seconds() / span * 100, f"{day:%b %y}"))
            day += dt.timedelta(days=1)
            continue
        ticks.append(((day - start).total_seconds() / span * 100, f"{day:%d.%m.}"))
        day += dt.timedelta(days=schritt)
    return ticks


def detail_card(marker: Marker | None) -> str:
    """Detailkarte zu einem Marker oder der Hinweis-Platzhalter."""
    if None is marker:
        return (
            f'<div class="panel" id="detailbox" style="{_tone("mut")}">'
            '<p class="hint">Punkt auf der Zeitachse anklicken</p></div>'
        )
    lead = f'<p class="lead" style="margin-bottom:10px">{e(marker.lead)}</p>' if marker.lead else ""
    items = "".join(f"<li>{e(text)}</li>" for text in marker.bullets)
    body = f"<ul>{items}</ul>" if items else ""
    return (
        f'<div class="panel" id="detailbox" style="{_tone(marker.tone)}">'
        f'<div class="phd"><span class="badge">{e(marker.kind)} · '
        f"{marker.when:%d.%m.%Y %H:%M}</span>"
        f'<h3>{e(marker.title)}</h3><p class="lead">{e(marker.actor)}</p></div>'
        f'<div class="pbody">{lead}{body}</div></div>'
    )


def metric_cards(report: Report) -> str:
    """Fluss- und Reibungskennzahlen als Kachelreihe."""
    cards = "".join(
        f'<div class="mc" style="{_tone(m.tone)}">'
        f'<span class="mlab">{e(m.label)}</span>'
        f'<span class="mval">{e(m.value)}</span>'
        f'<p class="mnote">{e(m.note)}</p></div>'
        for m in report.metrics
    )
    return f'<div class="mgrid">{cards}</div>'


def people_ledger(report: Report, mode: str = "owner") -> str:
    """Beteiligte mit Anteilsbalken - Besitzzeit oder Aktionen."""
    ordered = sorted(
        report.people,
        key=lambda item: -(item.owner_pct if mode == "owner" else item.action_pct),
    )
    rows = []
    for person in ordered:
        pct = person.owner_pct if mode == "owner" else person.action_pct
        detail = (
            (f"{person.owner_text} zugewiesen" if person.owner_pct else "nie zugewiesen")
            if mode == "owner"
            else f"{person.comments} Kommentare, {person.changes} Änderungen"
        )
        badge = '<span class="hb">aktuell</span>' if person.is_current else ""
        value = f"{pct:.1f}".replace(".", ",")
        rows.append(
            f'<div class="lrow" style="{_tone("clock" if person.is_current else "pine")}">'
            f'<span class="lsw"></span><div class="ltxt">'
            f'<span class="llab">{e(person.name)}</span>'
            f'<span class="lnm">{e(detail)} · aktiv {e(person.first)} - {e(person.last)}</span>'
            f'<div class="lbar"><span style="width:{pct:.1f}%"></span></div></div>'
            f'<span class="lpct">{value} %</span>{badge}</div>'
        )

    other = "action" if mode == "owner" else "owner"
    label = (
        "Ansicht: Besitzzeit  (umschalten auf Aktionen)"
        if mode == "owner"
        else "Ansicht: Aktionen  (umschalten auf Besitzzeit)"
    )
    active = " act" if mode == "action" else ""
    return (
        f'<button class="toggle{active}" data-mode="{other}">{e(label)}</button>'
        f'<div class="led">{"".join(rows)}</div>'
    )


def _density(segment: Segment) -> str:
    """Beschreibt, wie viel in einer Phase geschrieben und belegt wurde."""
    parts = []
    if segment.comments:
        parts.append(f"{segment.comments} Kommentar" + ("e" if segment.comments > 1 else ""))
    if segment.attachments:
        parts.append(
            f"{segment.attachments} Anhang"
            if segment.attachments == 1
            else f"{segment.attachments} Anhänge"
        )
    return " · ".join(parts)


def duration_bars(report: Report) -> str:
    """Liegezeit je Status - Kalenderzeit hell, Arbeitszeit gefuellt."""
    longest = max((s.gross_seconds for s in report.segments), default=1) or 1
    rows = []
    for segment in report.segments:
        gross = segment.gross_seconds / longest * 100
        net = segment.net_seconds / longest * 100
        density = _density(segment)
        sub = f'<span class="dsub">{e(density)}</span>' if density else ""
        rows.append(
            f'<div class="drow{" long" if segment.long else ""}" '
            f'style="{_tone(segment.tone)}">'
            f'<span class="dnm">{e(segment.status)}{sub}</span>'
            f'<div class="dbar"><span class="g" style="width:{gross:.2f}%"></span>'
            f'<span class="n" style="width:{net:.2f}%"></span></div>'
            f'<span class="dval"><span>{e(segment.gross)}</span> / '
            f'<span style="font-weight:700">{e(segment.net)}</span></span></div>'
        )
    legend = (
        '<div class="legend"><span class="g"><span></span>Kalenderzeit</span>'
        '<span class="n"><span></span>davon Arbeitszeit</span></div>'
    )
    return f'{legend}<div class="dur">{"".join(rows)}</div>'


def findings_cards(report: Report) -> str:
    """Automatisch abgeleitete, belegte Beobachtungen."""
    cards = "".join(
        f'<div class="fc" style="{_tone(f.tone)}">'
        f'<h3 style="margin:0 0 5px;font:700 13.5px/1.25 var(--disp)">{e(f.title)}</h3>'
        f"<p>{e(f.text)}</p></div>"
        for f in report.findings
    )
    return f'<div class="finds">{cards}</div>'


def related_cards(report: Report) -> str:
    """Verwandte und im Text erwaehnte Tickets."""
    cards = "".join(
        f'<a class="rc" href="{e(item["url"])}" target="_blank">'
        f'<span class="rk">{e(item["key"])}</span>'
        + (f'<span class="rs">{e(item["summary"])}</span>' if item.get("summary") else "")
        + f'<span class="ro">{e(item["origin"])}</span></a>'
        for item in report.related
    )
    return f'<div class="rel">{cards}</div>'


def _section(title: str, body: str, note: str = "") -> str:
    """Rahmt einen Abschnitt mit Ueberschrift."""
    hint = f'<span class="hnote">{e(note)}</span>' if note else ""
    return f'<section class="sec"><p class="h">{e(title)}{hint}</p>{body}</section>'


# ---------------------------------------------------------------------------
# Gesamtdokument
# ---------------------------------------------------------------------------
def build_html(report: Report) -> str:
    """Setzt den vollstaendigen Bericht als HTML-Text zusammen.

    Args:
        report:
            Fertiges Anzeigemodell.

    Returns:
        Vollstaendiges HTML-Dokument, self-contained und offline lauffaehig.
    """
    panels = {marker.key: detail_card(marker) for marker in report.markers}
    ledgers = {mode: people_ledger(report, mode) for mode in ("owner", "action")}
    runtime = (
        f"var PANELS={json.dumps(panels, ensure_ascii=False)};"
        f"var LEDGERS={json.dumps(ledgers, ensure_ascii=False)};{SCRIPT}"
    )

    body = (
        masthead(report)
        + _section(
            "Chronologie",
            rail(report)
            + '<button class="toggle" style="margin-top:12px" data-off="1" '
            'data-label-on="Arbeitsfreie Zeit einblenden (Mo-Fr, 8-18 Uhr)" '
            'data-label-off="Arbeitsfreie Zeit ausblenden">'
            "Arbeitsfreie Zeit einblenden (Mo-Fr, 8-18 Uhr)</button>",
            "Zeitachse massstabsgetreu · ×N = Ereignisse an diesem Punkt · "
            "Punkt anklicken zeigt sie einzeln",
        )
        + _section("Kennzahlen", metric_cards(report), "Arbeitszeit = Mo-Fr, 8-18 Uhr")
        + '<div class="grid"><div>'
        + _section("Detail", detail_card(None))
        + _section("Befunde", findings_cards(report), "automatisch abgeleitet, jeder mit Beleg")
        + "</div><div>"
        + _section("Beteiligte", f'<div id="peoplebox">{ledgers["owner"]}</div>')
        + _section("Liegezeit je Status", duration_bars(report))
        + _section("Verwandte Tickets", related_cards(report))
        + "</div></div>"
        + f'<p class="foot">{e(report.key)} · Stand {e(report.generated)} · '
        "Quelle: Jira-Änderungsprotokoll und Kommentare · "
        "erstellt mit retro-from-ticket · INTERN</p>"
    )

    css = re.sub(r"\s+", " ", CSS).strip()
    return (
        "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(report.key)} - Lebenszyklus</title>"
        f"<style>{css}</style></head><body>{body}"
        f"<script>{runtime}</script></body></html>"
    )


def write_report(report: Report, target: pathlib.Path | str | None = None) -> pathlib.Path:
    """Schreibt den Bericht als eine HTML-Datei.

    Args:
        report:
            Fertiges Anzeigemodell.
        target:
            Zieldatei. Vorgabe ist ``<TICKET>.html`` im Arbeitsverzeichnis.

    Returns:
        Pfad der geschriebenen Datei.
    """
    path = pathlib.Path(target) if target else pathlib.Path(f"{report.key}.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" - der Textmodus wuerde unter Windows sonst CRLF schreiben.
    path.write_text(build_html(report), encoding="utf-8", newline="\n")
    return path

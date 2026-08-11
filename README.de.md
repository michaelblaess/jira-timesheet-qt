# jira-timesheet-qt

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <a href="README.md">English</a> ·
  <img src="docs/flags/de.svg" height="13" alt=""> <b>Deutsch</b>
</p>

---

[![Stars](https://img.shields.io/github/stars/michaelblaess/jira-timesheet-qt?logo=github&logoColor=white&color=fbbf24)](https://github.com/michaelblaess/jira-timesheet-qt/stargazers)
[![Issues](https://img.shields.io/github/issues/michaelblaess/jira-timesheet-qt?logo=github&logoColor=white&color=f87171)](https://github.com/michaelblaess/jira-timesheet-qt/issues)
[![Last Commit](https://img.shields.io/github/last-commit/michaelblaess/jira-timesheet-qt?logo=git&logoColor=white&color=3b82f6)](https://github.com/michaelblaess/jira-timesheet-qt/commits/main)
[![License](https://img.shields.io/badge/license-Apache_2.0-3b82f6)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3b82f6?logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41cd52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)

Eine native Desktop-Anwendung (PySide6 / Qt 6) für Stundenzettel aus Jira-Worklogs - inklusive manueller Nacherfassung für Zeiten, die nicht in Jira gebucht sind.

<p align="center">
  <img src="docs/images/teaser.png" width="70%" alt="jira-timesheet-qt">
</p>

> **Haftungshinweis:** Dieses Projekt ist **nicht** von Atlassian entwickelt, unterstützt oder autorisiert. "Jira" und "Atlassian" sind eingetragene Markenzeichen von [Atlassian Corporation](https://www.atlassian.com/). Dieses Werkzeug nutzt die öffentliche Jira-REST-API und steht in keiner Verbindung zu Atlassian.

## TUI oder GUI?

Das ist der native Desktop-Port für die Textual-TUI
[jira-timesheet](https://github.com/michaelblaess/jira-timesheet). Beide bauen auf **demselben
Code** auf - dieselbe Jira-Anbindung, dieselbe Stundenzettel-Logik, manuelle Zeiterfassung,
Feiertagskalender und Excel-/PDF-Export - und liefern deshalb identische Ergebnisse. Beide
laufen unter **Windows, macOS und Linux**. Sie unterscheiden sich nur darin, wie Du mit ihnen
arbeitest, und jede hat echte Stärken:

- **[Terminal (TUI)](https://github.com/michaelblaess/jira-timesheet)** - läuft in jedem
  Terminal, **auch über SSH**, und braucht **keinen Window-Manager**. Das macht sie zur
  natürlichen Wahl auf einem entfernten Rechner oder einem Linux-Server ohne Oberfläche, wo
  ein Desktop schlicht nicht da ist. Tastaturzentriert, leichtgewichtig, mit Retro-Themes -
  und sie kann alles, was diese GUI kann.
- **Desktop (diese Anwendung)** - native Fenster, Menüs und Dialoge, durchgehend mit der Maus
  bedienbar, Spalten per Maus ziehbar, betriebssystemeigene Datei- und Druckdialoge. Die
  komfortable Wahl, wenn Du am Desktop sitzt und ein Fenster-Programm bevorzugst.

Keine ersetzt die andere - nimm die, die zu Deiner Umgebung oder Deinen Vorlieben passt, oder
beide. Sie legen ihre Daten getrennt ab und laufen problemlos nebeneinander.

## Screenshots

Die Anwendung folgt dem hellen oder dunklen Erscheinungsbild und einer einstellbaren Akzentfarbe.

### Listenansicht - sortierbar, durchsuchbar, mit Tagesgruppen

<p align="center">
  <img src="docs/screenshots/main-dark.png" width="49%" alt="Listenansicht (dunkel)">
  <img src="docs/screenshots/main-light.png" width="49%" alt="Listenansicht (hell)">
</p>

### Live-Suche - Filter nach Ticket oder Beschreibung, Treffer hervorgehoben

<p align="center">
  <img src="docs/screenshots/search-dark.png" width="49%" alt="Suchfilter (dunkel)">
  <img src="docs/screenshots/search-light.png" width="49%" alt="Suchfilter (hell)">
</p>

### Kalender- und Jahresansicht

<p align="center">
  <img src="docs/screenshots/calendar-dark.png" width="49%" alt="Kalenderansicht (dunkel)">
  <img src="docs/screenshots/year-dark.png" width="49%" alt="Jahresansicht (dunkel)">
</p>

### Meine Tickets - gruppiert danach, wer am Zug ist

<p align="center">
  <img src="docs/screenshots/board-assigned-dark.png" width="49%" alt="Meine Tickets (dunkel)">
  <img src="docs/screenshots/board-assigned-light.png" width="49%" alt="Meine Tickets (hell)">
</p>

### Meine Aktivitäten - alles, woran Du mitgewirkt hast

<p align="center">
  <img src="docs/screenshots/board-relevant-dark.png" width="49%" alt="Meine Aktivitäten (dunkel)">
  <img src="docs/screenshots/board-relevant-light.png" width="49%" alt="Meine Aktivitäten (hell)">
</p>

### Ticket-Details

<p align="center">
  <img src="docs/screenshots/detail-dark.png" width="55%" alt="Ticket-Details">
</p>

### Einstellungen - Jira-Zugang mit Budget-Feld-Autoerkennung

<p align="center">
  <img src="docs/screenshots/settings-dark.png" width="80%" alt="Einstellungen - Jira-Zugang">
</p>

### Einstellungen - Statuszuordnung der Ticket-Ansichten

<p align="center">
  <img src="docs/screenshots/settings-tickets-light.png" width="80%" alt="Einstellungen - Ticket-Ansichten">
</p>

## Funktionen

- **Jira Cloud &amp; Data Center** - Worklogs über die REST-API; standardmäßig Jira Cloud (v3,
  Basic-Auth mit API-Token), per Schalter auch altes Jira Server/Data Center (v2, Bearer-Token)
- **Budget-Feld automatisch ermitteln** - Bei Jira Cloud findet ein Klick das Budget-Custom-Field
  automatisch (kein manuelles Nachschlagen der Field-ID)
- **Listenansicht** - Tabellarisch mit Kalenderwoche, Wochentag, Tagesgruppen und Soll-/Ist-Stunden;
  die Tagessummen sind über Soll grün und unter Soll rot eingefärbt
- **Live-Suche / Filter** - Filtert beim Tippen nach Ticket-ID oder Beschreibung (`Strg+F`);
  Treffer werden in der Liste hervorgehoben
- **Verstellbare Spalten** - Zieh den Trenner im Spaltenkopf, die Breiten bleiben erhalten;
  ansonsten füllt die Beschreibungsspalte automatisch den restlichen Platz
- **Manuelle Zeiterfassung** - Erfasse Zeiten, die nicht in Jira gebucht sind, über einen Dialog
  (`Strg+N`), bearbeite sie direkt in der Tabelle oder über das Kontextmenü; abgelegt in SQLite,
  farblich markiert in Liste, Excel und PDF
- **Konfigurierbare Export-Spalten** - Jede Spalte lässt sich getrennt für Anzeige und Export
  schalten und im Export frei benennen (Einstellungsseite "Spalten"), inklusive Kunden-Spalte
- **Kalenderansicht** - Monatsgrid mit farbcodierten Tageskacheln; anklickbare Ticket-Links
  öffnen den Detail-Dialog
- **Jahresansicht** - Zwölf Monatskacheln mit Fortschrittsbalken, Prognose, Umsatz-Summen und
  den Top-Tickets je Monat; jedes Ticket ist ein Link zum Detail-Dialog
- **Excel-Export** - Formatierter Stundenzettel mit Logo und Unterschriftszeile
- **PDF-Export** - Adobe-signierbar, Unicode-Schrift
- **Druckvorschau** - Vorschau und Druck des Stundenzettels direkt aus der Anwendung (`Strg+P`)
- **Feiertage** - Deutsche Feiertage pro Bundesland, Lücken-Erkennung
- **Soll/Ist &amp; Prognose** - Arbeitszeitvergleich mit Differenz; Jahres-Prognose mit
  Urlaubstagen und einer Netto-/Brutto-Umsatzprognose (Stundensatz und MwSt einstellbar)
- **Ticket-Details** - Ein modaler Dialog zeigt Status, Typ, Bearbeiter, Komponenten und einen
  Link zum Ticket
- **Ticket-Analyse** - Macht aus einem Ticket einen interaktiven Bericht: maßstabsgetreue
  Zeitachse des Lebenszyklus, Liegezeit je Status (Kalenderzeit gegen echte Arbeitszeit),
  die Beteiligten, Kennzahlen wie Flow-Effizienz und erste Reaktion, dazu Befunde, die
  jeweils ihren Beleg mitbringen. Ergebnis ist eine einzelne HTML-Datei, die offline läuft
  und sich weitergeben lässt (`Strg+T`) Auffällig lange Liegezeiten werden rot markiert, verwandte Tickets zeigen ihren Titel, und der fertige Bericht öffnet sich gleich im Browser.
- **Meine Tickets** - Alle Tickets, die Dir zugewiesen sind, gruppiert danach, wer am Zug ist:
  ich bin dran, andere sind dran, Backlog, live und wartet auf Test, Übergabe, abgeschlossen. Dazu Merkmale für
  Handlungsbedarf, die Liegezeit in Arbeitstagen und drei Diagramme (Zulauf gegen Abgang,
  Bestand, Altersverteilung)
- **Meine Aktivitäten** - Tickets, an denen Du mitgewirkt hast, auch wenn sie jemand anderem
  gehören: kommentiert, erwähnt, bearbeitet oder bebucht, in einem einstellbaren Zeitfenster
- **Mein Team** - Derselbe Blick auf den Ticketstand von Kolleginnen und Kollegen, ohne dass
  die etwas installieren müssen. Gepflegt wird eine Merkliste in den Einstellungen, die Suche
  läuft über den **Namen** - eine Person kann mehrere Jira-Konten führen, und viele Konten
  geben ihre Mailadresse gar nicht heraus. Bewusst **ohne Diagramme**: Durchsatz je Monat wäre
  über eine andere Person eine Leistungskennzahl, und darum geht es hier nicht
- **Pile of Shame** - Markiert Tickets, deren Status Aktivität behauptet, obwohl es seit der
  Schwelle weder eine Änderung noch eine gebuchte Stunde gab. Die zweite Hälfte ist der
  Trick: ein bewusst offengehaltenes Dauerticket mit regelmäßigen Buchungen bleibt draußen,
  eine Ausnahmeliste braucht es nicht
- **Anonymisierung** - Ersetzt Tickets, Beschreibungen, Autoren, Statusnamen und den Jira-Host
  durch Dummy-Werte für sichere Screenshots - die echten Daten bleiben unangetastet
- **Andockbares Log** - Ein anheftbares Meldungsfenster mit dem vollen Verlauf (`Strg+L`)
- **Zoom** - Skaliert die ganze Oberfläche mit `Strg` +/- / 0 oder `Strg` + Mausrad, wie im Browser
- **Worklog-Cache** - Abgeschlossene Monate werden gecacht, die Jahresansicht lädt sofort
- **Zweisprachige Oberfläche** - Deutsch / Englisch
- **Einstellungs-Backup** - Jedes Speichern legt eine rollierende Sicherung und eine goldene
  Kopie an; ein verlorener Jira-Zugang lässt sich beim nächsten Start wiederherstellen

## Installation

### Ein-Klick-Installation

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/michaelblaess/jira-timesheet-qt/main/install.ps1 | iex
```

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/michaelblaess/jira-timesheet-qt/main/install.sh | bash
```

### Download

Lieber als Datei? Hol Dir das aktuelle Archiv von der
[Releases](https://github.com/michaelblaess/jira-timesheet-qt/releases)-Seite, entpack es und
starte die Anwendung. Sie läuft unter **Windows, macOS und Linux**.

## Benutzung

```bash
jira-timesheet-qt              # Anwendung starten
jira-timesheet-qt --demo       # Start mit Beispieldaten, ohne Jira-Zugang
```

Beim ersten Start die Einstellungen öffnen (`Strg+,`) und den **Jira-Zugang** eintragen:

- **Jira-Host-URL** - Cloud: die kanonische `https://deine-firma.atlassian.net`
- **E-Mail / Login** - Cloud: Deine Atlassian-Login-Mail; Data Center: Dein Jira-Benutzername
- **Token** - Cloud: ein API-Token von
  [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens);
  Data Center: ein Bearer-Token (PAT)
- **Jira-Modus** - für Jira Cloud aus lassen, für altes Server/Data Center einschalten
- **Budget-Feld** - bei Cloud mit **Automatisch ermitteln** das Custom-Field automatisch füllen
- **Bundesland** - für die Feiertagsberechnung

Dann `F5` drücken, um die Buchungen des gewählten Monats zu holen.

### Zeiten erfassen, die nicht in Jira stehen

Nicht jede Stunde landet als Worklog in Jira. `Strg+N` öffnet einen Dialog für Datum, Ticket,
Beschreibung, Kunde und Aufwand. Den Aufwand darfst Du so schreiben, wie Du ihn ohnehin
notierst: `3h 30m`, `3:30`, `3,5` oder `45m`.

Diese Einträge liegen in einer eigenen SQLite-Datei (`~/.jira-timesheet-qt/manual-entries.db`)
und **nie** im Jira-Cache. Sie zählen überall mit - Tagessumme, Monatssumme, Soll/Ist,
Kalender, Jahresansicht, Excel und PDF - und sind farblich markiert, damit auf einen Blick klar
ist, was aus Jira kommt und was nicht. Ein Rechtsklick auf eine Zeile öffnet ein Kontextmenü;
Beschreibung und Aufwand eines manuellen Eintrags lassen sich direkt in der Tabelle bearbeiten.

### Ticket-Ansichten einrichten

Die Reiter **Meine Tickets**, **Meine Aktivitäten** und **Mein Team** laden beim ersten
Hinschauen von selbst, `F5` holt sie neu. Alle drei gruppieren nicht nach Statusnamen, sondern
nach der Frage **wer ist am Zug**. Weil jede Jira-Instanz ihre Status anders nennt, muss diese
Zuordnung einmal eingetragen werden: Einstellungen (`Strg+,`), Seite **Tickets**.

Bleiben die Felder leer, ordnet die Anwendung nach Jiras eigener Statuskategorie zu. Das
funktioniert sofort, ist aber grob - Jira kennt nur "neu", "in Arbeit" und "fertig".

| Gruppe | Was dort hingehört | Beispiel |
| --- | --- | --- |
| Ich bin dran | Der Ball liegt bei Dir, es wird gerade gearbeitet | `In Bearbeitung, Im Review` |
| Backlog | Fertig verfeinert, wartet darauf, gezogen zu werden | `Bereit, Eingeplant` |
| Andere sind dran | Wartet auf Freigabe durch jemand anderen - hier hakt man nach | `Wartet auf Freigabe` |
| Live, wartet auf Test | Produktiv gesetzt, muss auf PROD noch getestet werden | `Ausgeliefert, Zur Bewertung` |
| Übergabe | Status, die Jira als **fertig** zählt, obwohl das Ticket noch auf die Live-Setzung wartet | `Zur Übergabe, Deployment offen` |
| Abgeschlossen | Wirklich fertig - reiner Kontrollblick, ohne Handlungsbedarf und ohne Schwelle | `Erledigt, Abgeschlossen` |

**Das Feld "Übergabe" ist das wichtigste.** Ein Status wie "Deployment offen" oder "Zur
Übergabe" liegt in Jira in der Kategorie *Done*. Solche Tickets fallen durch jeden normalen
Filter und werden ohne diesen Eintrag **gar nicht erst abgefragt** - sie fehlen dann
vollständig, ohne dass es auffällt.

Bei **Live, wartet auf Test** gilt eine Sonderregel: Ist der Autor jemand anderes, gehört das Ticket
zurückgegeben und nicht bearbeitet. Bist Du selbst der Autor, gibt es niemanden, dem man es
zurückgeben könnte - dann wandert es zu "Ich bin dran", damit es nicht in einer Gruppe
verstaubt, die "nicht bearbeiten" heißt.

Die **Prioritäten** sind eine Rangfolge, dringendstes zuerst. Sie bestimmt die Sortierung
innerhalb einer Gruppe und, welche Tickets das Merkmal *Priorität* bekommen. Bugs stehen
dabei immer vor allem anderen.

#### Merkmale

Ein Ticket kann mehrere gleichzeitig tragen - deshalb sind es Merkmale und keine weiteren
Gruppen. Eine Schublade könnte jedes Ticket nur einmal einsortieren.

| Merkmal | Bedeutung |
| --- | --- |
| Pile of Shame | Der Status behauptet Aktivität, aber seit der Schwelle gab es weder eine Änderung noch eine gebuchte Stunde |
| Rückgabe | Ausgeliefert, fremder Autor - zurückgeben, nicht bearbeiten |
| verwaist | Seit sehr langer Zeit unverändert (Standard: 180 Tage) |
| Priorität | Priorität in der oberen Gruppe der Rangfolge |
| nachhaken | Wartet auf Freigabe durch jemand anderen |
| blockiert | Ein Vorgänger ist noch offen |

#### Schwellen und Zeitfenster

| Einstellung | Wofür | Standard |
| --- | --- | --- |
| Zeitfenster | Nur für "Meine Aktivitäten". 0 = kein Fenster, dann wird die Liste zum Archiv statt zum Arbeitsvorrat | 90 Tage |
| Verwaist ab | Ab wann das Merkmal *verwaist* gesetzt wird | 180 Tage |
| Schwelle: ich dran | Arbeitstage bis zum Pile of Shame in der eigenen Gruppe | 20 |
| Schwelle: andere | Dasselbe für Tickets, die auf Freigabe warten | 10 |
| Schwelle: Abschluss | Dasselbe für die Abschluss-Gruppe. 0 schaltet die Rolle davon frei | 0 |

Die Zahlen sind eine **Setzung, keine Messung**. Zu klein gewählt trifft der Hinweis alles
und sagt dann nichts mehr - such Dir die Schwelle so, dass eine Handvoll Tickets übrig
bleibt, nicht die halbe Liste.

Gerechnet wird in **Arbeitstagen** (Mo-Fr, 8-18 Uhr), nicht in Kalendertagen. Ein Ticket, das
über ein langes Wochenende liegt, ist nicht drei Tage vernachlässigt worden.

### Mein Team einrichten

Der Reiter **Mein Team** zeigt den Ticketstand von Kolleginnen und Kollegen - dieselbe
Gruppierung wie bei den eigenen, nur aus deren Sicht. Wer dort erscheint, steht in einer
Merkliste: Einstellungen (`Strg+,`), Seite **Mein Team**.

Gesucht wird über den **Namen**, nicht über die Mailadresse. Das ist kein Schönheitsfehler,
sondern gemessen: In einer echten Instanz gab ein Konto mit hinterlegter Adresse null Tickets
her, ein zweites Konto derselben Person ohne sichtbare Adresse dagegen einhundertzwanzig.
Nicht auslesbar heißt eben nicht, dass keine Adresse da ist - es ist eine Frage der
Profil-Sichtbarkeit.

Die Trefferliste zeigt je Konto die Zahl offener Tickets und den letzten Kontakt, das zuletzt
benutzte Konto steht oben. **Über das aktuelle Konto entscheidet das Datum, nicht die Menge**:
in derselben Messung trug das aktive Konto zwei Tickets, ein stillgelegtes achtzehn. Führt eine
Person mehrere Konten, markierst Du sie mit `Strg` alle zusammen und übernimmst sie als eine
Person. Ein später gefundenes Konto legst Du unter demselben Anzeigenamen dazu.

Bewusst weggelassen: **die Auswertung**. Die Diagramme zeigen Durchsatz je Monat, und das wäre
über eine andere Person eine Leistungskennzahl. Auch die Buchungszeiten werden für fremde
Tickets gar nicht erst abgefragt, weshalb dort kein Pile of Shame entsteht. Der Maßstab ist
einfach: Was das Kanban-Board in Jira ohnehin zeigt, darf diese Ansicht auch zeigen.

### Anonymisieren für Screenshots

*Ansicht -> Daten anonymisieren* (auch in der Toolbar) ersetzt Tickets, Beschreibungen, Autoren
und den Jira-Host in allen Ansichten und im Log durch neutrale Dummy-Werte. Deine echten Daten
bleiben im Cache und kehren zurück, sobald Du wieder umschaltest - praktisch für Screenshots
und Demos.

## Haftungshinweis beim ersten Start

Beim ersten Start erscheint ein Hinweis, der bestätigt werden muss - ohne Zustimmung beendet sich das Programm. Grund: Das Werkzeug liest über die Jira-REST-API Arbeitszeit-Buchungen aus einem fremden System. Welche Vorgänge und Worklogs dabei sichtbar werden, bestimmen allein die Berechtigungen des verwendeten Zugangs, und je nach Rechtevergabe gehören dazu auch Buchungen anderer Personen. Mit der Bestätigung erklärst Du, das Programm nur gegen dazu berechtigte Jira-Instanzen einzusetzen und nur Daten auszuwerten, zu deren Verarbeitung Du befugt bist.

Die Zustimmung wird in `~/.jira-timesheet-qt/disclaimer.json` festgehalten und nur erneut abgefragt, wenn sich der Wortlaut ändert. Den Speicherort zeigt der Reiter "Speicherort" im Einstellungsdialog - dort lässt sich die Datei auch löschen, um den Hinweis wieder anzuzeigen.

Die Software wird kostenlos und ohne jede Gewährleistung bereitgestellt ("as is"), wie in Abschnitt 7 der Apache License 2.0 geregelt. Die Haftung des Autors (Michael Blaess) für Schäden aus der Nutzung ist im gesetzlich zulässigen Rahmen ausgeschlossen. Die Haftung für Vorsatz und grobe Fahrlässigkeit, für die Verletzung von Leben, Körper oder Gesundheit sowie nach zwingendem Produkthaftungsrecht bleibt unberührt.

## Tastenkürzel

| Taste | Aktion |
| --- | --- |
| `F5` | Buchungen des Monats holen (bzw. das Jahr in der Jahresansicht) |
| `Strg+F` | Suchfeld fokussieren |
| `Strg+N` | Manuelle Zeit erfassen |
| `Strg+D` | Ticket-Details anzeigen |
| `Strg+T` | Ticket-Analyse (interaktiver Bericht als HTML-Datei) |
| `Strg+E` | Excel-Export |
| `Strg+Umschalt+E` | PDF-Export |
| `Strg+P` | Druckvorschau |
| `Strg+L` | Meldungsfenster ein-/ausblenden |
| `Strg` +/- / 0 | Zoom rein / raus / zurücksetzen (auch `Strg` + Mausrad) |
| `Strg+,` | Einstellungen |
| `F1` | Info |
| `Strg+Q` | Beenden |

## Konfiguration

Die Einstellungen liegen in `~/.jira-timesheet-qt/settings.json`:

| Einstellung | Beschreibung | Standard |
| --- | --- | --- |
| Jira-Host | URL der Jira-Instanz (Cloud: `...atlassian.net`) | - |
| Token | API-Token (Cloud) oder Bearer-Token (Data Center) | - |
| E-Mail | Atlassian-Login (Cloud) oder Jira-Benutzername (Data Center) | - |
| Jira-Modus (Legacy-API) | Aus = Jira Cloud (v3), an = Data Center (v2) | aus |
| Budget-Custom-Field | Custom-Field-ID; Cloud unterstützt **Automatisch ermitteln** | customfield_... |
| Bundesland | Für die Feiertagsberechnung | SN |
| Soll-Stunden/Tag | Arbeitsstunden pro Tag | 8,0 |
| Max. Jahresstunden | Obergrenze für den Fortschrittsbalken | 1720 |
| Urlaubstage | Für die Jahresprognose | 30 |
| Stundensatz | Netto, für die Umsatzprognose | 0 (aus) |
| MwSt-Satz | Prozent, für die Brutto-Berechnung | 19 |
| Soll-Stunden im Export | Zeigt die Soll-Zeile in Excel/PDF | falsch |
| Ticket-Links im Export | Hyperlinks in Excel/PDF | falsch |
| Standard-Kunde | Kunde für alle aus Jira geholten Einträge | Vertrieb |
| Manuelle Einträge markieren | Färbt manuelle Zeiten in Liste, Excel und PDF | wahr |
| Tagessummen einfärben | Färbt Tagessummen nach Soll/Ist | wahr |
| Spalten | Je Spalte: Anzeige, Export und Bezeichnung | alle an |
| Status "Ich bin dran" | Statusnamen für die eigene Arbeitsgruppe | leer |
| Status "Backlog" | Statusnamen für den Arbeitsvorrat | leer |
| Status "Andere sind dran" | Statusnamen für Tickets in fremder Hand | leer |
| Status "Rückgabe" | Statusnamen für ausgelieferte Tickets zur Bewertung | leer |
| Status "Übergabe" | Von Jira als fertig gezählte Status, die noch auf die Live-Setzung warten | leer |
| Status "Abgeschlossen" | Wirklich fertige Status - reiner Kontrollblick | leer |
| Prioritäten | Rangfolge, dringendstes zuerst | leer (Reihenfolge aus Jira) |
| Zeitfenster | Rückblick für "Meine Aktivitäten" | 90 Tage |
| Verwaist ab | Schwelle für das Merkmal *verwaist* | 180 Tage |
| Pile-of-Shame-Schwellen | Arbeitstage je Gruppe, 0 schaltet ab | 20 / 10 / 0 |
| Theme / Akzent / Zoom | Erscheinungsbild | System / Orange / 100 % |
| Sprache | Oberflächensprache (de / en) | de |

## Verhältnis zur Textual-Fassung

Der Code (`models/`, `services/`, `i18n.py`) ist aus
[jira-timesheet](https://github.com/michaelblaess/jira-timesheet) **kopiert, nicht
eingebunden** - eine Änderung dort kommt hier nicht automatisch an. Das ist gewollt: Eine
Einbindung würde das gesamte TUI-Framework mitziehen. Damit die beiden Kerne nicht unbemerkt
auseinanderlaufen:

```bash
uv run poe core-sync      # vergleicht beide Kerne und meldet Abweichungen
```

Beide Anwendungen legen ihre Dateien getrennt ab (`~/.jira-timesheet-qt` bzw.
`~/.jira-timesheet`) und lassen sich parallel benutzen.

## Tech-Stack

- [Python](https://python.org) >= 3.12
- [PySide6](https://doc.qt.io/qtforpython/) - Qt-6-Bindings (LGPL)
- [qtawesome](https://github.com/spyder-ide/qtawesome) - Material-Design-Icons
- [httpx](https://www.python-httpx.org) - asynchroner HTTP-Client
- [openpyxl](https://openpyxl.readthedocs.io) - Excel-Export
- [fpdf2](https://py-pdf.github.io/fpdf2) - PDF-Export
- [holidays](https://python-holidays.readthedocs.io) - Feiertagsberechnung

## Entwicklung

Die Entwicklungsumgebung aufsetzen (das ist für Mitwirkende, nicht zum Installieren der App):

```bash
git clone https://github.com/michaelblaess/jira-timesheet-qt.git
cd jira-timesheet-qt
./bootstrap.ps1        # Dev-Umgebung mit uv einrichten (Linux/macOS: ./bootstrap.sh)
uv run poe run         # aus dem Quellcode starten
uv run poe test        # Testsuite
uv run poe lint        # ruff + mypy (strict)
```

## Lizenz

Apache License 2.0, siehe [LICENSE](LICENSE).

---

> **Markenhinweis:** "Jira" ist ein eingetragenes Markenzeichen der
> [Atlassian Corporation](https://www.atlassian.com/). Dieses Projekt steht in keiner
> Verbindung zu Atlassian, wird von Atlassian nicht unterstützt und nicht gesponsert.

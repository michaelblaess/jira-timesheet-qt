# jira-timesheet-qt - Oberflächenkonzept

Desktop-GUI für Stundenzettel aus Jira-Worklogs, auf PySide6. Nachfolger der
Textual-TUI [jira-timesheet](https://github.com/michaelblaess/jira-timesheet) (v1.14.0).

Stand: 26.07.2026. Dieses Dokument beschreibt den Entwurf, nicht den Ist-Zustand.

---

## Leitsätze

1. **Das ist kein Port, sondern ein Neuentwurf.** Ein großer Teil der TUI besteht aus
   Kompensationen für Terminal-Grenzen. Die wandern nicht mit.
2. **Man soll der Anwendung nicht ansehen, dass Qt darunter liegt.** Kein graues
   Standard-Widget-Gesicht, keine Menüleiste im Stil von 2005.
3. **Entzippen, starten, läuft.** Auf Windows, macOS und Linux, ohne dass jemand etwas
   nachinstalliert. Diese Anforderung hat gegen Electron und Tauri entschieden und bleibt
   das Ausschlusskriterium für jede weitere Entscheidung.
4. **Der fachliche Kern bleibt unangetastet.** `models/`, `services/`, `i18n.py` und die
   Exporter sind unverändert aus der TUI übernommen und kennen keine Oberfläche.

---

## Woran man eine Qt-Anwendung normalerweise erkennt

Bestandsaufnahme dessen, was vermieden werden muss - jeder Punkt ist eine Design-Vorgabe:

| Verräter | Gegenmaßnahme |
| --- | --- |
| Menüleiste mit Datei/Bearbeiten/Ansicht | keine `QMenuBar`, stattdessen Seitenleiste und Kontextaktionen |
| Reiter eines `QTabWidget` | Navigation über die Seitenleiste, Inhalte im `QStackedWidget` |
| Standard-Scrollbars | eigene, schmale, überlagernde Scrollbars per QSS |
| 3D-Rahmen an Schaltflächen, Fokus-Rechtecke | flaches QSS, eigener Fokus-Stil |
| Systemschriftart in Standardgröße | Manrope und JetBrains Mono werden mitgeliefert und per `QFontDatabase` geladen |
| `QMessageBox` und Standard-Dialoge | eigene Dialoge im Design der Anwendung |
| Qt-Standard-Symbole | eigene SVG-Symbole, farblich an das Thema gebunden |
| `QHeaderView` im Werksdesign | gestylter Kopf, eigene Sortierpfeile |
| Der Hinweis "About Qt" | `QApplication.aboutQt` wird nirgends verwendet |

Der größte einzelne Hebel ist die **Titelleiste** - siehe offene Entscheidung E1.

---

## Designsprache

Übernommen aus dem PRECISION-Design-System der GitHub-Pages-Seiten
(`docs/css/precision.css`), damit Web-Auftritt und Anwendung zusammengehören. Die Werte
sind dort bereits erprobt und werden 1:1 zu QSS-Variablen.

**Dunkel (Vorgabe)**

```
Hintergrund     #0f1114   Flächen  #171a1f   Erhöht  #242930
Rahmen          #2a2f38   Hover    #3d4450
Text            #e8ecf1   Sekundär #9ba3b0   Tertiär #6b7280
Akzent          #3b82f6   Hover    #60a5fa
Grün #34d399    Orange #fbbf24    Rot #f87171    Violett #a78bfa
```

**Hell**

```
Hintergrund     #ffffff   Flächen  #f8f9fb   Erhöht  #ffffff
Rahmen          #e2e5ea   Hover    #c8cdd5
Text            #111318   Sekundär #5f6775   Tertiär #8b929e
Akzent          #2563eb   Hover    #3b82f6
```

**Weitere Größen:** Radien 6/10/16 px, Übergang 0,3 s `cubic-bezier(0.4, 0, 0.2, 1)`,
Schrift Manrope für die Oberfläche, JetBrains Mono für Zahlen, Ticketschlüssel und Zeiten.

Beide Themen sind zur Laufzeit umschaltbar, Vorgabe folgt der Systemeinstellung.

---

## Fensteraufbau

```
┌───────────────────────────────────────────────────────────────────────┐
│  ○ ○ ○   Juli 2026                                   ⌄ Suche    ⚙  ◐  │  Kopfzeile
├──────────┬────────────────────────────────────────────────────────────┤
│          │                                                            │
│  Liste   │   Mo  Di  Mi  Do  Fr        │  PROJ-101                   │
│  Kalender│   ─────────────────────     │  ─────────────────────────   │
│  Jahr    │   [Stundenzettel-Inhalt]    │  Sitefinity Security ...     │
│          │                             │                              │
│  ─────   │                             │  Datum      23.07.2026       │
│  Juni    │                             │  Dauer      0,5 h            │
│  Mai     │                             │  Autor      Michael          │
│  April   │                             │                              │
│          │                             │  [ Bearbeiten ]  [ Löschen ] │
│          │                             │                              │
│  ─────   │                             │                              │
│  38,5 h  │                             │                              │
└──────────┴─────────────────────────────┴──────────────────────────────┘
   Seitenleiste        Inhalt (QStackedWidget)      Detail (einblendbar)
```

- **Kopfzeile** trägt den Zeitraum als Überschrift, Monatsnavigation, Suche, Einstellungen
  und den Themenumschalter. Ersetzt Menüleiste und Fußzeile der TUI.
- **Seitenleiste** schaltet zwischen Liste, Kalender und Jahr um und zeigt darunter die
  zuletzt geöffneten Monate sowie die Monatssumme. Einklappbar auf reine Symbole.
- **Inhalt** ist ein `QStackedWidget`, kein `QTabWidget` - kein Reiter zu sehen.
- **Detailbereich** rechts, einblendbar. Ersetzt den Modal-Dialog der TUI: die Auswahl in
  der Tabelle aktualisiert ihn unmittelbar.

Fenstergröße, Seitenleistenbreite, Detailbreite und Spaltenbreiten werden über `QSettings`
gemerkt.

---

## Was aus der TUI verschwindet

| TUI | Warum sie dort so ist | Hier |
| --- | --- | --- |
| 16 Einzelbuchstaben-Kürzel mit Fußzeilen-Erklärung | keine Menüleiste verfügbar | Symbolschaltflächen mit Tooltip, Standardkürzel (Strg+S, F5), Befehlspalette über Strg+K |
| Blinkende Fußzeile als Hinweis auf die nächste Aktion | kein Platz für Hinweistext | Leerzustand mit erklärendem Text und Schaltfläche |
| Detailansicht als Modal-Bildschirm | ein Bildschirm zur Zeit | Detailbereich, dauerhaft sichtbar |
| Jahresansicht als Modal-Bildschirm | dito | eigene Ansicht in der Seitenleiste |
| Manuelle Erfassung als Dialog | Tabellenzellen nicht editierbar | **direkt in der Tabelle tippen** (`QStyledItemDelegate`) |
| Selbstgebaute Spaltenbreiten-Logik (263 Zeilen) | Textual kann das nicht | `QHeaderView` kann es |
| Log-Panel mit eigenem Splitter | festes Layout | `QDockWidget`, ausblendbar, Position wird gemerkt |
| Anonymisierung per Tastendruck | für Bildschirmfotos | bleibt, als Schalter in den Einstellungen |

---

## Was dazukommt

Möglichkeiten, die das Terminal nicht hergab - nach Nutzen sortiert:

1. **Druckvorschau** (`QPrintPreviewDialog`). Bei einem Stundenzettel die naheliegendste
   Funktion überhaupt, in der TUI nur über den Umweg PDF-Export erreichbar.
2. **Inline-Bearbeitung** in der Tabelle. Für die manuelle Nacherfassung der größte
   Gewinn an Bedienbarkeit.
3. **Rückgängig und Wiederherstellen** über `QUndoStack`, besonders beim manuellen
   Erfassen.
4. **Diagramme** - Stunden pro Woche, Verteilung auf Vorgänge.
5. **Zwei Monate nebeneinander** vergleichen.
6. **Ziehen und Ablegen** von Einträgen im Kalender, um sie auf einen anderen Tag zu legen.

Punkte 1 bis 3 gehören in den ersten Ausbau, 4 bis 6 sind Kür.

---

## Offene Entscheidungen

### E1 - Eigene Titelleiste?

Die native Titelleiste ist der stärkste verbleibende Hinweis auf ein Standard-Toolkit.
Moderne Anwendungen (VS Code, Spotify, Figma) zeichnen sie selbst.

- **Dafür:** der mit Abstand größte Effekt für Leitsatz 2.
- **Dagegen:** Verschieben, Größenänderung, Andocken an Bildschirmränder und
  Maximieren müssen selbst implementiert werden. Unter Windows lässt sich das
  Andocken über die WinAPI zurückholen, unter Wayland ist die Lage unklar. Das
  berührt Leitsatz 3 unmittelbar.

**Vorschlag:** Stufe 1 des Prototyps mit nativer Titelleiste und vollständigem QSS bauen.
Wenn das Ergebnis schon un-Qt genug aussieht, bleibt es dabei. Sonst Stufe 2 als
abgegrenztes Experiment, zuerst unter Linux geprüft.

### E2 - qasync oder QThread?

Der Jira-Abruf ist heute `async` über httpx. Qt bringt eine eigene Ereignisschleife mit.
`qasync` legt asyncio auf die Qt-Schleife, `QThread` mit Signals wäre der Qt-eigene Weg.
Da hier nur wenige Netzwerkaufrufe betroffen sind, ist die Entscheidung überschaubar -
im Prototyp beide Varianten an einem echten Abruf messen.

### E5 - Schriften mitliefern

Manrope und JetBrains Mono liegen in den GitHub-Pages nur als **woff2** vor, was Qt
nicht laden kann. Für `resources/fonts/` werden TTF oder OTF gebraucht. Solange sie
fehlen, greift die Rückfallkette (unter Windows 11: Segoe UI Variable Text und Cascadia
Code) - das sieht gut aus, ist aber je nach Betriebssystem verschieden.

### E3 - Wie weit trägt QSS?

Ob sich die Designsprache vollständig in QSS abbilden lässt oder ob einzelne Stellen
eigenes Zeichnen brauchen (`QStyledItemDelegate`, `paintEvent`), zeigt sich erst am
laufenden Bild. Zuerst an der Tabelle prüfen, dort ist der Anspruch am höchsten.

### E4 - Startet es auf einem nackten Linux?

Die wichtigste offene Frage überhaupt, weil eine negative Antwort die Toolkit-Wahl kippt.
Qt lädt sein `xcb`-Plattform-Plugin, das gegen System-Bibliotheken linkt. Ob Nuitka die
mitnimmt, ist ungeprüft.

```bash
./compile-linux.sh
docker run --rm -v $PWD/dist:/app ubuntu:22.04 /app/jira-timesheet-qt --version
```

**Dieser Test kommt vor jeder weiteren Ausbaustufe.**

---

## Reihenfolge

**Stufe 0 - Fundament** (erledigt am 26.07.2026)

- [x] `bootstrap`- und `run`-Skripte für beide Plattformen
- [x] Hauptfenster mit Kopfzeile, Seitenleiste, Liste und Detailbereich
- [x] QSS für beide Themen, Umschalten zur Laufzeit
- [x] Schriftauswahl mit Rückfallkette (Manrope und JetBrains Mono fehlen noch als TTF)
- [x] Tabelle über `QAbstractTableModel` und `QSortFilterProxyModel`, Beispieldaten über `--demo`
- [ ] `compile-*`-Skripte auf PySide6
- [ ] **E4 beantworten** - Linux-Test gegen ein nacktes Ubuntu (zurückgestellt)
- [ ] Artefaktgröße messen und im `qt-specialist` festhalten

**Stufe 1 - Tragfähigkeit zeigen** (erledigt am 26.07.2026)

- [x] Tabelle mit `QAbstractTableModel` und `QSortFilterProxyModel`
- [x] Seitenleiste, Kopfzeile, Detailbereich
- [x] Jira-Abruf angebunden - **E2 entschieden: QThread**, kein qasync
- [x] Haftungshinweis beim ersten Start

**Stufe 2 - Gleichstand mit der TUI** (erledigt am 26.07.2026)

- [x] Kalender- und Jahresansicht
- [x] Einstellungen samt Speicherort-Bereich, Info-Dialog
- [x] Excel- und PDF-Export, Druckvorschau
- [x] Absturzschutz als Qt-Gegenstück zum CrashGuard
- [x] Meldungsfenster als `QDockWidget`
- [ ] Inline-Bearbeitung und Rückgängig-Funktion
- [ ] Manuelle Zeiterfassung (Dialog fehlt noch, die Daten werden bereits gelesen)

**Stufe 3 - darüber hinaus**

- [ ] Diagramme, Monatsvergleich, Ziehen und Ablegen
- [ ] **E1 entscheiden**

---

## Übernommen und bewusst nicht übernommen

**Übernommen** (unverändert aus jira-timesheet v1.14.0): `models/`, `services/`,
`i18n.py` samt `locale/`, sowie die Tests `test_models`, `test_services`,
`test_manual_entries`.

**Bewusst nicht übernommen:** `app.py`, `widgets/`, `screens/`, `app.tcss`, `__main__.py`
und alle Textual-Abhängigkeiten.

**Getrennte Nutzerdaten:** Die Anwendung legt ihre Dateien unter `~/.jira-timesheet-qt`
ab, nicht unter `~/.jira-timesheet`. So laufen TUI und GUI nebeneinander, ohne sich
gegenseitig die Einstellungen zu überschreiben. Ob am Ende migriert oder zusammengeführt
wird, entscheidet sich, wenn die GUI die TUI ablöst.

**Haftungshinweis:** Pflicht in jeder Anwendung. Der Wortlaut ist derselbe wie in der TUI
und stammt aus `textual-widgets`. Weil dieses Paket `textual` mitzieht, wird es hier
**nicht** als Abhängigkeit aufgenommen - der Text wird kopiert. Sobald es eine zweite
Qt-Anwendung gibt, gehört er in ein gemeinsames Paket ohne Oberflächen-Abhängigkeit,
damit die Fassungen nicht auseinanderlaufen.

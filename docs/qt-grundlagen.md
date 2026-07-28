# Qt-Grundlagen: Widgets, Grid, Charts, Themes, Architektur und Styleguide

Grundlagendokument fuer den Bau konservativer, enterprise-tauglicher PySide6-Anwendungen.
Ausgangspunkt ist der Port von jira-timesheet nach Qt, das Dokument gilt aber fuer alle
weiteren Qt-Werkzeuge.

Stand: 27.07.2026. Jeder nicht-triviale Befund ist belegt (Qt-Doku, PyPI-Metadaten, Repo-LICENSE,
Foren-Threads) oder ausdruecklich als **unverifiziert** markiert. Vermutungen stehen nur im
Abschnitt "Offene Fragen", nicht im Fakten-Teil. Grundlage: fuenf parallele Recherchestraenge plus
der gelesene Stand von `src/jira_timesheet_qt/ui/theme.py`.

---

## 0. Kernentscheidungen auf einen Blick

| Thema | Entscheidung | Warum |
| --- | --- | --- |
| Binding | **PySide6** (nicht PyQt6) | PyQt6 ist GPL, PySide6 ist LGPL - passt zu Apache-2.0 |
| Charts | **PyQtGraph (MIT)**, Matplotlib (BSD) fuer Statik, QPainter fuer Sparklines | **QtCharts ist GPL** - siehe Abschnitt 3, harte Warnung |
| Grid | Bordmittel-Model/View, Gruppierung als handgebautes QTreeView-Modell | Kein freies, gepflegtes "Super-Grid" fuer PySide6 |
| Fehlende Widgets | **superqt (BSD-3)** | Range-/Labeled-Slider, Collapsible, searchable Combos - nuechtern |
| Icons | **QtAwesome (MIT)** + eigene SVG-Paare fuer App-Symbole | Loest das fehlende `currentColor` (Laufzeit-Umfaerbung) |
| Theme-Basis | **Entschieden (E1, 27.07.2026): Fusion nativ + QPalette + duennes Struktur-QSS** | Klassisch, leicht verstaendlich, wartungsarm - Enterprise vor Distinktion |
| Design-System | Token-Dataclass mit **Spacing- und Typo-Scale**, ein `theme.qss.tmpl` | Genau der fehlende Baustein zum heutigen `theme.py` |
| App-Architektur | **MVP / Humble View** + ViewModels, Model/View nur fuers Grid | Qt Model/View ist keine App-Architektur |
| Widgets bauen | **Handgeschrieben + geteilte Builder**, kein Qt Designer als Default | Erzwingt Konsistenz |
| Styleguide | **Eigene Gallery-App** (`ui/gallery/`), die echtes QSS + echte Widgets zieht | Lebender Styleguide statt Mockup |
| Verboten | PyQt-/PySide6-Fluent-Widgets (GPL/kommerziell), pyqtconfig (GPL), QtCharts (GPL) | Lizenz-Dealbreaker fuer Apache-2.0 |

---

## 1. Befund am aktuellen Stand (theme.py)

Bevor die Recherche greift, der konkrete Ist-Zustand, weil Deine Beobachtung "die Optik ist
sehr uneinheitlich" strukturelle Ursachen hat:

**Was schon ein System ist:**
- Echte Farb-Tokens (`Palette`-Dataclass, Dark/Light), QSS wird per f-String daraus erzeugt.
- Button-Varianten ueber `[variant="primary|secondary|ghost"]` - der richtige Ansatz.
- Radien als Konstanten (`RADIUS_SM/MD/LG`).

**Woher die Inkonsistenz strukturell kommt:**
1. **Kein Spacing-Scale.** Paddings sind pro Regel handgesetzt und driften: `8px 16px`, `6px 14px`,
   `9px 12px`, `7px 10px`, `8px 12px`, `9px 10px`. Es gibt keine Stufen, an die man sich haelt.
2. **Kein Typografie-Scale.** Schriftgroessen verstreut ueber die ganze Datei: 11, 12, 13, 15, 17,
   19, 20, 22, 26 px - ohne definierte Stufen. Jeder Screen erfindet seine eigene Groesse.
3. **Styling fast nur ueber `#objectName`.** Header, Sidebar, Detail, Settings, About, Summary -
   jeder Bereich hat eigene ID-Selektoren statt geteilter Komponenten-Klassen. Eine neue Maske
   bringt zwangslaeufig neue, leicht abweichende Regeln mit. Genau das erzeugt den Flickenteppich.

**Kurzdiagnose:** Farben sind ein System, Abstaende und Typografie noch nicht - und Komponenten
werden nicht wiederverwendet, sondern pro Screen neu gestylt. Der Styleguide (Abschnitt 8) setzt
genau hier an.

---

## 2. Widget-Set: was bulletproof ist, wo es klemmt

Empfohlenes Standard-Set. Belege in den Qt-6-Docs (doc.qt.io), Details siehe die
Stolperstein-Spalte.

| Bedarf | Widget | Wichtigster Vorbehalt |
| --- | --- | --- |
| Datumsfeld | `QDateEdit` (+ `setCalendarPopup`) | Popup ist intern eine QTableView - globale `QTableView::item`-Regeln lecken in die Tageszellen. Eigenen `QCalendarWidget`-Block schreiben (haben wir gelernt) |
| Datum+Zeit / Zeit | `QDateTimeEdit` / `QTimeEdit` | Spin-Pfeile brauchen eigene Icons je Theme |
| Kalender solo | `QCalendarWidget` | Runde Aussenecken evtl. nur ueber `WA_TranslucentBackground` im Code, nicht QSS (unverifiziert) |
| Third-Party-DatePicker | **keiner empfohlen** | Kein nachweisbar besserer, permissiv lizenzierter PySide6-Picker gefunden - bei Bordmittel bleiben |
| Tabs | `QTabWidget` | `setTabsClosable` + `tabCloseRequested` selbst behandeln (kein Auto-Remove), `setMovable(True)` opt-in |
| Andockbare Bereiche | `QMainWindow` + `QDockWidget`, `saveState`/`restoreState` | **Eindeutiger `objectName` je Dock UND Toolbar**, State versionieren - sonst schlaegt `restoreState` still fehl |
| Menues | `QMenuBar` / `QMenu` / `QAction` | Kontextmenue = `setContextMenuPolicy(CustomContextMenu)` + `customContextMenuRequested`, Proxy->Source mappen, `triggered` sendet ein bool mit |
| Toolbars | `QToolBar` + `QToolButton` | Eindeutiger `objectName`, `menu-indicator`-Pfeil ausblenden |
| Assistent / Schritte | `QWizard`, sonst `QStackedWidget` | QWizard-Chrome nur teilweise per QSS steuerbar, AeroStyle zieht natives Windows-Theming |
| Seitenwechsel | `QStackedWidget` | Reiner Container, keine Styling-Flaeche |
| Resize-Bereiche | `QSplitter` | Explizite `::handle`-Groesse setzen, sonst unter QSS unsichtbar duenn |
| Spin/Combo/Check/Scrollbar/Header | Unterelemente einzeln stylen | QSS kennt **kein `currentColor`** - ein Icon je Theme, und jede `url()` muss auf Disk existieren |
| Baeume / Listen (Daten) | `QTreeView` / `QListView` / `QTableView` + Model | Item-basierte `*Widget` nur fuer kleine statische Daten, `::branch` braucht eigene Bilder |
| Status / Fortschritt | `QStatusBar` / `QProgressBar` | `min==max==0` = Busy-Modus |
| Toast / Meldung | **kein eingebautes In-Fenster-Toast** | Selbst bauen (frameless QWidget + Fade + Timer) oder `pyqttoast` (MIT) |
| Modale Dialoge | `QMessageBox` / `QDialog` / `QInputDialog` / `QFileDialog` | `exec()` blockiert - Deadlock im Headless-Test. Validierung in reine Methode trennen, nativer QFileDialog ignoriert QSS |

**Wiederkehrende QSS-Fallen (belegt an unserem eigenen Fenster):**
- `QWidget { background-color: ... }` faerbt auch jedes `QLabel` - `QLabel { background: transparent; }` dagegen.
- Ein umbrechendes `QLabel` (`setWordWrap`) wird in der Feldspalte eines `QFormLayout` abgeschnitten - Hinweistexte einspaltig ueber die volle Breite.
- `url()` braucht Vorwaerts-Schraegstriche, auch unter Windows (`ICON_DIR.as_posix()`).
- Fehlt eine `url()`-Datei, zeichnet Qt **still** wieder seine Standardpfeile. Deshalb: Test, der jede `url()` im erzeugten QSS gegen das Dateisystem prueft.

---

## 3. Charts + Lizenz: die wichtigste Warnung

**QtCharts, QtDataVisualization und QtGraphs sind GPLv3-oder-kommerziell, nicht LGPL.**
Beleg: die offizielle Qt-Moduldoku sagt woertlich fuer alle drei "available under commercial
licenses ... In addition, it is available under the GNU General Public License, version 3" -
ohne LGPL (doc.qt.io/qt-6/qtcharts-index.html, qtdatavisualization-index.html, qtgraphs-index.html).
Die Kern-Module (QtCore/Gui/Widgets) sind LGPL, diese Visualisierungsmodule ausdruecklich nicht
(doc.qt.io/qt-6/licensing.html, bestaetigt von einem Qt-Moderator im Forum).

Das PySide6-Addons-Wheel traegt ein pauschales `LGPL-3.0 OR GPL-2.0 OR GPL-3.0`-Klassifikat, das
gilt aber fuer alle ~40 Module gemeinsam und ist Verpackungs-Metadatum, keine Pro-Modul-Freigabe der
gewrappten C++-Bibliothek. GPL hat - anders als LGPL - **keine Dynamic-Linking-Ausnahme**, das
Linken zur Laufzeit genuegt. Ob die Qt Company die gebuendelte QtCharts-Binary im Wheel gesondert
unter LGPL stellt, liess sich aus keiner autoritativen Quelle bestaetigen. Das ist **unverifiziert
und als echtes Risiko zu behandeln, nicht als gruenes Licht**.

**Konsequenz fuer Apache-2.0-Repos:** `PySide6.QtCharts`, `PySide6.QtDataVisualization` und
`PySide6.QtGraphs` **nicht** einsetzen (ausser mit kommerzieller Qt-Lizenz oder schriftlicher
Klarstellung der Qt Company). Beide Altmodule sind ausserdem seit Qt 6.10 deprecated.

**Lizenzsaubere Alternativen:**

| Anwendungsfall | Empfehlung | Lizenz | Vorbehalt |
| --- | --- | --- | --- |
| Interaktive Linien-/Zeitreihen-/Finanzcharts, Live-Updates | **PyQtGraph** | **MIT** | Kein eingebautes Theme-System, Candlesticks als kleines eigenes Item |
| Statisch, publikationsreif, Export PDF/SVG, viele Typen | Matplotlib (`FigureCanvasQTAgg`) | BSD/PSF | Langsamer fuer Realtime, Nuitka braucht Backend-/Anti-Bloat-Fix |
| Winzige Sparklines / Balken / Heat-Streifen in Zellen | Eigenes `QPainter`-Widget | LGPL via Qt | Achsen/Tooltips selbst bauen, nur fuer einfache Formen |
| Web-Dashboard / bestehende JS-Charts (ECharts/Plotly) | QtWebEngine + JS-Lib | QtWebEngine LGPL, JS-Libs Apache/MIT | Schwer (Chromium), grosses Bundle, am schwersten mit Nuitka |
| QtCharts / QtDataVisualization / QtGraphs | **meiden** | **GPL/kommerziell** | Wuerde die Binary GPLv3 machen, ausserdem deprecated |

**Empfehlung fuer uns:** PyQtGraph (MIT) als Haupt-Chart-Library, Matplotlib (BSD) fuer statische
Exporte, QPainter fuer Inline-Sparklines (z.B. Monats-/Wochen-Heatstreifen im Stundenzettel).

**Nuitka-Nebenbefund (bestaetigt unsere Regel):** `--onefile` erfuellt die LGPL-Weitergabepflicht
von PySide6 nicht, `--standalone` (Ordner) schon. Wir bauen ohnehin standalone.

---

## 4. Grid: was Qt kann und wo die Decke ist

Qt hat **kein DataGrid-Control**, sondern ein Model/View-Baukasten. DevExpress liefert ein Grid,
Qt liefert die Teile. Das zieht sich durch alles.

**Bulletproof auf Bordmitteln (geringes Risiko):**
- Flat-Grid, virtualisiert (QTableView rendert nur sichtbare Zellen), zehntausende Zeilen problemlos.
- `QAbstractTableModel` ueber eine Objektliste oder einen DataFrame - minimaler Boilerplate.
- Klick-Sortierung und Filter-Logik ueber `QSortFilterProxyModel`. Multi-Spalten-Filter: `filterAcceptsRow` ueberschreiben, Praedikat-Dict pro Spalte.
- **Inline-Editing per Delegate** (`createEditor`/`setEditorData`/`setModelData`) - erstklassig, teils auf DevExpress-Niveau.
- **In-Zellen-Highlighting** (Suchtreffer einfaerben) ueber `QStyledItemDelegate` mit `QTextDocument` - kanonisches Muster. Wichtig: `opt.text=""` setzen, `doc.setTextWidth(...)`, `painter.translate(...)`, und **nie** echte Rich-Text-Widgets pro Zelle (Forum-Messung: 15+ Minuten fuer 7000 Zeilen).

**Viel Arbeit, aber machbar:**
- **Gruppieren mit Gruppensummen** = QTreeView + handgebautes Baum-Modell (Gruppenknoten als Eltern mit Subtotal in der Zeile, Detailzeilen als Kinder). Fuer feste 2-Ebenen-Gruppierung gut machbar (ein paar hundert Zeilen, robust). Laufzeit-konfigurierbares Drag-to-Group waere ein eigenes Projekt.
- **Grand-Total / eingefrorene Summenzeile** = zweite Ein-Zeilen-QTableView darunter, Spaltenbreiten synchronisiert. Kein Footer-Primitiv in Qt.
- **Excel-artige Spalten-Filter-Dropdowns** mit Distinct-Value-Checklisten = eigenes `QHeaderView`-Widget + Popup. Die Filter-Logik ist leicht, die Header-UX ist die eigentliche Luecke zu einem Kommerzgrid.

**Nicht ohne Kommerzgrid / grosses Projekt:**
- **Interaktives Pivot** (Felder auf Achsen ziehen) - Qt hat dafuer gar keinen Baustein. Realistisch: pandas `pivot_table` rechnen, das breite Ergebnis in ein normales Table-Model.
- Die **integrierte Breite**, die DevExpress out-of-the-box liefert (alle Features zusammen, gethemt).

**Library-Realitaet:** Kein gepflegtes, permissiv lizenziertes, einbettbares PySide6-"Super-Grid".
Die permissiven (PandasGUI MIT-0, qtpandas MIT) sind Apps auf toten/alten Bindings, die
featurereiche (tablexplore) ist **GPL - Dealbreaker**, die naechste (QAIV, LGPL) ist reines C++
ohne Python-Bindings (nur als Vorlage zum Nachbauen). Bester Weg: auf rohem Model/View bauen,
pandas die Datenarbeit (groupby/pivot/aggregate) machen lassen, Qt nur anzeigen.

**Der ehrliche Satz:** Qt Model/View erreicht ein sehr gutes eigenes Grid, aber jedes
Enterprise-Feature ist a la carte und handgebaut. Wir tauschen Lizenzfreiheit und volle Kontrolle
gegen Engineering-Zeit.

**Fuer den Stundenzettel konkret:** Wir brauchen Gruppieren (nach Tag/Woche/Ticket) mit
Gruppensummen und Suche mit Highlighting - alles im "machbar"-Bereich. Pivot brauchen wir vorerst
nicht. Das Grid ist damit ein handgebautes QTreeView-Modell mit Delegate-Highlighting, keine
Fremd-Library.

---

## 5. Themes und Design-System

### Entscheidung E1 (27.07.2026): Fusion nativ - Variante A

Zwei Prototypen wurden gebaut und in Hell und Dunkel mit gefuelltem Grid verglichen
(die Vergleichs-Screenshots wurden entfernt, weil die Beispieldaten reale Ticketdaten
zeigten):

- **A - Fusion + QPalette + duennes QSS.** Der `Fusion`-Style ist Qts plattformneutraler, nuechterner
  Business-Look, folgt der `QPalette` und schaltet ab Qt 6.5 automatisch Hell/Dunkel nach
  OS-Einstellung (`styleHints().colorScheme()`). Farben grossteils ueber eine QPalette (robuster als
  ein Riesen-QSS), nur duennes Struktur-QSS drueber. Steuerelemente bleiben nativ.
- **B - eigenen precision-Look zurueckgenommen** (weniger Radius, gedeckter Akzent, Mono-Ziffern).
  Behaelt die Marken-Naehe zur Web-Seite, bleibt aber vollstaendig selbstgestyltes QSS (mehr Pflege,
  mehr Fallen).

**Gewaehlt: A.** Begruendung (Michael): es geht um enterprise-faehige Anwendungen, die Benutzer
ohne Einarbeitung verstehen und bedienen sollen - auch wenn es langweilig aussieht. Leichte
Verstaendlichkeit und Wartungsarmut schlagen Distinktion. Der distinktive ("wilde") Look wie bei
DAWs kommt spaeter und getrennt, nicht in Enterprise-Werkzeugen.

### Design-System: Token-Dataclass mit Spacing- und Typo-Scale

Unabhaengig von E1 ist das der fehlende Baustein. QSS hat **keine Variablen** - der Weg ist eine
Token-Dataclass als Single Source of Truth plus ein `theme.qss.tmpl`, das per `str.format` gefuellt
wird (genau unser heutiger f-String-Ansatz, nur um Abstaende und Typografie erweitert):

```python
@dataclass(frozen=True)
class Tokens:
    bg: str; surface: str; text: str; accent: str; border: str
    space_1: int; space_2: int; space_3: int          # Spacing-Scale (z.B. 4/8/16)
    radius: int; font_sans: str; font_mono: str
    fs_body: int; fs_h1: int                           # Typo-Scale (feste Stufen)
```

Regeln daraus:
- **Nur noch Scale-Stufen** fuer Padding und Schriftgroesse. Kein `padding: 9px 10px` mehr, sondern `{space_2}`. Kein `font-size: 22px` mehr, sondern `{fs_h1}`.
- **Komponenten-Klassen statt `#objectName`**, wo eine Sache mehrfach vorkommt (Feldzeile, Sektionskopf, Summenkachel). ID-Selektoren nur fuer echte Einzelstuecke.
- **Laufzeit-Umschaltung Hell/Dunkel** = QSS aus dem anderen Token-Satz neu bauen und `setStyleSheet` erneut aufrufen, danach ggf. `unpolish/polish`.
- **Verifikations-Gate:** jede `url()` im erzeugten QSS gegen das Dateisystem pruefen (Test, der scheitern kann).
- Alternative zu `str.format`, falls das QSS gross wird: SCSS -> QSS via `qtsass` (BSD), so baut QDarkStyle sein Stylesheet.

### Fremd-Libraries (verifizierte Lizenzen)

**Empfohlen:**

| Paket | Lizenz | Nutzen |
| --- | --- | --- |
| `superqt` | BSD-3 | 23 fehlende nuechterne Standard-Widgets (Range-/Labeled-Slider, Collapsible, searchable Combos, Toggle, EnumCombo, ElidingLabel) |
| `QtAwesome` | MIT | Icon-Font-Glyphen als zur Laufzeit umfaerbbare `QIcon`s - loest `currentColor`. Material Design Icons / Codicons sind sehr nuechtern |
| `qtsass` | BSD | QSS als SCSS schreiben (Variablen/Partials) und kompilieren - optional |
| `PyQtDarkTheme-fork` | MIT | Fertiges flaches Hell/Dunkel-Theme mit OS-Auto-Erkennung, falls kein eigenes QPalette gebaut wird (Import heisst `qdarktheme`) |
| `pyqttoast` | MIT | In-Fenster-Toast, falls gebraucht (Qt hat keins) |

**Verboten (Lizenz-Dealbreaker fuer Apache-2.0):**

| Paket | Lizenz | Warum |
| --- | --- | --- |
| `PyQt-/PySide6-Fluent-Widgets` | **GPLv3 + kommerziell** (aus Repo-LICENSE verifiziert) | Copyleft erzwingt Quelloffenlegung oder Kauf, ausserdem zu "modern-Microsoft" fuer konservativ |
| `pyqtconfig` | **GPL** | Copyleft - stattdessen duenner `QSettings`-Wrapper selbst |
| `qtpandas` | MIT, aber **PyQt4** | Tot, nicht Qt-6-tauglich |
| `qt-material` | BSD (sauber) | Lizenz ok, aber Material-Look zu "modern" fuer konservativ |

### Icons und Schrift

- **Icons:** QtAwesome (Material Design Icons / Codicons) als Hauptquelle, monochrom, Fuellfarbe aus dem Theme. Fuer app-spezifische Symbole weiter eigene SVG-Paare (`icon-light.svg`/`icon-dark.svg`) wie schon im Repo.
- **Schrift:** **IBM Plex Sans** oder **Inter** (beide OFL, corporate-neutral, frei buendelbar) via `QFontDatabase.addApplicationFont` registrieren. Garantiert gleiche Darstellung auf Rechnern ohne installierte Schrift.

---

## 6. Architektur-Muster

**Qt Model/View ist keine App-Architektur**, sondern ein Widget-Werkzeug fuer Tabellen/Baeume.
Fuers Ganze:

- **MVP / Humble View.** Views sind duenne `QWidget`-Subklassen, die nur Layout bauen, typisierte
  Absichts-Signale melden (`entrySaveRequested`) und Setter-Slots zum Rendern haben. Keine
  Geschaeftslogik, keine Service-Aufrufe in der View.
- **ViewModels** sind `QObject`s in `ui/viewmodels/` mit `notify`-Signalen, kennen Services, aber
  **keine Widgets** - headless testbar.
- **Kein MVVM-/Binding-Framework.** Manuelles Signal-Binding (notify -> Setter-Slot), explizit und
  debugbar. Reaktives `QBindable` aus Python ist **unverifiziert** - vor Nutzung prototypen.
- **Harte Grenze:** `domain/ services/ models/ infrastructure/` importieren **nie** `PySide6`. Mit
  einem Grep-Test absichern.
- **Handgeschriebene Widgets + geteilte Builder** als Default (ein `field_row(label, widget)` ->
  alle Formulare fluchten gleich). Qt Designer nur fuer einzelne grosse statische Panels, und dann
  nie die generierte `*_ui.py` editieren.
- **Threading:** `QThread`+`run()` mit `asyncio.run(...)` und Rueckgabe nur ueber Signale ist fuer
  wenige Aufrufe korrekt (event-loop-frei). Worker fasst keine Widgets an, `closeEvent` wartet auf
  ihn (`wait(3000)`). `moveToThread` nur, wenn der Faden eine Event-Loop fuer viele Queued-Calls
  braucht. `@Slot(...)` auf **jedem** Cross-Thread-Slot (sonst Segfault-Gefahr).
- **`QDialogButtonBox`** in jedem Dialog - ordnet OK/Abbrechen/Uebernehmen plattformkorrekt an, per
  Rolle (`AcceptRole`/`RejectRole`/`ApplyRole`/`DestructiveRole`), nie per Handpositionierung. Ein
  `BaseDialog` mit dem Skelett Titel -> Inhalt -> ButtonBox vereinheitlicht alle Dialoge.
- **Validierung** in reine, UI-freie Methoden (Rueckgabe Wert oder `None`), `QMessageBox` nur im
  Fehlerpfad - sonst blockiert `exec()` die Headless-Tests.

---

## 7. Konservative Enterprise-Konventionen

- Konsistente Dichte ueber die Spacing-Tokens, Label-Ausrichtung ueber `QFormLayout` einheitlich.
- Mnemonics (`&Speichern`) + `QLabel.setBuddy()` fuer `Alt+Buchstabe`, Standard-Shortcuts ueber `QKeySequence.StandardKey`.
- Tab-Reihenfolge bewusst mit `setTabOrder()` setzen, nicht auf Konstruktionsreihenfolge verlassen.
- `setAccessibleName`/`setAccessibleDescription` auf nicht-offensichtlichen Controls.
- Aktionen in Menue + Toolbar (gemeinsame `QAction`) statt TUI-artiger Einzeltasten.

---

## 8. Styleguide / Storybook

Es gibt **kein Storybook-Aequivalent** fuer Qt. Etablierte Praxis: eine **Gallery-App** im Repo.
Vorbild ist Qts eigene "Widgets Gallery".

**Plan `ui/gallery/`** - eigener Einstiegspunkt (`python -m jira_timesheet_qt.ui.gallery`):
- Linke Navigation (Kategorien): *Foundations* (Farb-Swatches aus den Tokens, Typo-Scale,
  Spacing-Lineal), *Controls* (jedes Basis-Widget), *Composites* (unsere `ui/widgets/`-Bibliothek),
  *Forms* (Beispiel-`QFormLayout` + `QDialogButtonBox`), *Data* (QTableView mit echtem Modell auf
  Beispieldaten), *Dialogs*.
- Theme-Umschalter, der dasselbe `build_qss(LIGHT/DARK)` wie die App aufruft - die Gallery rendert
  das **echte** Produktions-QSS, ist also ein lebender Styleguide, kein Mockup.
- Zustandsabdeckung je Komponente: normal / disabled / fokussiert / Fehler / Leerzustand
  nebeneinander.
- Importiert dieselben `ui/widgets/` und `theme/` wie die App - Drift ist damit unmoeglich.

Das dient zugleich als manuelle QA und als Onboarding-Doku.

---

## 9. Standards-Checkliste (uebernehmen)

**Architektur**
- [ ] Harte Regel: `domain/ services/ models/ infrastructure/` nie `import PySide6` (Grep-Test).
- [ ] MVP / Humble View fuer Screens+Dialoge, Qt Model/View nur fuer Grids.
- [ ] ViewModels als `QObject` in `ui/viewmodels/` mit `notify`-Signalen, ohne Widget-Imports, headless getestet.
- [ ] Manuelles Signal-Binding, kein Binding-Framework.
- [ ] Handgeschriebene Widgets + geteilte Builder, generierte `*_ui.py` nie editieren.

**Signals / Threading**
- [ ] Neue typisierte Verbindungen, Verdrahtung in einem `_connect()` je View, domaenenbenannte Absichts-Signale.
- [ ] `@Slot(...)` auf jedem Cross-Thread-Slot.
- [ ] Worker: kein Widget-Zugriff, Rueckgabe per Signal, `wait()` im `closeEvent`.

**Design-System**
- [ ] Eine `Tokens`-Dataclass (Farbe, **Spacing-Scale, Typo-Scale**, Radius, Fonts), Hell/Dunkel.
- [ ] Ein `theme.qss.tmpl` per `str.format`, Vorwaerts-Schraegstriche in `url()`, Icon-Paare je Theme.
- [ ] Globales `QLabel { background: transparent; }`, Tabellen-/Kalender-Regeln scopen.
- [ ] Laufzeit-Theme-Wechsel = QSS neu bauen.
- [ ] Komponenten-Klassen statt `#objectName`, wo etwas mehrfach vorkommt.

**UI-Konventionen**
- [ ] Jeder Dialog endet in `QDialogButtonBox` mit rollenbasierten Buttons, ueber ein `BaseDialog`.
- [ ] Formulare ueber `QFormLayout`, volle-Breite-Hinweise in eigener Zeile.
- [ ] Mnemonics + `setBuddy`, `setTabOrder`, `QKeySequence.StandardKey`, `setAccessibleName`.
- [ ] Validierung in reine Methoden, `QMessageBox` nur im Fehlerpfad.

**Storybook & Tests**
- [ ] Eigene `ui/gallery/`-App, die echtes `theme/` + echte `ui/widgets/` zieht, mit Theme-Umschalter und Zustaenden.
- [ ] pytest-qt + `QT_QPA_PLATFORM=offscreen`, `waitSignal`/`waitUntil` fuer Async, echte Plattform fuer Screenshots.
- [ ] QSS-`url()`-Resolve-Test, Widget-Referenzen im Test am Leben halten, kein blockierendes `exec()` im Headless-Pfad.

---

## 10. Offene Fragen (nicht als Fakt behandeln, erst pruefen)

- **QtCharts-LGPL-Status via PySide6-Wheel** - autoritativ nicht bestaetigbar. Sichere Lesart:
  GPL, deshalb meiden. Nur eine schriftliche Qt-Company-Klarstellung oder eine kommerzielle Lizenz
  wuerde das aufheben.
- **Reaktives `QBindable`/`BINDABLE` aus reinem Python** - PySide6-Doku beschreibt nur das klassische
  Property-System. Vor Nutzung prototypen.
- **Qt-6.5-`colorScheme()`-Follow-System-Verhalten in PySide6** - vor Verlass darauf pruefen.
- **QCalendarWidget-Popup runde Aussenecken** - ob `WA_TranslucentBackground` noetig ist, ungeprueft.
- **QAdvancedItemViews Qt6-Kompatibilitaet** - Doku von 2014, unverifiziert (nur Vorlage, nicht importierbar).

---

## 11. Empfohlene naechste Schritte

1. **Entscheidung E1 getroffen: Variante A** (Fusion nativ). Naechster Umbau: `theme.py` von schwerem
   Custom-QSS auf QPalette (Hell/Dunkel) + duennes Struktur-QSS umstellen, Steuerelemente nativ lassen.
2. **Token-Schicht einziehen**: `Tokens`-Dataclass um Spacing- und Typo-Scale erweitern, `theme.py`
   darauf umstellen, verstreute Pixelwerte durch Scale-Stufen ersetzen.
3. **Gallery-App** (`ui/gallery/`) als lebenden Styleguide aufsetzen - deckt sofort die
   Inkonsistenzen auf und wird die Bearbeitungsflaeche fuer alle folgenden Feinschliffe.
4. **superqt + QtAwesome** als Dependencies aufnehmen, Icon-Strategie auf QtAwesome umstellen.
5. Grid-Ausbau (Gruppierung mit Gruppensummen, Suche mit Highlighting) auf QTreeView-Modell planen.

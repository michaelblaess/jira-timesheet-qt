# Qt-Menüsysteme: Evaluation und datengetriebene Architektur

Grundlagendokument zur Frage "welches Menüsystem für komplexe PySide6-Anwendungen".
Ausgangspunkt: die heutige Kopfzeile in jira-timesheet-qt ist ein `QWidget` mit `QToolButton`s -
für ein einfaches Werkzeug ok, für komplexe Anwendungen zu wenig.

Stand: 28.07.2026. Jeder nicht-triviale Befund ist belegt (Qt-Doku, Repo-LICENSE, Foren) oder als
**unverifiziert** markiert. Grundlage: vier parallele Recherchestraenge (Bordmittel-Menüs/Toolbars,
Ribbon-Libraries, Sidebar/Modern-Nav, datengetriebene Architektur).

---

## 0. Kernaussage

**Die Wahl des Menü-Paradigmas (klassisch / modern / Ribbon / Sidebar) ist die kleinere Frage. Der
eigentliche Hebel ist die datengetriebene Command-Architektur** - und die ist fuer alle vier Formen
identisch. Michaels Anforderung ("Struktur kommt aus JSON/DB, nie statisch") loest sich sauber ueber
EINE Qt-Tatsache:

> Eine `QAction` ist die Abstraktion eines Benutzer-Kommandos und kann gleichzeitig in Menü,
> Toolbar, Kontextmenü, Sidebar UND Ribbon haengen - Qt haelt alle synchron.
> (doc.qt.io/qt-6/qaction.html)

Damit trennt sich: **Struktur = Daten (JSON/DB)**, **Verhalten = Code (Command-Registry)**, verbunden
nur ueber eine **Command-ID**. Ein `MenuBuilder` laeuft den Baum je **Surface** ab und materialisiert
`QMenuBar` / `QToolBar` / Sidebar / Ribbon aus **derselben** Definition. Eine neue Platzierung ist
dann nur ein Tag mehr, keine neue Verdrahtung. Details in Abschnitt 5 - das ist der Teil, der wirklich
gebaut werden muss.

---

## 1. Die vier Paradigmen: was Qt kann, Aufwand, Lizenz

| Paradigma | Vorbild | Qt-Bordmittel? | Aufwand | Lizenz |
| --- | --- | --- | --- | --- |
| **Klassisch: Menü + Toolbar darunter** | KeePass | **Ja, voll nativ** | gering | LGPL (Qt) |
| **Modern: flaches Menü + kompakte Toolbar-Reihen** | Visual Studio | **Ja, voll nativ** (nur Styling anders) | gering-mittel | LGPL (Qt) |
| **Ribbon: Tabs -> Gruppen -> Buttons/Galerie** | Office | **Nein** | mittel-hoch | pyqtribbon MIT, sonst Eigenbau/kommerziell |
| **Hamburger + Seitenleiste** | MS Teams | **Nein als fertiges Widget**, aber trivial baubar | gering | LGPL (Eigenbau), kein permissives Drop-in |

### Klassisch (KeePass) und modern (VS) - beides dasselbe Fundament

`QMenuBar` + `QMenu` + `QAction` + `QToolBar` + `QToolButton`, alles nativ und **produktionsfest**
(Qts Heimspiel). Beleg für die Bausteine:
- **Menübaum, Untermenüs, Trenner, Sektionen:** `QMenu.addAction/addMenu/addSeparator/addSection` - erstklassig.
- **Checkable / Radio:** `QAction.setCheckable`, `QActionGroup` mit `ExclusionPolicy.Exclusive`.
- **Shortcuts plattformkorrekt:** `QKeySequence.StandardKey.Save` liefert Ctrl+S auf Windows/Linux, Cmd+S auf macOS automatisch - **StandardKey den Literalen vorziehen**.
- **Split-/Dropdown-Buttons** (das VS-Merkmal): `QToolButton` mit `ToolButtonPopupMode.MenuButtonPopup` (Split) oder `InstantPopup` (reiner Dropdown) + `setMenu()`.
- **Inline-Widgets in der Toolbar** (Combo, Suchfeld wie in VS): `QToolBar.addWidget(QComboBox/QLineEdit)`. **Falle:** Sichtbarkeit ueber `QAction.setVisible` steuern, NICHT `widget.hide()`.
- **Mehrere Toolbar-Reihen** (VS-Look): `addToolBar()` + `addToolBarBreak()`.
- **Overflow gratis:** wird die Toolbar zu schmal, erscheint automatisch ein Extension-Button ("...") mit Popup - VS-artiger Kollaps ohne Code.
- **Layout persistieren:** `QMainWindow.saveState/restoreState`. **Zwei harte Regeln:** eindeutiger `objectName` je Toolbar (sonst still nicht wiederhergestellt) und eine Versionsnummer (bei Aenderung erhoehen, sonst wird ein alter Stand still verworfen).

"Modern (VS)" unterscheidet sich von "klassisch (KeePass)" fast nur im **Styling** (flach, Icons,
kompakte Reihen) - kein anderer Unterbau.

### Ribbon (Office) - nicht nativ

Qt hat **kein** Ribbon-Widget (Foren-Beleg + Vendor-Bestaetigung). Optionen:
- **pyqtribbon (MIT)** - die einzige gepflegte, permissiv lizenzierte, PySide6-taugliche Python-Ribbon. Voll zur Laufzeit baubar (`addCategory`/`addPanel`/`addLargeButton`/`addGallery`) - genau die imperativen APIs fuer einen JSON/DB-Builder. Einschraenkung: Beta, Einzelmaintainer (0.7.8 / Mai 2025), eigener QSS-Look.
- **Eigenbau** auf `QTabWidget` + `QToolButton` (icon-ueber-text via `ToolButtonTextUnderIcon`) - ein bis zwei Tage fuer eine schlichte Variante, mehr fuer Galerien/Kollaps. Design von **SARibbon** (MIT, aber C++) portierbar.
- **QtitanRibbon** - nur kommerziell, liefert aber PySide6-Bindings; nur wenn gekauft.
- **nedrysoft qt-ribbon = GPL - meiden.**

### Hamburger + Seitenleiste (Teams) - Eigenbau, klein

Kein fertiges permissives Widget. Die einzige Library, die genau das liefert (**QFluentWidgets
`NavigationInterface`**), ist **GPLv3 + kostenpflichtig kommerziell** - Dealbreaker (aus LICENSE
re-verifiziert, 28.07.2026). Der Eigenbau ist aber klein:

```
QSplitter(horizontal)
├─ Rail: schmales QFrame, QVBoxLayout aus checkable QToolButtons in
│        exklusiver QButtonGroup; Hamburger-QToolButton oben; Overflow via QMenu
├─ Sekundaerpanel: QTreeView (Kanaele) / QListView; optional superqt.QCollapsible
└─ Inhalt: QStackedWidget (eine Seite pro Ziel)
```

Verdrahtung: `QButtonGroup.idClicked -> QStackedWidget.setCurrentIndex`. Kollaps: Hamburger schaltet
je Button `toolButtonStyle` (nur-Icon <-> Icon+Text) und animiert die `maximumWidth` per
`QPropertyAnimation`. Voll datengetrieben in einer Schleife baubar.

---

## 2. Lizenz-Übersicht (kommerziell nutzbar, Apache-2.0-kompatibel)

| Baustein | Lizenz | Fuer Apache-2.0 |
| --- | --- | --- |
| Qt-Bordmittel (QMenuBar/QToolBar/QAction/QStackedWidget/...) | LGPL (via PySide6) | **ja** |
| **pyqtribbon** | **MIT** (verifiziert) | **ja** - Ribbon |
| **superqt** (`QCollapsible`) | BSD-3 | **ja** |
| **QtAwesome** (mdi6-Icons) | MIT (Icons Apache 2.0) | **ja** - Icons |
| **pydantic** | MIT | **ja** - Schema-Validierung |
| SARibbon | MIT, aber **C++** | nur Design portieren |
| **QFluentWidgets** (Nav-Rail) | **GPLv3 + kommerziell** | **nein** - Dealbreaker |
| **nedrysoft qt-ribbon** | **GPLv3** | **nein** |
| QtitanRibbon | kommerziell | nur gekauft |

---

## 3. Was Qt-Bordmittel NICHT abdecken

1. **Kein Customize-Toolbar-Dialog** (Buttons per Drag waehlen/ordnen/als Preset speichern). Qt liefert nur `createPopupMenu()` (Toolbars/Docks ein-/ausblenden). Der Rest ist Eigenbau (eigener Dialog mit zwei `QListWidget`s).
2. **Kein Ribbon-Primitiv** (siehe oben).
3. **Kein `currentColor` in QSS** - monochrome Icons/Pfeile brauchen eine Datei je Theme ODER QtAwesome zur Laufzeit (haben wir schon).
4. **Menü-Styling ist stil-/plattformabhaengig** - keine pixelgleichen Menüs ueber alle nativen Stile. Konsistenz erzwingt praktisch die Festlegung auf **Fusion** (haben wir, E1=A).
5. **Kein Overflow/Customize fuer Menüleisten** (der Extension-Button gilt nur fuer Toolbars).
6. **macOS-Kanten:** Mehrfach-Chord-Shortcuts rendern nicht in der nativen Menüleiste, `setUnifiedTitleAndToolBarOnMac` vertraegt sich nicht mit beweglichen/dockbaren Toolbars und crasht unter der offscreen-Testplattform ([QTBUG-80946](https://bugreports.qt.io/browse/QTBUG-80946)) - im Test guarden.

---

## 4. macOS-Menüleiste (falls relevant)

Qt macht die globale macOS-Menüleiste automatisch. Zwei Punkte fuer eine deutsche UI:
- **Menü-Rollen setzen** (`QAction.setMenuRole(AboutRole/PreferencesRole/QuitRole)`), sonst verschiebt Qts Text-Heuristik "Über.../Einstellungen/Beenden" nicht korrekt ins Anwendungsmenü. Wirkt nur auf Aktionen direkt in der Menüleiste, nicht in Untermenüs.
- App-weite Leiste als `QMenuBar(None)` erzeugen, nicht ueber `QMainWindow.menuBar()`.

---

## 5. Die datengetriebene Command-Architektur (der eigentliche Kern)

Vier Bausteine, je ein reines Python-Modul, nur am Composition-Root verdrahtet. Vorbild: das Modell
von **VS Code** (`contributes.menus`/`commands` + `when`-Klausel) und **Qt Creator**
(`ActionManager`) - id-adressierter Command, Handler im Code, Platzierung als Daten.

### 5.1 Schema (Daten) - ein Baum aus Knoten

Jeder Knoten hat einen kleinen, geschlossenen Typ-Satz. Strukturknoten (`menu`, `toolbar`,
`separator`, `group`) tragen nur Layout. Das Blatt (`action`/`nav-item`/`ribbon-button`) traegt
**nur eine `command`-ID** - nie einen Callable.

Felder: `id` (Knoten-ID, stabil, fuer Tests/RBAC), `type`, `title` (**i18n-Key**, nicht Literal),
`icon` (**logisches Token** wie `mdi6.content-save`, kein Pfad), `shortcut` (`StandardKey.Save` oder
Literal), `command` (Registry-ID - der einzige Link zum Verhalten), `when`/`enabled_when`
(Boolean-Ausdruck gegen App-Zustand), `checkable`/`checked`/`group` (Radio via `QActionGroup`),
`permission` (RBAC-Gate), `surfaces` (`["menu","toolbar","context:table"]` - EINE Definition, viele
Ziele), `children`.

**`id` vs `command`:** `id` benennt den Platz im Baum (eindeutig, fuer Tests/RBAC), `command` das
Verhalten (darf sich wiederholen - dasselbe "Speichern" haengt legitim in Menü, Toolbar und Ctrl+S).

Beispiel (Auszug):
```json
{ "id": "act.file.save", "type": "action", "command": "file.save",
  "title": "cmd.file.save", "icon": "mdi6.content-save",
  "shortcut": "StandardKey.Save", "enabled_when": "document.dirty",
  "surfaces": ["menu", "toolbar"] }
```

### 5.2 Command-Registry (Verhalten)

`command_id -> Command(run, is_enabled, is_checked, action)`. Beim Start registriert, von jedem Menü
entkoppelt. Besitzt die **EINE `QAction` pro Command**, lazy erzeugt und ueber alle Surfaces
wiederverwendet - Qt haelt Text/Icon/Enabled/Checked synchron.

```python
@dataclass
class Command:
    id: str
    run: Callable[[], None]                 # Verhalten - der einzige Ort fuer einen Callable
    text_key: str
    is_enabled: Callable[[], bool] = lambda: True
    is_checked: Callable[[], bool] | None = None
    action: QAction | None = None           # die EINE QAction, vom Builder lazy erzeugt
```

Enabled/Checked synchron halten: `aboutToShow` fuer Menüs (Zustand ist beim Oeffnen frisch),
explizites `refresh(id)` fuer dauersichtbare Toolbar-Buttons.

### 5.3 MenuBuilder (Struktur -> Qt)

Laeuft den validierten Baum fuer eine gegebene **Surface** ab und emittiert `QMenuBar`/`QMenu`
(menu), `QToolBar` (toolbar), `QToolButton`-Liste (sidebar) oder Ribbon-Seiten (auch pyqtribbon,
dessen imperative API dazu passt) - aus DERSELBEN Definition, gefiltert ueber `surfaces`.

- Icons ueber die QtAwesome-Fassade (`mdi6.*`, zur Laufzeit gefaerbt), Shortcuts ueber `QKeySequence.StandardKey`, Titel ueber `tr()`, exklusive Toggles ueber `QActionGroup`.
- **`objectName` je Knoten aus der `id` setzen** - dann ist der gebaute Baum headless gegen die Definition testbar.
- Jedes Blatt holt die **geteilte** `QAction` aus der Registry - dieselbe Instanz in Menü und Toolbar.

### 5.4 Dynamische Menüs, Persistenz, RBAC

- **Dynamisch** (Recent Files, Plugins, Kontext): Region als Knoten mit `provider`-ID; auf `aboutToShow` liefert ein registrierter Provider frische Kind-Knoten (gleiches Schema). Beim Neuaufbau `widget.setParent(None)` **vor** `deleteLater()` (Geist-Bug, schon belegt).
- **Quelle** JSON-Datei ODER SQLite-Zeilen -> identischer Knotenbaum. Mit **pydantic** validieren, plus Referenz-Check: jede `command`-ID muss in der Registry existieren (der Test, der scheitern kann). `schema_version` + geordnete Migrationskette.
- **RBAC:** statisch ueber `permission` (ganzer Teilbaum verschwindet ohne Recht), dynamisch ueber `when`/`enabled_when` gegen Live-Zustand. **Kein `eval()`** auf DB-Strings - eine Whitelist-Grammatik (Gleichheit, `&&`, `||`, `!`, Kontext-Keys) auf Booleans abbilden.

### 5.5 Testbarkeit (headless)

Weil die Struktur Daten ist und der Builder deterministisch: `objectName` je Knoten setzen, dann den
gebauten Baum gegen die Definition asserten (Menü-Titel, Aktions-Labels, Trenner). Der wertvollste
Test: jede referenzierte `command`-ID loest in der Registry auf. Plus: `QAction`-Wiederverwendung
(`registry.get("file.save").action is toolbar_action`), RBAC (Permission-Stub verweigert -> Menü
`is None`), dynamische Menüs (`aboutToShow` emittieren). `QT_QPA_PLATFORM=offscreen` fuer Struktur,
echte Plattform nur fuer Screenshots.

---

## 6. Empfehlung

1. **Zuerst die Command-Architektur bauen, nicht das Chrome.** Registry + JSON/DB-Schema + MenuBuilder + Context/Permissions sind die eigentliche Investition und paradigma-unabhaengig. Das gehoert - sobald die zweite Qt-App kommt - in das geplante `qt-foundation`-Repo (siehe qt-grundlagen.md).
2. **Chrome nach Bedarf, aus derselben Definition:**
   - **Klassisch/modern Menü + Toolbar (nativ)** ist der Default fuer konservative Enterprise-Anwendungen (E1=A) - null Lizenzrisiko, jeder kennt es. Deckt KeePass UND VS ab (nur Styling-Unterschied).
   - **Sidebar-Rail (nativ, Eigenbau)** fuer die Top-Navigation komplexer Apps (mehrere Bereiche), ergaenzend zum Menü. Klein.
   - **Ribbon nur, wenn ein konkretes Produkt es fachlich will** - dann pyqtribbon (MIT). Ribbon ist polarisierend und schwer; nicht als Default.
3. **Lizenz-Leitplanken:** pyqtribbon/superqt/QtAwesome/pydantic sind sauber. QFluentWidgets und nedrysoft-Ribbon sind GPL - raus.

Fuer jira-timesheet-qt selbst (einfaches Werkzeug) reicht die heutige Toolbutton-Kopfzeile bzw. eine
schlanke native Menü+Toolbar. Der volle datengetriebene Apparat lohnt erst fuer die komplexen
Anwendungen, um die es Michael eigentlich geht - dort dann aber von Anfang an so.

---

## 7. Offene Fragen

- pyqtribbon-Reife im echten Einsatz (Beta, Einzelmaintainer) - vor produktivem Ribbon einen Prototyp mit echten Daten bauen.
- QtitanRibbon-Preis - unverifiziert (JS-Seite).
- macOS: ob der Unified-Toolbar visuell mit custom-gestyleter (QSS) Toolbar harmoniert - am echten Mac testen.
- Lizenzen von collapsiblepane / PySide6-DAW / pyside6-utils - unverifiziert, vor Nutzung pruefen.

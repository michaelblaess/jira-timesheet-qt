# Plan: Qt-Version auf TUI-Niveau bringen (Vollständigkeit + Farbe)

Ziel (Michael, 26.07.2026): Die Qt-Version soll so **bunt, vollständig und
lebendig** werden wie die Textual-TUI (`jira-timesheet`). Aktuell ist sie
funktional dünner und optisch trist.

Alle Formeln/Schwellen unten sind aus der TUI-Codebasis belegt (Datei:Zeile in
`C:\ZusatzSW\Tools\jira-timesheet\src\jira_timesheet\`).

---

## Bereits erledigt (dieser Durchgang)

- **i18n-Leak behoben:** `load_locale()` wurde in `__main__.py` nie aufgerufen,
  daher lecken alle `t()`-Keys durch (`jira.budget_unassigned`, `jira.jql`,
  `jira.connecting`, `jira.issues_found`, `jira.worklogs_found`). Jetzt geladen.
- App-Name `Stundenzettel` -> `jira-timesheet-qt`.
- Legacy-Import der Jira-Einstellungen (Auto + Button).
- Log-Button in der Kopfleiste, `secondary`-Button-Stil.

---

## Phase 1 - Summen-/Forecast-Leiste (ersetzt "SUMME 131,25 h")

Reihenfolge wie TUI: `Arbeitstage | Ist | (davon manuell) | Soll | Diff | Ø/Tag | (Netto | Brutto)`
Trenner `  |  `. Labels dim, Werte bold.

- **Arbeitstage** = Tage mit mindestens einem Eintrag (`len(days)`).
- **Ist** = Σ Stunden aller Einträge.
- **davon manuell** = Σ Stunden manueller Einträge (nur wenn > 0), in `manual_color` (Default rot `FF0000`).
- **Soll** = `count_workdays(from,to) × hours_per_day` (Mo-Fr ohne Feiertag × 8,0). Nur wenn > 0.
- **Diff** = Ist - Soll. Vorzeichen `+`/`-`. **rot wenn < 0, sonst grün.**
- **Ø/Tag** = Ist / Arbeitstage.
- **Netto** = Ist × `hourly_rate` (nur wenn > 0). **Brutto** = Netto × (1 + `vat_rate`/100).

Defaults: hours_per_day 8,0 · vat 19,0 · hourly_rate 0,0 · manual_color FF0000.
Alle Geldwerte müssen im (noch fehlenden) Anonymisierungsmodus zensierbar sein (`••••• €`).

## Phase 2 - Farbigkeit in der Tabelle (Kern von "trist -> bunt")

Qt braucht pro Zelle Foreground/Font über das `QAbstractTableModel`
(`ForegroundRole`/`FontRole`).

- **Tagessumme** rot (bold) wenn Tag < `hours_per_day`, sonst normal fett.
- **Manuelle Einträge** komplett in `manual_color` (bold): Stunden, Ticket, Kunde, Beschreibung.
- **Lückenzeile** ("- kein Eintrag -") rot, **Feiertagszeile** dim.
- **Kunde-Spalte:** Jira-Einträge = `default_customer` ("Vertrieb", normal); manuelle = gewählter Kunde (z.B. "Corporate", rot weil manuell). Es gibt KEIN automatisches Corporate-Mapping - rot = manuell.

**Offene Design-Entscheidung (Tabellenstruktur):** die TUI-Tabelle hat
`KW | Tag | Datum | Ticket | Beschreibung | Kunde | h | Tages-h`.
Die Qt-Tabelle hat aktuell `Datum | Tag | Vorgang | Beschreibung | Autor | Stunden`
(keine KW-, Kunde-, Tages-Summen-Spalte). -> siehe Frage.

## Phase 3 - Jahresansicht: alle Monate laden + Forecast

- Beim Wechsel auf "Jahr" alle 12 Monate laden: abgeschlossene aus Cache
  (fehlende live holen + cachen), zukünftige nur Soll. Manuelle Zeiten mergen.
- Pro Monat: `pct = min(actual/target*100, 100)`, Balken 18 breit.
  **Farben: >=95% grün, >=70% gelb, sonst rot** (Kachel).
- **Jahres-Gesamt:** `Σactual / max_yearly_hours` (Default 1720h), Verbleibend,
  `{pct:.1f}%`, Balken 20 breit. Summenbalken-Semantik umgekehrt: <80% grün, <95% gelb, sonst rot.
- **Forecast:** `workdays_year(DE, subdiv)` - `vacation_days` (30) = verfügbar;
  `× hours_per_day` = Forecast-Stunden; × rate/vat = Forecast-Umsatz (grün).

## Phase 4 - Kontextmenü in der Tabelle (Rechtsklick)

Einträge wie TUI: Details anzeigen · Ticket im Browser öffnen · (Trenner) ·
Manuelle Zeit erfassen · Manuellen Eintrag bearbeiten · Manuellen Eintrag löschen.
Hinweis: die drei Manuell-Punkte brauchen einen Manual-Entry-Dialog (in Qt noch
nicht vorhanden) - ggf. eigener Schritt. Details + Ticket öffnen gehen sofort.

## Phase 5 (optional) - Detail-Modal

Das rechte Detail-Panel existiert bereits. Zusätzlich ein größeres `d`-Modal wie
die TUI (mehr Felder: Typ/Status/Priorität/Components/Labels/Timestamps) ist
optional - nur wenn gewünscht.

---

## Farbpalette (Vorschlag für Qt, theme-abhängig)

Damit es in Hell UND Dunkel funktioniert, nicht die Terminal-ANSI-Namen 1:1,
sondern Theme-Farben in `theme.py` ergänzen:
`ok`=grün, `warn`=gelb/orange, `bad`=rot, plus `manual` (= manual_color aus Settings).

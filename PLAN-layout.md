# Layout-Umbau: naeher an die TUI

Ziel: Das Hauptfenster von der aktuellen Drei-Spalten-Anordnung (Seitenleiste |
Inhalt | Detailbereich) auf ein TUI-nahes Layout bringen.

## Vorher (aktuell)

```
Menue
Toolbar (Aktionsknoepfe)
Kopfzeile: Juli 2026  < >            [Suchen]
Seitenleiste | Inhalt (Liste/Kalender/Jahr) | Detailbereich
Summenleiste
Statuszeile
```

## Nachher (Ziel)

```
Menue
Toolbar: [Aktionen]      < Juli 2026 >        [Suchen]
Tabs: [Liste] [Kalender] [Jahr]
Inhalt (aktive Ansicht, volle Breite)
Unteres Panel (dynamisch je Ansicht: Summen, Progress-Bars, Charts)
Statuszeile
```

## Punkte (aus Michaels Vorgaben, 28.07.2026)

1. **Detailbereich rechts weg.** Er macht ueber die Ansichten Probleme (Kalender/
   Jahr liefern keine Zeilendaten). Ersatzlos entfernt.
2. **Ticket-Details als modaler Dialog** wie in der TUI (orange umrandet):
   Titel `TICKET - Beschreibung`, Felder Datum/Stunden/Autor/Bearbeiter/Typ/
   Status/Prioritaet/Budget/Erstellt/Aktualisiert/Gesamt-Protokoll, Jira-Link,
   Schliessen (ESC). Ausgeloest per **Doppelklick**, **Toolbar-Knopf** und
   **Kontextmenue**.
3. **Suchfeld** nach oben in die Toolbar, rechts.
4. **Monat + Blaetter-Pfeile** in die Toolbar, mittig.
5. **Ansicht-Seitenleiste links weg** -> **Tabs** (Liste / Kalender / Jahr).
6. **Unteres Panel je Ansicht dynamisch** (aehnlich TUI-Fussleiste), kann
   Progress-Bars und Charts enthalten. Startpunkt: die bestehende Summenleiste
   wird ansichtsabhaengig befuellt.

## Schritte (je ein Commit)

- [x] S1: TicketDetailDialog (modal) + Detailbereich entfernen; Doppelklick/
      Toolbar/Kontextmenue verbinden. (Commit folgt)
- [x] S2: Layout-Restrukturierung: Tabs statt Seitenleiste, Monat+Suche in die
      Toolbar, Kopfzeilen-Widget aufgeloest. (Commit folgt) header.py + sidebar.py
      entfallen.
- [x] S3: Unteres Panel dynamisch je Ansicht mit Fortschrittsbalken. (Commit
      folgt) Liste: volle Summenleiste + Ist/Soll-Balken. Kalender: gebuchte
      Tage/Ist/Soll/Fehlt + Tage-Balken. Jahr: Ist/Soll/Prognose + Ist/Soll-Balken.
      Charts (Verlauf) bewusst spaeter.

Spaeter (Michaels Feedback-Batch, nicht Teil dieses Umbaus): Summen/Forecast mit
Charts, Jahresansicht reicher, Orange final justieren.

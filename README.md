# jira-timesheet-qt

Desktop-GUI für Stundenzettel aus Jira-Worklogs, auf PySide6 (Qt 6).

> **Status:** Im Aufbau. Es gibt noch keine lauffähige Oberfläche - bisher stehen der
> fachliche Kern und das Oberflächenkonzept. Siehe [PLAN.md](PLAN.md).

Nachfolger der Textual-TUI
[jira-timesheet](https://github.com/michaelblaess/jira-timesheet). Der fachliche Kern
(Jira-Anbindung, Stundenzettel-Aufbau, Excel- und PDF-Export, manuelle Nacherfassung) ist
von dort unverändert übernommen, die Oberfläche entsteht neu.

> **Disclaimer:** Dieses Projekt ist **nicht** von Atlassian entwickelt, unterstützt oder
> autorisiert. "Jira" und "Atlassian" sind eingetragene Markenzeichen von
> [Atlassian Corporation](https://www.atlassian.com/). Dieses Werkzeug nutzt die
> öffentliche Jira-REST-API und steht in keiner Verbindung zu Atlassian.

## Warum eine GUI

Die TUI stößt an Grenzen, die das Terminal setzt: keine Druckvorschau, keine Bearbeitung
direkt in der Tabelle, jede zweite Ansicht ein Vollbild-Dialog. Rund die Hälfte des
Oberflächen-Codes bestand aus Umgehungen dieser Grenzen. Die Einzelheiten stehen in
[PLAN.md](PLAN.md).

## Warum PySide6

- **LGPL** statt GPL wie bei PyQt6, damit das Projekt unter Apache-2.0 bleiben kann
- **Nuitka** hat ein gepflegtes `pyside6`-Plugin mit Auto-Erkennung
- **Ein Stack:** Python bleibt Python. Electron und Tauri hätten einen zweiten Stack und
  eine Prozessgrenze zum Kern bedeutet, Tauri zusätzlich eine System-WebView

## Nutzerdaten

Die Anwendung legt ihre Dateien unter `~/.jira-timesheet-qt` ab, getrennt von der TUI.
Beide lassen sich damit parallel benutzen.

## Entwicklung

```bash
./bootstrap.ps1     # bzw. ./bootstrap.sh
uv run poe run
uv run poe test
```

## Lizenz

Apache-2.0, siehe [LICENSE](LICENSE).

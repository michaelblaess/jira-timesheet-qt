"""Registrierung - liegt in QAppFramework.

Hier bleibt, was diese Anwendung beisteuert: der oeffentliche Schluessel, der
Ablageort, die Strenge und die Aufzaehlung dessen, was eine Registrierung
bringt.

Der Modus ist bewusst FREE: gefragt wird genau einmal, beim ersten Start.
Selbst bauen und benutzen bleibt nach der Lizenz frei, und wer ablehnt, wird
nicht wieder behelligt.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget
from QAppFramework.registration import (
    RegistrationMode,
    RegistrationOutcome,
    RegistrationStore,
)
from QAppFramework.registration import check_registration as _check
from QAppFramework.registration import days_left as _days_left
from QAppFramework.registration_dialog import ask_for_registration as _ask

from jira_timesheet_qt.i18n import current_language
from jira_timesheet_qt.models.settings import Settings

# Der oeffentliche Schluessel darf hier stehen - mit ihm laesst sich pruefen,
# aber nichts ausstellen. Der private liegt ausserhalb jedes Repos.
PUBLIC_KEY = bytes.fromhex("8249f683a9844224520b37eb2bfa9c66a96d1e398e9239d6584bff0a6803135a")

MODE = RegistrationMode.FREE

# Was die Registrierung bringt. Bewusst nur, was es wirklich gibt oder
# unmittelbar geplant ist - eine Aufzaehlung, die zu viel verspricht, faellt
# beim ersten Anwender auf.
BENEFITS = (
    "Hinweis auf neue Versionen",
    "Unterstützung bei Fragen und Fehlern",
    "Zusätzliche Auswertungen in Vorbereitung",
)

__all__ = [
    "BENEFITS",
    "MODE",
    "PUBLIC_KEY",
    "ask",
    "days_left",
    "is_enforced",
    "check",
    "store",
]


def store() -> RegistrationStore:
    """Die Ablage, neben den uebrigen Einstellungen dieser Anwendung."""
    return RegistrationStore(Settings.SETTINGS_DIR / "registration.json")


def is_enforced() -> bool:
    """Ob die Pruefung ueberhaupt greift.

    Nur die offiziellen Programmpakete setzen das - beim Nuitka-Lauf ueber eine
    Umgebungsvariable. Wer aus dem Quelltext baut, darf die Anwendung laut
    Additional Use Grant der Lizenz uneingeschraenkt nutzen, und eine Pruefung,
    die ihn aussperrt, widerspraeche der eigenen Lizenz.
    """
    return bool(getattr(_marker(), "OFFICIAL_BUILD", False))


def _marker() -> object:
    """Das Kennzeichen des offiziellen Builds, falls vorhanden."""
    try:
        from jira_timesheet_qt import _build  # type: ignore[attr-defined]
    except ImportError:
        return object()
    return _build


def check() -> RegistrationOutcome:
    """Prueft beim Start und sagt, wie es weitergeht."""
    return _check(store(), PUBLIC_KEY, mode=MODE, enforced=is_enforced())


def days_left() -> int | None:
    """Verbleibende Tage im Testzeitraum, oder None."""
    return _days_left(store())


def ask(parent: QWidget | None = None) -> bool:
    """Zeigt den Registrierungsdialog."""
    return _ask(
        store(),
        PUBLIC_KEY,
        mode=MODE,
        days_left=days_left(),
        benefits=BENEFITS,
        sprache=current_language(),
        parent=parent,
    )


def license_path() -> Path:
    """Wo die Lizenzdatei liegt - fuer die Anzeige im Einstellungsdialog."""
    return store().path

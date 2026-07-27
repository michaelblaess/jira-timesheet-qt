"""SQLite-Ablage fuer manuell erfasste Zeiten.

Zeiten, die nicht in Jira gebucht sind, liegen in einer eigenen SQLite-Datei -
bewusst NICHT im Jira-Worklog-Cache. Der Cache ist ein Abbild dessen, was Jira
geliefert hat; manuelle Eintraege dort abzulegen wuerde sie beim naechsten
Abgleich ueberschreiben oder doppelt zaehlen.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import TracebackType

from jira_timesheet_qt.models.timesheet import WorklogEntry

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".jira-timesheet-qt"
DB_FILE = DB_DIR / "manual-entries.db"


@dataclass
class ManualEntry:
    """Ein manuell erfasster Zeiteintrag."""

    entry_date: date
    ticket: str = ""
    summary: str = ""
    customer: str = ""
    hours: float = 0.0
    entry_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_worklog(self, author: str = "", budget: str = "") -> WorklogEntry:
        """Wandelt den Eintrag in einen WorklogEntry fuer die Timesheet-Pipeline."""
        return WorklogEntry(
            date=self.entry_date,
            ticket=self.ticket,
            summary=self.summary,
            author=author,
            budget=budget,
            hours=self.hours,
            manual=True,
            manual_id=self.entry_id,
            customer=self.customer,
        )


@dataclass
class ManualEntryService:
    """Repository fuer manuelle Zeiteintraege (SQLite).

    Haelt genau eine Verbindung pro App-Instanz. WAL-Journal und busy_timeout
    verhindern das klassische "database is locked", wenn parallel gelesen und
    geschrieben wird.
    """

    db_path: Path = DB_FILE
    _conn: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    # --- Verbindung -------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Oeffnet die Verbindung (lazy) und legt das Schema an."""
        if self._conn is not None:
            return self._conn

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL: Leser blockieren Schreiber nicht. busy_timeout: statt sofortigem
        # "database is locked" bis zu 5s auf die Sperre warten.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        self._conn = conn
        self._migrate(conn)
        return conn

    def close(self) -> None:
        """Schliesst die Verbindung, falls offen."""
        if self._conn is None:
            return
        try:
            self._conn.close()
        except sqlite3.Error as exc:
            logger.warning("SQLite-Verbindung konnte nicht geschlossen werden: %s", exc)
        finally:
            self._conn = None

    def __enter__(self) -> ManualEntryService:
        """Context-Manager: oeffnet die Verbindung."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Context-Manager: schliesst die Verbindung."""
        self.close()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Legt das Schema idempotent an bzw. ruestet fehlende Spalten nach."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date  TEXT NOT NULL,
                ticket      TEXT NOT NULL DEFAULT '',
                summary     TEXT NOT NULL DEFAULT '',
                customer    TEXT NOT NULL DEFAULT '',
                hours       REAL NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_entries_date ON manual_entries(entry_date)")

        # Spalten nachruesten (idempotent) - fuer DBs aelterer Versionen.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(manual_entries)")}
        for column, ddl in (
            ("customer", "ALTER TABLE manual_entries ADD COLUMN customer TEXT NOT NULL DEFAULT ''"),
            ("created_at", "ALTER TABLE manual_entries ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"),
            ("updated_at", "ALTER TABLE manual_entries ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in existing:
                conn.execute(ddl)

        conn.commit()

    # --- Lesen ------------------------------------------------------

    def entries_between(self, date_from: date, date_to: date) -> list[ManualEntry]:
        """Liefert alle manuellen Eintraege im Zeitraum (inklusive Grenzen)."""
        try:
            cursor = self.connect().execute(
                """
                SELECT id, entry_date, ticket, summary, customer, hours, created_at, updated_at
                FROM manual_entries
                WHERE entry_date BETWEEN ? AND ?
                ORDER BY entry_date, ticket, id
                """,
                (date_from.isoformat(), date_to.isoformat()),
            )
            return [self._row_to_entry(row) for row in cursor]
        except (sqlite3.Error, ValueError) as exc:
            logger.warning("Manuelle Eintraege konnten nicht gelesen werden: %s", exc)
            return []

    def worklogs_between(
        self,
        date_from: date,
        date_to: date,
        author: str = "",
    ) -> list[WorklogEntry]:
        """Liefert die manuellen Eintraege des Zeitraums als WorklogEntry-Liste."""
        return [entry.to_worklog(author=author) for entry in self.entries_between(date_from, date_to)]

    def get(self, entry_id: int) -> ManualEntry | None:
        """Liest einen einzelnen Eintrag, None wenn es ihn nicht gibt."""
        try:
            row = (
                self.connect()
                .execute(
                    """
                SELECT id, entry_date, ticket, summary, customer, hours, created_at, updated_at
                FROM manual_entries WHERE id = ?
                """,
                    (entry_id,),
                )
                .fetchone()
            )
        except sqlite3.Error as exc:
            logger.warning("Manueller Eintrag %d konnte nicht gelesen werden: %s", entry_id, exc)
            return None
        return self._row_to_entry(row) if row is not None else None

    def distinct_customers(self) -> list[str]:
        """Alle in der Datenbank vorkommenden Kunden, alphabetisch."""
        try:
            cursor = self.connect().execute(
                "SELECT DISTINCT customer FROM manual_entries WHERE customer <> '' ORDER BY customer"
            )
            return [str(row[0]) for row in cursor]
        except sqlite3.Error as exc:
            logger.warning("Kundenliste konnte nicht gelesen werden: %s", exc)
            return []

    def count(self) -> int:
        """Anzahl aller gespeicherten manuellen Eintraege."""
        try:
            row = self.connect().execute("SELECT COUNT(*) FROM manual_entries").fetchone()
        except sqlite3.Error as exc:
            logger.warning("Manuelle Eintraege konnten nicht gezaehlt werden: %s", exc)
            return 0
        return int(row[0]) if row is not None else 0

    # --- Schreiben --------------------------------------------------

    def add(self, entry: ManualEntry) -> int:
        """Legt einen Eintrag an und liefert dessen Id (0 bei Fehler)."""
        now = datetime.now().isoformat(timespec="seconds")
        try:
            conn = self.connect()
            cursor = conn.execute(
                """
                INSERT INTO manual_entries
                    (entry_date, ticket, summary, customer, hours, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_date.isoformat(),
                    entry.ticket,
                    entry.summary,
                    entry.customer,
                    float(entry.hours),
                    now,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Manueller Eintrag konnte nicht gespeichert werden: %s", exc)
            return 0
        return int(cursor.lastrowid or 0)

    def update(self, entry: ManualEntry) -> bool:
        """Aktualisiert einen Eintrag. False, wenn keine Zeile getroffen wurde."""
        if entry.entry_id <= 0:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        try:
            conn = self.connect()
            cursor = conn.execute(
                """
                UPDATE manual_entries
                SET entry_date = ?, ticket = ?, summary = ?, customer = ?, hours = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    entry.entry_date.isoformat(),
                    entry.ticket,
                    entry.summary,
                    entry.customer,
                    float(entry.hours),
                    now,
                    entry.entry_id,
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Manueller Eintrag %d konnte nicht geaendert werden: %s", entry.entry_id, exc)
            return False
        return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Loescht einen Eintrag. False, wenn es ihn nicht gab."""
        try:
            conn = self.connect()
            cursor = conn.execute("DELETE FROM manual_entries WHERE id = ?", (entry_id,))
            conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Manueller Eintrag %d konnte nicht geloescht werden: %s", entry_id, exc)
            return False
        return cursor.rowcount > 0

    def import_from_legacy(self, legacy_path: Path) -> int:
        """Uebernimmt einmalig die manuellen Zeiten der Textual-TUI.

        Kopiert nur, wenn die EIGENE Datenbank noch keine Eintraege hat - so
        laeuft der Import genau einmal und ueberschreibt spaeter nichts.

        Args:
            legacy_path:
                Pfad zur manual-entries.db der TUI.

        Returns:
            Anzahl der uebernommenen Eintraege (0, wenn nichts zu tun war).
        """
        if legacy_path == self.db_path or not legacy_path.is_file():
            return 0
        if self.count() > 0:
            return 0

        try:
            source = sqlite3.connect(str(legacy_path))
            source.row_factory = sqlite3.Row
            try:
                rows = source.execute(
                    "SELECT entry_date, ticket, summary, customer, hours FROM manual_entries"
                ).fetchall()
            finally:
                source.close()
        except sqlite3.Error as exc:
            logger.warning("TUI-Manuell-DB %s konnte nicht gelesen werden: %s", legacy_path, exc)
            return 0

        imported = 0
        for row in rows:
            entry = ManualEntry(
                entry_date=date.fromisoformat(str(row["entry_date"])),
                ticket=str(row["ticket"] or ""),
                summary=str(row["summary"] or ""),
                customer=str(row["customer"] or ""),
                hours=float(row["hours"] or 0.0),
            )
            if self.add(entry) > 0:
                imported += 1

        if imported:
            logger.info("%d manuelle Eintraege aus %s uebernommen", imported, legacy_path)
        return imported

    # --- Interna ----------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> ManualEntry:
        """Wandelt eine DB-Zeile in einen ManualEntry."""
        return ManualEntry(
            entry_id=int(row["id"]),
            entry_date=date.fromisoformat(str(row["entry_date"])),
            ticket=str(row["ticket"] or ""),
            summary=str(row["summary"] or ""),
            customer=str(row["customer"] or ""),
            hours=float(row["hours"] or 0.0),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

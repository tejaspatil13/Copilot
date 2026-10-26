"""Each employee's "My sheet": properties collected from many searches, downloadable as one Excel file."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.excel import ExportRow
from app.models import ResultRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sheet_rows (
    employee_key TEXT NOT NULL,
    uarn TEXT NOT NULL,
    record_json TEXT NOT NULL,
    search TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (employee_key, uarn)
);
"""


def employee_key(name: str) -> str:
    return " ".join(name.split()).casefold()


class SheetStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with self._db() as con:
            con.executescript(_SCHEMA)

    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def add(self, employee: str, records: list[ResultRecord], search: str) -> tuple[int, int]:
        """Add records (one row per property). Returns (added, already_in_sheet)."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        key = employee_key(employee)
        added = 0
        with self._db() as con:
            for rec in records:
                cur = con.execute(
                    "INSERT OR IGNORE INTO sheet_rows VALUES (?, ?, ?, ?, ?)",
                    (key, rec.uarn, rec.model_dump_json(), search, now),
                )
                added += cur.rowcount
        return added, len(records) - added

    def rows(self, employee: str) -> list[ExportRow]:
        with self._db() as con:
            found = con.execute(
                "SELECT record_json, search, added_at FROM sheet_rows WHERE employee_key = ? "
                "ORDER BY added_at, rowid",
                (employee_key(employee),),
            ).fetchall()
        return [
            ExportRow(ResultRecord.model_validate_json(r[0]), r[1], datetime.fromisoformat(r[2])) for r in found
        ]

    def remove(self, employee: str, uarns: list[str]) -> int:
        with self._db() as con:
            return sum(
                con.execute(
                    "DELETE FROM sheet_rows WHERE employee_key = ? AND uarn = ?", (employee_key(employee), u)
                ).rowcount
                for u in uarns
            )

    def clear(self, employee: str) -> int:
        with self._db() as con:
            return con.execute("DELETE FROM sheet_rows WHERE employee_key = ?", (employee_key(employee),)).rowcount

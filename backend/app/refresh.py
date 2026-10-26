"""Periodic dataset refresh, run inside the web process.

Imports run as subprocesses (separate memory, crash-isolated) and build a new SQLite file that is
atomically swapped in, so searches keep working throughout.
"""
import asyncio
import logging
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings

log = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]
CHECK_EVERY_S = 6 * 3600


def imported_age_days(db_path: Path) -> float | None:
    """Days since the dataset was imported, or None if it does not exist / is unreadable."""
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            row = con.execute("SELECT value FROM meta WHERE key = 'imported_at'").fetchone()
        return (datetime.now(timezone.utc) - datetime.fromisoformat(row[0])).total_seconds() / 86400
    except (sqlite3.Error, TypeError, ValueError):
        return None


async def run_import(module: str) -> bool:
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", module, cwd=BACKEND_DIR)
    code = await proc.wait()
    (log.info if code == 0 else log.error)("dataset import %s finished with exit code %s", module, code)
    return code == 0


async def refresh_loop(settings: Settings, on_places_updated: Callable[[], None]) -> None:
    datasets = (
        ("app.voa.importer", settings.voa_db_path, settings.refresh_voa_days, lambda: None),
        ("app.contacts.overture_import", settings.places_db_path, settings.refresh_places_days, on_places_updated),
    )
    while True:
        for module, db_path, max_age, callback in datasets:
            age = imported_age_days(db_path)
            missing = age is None and settings.auto_import_on_start
            stale = age is not None and max_age > 0 and age >= max_age
            if missing or stale:
                log.info("refreshing %s (age: %s days)", module, "missing" if age is None else f"{age:.0f}")
                if await run_import(module):
                    callback()
        await asyncio.sleep(CHECK_EVERY_S)

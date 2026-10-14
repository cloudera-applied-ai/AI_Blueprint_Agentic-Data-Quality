"""Persistent app settings store.

SQLite database in the settings/ directory, which docker-compose bind-mounts
to the host so settings survive rebuilds and travel with the project folder.
Note: values (including API keys) are stored in plain text — the same
protection level as a .env file. Keep the settings/ dir out of git.
"""

import os
import sqlite3

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_DIR = os.path.join(_BACKEND_DIR, "settings")
DB_PATH = os.path.join(SETTINGS_DIR, "settings.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def get_all() -> dict[str, str]:
    """Return all stored settings as a dict."""
    with _connect() as conn:
        return dict(conn.execute("SELECT key, value FROM settings").fetchall())


def set_many(values: dict[str, str]) -> None:
    """Upsert the given settings."""
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(values.items()),
        )

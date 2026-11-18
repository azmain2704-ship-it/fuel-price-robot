"""Saving the prices in a small SQLite database (data/prices.db), which the robot commits back to the repo."""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "prices.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    week        TEXT PRIMARY KEY,      -- Monday the price was recorded, YYYY-MM-DD
    petrol      INTEGER NOT NULL,      -- hundredths of a penny per litre (16707 = 167.07p)
    diesel      INTEGER NOT NULL,
    first_seen  TEXT NOT NULL          -- when the robot first saved this week (UTC)
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT NOT NULL,         -- UTC
    status      TEXT NOT NULL,         -- 'ok' or 'failed'
    new_weeks   INTEGER NOT NULL DEFAULT 0,
    changed     INTEGER NOT NULL DEFAULT 0,
    message     TEXT NOT NULL DEFAULT ''
);
"""


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_prices(conn, prices):
    """Add new weeks and update any the government has revised. Returns (new_weeks, changed_weeks).

    Safe to run again and again: weeks already saved with the same numbers are left alone.
    """
    existing = {r["week"]: (r["petrol"], r["diesel"]) for r in conn.execute("SELECT * FROM prices")}
    new, changed = [], []
    stamp = now_utc()
    for week, petrol, diesel in prices:
        key = week.isoformat()
        if key not in existing:
            new.append((key, petrol, diesel, stamp))
        elif existing[key] != (petrol, diesel):
            changed.append((petrol, diesel, key))
    with conn:
        conn.executemany("INSERT INTO prices (week, petrol, diesel, first_seen) VALUES (?, ?, ?, ?)", new)
        conn.executemany("UPDATE prices SET petrol = ?, diesel = ? WHERE week = ?", changed)
    return len(new), len(changed)


def log_run(conn, status, new_weeks=0, changed=0, message=""):
    with conn:
        conn.execute(
            "INSERT INTO runs (ran_at, status, new_weeks, changed, message) VALUES (?, ?, ?, ?, ?)",
            (now_utc(), status, new_weeks, changed, message),
        )


def latest_weeks(conn, n=2):
    """The n most recent weeks, newest first."""
    return conn.execute("SELECT * FROM prices ORDER BY week DESC LIMIT ?", (n,)).fetchall()


def pence_text(hundredths):
    """16707 -> '167.07', using whole numbers only so nothing gets rounded on the way out."""
    return f"{hundredths // 100}.{hundredths % 100:02d}"


def export_csv(conn, path):
    """Write every week to a CSV in plain pence (167.07, not 16707), for Power BI and spreadsheets."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT week, petrol, diesel FROM prices ORDER BY week").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["week", "petrol_pence", "diesel_pence"])
        for r in rows:
            writer.writerow([r["week"], pence_text(r["petrol"]), pence_text(r["diesel"])])
    return path

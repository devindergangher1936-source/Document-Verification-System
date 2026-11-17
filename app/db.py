import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "documents.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    kind          TEXT NOT NULL,
    size          INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    text_hash     TEXT,
    uploaded_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    doc_type      TEXT,
    risk_score    INTEGER NOT NULL,
    auto_status   TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewer_note TEXT,
    reviewed_at   TEXT,
    has_ela       INTEGER NOT NULL DEFAULT 0,
    findings      TEXT NOT NULL,
    fields        TEXT NOT NULL,
    meta          TEXT NOT NULL,
    text_excerpt  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sha ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_text ON documents(text_hash);
"""

JSON_COLS = ("findings", "fields", "meta")


def init():
    DB_PATH.parent.mkdir(exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row, full=True):
    d = dict(row)
    for col in JSON_COLS:
        d[col] = json.loads(d[col])
    if not full:
        d.pop("meta", None)
        d.pop("text_excerpt", None)
    return d

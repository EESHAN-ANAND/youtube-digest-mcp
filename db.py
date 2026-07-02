"""Database layer for the YouTube digest MCP server (Neon Postgres).

Two tables:
  - channels     : a synced snapshot of your subscriptions.
  - seen_videos  : a log of videos already shown, so the daily digest never
                   repeats and you can catch up on missed days.

Run directly to create the tables:

    uv run python db.py
"""

import os

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id          TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    uploads_playlist_id TEXT NOT NULL,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seen_videos (
    video_id     TEXT PRIMARY KEY,
    channel_id   TEXT REFERENCES channels(channel_id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    url          TEXT NOT NULL,
    seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def get_conn():
    """Open a Postgres connection with dict-style rows."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    """Create the channels and seen_videos tables if they don't exist."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(_SCHEMA)  # executes both statements
        conn.commit()


if __name__ == "__main__":
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
    print("✅ Tables ready. Current tables in the database:")
    for r in rows:
        print("   -", r["table_name"])

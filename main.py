"""YouTube Digest MCP server (stdio, local).

A calm, once-a-day view of your YouTube subscriptions: which of your subscribed
channels posted today, without opening the algorithmic feed.

Tools:
  - sync_subscriptions() : pull your subscriptions into the `channels` table.
  - todays_uploads()     : channels that posted today (title + link + time).
  - uploads_since(date)  : catch up on a range of days.
  - list_channels()      : what's currently being watched.

Reads your account read-only via auth.py; stores state in Neon via db.py.
"""

from datetime import date, datetime

from fastmcp import FastMCP

from auth import get_youtube
from db import get_conn, init_db

mcp = FastMCP("youtube-digest")

init_db()  # make sure the channels / seen_videos tables exist


# --- helpers ---------------------------------------------------------------
def _parse_dt(iso: str) -> datetime:
    """Parse YouTube's publishedAt (e.g. '2026-07-01T12:34:56Z')."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _local_date(iso: str) -> date:
    """The upload's date in your local timezone."""
    return _parse_dt(iso).astimezone().date()


def _recent_uploads(yt, uploads_playlist_id: str, max_items: int = 15) -> list[dict]:
    """Fetch the most recent uploads from a channel's uploads playlist (cheap)."""
    resp = (
        yt.playlistItems()
        .list(part="snippet", playlistId=uploads_playlist_id, maxResults=max_items)
        .execute()
    )
    videos = []
    for item in resp.get("items", []):
        sn = item["snippet"]
        vid = sn["resourceId"]["videoId"]
        videos.append(
            {
                "video_id": vid,
                "title": sn["title"],
                "published_at": sn["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return videos


def _digest(keep) -> list[dict]:
    """Core: gather uploads across all channels where keep(local_date) is True."""
    yt = get_youtube()
    with get_conn() as conn:
        channels = conn.execute(
            "SELECT channel_id, title, uploads_playlist_id FROM channels"
        ).fetchall()

    results = []
    with get_conn() as conn:
        for ch in channels:
            for v in _recent_uploads(yt, ch["uploads_playlist_id"]):
                if keep(_local_date(v["published_at"])):
                    seen = conn.execute(
                        "SELECT 1 FROM seen_videos WHERE video_id = %s",
                        (v["video_id"],),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO seen_videos "
                        "(video_id, channel_id, title, published_at, url) "
                        "VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (video_id) DO NOTHING",
                        (v["video_id"], ch["channel_id"], v["title"],
                         v["published_at"], v["url"]),
                    )
                    results.append(
                        {
                            "channel": ch["title"],
                            "title": v["title"],
                            "url": v["url"],
                            "published_at": _parse_dt(v["published_at"]).astimezone().isoformat(),
                            "new": seen is None,
                        }
                    )
        conn.commit()

    results.sort(key=lambda r: r["published_at"], reverse=True)
    return results


# --- tools -----------------------------------------------------------------
@mcp.tool()
def sync_subscriptions() -> dict:
    """Pull your current YouTube subscriptions into the channels table.

    Run this first, and again whenever you subscribe/unsubscribe.
    """
    yt = get_youtube()

    # 1) collect all subscribed channel ids (paginated).
    channel_ids = []
    req = yt.subscriptions().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        resp = req.execute()
        for item in resp.get("items", []):
            channel_ids.append(item["snippet"]["resourceId"]["channelId"])
        req = yt.subscriptions().list_next(req, resp)

    # 2) look up each channel's title + uploads playlist (50 ids per call).
    channels = []
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        resp = (
            yt.channels()
            .list(part="snippet,contentDetails", id=",".join(batch), maxResults=50)
            .execute()
        )
        for item in resp.get("items", []):
            channels.append(
                (
                    item["id"],
                    item["snippet"]["title"],
                    item["contentDetails"]["relatedPlaylists"]["uploads"],
                )
            )

    # 3) upsert into the channels table.
    with get_conn() as conn:
        for cid, title, uploads in channels:
            conn.execute(
                "INSERT INTO channels (channel_id, title, uploads_playlist_id, synced_at) "
                "VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (channel_id) DO UPDATE SET "
                "title = EXCLUDED.title, "
                "uploads_playlist_id = EXCLUDED.uploads_playlist_id, "
                "synced_at = now()",
                (cid, title, uploads),
            )
        conn.commit()

    return {"status": "synced", "channels_synced": len(channels)}


@mcp.tool()
def todays_uploads() -> dict:
    """Which subscribed channels posted TODAY (your local date). The daily digest."""
    today = datetime.now().astimezone().date()
    uploads = _digest(lambda d: d == today)
    return {"date": today.isoformat(), "count": len(uploads), "uploads": uploads}


@mcp.tool()
def uploads_since(start_date: str) -> dict:
    """Uploads from start_date (YYYY-MM-DD) up to now. For catching up on missed days."""
    d0 = date.fromisoformat(start_date)
    uploads = _digest(lambda d: d >= d0)
    return {"since": start_date, "count": len(uploads), "uploads": uploads}


@mcp.tool()
def list_channels() -> dict:
    """List the channels currently being watched (from the last sync)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT channel_id, title, synced_at FROM channels ORDER BY title"
        ).fetchall()
    return {
        "count": len(rows),
        "channels": [
            {
                "title": r["title"],
                "channel_id": r["channel_id"],
                "synced_at": r["synced_at"].isoformat() if r["synced_at"] else None,
            }
            for r in rows
        ],
    }


if __name__ == "__main__":
    # HTTP so it can be deployed remotely (FastMCP Cloud). On the cloud the
    # platform imports `mcp` and serves it; this block is for local runs.
    mcp.run(transport="http", host="127.0.0.1", port=8000)

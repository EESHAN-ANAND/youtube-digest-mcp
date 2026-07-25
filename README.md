# YouTube Digest MCP

**A quiet, once-a-day answer to one question: did anyone I actually follow post something?**

No feed. No autoplay. No thumbnails engineered to hijack your attention. Just the channels you chose, and what they published today.

![Subscriptions in focus, feed out of focus](static/subscriptions.png)

---

## Why this exists

YouTube hosts some of the best explanatory material ever made — pure maths, orbital mechanics, monetary policy, competition climbing, machine learning, how companies actually work. It also hosts an industrial-scale outrage machine, and the same interface serves both.

The problem isn't the content you subscribed to. It's everything the recommendation engine bolts on around it. You open the tab to catch one video from a channel you trust, and thirty minutes later you're deep in something you didn't choose, don't value, and won't remember.

The subscriptions page was supposed to solve this. It doesn't — it's still a feed, still infinite, still ranked by engagement rather than by your intent.

So this server skips the interface entirely. It reads your subscriptions through the YouTube Data API, checks which of those channels published today, and hands back a list. Titles and links. That's the whole product.

**What you get:** the channels you deliberately chose.
**What you don't get:** everything designed to keep you there.

---

## What it does

Four tools, exposed over MCP:

| Tool | What it does |
|---|---|
| `sync_subscriptions()` | Pulls your current subscriptions into the `channels` table. Run once, then again whenever you subscribe or unsubscribe. |
| `todays_uploads()` | The daily digest — which subscribed channels posted today, in your local timezone. |
| `uploads_since(start_date)` | Catch up after a few days away. `YYYY-MM-DD`. |
| `list_channels()` | What's currently being watched, from the last sync. |

Ask your MCP client in plain English — *"anything new today?"*, *"what did I miss since Monday?"* — and it picks the right tool.

---

## How it works

```
main.py    FastMCP server — the four tools, digest logic, local-date handling
auth.py    Google OAuth — one browser login, then silent token refresh
db.py      Neon Postgres — schema and connections
```

**`auth.py`** requests exactly one scope:

```python
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
```

Read-only. The server can see your subscriptions and uploads. It cannot post, comment, subscribe, unsubscribe, or change one thing about your account — not by choice at runtime, but because Google never issued it the permission. It also supports a headless path: set `GOOGLE_TOKEN_JSON` and it refreshes silently with no browser, which is what makes cloud deployment possible.

**`db.py`** defines two tables in Neon:

```sql
channels (
    channel_id           TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    uploads_playlist_id  TEXT NOT NULL,
    synced_at            TIMESTAMPTZ NOT NULL DEFAULT now()
)

seen_videos (
    video_id      TEXT PRIMARY KEY,
    channel_id    TEXT REFERENCES channels(channel_id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    published_at  TIMESTAMPTZ NOT NULL,
    url           TEXT NOT NULL,
    seen_at       TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

`channels` is a snapshot of your subscriptions plus each channel's uploads playlist — reading that playlist is far cheaper in API quota than searching. `seen_videos` is the memory: every result carries a `new` flag, so a second look at the same day tells you what you'd already seen.

Because it's Postgres and not a local file, the state survives restarts and redeploys.

---

## Setup

**1. Google Cloud**

Create a project, enable **YouTube Data API v3**, and create an **OAuth 2.0 Client ID** of type *Desktop app*. Download the JSON as `client_secret.json` in the project root.

**2. Neon**

Create a project at [neon.com](https://neon.com) and copy the connection string.

**3. Local**

```bash
cd youtube-digest-mcp
uv sync

cat > .env <<'EOF'
DATABASE_URL=postgresql://user:password@host.neon.tech/dbname?sslmode=require
EOF

uv run python db.py      # create the tables
uv run python auth.py    # one-time browser login → token.json
uv run main.py           # serves http://127.0.0.1:8000/mcp
```

Then in your MCP client: `sync_subscriptions()` once, `todays_uploads()` daily.

**4. Deploy (optional)**

Run `auth.py` locally first, then set two environment variables on the host:

- `DATABASE_URL` — your Neon connection string
- `GOOGLE_TOKEN_JSON` — the full contents of `token.json`

The headless branch in `get_credentials()` picks up the token and refreshes it silently, so no browser is ever needed on the server.

---

## Design notes

**Read-only by construction.** The narrow OAuth scope is the security boundary. A prompt telling the model not to modify your account would be a suggestion; an unissued permission is a guarantee.

**Local dates, not UTC.** `_local_date()` converts each `publishedAt` into your own timezone before comparing. "Today" means your today, not Google's.

**Dead channels don't break the run.** Terminated, private, and empty channels raise `HttpError` on their uploads playlist. Those are caught per channel and skipped, so one broken subscription out of fifty doesn't take down the digest.

**Quota-aware.** Reading each channel's uploads playlist costs a fraction of what `search.list` costs, and only the 15 most recent items are fetched per channel.

---

## Secrets

`.gitignore` excludes `.env`, `client_secret.json`, and `token.json`. Keep it that way — `token.json` is a live credential for your Google account.

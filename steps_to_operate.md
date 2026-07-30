# Steps to Operate

A complete walkthrough for getting this server running from scratch — Google credentials, database, local run, and optional deployment.

No prior experience with the Google API Console or MCP is assumed. If you can copy and paste into a terminal, you can finish this.

**Time:** about 20 minutes, most of it waiting on Google's console.

---

## Contents

1. [Before you start](#1-before-you-start)
2. [Google Cloud setup](#2-google-cloud-setup)
3. [Database setup (Neon)](#3-database-setup-neon)
4. [Local installation](#4-local-installation)
5. [First login](#5-first-login)
6. [Connecting an MCP client](#6-connecting-an-mcp-client)
7. [Daily use](#7-daily-use)
8. [Deploying to a server](#8-deploying-to-a-server-optional)
9. [Troubleshooting](#9-troubleshooting)
10. [Security notes](#10-security-notes)

---

## 1. Before you start

You need:

- **Python 3.10 or newer** — check with `python3 --version`
- **[uv](https://docs.astral.sh/uv/)** — the package manager this project uses. Install it with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **A Google account** with YouTube subscriptions on it
- **A free [Neon](https://neon.com) account** for the Postgres database

Everything below is free. The YouTube Data API has a generous daily quota and this server is deliberately frugal with it.

Clone the repo and move into it:

```bash
git clone <your-repo-url>
cd youtube-digest-mcp
```

---

## 2. Google Cloud setup

This is the longest part. You're creating an app that can read *your own* YouTube data. Follow it in order — steps depend on the ones before.

### 2.1 Create a project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Sign in with the Google account whose subscriptions you want to read
3. Click the project dropdown in the top bar → **New Project**
4. Name it anything (`youtube-digest` works) → **Create**
5. Wait for the notification, then make sure the new project is selected in the dropdown

> Everything after this happens *inside* this project. If a screen looks empty or wrong, check the project selector first — it's the most common mistake.

### 2.2 Enable the YouTube Data API

1. In the search bar at the top, type **YouTube Data API v3**
2. Click the result under "Marketplace"
3. Click **Enable**

Without this, every API call returns a 403 telling you the API is disabled.

### 2.3 Configure the OAuth consent screen

Google requires this before it will issue you any credentials.

1. Left sidebar → **APIs & Services** → **OAuth consent screen**
2. User type: **External** → **Create**
   - *"External" sounds wrong for a personal tool, but "Internal" is only available to Google Workspace organisations. External is correct here.*
3. Fill in the required fields:
   - **App name:** `YouTube Digest`
   - **User support email:** your email
   - **Developer contact email:** your email
   - Leave everything else blank
4. **Save and Continue**
5. **Scopes** screen → click **Add or Remove Scopes**
   - Filter for `youtube.readonly`
   - Tick `.../auth/youtube.readonly`
   - **Update** → **Save and Continue**
6. **Test users** screen → **Add Users** → enter your own Gmail address → **Add**
   - **This step is not optional.** While the app is in Testing status, only listed test users can log in. If you skip it, your own login will be rejected.
7. **Save and Continue** → **Back to Dashboard**

> **Important, and the cause of most later breakage:** while your app sits in **Testing** status, Google expires refresh tokens after **7 days**. Your server will work fine and then suddenly start failing with `invalid_grant`. See [section 9](#9-troubleshooting) for the fix and the permanent solution.

### 2.4 Create the OAuth client ID

1. Left sidebar → **APIs & Services** → **Credentials**
2. **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
   - *Must be Desktop app. "Web application" requires redirect URIs that the local login flow doesn't use, and it will fail.*
4. Name it anything → **Create**
5. A dialog appears with your client ID and secret → click **Download JSON**
6. Rename the downloaded file to exactly `client_secret.json` and move it into the project root:

```bash
mv ~/Downloads/client_secret_*.json ./client_secret.json
```

Verify it landed correctly:

```bash
ls client_secret.json
```

This file identifies your *app* to Google. It is not yet a login — that comes in section 5.

---

## 3. Database setup (Neon)

The server stores your synced channel list and a record of videos it has already shown you. Postgres rather than a local file, so the state survives restarts and redeploys.

1. Sign up at [neon.com](https://neon.com) (free tier is plenty)
2. Create a project — any name, any region, though closer to you is faster
3. On the dashboard, find the **Connection string** and copy it

It looks like:

```
postgresql://user:password@ep-something-12345.region.aws.neon.tech/neondb?sslmode=require
```

Keep the `?sslmode=require` on the end. Neon rejects connections without it.

Now create your `.env` file in the project root:

```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql://paste-your-connection-string-here
EOF
```

Or just create `.env` in an editor with that one line. Either way, `.env` is already in `.gitignore` and must stay there.

---

## 4. Local installation

Install dependencies:

```bash
uv sync
```

This reads `pyproject.toml` and `uv.lock` and builds a `.venv` in the project folder. It's reproducible — you get the exact versions this was built against.

Now create the database tables:

```bash
uv run python db.py
```

Expected output:

```
✅ Tables ready. Current tables in the database:
   - channels
   - seen_videos
```

If you see that, your `DATABASE_URL` is correct and the database half is done. If you get a connection error, go back to section 3 — the string is almost certainly truncated or missing `?sslmode=require`.

---

## 5. First login

This is where you actually grant the app access to your account.

```bash
uv run python auth.py
```

What happens:

1. A browser window opens automatically
2. Choose the Google account you added as a test user in step 2.3
3. You'll see **"Google hasn't verified this app"** — this is expected and correct. It's *your* app, unverified because you never submitted it for review, which you don't need to do for personal use. Click **Advanced** → **Go to YouTube Digest (unsafe)**
4. Review the permission — it should ask only to *view* your YouTube account. Click **Continue**
5. The browser shows a success message; you can close the tab

Back in your terminal:

```
✅ Logged in successfully as channel: YOUR CHANNEL NAME
Token saved to: /path/to/youtube-digest-mcp/token.json
```

You now have `token.json` in the project root. **This file is a live credential for your Google account.** It's gitignored. Never commit it, never paste it into a chat, never put it in a screenshot.

Start the server:

```bash
uv run main.py
```

It serves on `http://127.0.0.1:8000/mcp`. Leave it running.

---

## 6. Connecting an MCP client

### Claude Desktop

Open the config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the server:

```json
{
  "mcpServers": {
    "youtube-digest": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/youtube-digest-mcp",
        "run",
        "main.py"
      ]
    }
  }
}
```

Use the **absolute** path — `~` and relative paths won't resolve. Get it with `pwd` inside the project folder.

Restart Claude Desktop completely (quit, don't just close the window). The four tools should appear in the tools menu.

### Other MCP clients

Point the client at `http://127.0.0.1:8000/mcp` while the server is running, or use the same `uv run main.py` command pattern.

---

## 7. Daily use

**Run once, first:**

```
sync_subscriptions()
```

This pulls every channel you're subscribed to into the database. Re-run it whenever you subscribe or unsubscribe — otherwise new subscriptions won't appear in your digest.

**Then, whenever you want:**

| Ask | Tool it calls |
|---|---|
| *"Anything new today?"* | `todays_uploads()` |
| *"What did I miss since Monday?"* | `uploads_since("2026-07-27")` |
| *"What channels am I watching?"* | `list_channels()` |

You don't need to name the tools. Ask in plain English and the client picks the right one.

Every result carries a `new` flag — `true` the first time a video appears, `false` if you've already been shown it. Checking twice in one day won't show you the same thing twice.

---

## 8. Deploying to a server (optional)

Skip this if you only run it locally.

The problem with deploying: there's no browser on a server to complete the OAuth login. This project solves it by letting you complete the login **locally** and then hand the resulting token to the server.

1. Complete section 5 on your own machine first, so `token.json` exists
2. Copy its contents to your clipboard without printing it to the terminal:
   ```bash
   cat token.json | pbcopy      # macOS
   cat token.json | xclip -sel c # Linux
   ```
   Avoid plain `cat` — you don't want a live credential sitting in your scrollback.
3. On your host (FastMCP Cloud, Railway, Render, wherever), set two environment variables:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Your Neon connection string |
   | `GOOGLE_TOKEN_JSON` | The entire contents of `token.json`, `{` to `}` |

4. Deploy

When `GOOGLE_TOKEN_JSON` is set, `auth.py` builds credentials from it and refreshes silently — no browser, no `client_secret.json` on the server.

When you update that variable, **clear the old value completely** before pasting. Pasting alongside the old one produces malformed JSON, and the error message you get won't tell you that's what happened.

---

## 9. Troubleshooting

### `invalid_grant: Bad Request`

The most common failure, and worth understanding rather than just fixing.

`invalid_grant` means your refresh token is no longer valid. Not malformed — rejected. Causes, in order of likelihood:

1. **Your app is in Testing status.** Google expires refresh tokens after **7 days** for unpublished apps. This will happen to you roughly weekly until you fix it properly.
2. You revoked the app's access in your Google account settings
3. The Google Cloud project or OAuth client was deleted
4. The token was issued for different scopes than the code requests

**Quick fix** — re-mint the token:

```bash
uv run python auth.py
```

If deployed, also update `GOOGLE_TOKEN_JSON` on the host with the new `token.json` contents.

**Permanent fix** — publish the app:

1. Google Cloud Console → **APIs & Services** → **OAuth consent screen**
2. Click **Publish App** → confirm
3. Re-run `uv run python auth.py`

Because you're only using sensitive-but-not-restricted scopes for your own account, publishing doesn't require Google's verification review. Refresh tokens then last indefinitely unless revoked.

> A confusing detail when this breaks: `list_channels()` keeps working perfectly while everything else fails, because it reads from the database rather than calling YouTube. The server looks half-alive. If some tools work and others don't, suspect the token before you suspect the code.

### `403 — YouTube Data API has not been used in project...`

You skipped or didn't complete step 2.2. Enable the API, then wait a couple of minutes for it to propagate.

### `Access blocked: YouTube Digest has not completed the Google verification process`

You're logging in with an account that isn't on the test users list. Either add it (step 2.3, item 6) or sign in with the account you did add.

### `KeyError: 'DATABASE_URL'`

The `.env` file is missing, in the wrong directory, or the variable name is misspelled. It must sit in the project root next to `main.py`.

### Connection errors from Neon

Check that `?sslmode=require` is still on the end of your connection string, and that your Neon project isn't suspended — the free tier sleeps after inactivity and takes a few seconds to wake.

### A channel is missing from the digest

Run `sync_subscriptions()` again. The channel list is a snapshot, not a live read, so subscriptions made after your last sync are invisible until you re-sync.

Also note: terminated, private, and empty channels are skipped deliberately. One dead subscription won't break the run, but it also won't appear.

### Quota exceeded

Default quota is 10,000 units/day. This server uses playlist reads (cheap) rather than search (expensive), and caps at 15 recent items per channel, so normal use stays far under. If you're hitting it, you're probably calling `sync_subscriptions()` in a loop.

---

## 10. Security notes

Three files must never be committed. They're all in `.gitignore` — check it's intact before your first push:

| File | What it is |
|---|---|
| `.env` | Your database credentials |
| `client_secret.json` | Identifies your app to Google |
| `token.json` | **A live credential for your Google account** |

`token.json` is the dangerous one. Anyone holding it can read your YouTube account until you revoke it.

If you ever leak one: go to [myaccount.google.com/permissions](https://myaccount.google.com/permissions), find the app, click **Remove Access**. That invalidates the token immediately. Then re-run `auth.py` to get a fresh one.

**On the read-only scope:** this server requests exactly one permission — `youtube.readonly`. It cannot post, comment, subscribe, unsubscribe, or modify anything, and not as a matter of good behaviour at runtime. Google never issued it the permission to do those things. An instruction telling a model not to modify your account is a suggestion; an unissued permission is a guarantee. That distinction is the entire security design here, and it's worth keeping if you fork this.

---

## Quick reference

```bash
uv sync                    # install dependencies
uv run python db.py        # create tables
uv run python auth.py      # log in / re-mint token
uv run main.py             # start the server
```

Then `sync_subscriptions()` once, `todays_uploads()` daily.

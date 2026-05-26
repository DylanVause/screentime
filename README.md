# ScreenTime

A lightweight, self-hosted screen-time tracker. A Windows client silently records which application has focus and for how long, then uploads the data to your own Ubuntu server. An admin web interface lets you view charts and session logs per device.

```
Windows PC                        Ubuntu Server
──────────────────                ─────────────────────────────────
tracker.py (background)  ──────▶  /api/v1/sessions  (API key auth)
  • detects active window                │
  • records app + title                  ▼
  • buffers in SQLite            SQLite database
  • uploads every 5 min                  │
                                         ▼
                                  Admin web UI
                                  • dashboard + charts
                                  • per-device analytics
                                  • API key management
```

---

## Features

- **Active-window tracking** — app name, window title, start/end time, duration
- **Local buffer** — sessions are stored in a local SQLite file and retried if the upload fails
- **Deduplication** — each session carries a UUID; the server ignores duplicate uploads
- **Multi-device** — one admin account, many devices, each with its own API key
- **Analytics** — daily activity charts, per-app breakdown, scrollable session log with date-range filtering
- **Privacy-first** — no screenshots, no third-party services, all data stays on your server

---

## Project structure

```
screentime/
├── docker-compose.yml       # Docker deployment
├── .env.example             # Required env vars
├── client/                  # Windows tracker
│   ├── tracker.py           # Main loop
│   ├── uploader.py          # HTTP upload client
│   ├── local_storage.py     # SQLite session buffer
│   ├── config.py            # Config loader
│   ├── config.toml          # ← edit this
│   ├── requirements.txt
│   ├── run.bat              # Launch with console
│   ├── run_silent.vbs       # Launch silently (no window)
│   └── install_startup.bat  # Add to Windows startup
└── server/                  # Ubuntu server
    ├── Dockerfile
    ├── app.py               # Flask app (all routes + DB)
    ├── requirements.txt
    ├── start.sh             # Quick dev launcher
    ├── setup.sh             # One-shot production setup
    └── templates/
        ├── base.html
        ├── login.html
        ├── setup.html
        ├── dashboard.html
        ├── devices.html
        ├── device_detail.html
        └── api_keys.html
```

---

## Server setup

### Docker (recommended)

```bash
git clone <your-repo> screentime
cd screentime

cp .env.example .env
# Edit .env and set a strong SECRET_KEY

docker compose up -d
# open http://localhost:5000/setup
```

The database is stored in a Docker named volume (`screentime_data`) and persists across restarts. To back it up:

```bash
docker run --rm -v screentime_screentime_data:/data -v $(pwd):/backup alpine \
  cp /data/screentime.db /backup/screentime.db
```

### Ubuntu (bare-metal)

```bash
git clone <your-repo> /opt/screentime
cd /opt/screentime/server

# Set your domain (or leave as localhost for local-only access)
DOMAIN=screentime.example.com sudo bash setup.sh
```

This script:
1. Installs Python 3, pip, venv, and nginx
2. Creates a virtualenv and installs dependencies
3. Registers a `systemd` service (gunicorn on `127.0.0.1:5000`)
4. Writes an nginx reverse-proxy config for your domain
5. Starts everything

After it finishes, open `http://your-domain/setup` to create your admin account.

### Add HTTPS (recommended, bare-metal only)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d screentime.example.com
```

### Manual / development

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

SECRET_KEY=changeme python3 app.py
# open http://localhost:5000/setup
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | random (ephemeral) | Flask session signing key — **set this** in production |
| `DB_PATH` | `screentime.db` | Path to the SQLite database file |
| `PORT` | `5000` | Port gunicorn listens on |
| `DEBUG` | `` | Set to `1` to enable Flask debug mode |

---

## Client setup (Windows)

### Requirements

- Python 3.9+ for Windows ([python.org](https://www.python.org/downloads/windows/))
- The `pywin32` post-install step must run — the installer normally handles this automatically

### Install

```bat
cd client
pip install -r requirements.txt
```

### Configure

Edit `client/config.toml`:

```toml
[server]
url     = "https://screentime.example.com"
api_key = "st_PASTE_YOUR_KEY_HERE"

[device]
name = "Home Desktop"

[tracking]
poll_interval    = 1    # seconds between window checks
upload_interval  = 300  # seconds between uploads (5 min)
min_session_seconds = 2 # discard shorter sessions (accidental clicks)
```

Get an API key from the admin interface: **API Keys → New Key**.

### Run

```bat
# With a visible console (good for testing)
run.bat

# Silently in the background
wscript run_silent.vbs
```

Press `Ctrl+C` in the console to stop — the current session is saved and a final upload is attempted on shutdown.

### Auto-start on login

```bat
install_startup.bat
```

This creates a shortcut to `run_silent.vbs` in your Windows startup folder. The tracker will start silently every time you log in.

To remove it, open `shell:startup` in Explorer and delete `ScreenTimeTracker.lnk`.

---

## Admin interface

### Dashboard

- Total tracked time today and over the last 7 days
- Doughnut chart of top apps today
- Bar chart of daily activity (last 7 days)
- Device table with per-device time today and last-seen status

### Devices

Lists all devices that have ever uploaded data, along with their associated API key, total sessions, and cumulative tracked time.

### Device detail

Click **Analytics** on any device. Use the date-range picker to filter. Shows:
- Summary stats (total time, session count, unique apps)
- Horizontal bar chart of top apps
- Daily activity bar chart
- Scrollable session log (app, window title, start time, duration)

### API Keys

Create, revoke, re-activate, or delete API keys. Each key:
- Can be used by one or more devices (devices are identified by `device_name` in the config)
- Shows the number of associated devices and when it was last used
- Deleting a key removes all associated device and session data

---

## API reference

These endpoints are used by the client. Authentication is via the `X-API-Key` header.

### `POST /api/v1/sessions`

Upload a batch of sessions.

**Request:**
```json
{
  "device_name": "Home Desktop",
  "sessions": [
    {
      "session_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "start":  "2026-05-26T14:00:00",
      "end":    "2026-05-26T14:35:12",
      "app":    "chrome.exe",
      "title":  "GitHub",
      "duration_seconds": 2112
    }
  ]
}
```

**Response:**
```json
{ "ok": true, "accepted": 1 }
```

Sessions with a `session_uuid` that was already accepted are silently ignored (idempotent).

### `POST /api/v1/ping`

Update the device's `last_seen_at` timestamp without uploading sessions.

```json
{ "device_name": "Home Desktop" }
```

---

## Dependencies

### Client

| Package | Purpose |
|---------|---------|
| `pywin32` | `GetForegroundWindow`, `GetWindowThreadProcessId` |
| `psutil` | Resolve PID → process name |
| `requests` | HTTP upload |
| `tomli` | TOML config parser (Python < 3.11 only) |

### Server

| Package | Purpose |
|---------|---------|
| `flask` | Web framework |
| `bcrypt` | Admin password hashing |
| `gunicorn` | Production WSGI server |

---

## Notes

- All timestamps are stored and displayed as **UTC**.
- The server database is a single SQLite file (`screentime.db`). Back it up with a simple `cp` or `rsync`.
- The client keeps sessions in its own `sessions.db` until they are successfully uploaded. If the server is unreachable, nothing is lost — the next upload attempt will include the pending sessions.
- Sessions shorter than `min_session_seconds` (default: 2 s) are discarded to filter out noise from brief window switches.

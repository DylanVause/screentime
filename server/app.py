"""
ScreenTime Server — Flask application.

Routes:
  GET/POST /setup          First-time admin account creation
  GET/POST /login          Admin login
  GET      /logout         Admin logout
  GET      /               Dashboard
  GET      /devices        Device list
  GET      /devices/<id>   Per-device analytics (date range filter)
  GET/POST /api-keys       List / create API keys
  POST     /api-keys/<id>/revoke   Disable a key
  POST     /api-keys/<id>/delete   Delete a key

  POST     /api/v1/sessions   Client upload endpoint (X-API-Key auth)
  POST     /api/v1/ping       Client heartbeat
"""

import os
import secrets
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from pathlib import Path

import bcrypt
from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
    flash,
    abort,
)

app = Flask(__name__)

# SECRET_KEY must be set in the environment for production.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
if not os.environ.get("SECRET_KEY"):
    app.logger.warning(
        "SECRET_KEY not set — using a random key.  Sessions will not survive restarts."
    )

DB_PATH = Path(os.environ.get("DB_PATH", "screentime.db"))


# ─── Database ────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db() -> None:
    with sqlite3.connect(str(DB_PATH)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id            INTEGER PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY,
                admin_id     INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                key          TEXT UNIQUE NOT NULL,
                name         TEXT NOT NULL,
                created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
                last_used_at TEXT,
                is_active    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS devices (
                id           INTEGER PRIMARY KEY,
                api_key_id   INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
                device_name  TEXT NOT NULL,
                last_seen_at TEXT,
                created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
                UNIQUE(api_key_id, device_name)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id               INTEGER PRIMARY KEY,
                device_id        INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                client_session_id TEXT,
                start_time       TEXT NOT NULL,
                end_time         TEXT NOT NULL,
                app_name         TEXT NOT NULL,
                window_title     TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                uploaded_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
                UNIQUE(device_id, client_session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_device_start
                ON sessions(device_id, start_time);
            CREATE INDEX IF NOT EXISTS idx_sessions_app
                ON sessions(app_name);
            """
        )


init_db()


# ─── Template filters ────────────────────────────────────────────────────────


@app.template_filter("duration")
def fmt_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


@app.template_filter("appname")
def fmt_appname(name: str) -> str:
    if name and name.lower().endswith(".exe"):
        return name[:-4]
    return name or "unknown"


@app.template_filter("dt")
def fmt_dt(value: str) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", ""))
        return dt.strftime("%b %d %Y, %H:%M") + " UTC"
    except ValueError:
        return value


@app.template_filter("ago")
def fmt_ago(value: str) -> str:
    if not value:
        return "never"
    try:
        dt = datetime.fromisoformat(value.replace("Z", ""))
        diff = int((datetime.utcnow() - dt).total_seconds())
        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"
    except ValueError:
        return value


# ─── Auth decorators ─────────────────────────────────────────────────────────


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)

    return decorated


def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "").strip()
        if not key:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        db = get_db()
        row = db.execute(
            "SELECT id, admin_id FROM api_keys WHERE key = ? AND is_active = 1",
            (key,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Invalid or revoked API key"}), 401
        db.execute(
            "UPDATE api_keys SET last_used_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE id = ?",
            (row["id"],),
        )
        db.commit()
        g.api_key_id = row["id"]
        g.api_admin_id = row["admin_id"]
        return f(*args, **kwargs)

    return decorated


# ─── Setup ──────────────────────────────────────────────────────────────────


@app.route("/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] > 0:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or not password:
            flash("Username and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        else:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            db.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (username, pw_hash),
            )
            db.commit()
            flash("Admin account created — please log in.", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")


# ─── Login / logout ──────────────────────────────────────────────────────────


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        return redirect(url_for("setup"))
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        row = db.execute(
            "SELECT id, password_hash FROM admins WHERE username = ?", (username,)
        ).fetchone()
        if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            session.clear()
            session["admin_id"] = row["id"]
            session["username"] = username
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Dashboard ───────────────────────────────────────────────────────────────


@app.route("/")
@login_required
def dashboard():
    db = get_db()
    admin_id = session["admin_id"]
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=6)).isoformat()

    # All devices belonging to this admin.
    devices = db.execute(
        """
        SELECT d.id, d.device_name, d.last_seen_at,
               COALESCE(SUM(s.duration_seconds), 0) AS total_today
        FROM devices d
        JOIN api_keys ak ON ak.id = d.api_key_id
        LEFT JOIN sessions s ON s.device_id = d.id
            AND DATE(s.start_time) = ?
        WHERE ak.admin_id = ?
        GROUP BY d.id
        ORDER BY d.last_seen_at DESC
        """,
        (today, admin_id),
    ).fetchall()

    device_ids = [d["id"] for d in devices]

    top_apps_today = []
    daily_totals = []
    total_today = 0

    if device_ids:
        ph = ",".join("?" * len(device_ids))

        top_apps_today = db.execute(
            f"""
            SELECT app_name, SUM(duration_seconds) AS total
            FROM sessions
            WHERE device_id IN ({ph})
              AND DATE(start_time) = ?
            GROUP BY app_name
            ORDER BY total DESC
            LIMIT 10
            """,
            (*device_ids, today),
        ).fetchall()

        daily_totals = db.execute(
            f"""
            SELECT DATE(start_time) AS day,
                   ROUND(SUM(duration_seconds) / 3600.0, 2) AS hours
            FROM sessions
            WHERE device_id IN ({ph})
              AND DATE(start_time) BETWEEN ? AND ?
            GROUP BY day
            ORDER BY day
            """,
            (*device_ids, week_ago, today),
        ).fetchall()

        total_today = sum(d["total_today"] for d in devices)

    return render_template(
        "dashboard.html",
        devices=devices,
        top_apps_today=top_apps_today,
        daily_totals=daily_totals,
        total_today=total_today,
        today=today,
    )


# ─── Devices ─────────────────────────────────────────────────────────────────


@app.route("/devices")
@login_required
def devices():
    db = get_db()
    rows = db.execute(
        """
        SELECT d.id, d.device_name, d.last_seen_at, d.created_at,
               ak.name AS key_name,
               COUNT(s.id) AS session_count,
               COALESCE(SUM(s.duration_seconds), 0) AS total_seconds
        FROM devices d
        JOIN api_keys ak ON ak.id = d.api_key_id
        LEFT JOIN sessions s ON s.device_id = d.id
        WHERE ak.admin_id = ?
        GROUP BY d.id
        ORDER BY d.last_seen_at DESC
        """,
        (session["admin_id"],),
    ).fetchall()
    return render_template("devices.html", devices=rows)


@app.route("/devices/<int:device_id>")
@login_required
def device_detail(device_id):
    db = get_db()
    device = db.execute(
        """
        SELECT d.*, ak.name AS key_name
        FROM devices d
        JOIN api_keys ak ON ak.id = d.api_key_id
        WHERE d.id = ? AND ak.admin_id = ?
        """,
        (device_id, session["admin_id"]),
    ).fetchone()
    if not device:
        abort(404)

    date_from = request.args.get("from", (date.today() - timedelta(days=6)).isoformat())
    date_to = request.args.get("to", date.today().isoformat())

    top_apps = db.execute(
        """
        SELECT app_name,
               SUM(duration_seconds) AS total,
               COUNT(*) AS session_count
        FROM sessions
        WHERE device_id = ?
          AND DATE(start_time) BETWEEN ? AND ?
        GROUP BY app_name
        ORDER BY total DESC
        LIMIT 20
        """,
        (device_id, date_from, date_to),
    ).fetchall()

    daily = db.execute(
        """
        SELECT DATE(start_time) AS day,
               ROUND(SUM(duration_seconds) / 3600.0, 2) AS hours
        FROM sessions
        WHERE device_id = ?
          AND DATE(start_time) BETWEEN ? AND ?
        GROUP BY day
        ORDER BY day
        """,
        (device_id, date_from, date_to),
    ).fetchall()

    total_seconds = db.execute(
        """
        SELECT COALESCE(SUM(duration_seconds), 0) AS total
        FROM sessions
        WHERE device_id = ?
          AND DATE(start_time) BETWEEN ? AND ?
        """,
        (device_id, date_from, date_to),
    ).fetchone()["total"]

    recent = db.execute(
        """
        SELECT start_time, end_time, app_name, window_title, duration_seconds
        FROM sessions
        WHERE device_id = ?
          AND DATE(start_time) BETWEEN ? AND ?
        ORDER BY start_time DESC
        LIMIT 200
        """,
        (device_id, date_from, date_to),
    ).fetchall()

    return render_template(
        "device_detail.html",
        device=device,
        top_apps=top_apps,
        daily=daily,
        recent=recent,
        total_seconds=total_seconds,
        date_from=date_from,
        date_to=date_to,
    )


# ─── API Keys ────────────────────────────────────────────────────────────────


@app.route("/api-keys", methods=["GET", "POST"])
@login_required
def api_keys():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("A name for the API key is required.", "error")
        else:
            new_key = "st_" + secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO api_keys (admin_id, key, name) VALUES (?, ?, ?)",
                (session["admin_id"], new_key, name),
            )
            db.commit()
            # Flash the full key once — it's stored in plain text so it can
            # also be viewed later in the key list.
            flash(new_key, "key_created")

    keys = db.execute(
        """
        SELECT ak.id, ak.name, ak.key, ak.created_at, ak.last_used_at,
               ak.is_active, COUNT(d.id) AS device_count
        FROM api_keys ak
        LEFT JOIN devices d ON d.api_key_id = ak.id
        WHERE ak.admin_id = ?
        GROUP BY ak.id
        ORDER BY ak.created_at DESC
        """,
        (session["admin_id"],),
    ).fetchall()
    return render_template("api_keys.html", keys=keys)


@app.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
@login_required
def revoke_key(key_id):
    db = get_db()
    db.execute(
        "UPDATE api_keys SET is_active = 0 WHERE id = ? AND admin_id = ?",
        (key_id, session["admin_id"]),
    )
    db.commit()
    flash("API key revoked.", "success")
    return redirect(url_for("api_keys"))


@app.route("/api-keys/<int:key_id>/activate", methods=["POST"])
@login_required
def activate_key(key_id):
    db = get_db()
    db.execute(
        "UPDATE api_keys SET is_active = 1 WHERE id = ? AND admin_id = ?",
        (key_id, session["admin_id"]),
    )
    db.commit()
    flash("API key re-activated.", "success")
    return redirect(url_for("api_keys"))


@app.route("/api-keys/<int:key_id>/delete", methods=["POST"])
@login_required
def delete_key(key_id):
    db = get_db()
    db.execute(
        "DELETE FROM api_keys WHERE id = ? AND admin_id = ?",
        (key_id, session["admin_id"]),
    )
    db.commit()
    flash("API key and all associated data deleted.", "success")
    return redirect(url_for("api_keys"))


# ─── Client API ──────────────────────────────────────────────────────────────


def _upsert_device(db: sqlite3.Connection, api_key_id: int, device_name: str) -> int:
    db.execute(
        """
        INSERT INTO devices (api_key_id, device_name, last_seen_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%S','now'))
        ON CONFLICT(api_key_id, device_name)
        DO UPDATE SET last_seen_at = excluded.last_seen_at
        """,
        (api_key_id, device_name),
    )
    row = db.execute(
        "SELECT id FROM devices WHERE api_key_id = ? AND device_name = ?",
        (api_key_id, device_name),
    ).fetchone()
    return row["id"]


@app.route("/api/v1/sessions", methods=["POST"])
@api_key_required
def upload_sessions():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected JSON object"}), 400

    device_name = str(data.get("device_name", "unknown"))[:128]
    sessions_data = data.get("sessions", [])
    if not isinstance(sessions_data, list):
        return jsonify({"error": "'sessions' must be a list"}), 400

    db = get_db()
    device_id = _upsert_device(db, g.api_key_id, device_name)

    accepted = 0
    for s in sessions_data:
        try:
            db.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (device_id, client_session_id, start_time, end_time,
                     app_name, window_title, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    s.get("session_uuid"),
                    s["start"],
                    s["end"],
                    s["app"][:256],
                    s.get("title", "")[:512],
                    int(s["duration_seconds"]),
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0]:
                accepted += 1
        except (KeyError, ValueError, sqlite3.Error):
            continue

    db.commit()
    return jsonify({"ok": True, "accepted": accepted})


@app.route("/api/v1/ping", methods=["POST"])
@api_key_required
def ping():
    data = request.get_json(silent=True) or {}
    device_name = str(data.get("device_name", "unknown"))[:128]
    db = get_db()
    _upsert_device(db, g.api_key_id, device_name)
    db.commit()
    return jsonify({"ok": True})


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)

"""
EmpireInstaller_V52.py

One-shot installer for DTF Command HQ – Empire OS V52.

What this does when you run it:
- Creates a folder: ./DTF_Command_HQ_V52
- Creates subfolders: logs, packets, backups, .streamlit
- Writes:
    - engine.py        (V52: resource guard, ffmpeg check, log rotation, backups)
    - dtf_command_hq.py (upgraded dashboard with Notification Center, System Health, Backups)
    - requirements.txt
    - launch.bat       (Windows launcher)
    - .streamlit/secrets.toml (template)

After running this:
1) Open a terminal in the DTF_Command_HQ_V52 folder.
2) Run:  pip install -r requirements.txt
3) Double-click launch.bat to start the engine + dashboard.
"""

import os
from textwrap import dedent

PROJECT_DIR = "DTF_Command_HQ_V52"


# =========================
#  ENGINE CODE (V52)
# =========================
ENGINE_CODE = '''import base64
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from datetime import date, datetime

import requests
import toml
from moviepy.editor import AudioFileClip, ColorClip, CompositeVideoClip, ImageClip

try:
    import psutil
except ImportError:
    psutil = None

# -----------------------------------------
# CONFIG
# -----------------------------------------
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "empire_activity.log")
PACKET_ROOT = "packets"
BACKUP_DIR = "backups"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(PACKET_ROOT, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Logging: file + console with basic rotation
def rotate_log(max_bytes: int = 5 * 1024 * 1024, backups: int = 3):
    """Simple size-based rotation for LOG_FILE."""
    if not os.path.exists(LOG_FILE):
        return
    try:
        size = os.path.getsize(LOG_FILE)
        if size <= max_bytes:
            return

        # Rotate older files
        for i in range(backups, 0, -1):
            src = f"{LOG_FILE}.{i}"
            dst = f"{LOG_FILE}.{i+1}"
            if os.path.exists(src):
                if i == backups:
                    os.remove(src)
                else:
                    os.replace(src, dst)

        # Move current log to .1
        rotated = f"{LOG_FILE}.1"
        if os.path.exists(rotated):
            os.remove(rotated)
        os.replace(LOG_FILE, rotated)
    except Exception as e:
        # If rotation fails, just print; we don't want to block startup
        print(f"Log rotation failed: {e}")


rotate_log()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


# -----------------------------------------
# DB HELPERS
# -----------------------------------------
def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            niche TEXT,
            link TEXT,
            status TEXT,
            app_url TEXT,
            image_url TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            item_name TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY,
            item_name TEXT,
            stage TEXT,
            message TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('system_status', 'RUNNING')
        """
    )

    # Default resource thresholds if not present
    defaults = {
        "throttle_cpu": "75",
        "pause_cpu": "90",
        "throttle_ram": "80",
        "pause_ram": "95",
    }
    for k, v in defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (k, v),
        )

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return default


def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def check_budget(daily_limit: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    today = str(date.today())
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date = ?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count < daily_limit


def log_run(item_name: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO run_log (run_date, item_name) VALUES (?, ?)",
        (str(date.today()), item_name),
    )
    conn.commit()
    conn.close()


def update_status(name: str, status: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE posts SET status = ? WHERE name = ?", (status, name))
    conn.commit()
    conn.close()


def insert_scouted_product(name: str, niche: str, app_url: str):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, image_url, created_at)
        VALUES (?, ?, '', 'Pending', ?, '', ?)
        """,
        (name, niche, app_url, now),
    )
    conn.commit()
    conn.close()


def get_ready_item():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, niche, link, status, app_url FROM posts "
        "WHERE status = 'Ready' LIMIT 1"
    )
    row = c.fetchone()
    conn.close()
    return row


def get_pending_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Pending'")
    count = c.fetchone()[0]
    conn.close()
    return count


# -----------------------------------------
# ERROR LOGGING
# -----------------------------------------
def log_error(item_name: str, stage: str, message: str):
    message_short = (message or "").strip()
    if len(message_short) > 600:
        message_short = message_short[:600] + "...[truncated]"

    logging.error("Error [%s] %s: %s", stage, item_name, message_short)

    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO error_log (item_name, stage, message, created_at)
            VALUES (?, ?, ?, ?
""" 
EmpireInstaller_V52.py

One-shot installer for DTF Command HQ – Empire OS V52.
Updated: Engine V53 (Memory Fixes) + Dashboard (AI Troubleshooter) included.

What this does when you run it:
- Creates a folder: ./DTF_Command_HQ_V52
- Creates subfolders: logs, packets, backups, .streamlit
- Writes:
    - engine.py         (V53: Full Auto-Pilot w/ Crash Prevention)
    - dtf_command_hq.py (Dashboard: w/ AI Error Fixing)
    - requirements.txt  (Correct versions)
    - launch.bat        (Windows launcher)
    - .streamlit/secrets.toml (Template)

After running this:
1) Open a terminal in the DTF_Command_HQ_V52 folder.
2) Run:  pip install -r requirements.txt
3) Double-click launch.bat to start.
"""

import os

PROJECT_DIR = "DTF_Command_HQ_V52"

# =========================
#  ENGINE CODE (V53)
# =========================
ENGINE_CODE = r'''import base64
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
# NOTE: This requires moviepy < 2.0
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

# -----------------------------------------
# LOGGING (Rotation Logic)
# -----------------------------------------
def rotate_log(max_bytes=5*1024*1024, backups=3):
    """Rotates logs to prevent huge files. Runs only on startup."""
    if not os.path.exists(LOG_FILE):
        return
    try:
        size = os.path.getsize(LOG_FILE)
        if size <= max_bytes:
            return
        for i in range(backups, 0, -1):
            src = f"{LOG_FILE}.{i}"
            dst = f"{LOG_FILE}.{i+1}"
            if os.path.exists(src):
                if i == backups:
                    os.remove(src)
                else:
                    os.replace(src, dst)
        rotated = f"{LOG_FILE}.1"
        if os.path.exists(rotated):
            os.remove(rotated)
        os.replace(LOG_FILE, rotated)
    except Exception as e:
        print("Log rotation error:", e)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# -----------------------------------------
# DB HELPERS (With Timeout Fix)
# -----------------------------------------
def get_conn():
    # FIX: Added timeout=30 to prevent 'database is locked' errors
    return sqlite3.connect(DB_FILE, timeout=30)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        niche TEXT,
        link TEXT,
        status TEXT,
        app_url TEXT,
        image_url TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS run_log (
        id INTEGER PRIMARY KEY,
        run_date TEXT,
        item_name TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS error_log (
        id INTEGER PRIMARY KEY,
        item_name TEXT,
        stage TEXT,
        message TEXT,
        created_at TEXT
    )""")

    # Default settings
    c.execute("""INSERT OR IGNORE INTO settings (key,value)
                 VALUES ('system_status','RUNNING')""")
    
    defaults = {
        "throttle_cpu": "75",
        "pause_cpu":    "90",
        "throttle_ram": "80",
        "pause_ram":    "95"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))

    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, val):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO settings(key,value) VALUES (?,?)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, val))
    conn.commit()
    conn.close()

def check_budget(limit: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    today = str(date.today())
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date=?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count < limit

def log_run(name: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO run_log (run_date,item_name) VALUES (?,?)",
              (str(date.today()), name))
    conn.commit()
    conn.close()

def update_status(name, status):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE posts SET status=? WHERE name=?", (status, name))
    conn.commit()
    conn.close()

def insert_scouted_product(name, niche, app_url):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO posts
                 (name,niche,link,status,app_url,image_url,created_at)
                 VALUES (?,?,?,?,?,?,?)""",
              (name, niche, "", "Pending", app_url, "", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_ready_item():
    conn = get_conn()
    c = conn.cursor()
    # Only pick up items that have been manually approved (Status='Ready')
    c.execute("SELECT id,name,niche,link,status,app_url FROM posts WHERE status='Ready' LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def get_pending_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts WHERE status='Pending'")
    ct = c.fetchone()[0]
    conn.close()
    return ct

# -----------------------------------------
# ERROR LOGGING
# -----------------------------------------
def log_error(item, stage, msg):
    msg = (msg or "")[:600]
    logging.error(f"ERROR [{stage}] {item}: {msg}")
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""INSERT INTO error_log(item_name,stage,message,created_at)
                     VALUES (?,?,?,?)""",
                  (item, stage, msg, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

# -----------------------------------------
# UTILS & API HELPERS
# -----------------------------------------
def clean_and_parse_json(raw_text):
    """FIX: Robust JSON parser that handles Markdown code blocks."""
    if not raw_text: 
        return None
    # Remove ```json and ``` if present
    cleaned = re.sub(r"

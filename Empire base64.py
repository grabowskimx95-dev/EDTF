import base64
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
    cleaned = re.sub(r"```json|```", "", raw_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def load_secrets():
    if not os.path.exists(SECRETS_PATH):
        log_error("SYSTEM", "secrets", "Missing secrets.toml")
        return {}
    try:
        return toml.load(SECRETS_PATH)
    except Exception as e:
        log_error("SYSTEM", "secrets", str(e))
        return {}

def safe_post(url, payload, headers, timeout=30, item_name="SYSTEM", stage="network"):
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if r.status_code != 200:
            log_error(item_name, stage, f"{r.status_code}: {r.text[:200]}")
            return None
        return r
    except Exception as e:
        log_error(item_name, stage, str(e))
        return None

def safe_get(url, headers=None, timeout=30, item_name="SYSTEM", stage="network"):
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            log_error(item_name, stage, f"{r.status_code}: {r.text[:200]}")
            return None
        return r
    except Exception as e:
        log_error(item_name, stage, str(e))
        return None

# -----------------------------------------
# RESOURCE GUARD
# -----------------------------------------
def get_system_load():
    if not psutil:
        return (None, None)
    try:
        return psutil.cpu_percent(0.3), psutil.virtual_memory().percent
    except:
        return (None, None)

def resource_guard():
    cpu, ram = get_system_load()
    if cpu is None:
        return "ok"

    tc = float(get_setting("throttle_cpu", 75))
    pc = float(get_setting("pause_cpu", 90))
    tr = float(get_setting("throttle_ram", 80))
    pr = float(get_setting("pause_ram", 95))

    if cpu >= pc or ram >= pr:
        log_error("SYSTEM", "system_load", f"Paused CPU={cpu} RAM={ram}")
        return "pause"
    if cpu >= tc or ram >= tr:
        return "throttle"
    return "ok"

# -----------------------------------------
# SCOUTING / RESEARCH / CONTENT
# -----------------------------------------
def run_scout_real(niche, pplx_key):
    logging.info(f"🔭 Scouting: {niche}")
    if not pplx_key:
        log_error("SYSTEM", "scout", "Missing pplx_key")
        return []
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "Return ONLY a comma-separated list of 3 trending contractor tools."},
            {"role": "user", "content": "DTF trending contractor tools."}
        ]
    }
    r = safe_post(url, payload, headers, item_name="SYSTEM", stage="scout")
    if not r:
        return []
    try:
        txt = r.json()["choices"][0]["message"]["content"]
        return [x.strip() for x in txt.split(",")][:3]
    except:
        return []

def find_app_link_real(product, pplx_key):
    if not pplx_key:
        log_error(product, "affiliate_lookup", "Missing pplx_key")
        return "https://google.com"
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "Output ONLY a signup or homepage URL."},
            {"role": "user", "content": f"Affiliate or homepage for: {product}"}
        ]
    }
    r = safe_post(url, payload, headers, item_name=product, stage="affiliate_lookup")
    if not r:
        return "https://google.com"
    try:
        link = r.json()["choices"][0]["message"]["content"].strip()
        return link if link.startswith("http") else "https://google.com"
    except:
        return "https://google.com"

def get_product_facts(product, pplx_key):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "Provide top specs, pros, cons, and contractor use cases."},
            {"role": "user", "content": f"Specs for {product}"}
        ]
    }
    r = safe_post(url, payload, headers, item_name=product, stage="fact_check")
    if not r:
        return "General tool summary."
    try:
        return r.json()["choices"][0]["message"]["content"]
    except:
        return "General tool summary."

def create_content(product, facts, openai_key):
    if not openai_key:
        log_error(product, "content", "Missing openai_key")
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    sys_prompt = f"""
    You are the voice of Design To Finish Contracting (DTF Command).
    Real St. Louis contractor tone. Use facts:
    {facts}
    Output JSON with blog_html, social_caption, video_script.
    """
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Write review for {product}"}
        ],
        "response_format": {"type": "json_object"}
    }
    r = safe_post(url, payload, headers, timeout=60, item_name=product, stage="content")
    if not r:
        return None
    try:
        return r.json()["choices"][0]["message"]["content"]
    except:
        return None

# -----------------------------------------
# MEDIA PRODUCTION (Fixed for Memory Leaks)
# -----------------------------------------
def produce_media(product, script, openai_key, base_dir):

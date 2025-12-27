"""
EmpireInstaller_V52.py

One-shot installer for DTF Command HQ – Empire OS V52.

What this does when you run it:
- Creates a folder: ./DTF_Command_HQ_V52
- Creates subfolders: logs, packets, backups, .streamlit
- Writes:
    - engine.py         (V52: resource guard, ffmpeg check, log rotation, backups)
    - dtf_command_hq.py (upgraded dashboard with Notification Center, System Health, Backups)
    - requirements.txt
    - launch.bat        (Windows launcher)
    - .streamlit/secrets.toml (template)

After running this:
1) Open a terminal in the DTF_Command_HQ_V52 folder.
2) Run:  pip install -r requirements.txt
3) Double-click launch.bat to start the engine + dashboard.
"""

import os

PROJECT_DIR = "DTF_Command_HQ_V52"


# =========================
#  ENGINE CODE (V52)
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
            VALUES (?, ?, ?, ?)
            """,
            (item_name, stage, message_short, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error("Failed to write to error_log: %s", e)


# -----------------------------------------
# SECRETS
# -----------------------------------------
def load_secrets():
    if not os.path.exists(SECRETS_PATH):
        logging.warning("secrets.toml not found at %s", SECRETS_PATH)
        return {}

    try:
        return toml.load(SECRETS_PATH)
    except Exception as e:
        logging.error("Failed to load secrets.toml: %s", e)
        log_error("SYSTEM", "secrets", f"Failed to load secrets: {e}")
        return {}


# -----------------------------------------
# NETWORK HELPERS
# -----------------------------------------
def safe_post(url, json_body, headers, timeout=30, item_name="SYSTEM", stage="network"):
    try:
        resp = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            msg = f"Status {resp.status_code}: {resp.text[:300]}"
            log_error(item_name, stage, msg)
            return None
        return resp
    except Exception as e:
        log_error(item_name, stage, f"POST {url} failed: {e}")
        return None


def safe_get(url, headers=None, timeout=30, item_name="SYSTEM", stage="network"):
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            msg = f"Status {resp.status_code}: {resp.text[:300]}"
            log_error(item_name, stage, msg)
            return None
        return resp
    except Exception as e:
        log_error(item_name, stage, f"GET {url} failed: {e}")
        return None


# -----------------------------------------
# SYSTEM LOAD / RESOURCE GUARD
# -----------------------------------------
def get_system_load():
    if psutil is None:
        return None, None
    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory().percent
        return cpu, mem
    except Exception as e:
        log_error("SYSTEM", "system_load", f"psutil error: {e}")
        return None, None


def resource_guard():
    cpu, mem = get_system_load()
    if cpu is None or mem is None:
        return "ok"

    try:
        throttle_cpu = float(get_setting("throttle_cpu", "75"))
        pause_cpu = float(get_setting("pause_cpu", "90"))
        throttle_ram = float(get_setting("throttle_ram", "80"))
        pause_ram = float(get_setting("pause_ram", "95"))
    except Exception as e:
        log_error("SYSTEM", "system_load", f"Threshold parse error: {e}")
        return "ok"

    if cpu >= pause_cpu or mem >= pause_ram:
        msg = f"Resource guard pause: CPU={cpu:.0f}%, RAM={mem:.0f}%"
        log_error("SYSTEM", "system_load", msg)
        return "pause"

    if cpu >= throttle_cpu or mem >= throttle_ram:
        logging.warning("Resource guard throttle: CPU=%.0f%%, RAM=%.0f%%", cpu, mem)
        return "throttle"

    return "ok"


# -----------------------------------------
# SCOUTING / FACT CHECK / CONTENT
# -----------------------------------------
def run_scout_real(niche: str, pplx_key: str):
    logging.info("🔭 Scouting niche: %s", niche)
    if not pplx_key:
        msg = "Missing pplx_key in secrets.toml"
        logging.error(msg)
        log_error("SYSTEM", "scout", msg)
        return []

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {pplx_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {
                "role": "system",
                "content": (
                    "List 3 specific, trending, high-ticket tools/products used by "
                    "professional contractors for siding, roofing, exterior work, "
                    "interior remodeling, or general construction. "
                    "Return ONLY a comma-separated list of names."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Best new contractor tools and systems for Design To Finish Contracting, "
                    f"DTF Command, St. Louis metro, 2024-2025."
                ),
            },
        ],
    }
    resp = safe_post(url, payload, headers, item_name="SYSTEM", stage="scout")
    if not resp:
        return []

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        items = [x.strip() for x in content.split(",") if x.strip()]
        return items[:3]
    except Exception as e:
        log_error("SYSTEM", "scout", f"Scout parsing error: {e}")
        return []


def find_app_link_real(product: str, pplx_key: str):
    if not pplx_key:
        msg = "Missing pplx_key for app link search"
        logging.error(msg)
        log_error(product, "affiliate_lookup", msg)
        return "https://google.com"

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {pplx_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {
                "role": "system",
                "content": "Output ONLY the affiliate program signup URL. No extra text.",
            },
            {
                "role": "user",
                "content": (
                    f"Affiliate program signup or referral link page for: {product}. "
                    f"If there is no direct affiliate page, give the official product homepage."
                ),
            },
        ],
    }
    resp = safe_post(url, payload, headers, item_name=product, stage="affiliate_lookup")
    if not resp:
        return "https://google.com"

    try:
        link = resp.json()["choices"][0]["message"]["content"].strip()
        if link.startswith("http"):
            return link
        return "https://google.com"
    except Exception as e:
        log_error(product, "affiliate_lookup", f"App link parsing error: {e}")
        return "https://google.com"


def get_product_facts(product: str, pplx_key: str):
    logging.info("🔎 Fact checking: %s", product)
    if not pplx_key:
        msg = "Missing pplx_key for fact check"
        logging.error(msg)
        log_error(product, "fact_check", msg)
        return "General contractor tool overview."

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {pplx_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical researcher for a remodeling contractor. "
                    "Provide a bulleted list of the top 5 technical specs, "
                    "real-world pros/cons, and ideal use cases for this tool, "
                    "with a focus on siding, roofing, framing, or remodeling work."
                ),
            },
            {"role": "user", "content": f"Technical specs for: {product}"},
        ],
    }
    resp = safe_post(url, payload, headers, item_name=product, stage="fact_check")
    if not resp:
        return "General contractor tool overview."

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log_error(product, "fact_check", f"Fact check parsing error: {e}")
        return "General contractor tool overview."


def create_content(product: str, facts: str, openai_key: str):
    logging.info("📝 Writing DTF content for: %s", product)
    if not openai_key:
        msg = "Missing openai_key"
        logging.error(msg)
        log_error(product, "content", msg)
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }

    sys_prompt = f"""
    You are the voice of **Design To Finish Contracting (DTF Command)**:
    - St. Louis metro remodeling contractor
    - Blue collar, straight-talk, no fluff
    - Veteran foreman tone: confident, experienced, but respectful
    - Audience: homeowners and contractors

    Use the facts below to create content that sounds like a real contractor
    who actually uses this tool on remodels, siding jobs, roofing, or bar builds.

    FACTS:
    {facts}

    Output JSON ONLY with these keys:
    1. "blog_html": 800-word review in HTML, with H2s, bullet lists, pros/cons,
       and real jobsite language. Mention Design To Finish Contracting or DTF Command
       naturally 2-3 times.
    2. "social_caption": An Instagram/Facebook caption with a strong hook, emoji,
       and these style of hashtags where relevant:
       #DesignToFinish #DTFCommand #BlueCollarEmpire #StLouisContractor
    3. "video_script": 30-second narrator script as if the foreman is talking on camera,
       addressing homeowners or other contractors directly. No scene directions, only spoken words.
    """

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Write DTF Command review for {product}"},
        ],
        "response_format": {"type": "json_object"},
    }

    resp = safe_post(
        url, payload, headers, timeout=60, item_name=product, stage="content"
    )
    if not resp:
        return None

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log_error(product, "content", f"Content generation parsing error: {e}")
        return None


def produce_media(product: str, script: str, openai_key: str, base_dir: str):
    logging.info("🎨 Producing media for: %s", product)
    if not openai_key:
        msg = "Missing openai_key"
        logging.error(msg)
        log_error(product, "media", msg)
        return None, None, None

    h_oa = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }

    img_url = None
    try:
        img_payload = {
            "model": "dall-e-3",
            "prompt": (
                f"Professional photo of {product} being used by a contractor on a real "
                f"construction site (siding, roofing, or remodeling), with a subtle "
                f"DTF Command / Design To Finish branding vibe. Cinematic lighting."
            ),
            "size": "102
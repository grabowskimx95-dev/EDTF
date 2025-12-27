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
    url_img = "https://api.openai.com/v1/images/generations"
    url_aud = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}

    img_url = None
    audio_bytes = None

    # IMAGE GENERATION
    try:
        payload_img = {
            "model": "dall-e-3",
            "prompt": f"Contractor using {product} on real jobsite. DTF branding vibe.",
            "size": "1024x1024"
        }
        r = safe_post(url_img, payload_img, headers, item_name=product, stage="media_image")
        if r:
            img_url = r.json()["data"][0]["url"]
    except Exception as e:
        log_error(product, "media_image", str(e))

    # AUDIO GENERATION
    try:
        payload_aud = {"model": "tts-1", "voice": "onyx", "input": script}
        r = safe_post(url_aud, payload_aud, headers, item_name=product, stage="media_audio", timeout=120)
        if r:
            audio_bytes = r.content
    except Exception as e:
        log_error(product, "media_audio", str(e))

    clean = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    img_path = os.path.join(base_dir, f"{clean}.jpg")
    aud_path = os.path.join(base_dir, f"{clean}.mp3")
    vid_path = os.path.join(base_dir, f"{clean}.mp4")

    # Save Image File
    if img_url:
        r = safe_get(img_url, item_name=product, stage="media_image")
        if r:
            try:
                open(img_path, "wb").write(r.content)
            except:
                img_path = None
        else:
            img_path = None
    else:
        img_path = None

    # Save Audio File
    if audio_bytes:
        try:
            open(aud_path, "wb").write(audio_bytes)
        except:
            aud_path = None
    else:
        aud_path = None

    # VIDEO GENERATION (With cleanup)
    if not FFMPEG_AVAILABLE:
        log_error(product, "media_video", "ffmpeg missing - skipping video")
        vid_path = None
    elif img_path and aud_path:
        try:
            ac = AudioFileClip(aud_path)
            dur = ac.duration + 0.5
            ic = ImageClip(img_path).set_duration(dur).resize(height=1920)
            if ic.w > 1080:
                ic = ic.crop(x1=(ic.w/2-540), y1=0, width=1080, height=1920)
            
            bg = ColorClip(size=(1080, 1920), color=(20,20,20), duration=dur)
            final = CompositeVideoClip([bg, ic]).set_audio(ac)
            
            final.write_videofile(
                vid_path, fps=24, verbose=False, logger=None, threads=4
            )
            
            # FIX: Close clips to release memory/file handles
            final.close()
            ac.close()
            ic.close()
            bg.close()
            
        except Exception as e:
            log_error(product, "media_video", str(e))
            vid_path = None
    else:
        vid_path = None

    return img_path, aud_path, vid_path

# -----------------------------------------
# SMART LINK + WORDPRESS
# -----------------------------------------
def create_smart_link(wp_url, product, raw_link):
    clean = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    enc = base64.b64encode(raw_link.encode()).decode()
    return f"{wp_url.rstrip('/')}/?df_track={clean}&dest={enc}"

def publish_to_wordpress(name, html, smart_link, img_path, secrets):
    wp_url  = secrets.get("wp_url", "").rstrip("/")
    wp_user = secrets.get("wp_user", "")
    wp_pass = secrets.get("wp_pass", "")

    if not (wp_url and wp_user and wp_pass):
        log_error(name, "wordpress", "Missing WP credentials")
        return

    html += f"""
    <div style='text-align:center;margin-top:20px;'>
        <a href='{smart_link}' style='background:#c1121f;color:white;
        padding:12px 20px;font-weight:bold;border-radius:6px;text-decoration:none;'>
        CHECK CURRENT PRICING
        </a>
        <p style='font-size:12px;margin-top:8px;'>Recommended by DTF Command</p>
    </div>
    """

    auth = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()

    media_id = None
    if img_path and os.path.exists(img_path):
        try:
            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "image/jpeg",
                "Content-Disposition": "attachment; filename=feature.jpg"
            }
            img = open(img_path, "rb").read()
            r = requests.post(f"{wp_url}/wp-json/wp/v2/media",
                              data=img, headers=headers, timeout=60)
            if r.status_code in (200, 201):
                media_id = r.json().get("id")
        except Exception as e:
            log_error(name, "wordpress_media", str(e))

    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    post = {
        "title": f"{name} – DTF Command Review",
        "content": html,
        "status": "draft"
    }
    if media_id:
        post["featured_media"] = media_id

    try:
        r = requests.post(f"{wp_url}/wp-json/wp/v2/posts", json=post, headers=headers, timeout=60)
        if r.status_code not in (200, 201):
            log_error(name, "wordpress_post", str(r.text)[:200])
    except Exception as e:
        log_error(name, "wordpress_post", str(e))

# -----------------------------------------
# PRODUCTION LINE (Logic Fixes)
# -----------------------------------------
def production_line(row, secrets):
    _id, name, niche, link, status, app = row

    # FIX: Fallback to app_url if link is empty so we don't crash
    target_link = link if link else app

    if not target_link:
        log_error(name, "precheck", "Missing affiliate link and app url")
        update_status(name, "Failed")
        return

    facts = get_product_facts(name, secrets.get("pplx_key", ""))
    raw = create_content(name, facts, secrets.get("openai_key", ""))
    
    # FIX: Use helper to parse JSON safely
    data = clean_and_parse_json(raw)

    if not data:
        log_error(name, "content", "Failed to generate/parse valid JSON")
        update_status(name, "Failed")
        return

    blog = data.get("blog_html", "")
    script = data.get("video_script", "")

    # Build folder
    today = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(PACKET_ROOT, f"Daily_Packet_{today}")
    os.makedirs(folder, exist_ok=True)

    # Media
    img, aud, vid = produce_media(name, script, secrets.get("openai_key", ""), folder)

    # Link
    smart = create_smart_link(secrets.get("wp_url", ""), name, target_link)

    # Publish
    publish_to_wordpress(name, blog, smart, img, secrets)

    update_status(name, "Published")
    log_run(name)

# -----------------------------------------
# BACKUP
# -----------------------------------------
def run_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(BACKUP_DIR, f"backup_{ts}")
    os.makedirs(d, exist_ok=True)
    try:
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, os.path.join(d, "empire.db"))
        if os.path.exists(SECRETS_PATH):
            os.makedirs(os.path.join(d, ".streamlit"), exist_ok=True)
            shutil.copy2(SECRETS_PATH, os.path.join(d, ".streamlit", "secrets.toml"))
    except Exception as e:
        log_error("SYSTEM", "backup", str(e))

# -----------------------------------------
# AUTOPILOT LOOP
# -----------------------------------------
def autopilot_loop():
    logging.info("=== DTF COMMAND ENGINE V53 ONLINE ===")
    init_db()
    backoff = 30

    while True:
        try:
            secrets = load_secrets()
            openai_key = secrets.get("openai_key", "")
            pplx_key = secrets.get("pplx_key", "")
            limit = int(secrets.get("daily_run_limit", 5))

            if not openai_key or not pplx_key:
                log_error("SYSTEM", "main_loop", "Missing API keys")
                time.sleep(30)
                continue

            # Engine STOP/START from dashboard
            if get_setting("system_status", "RUNNING") != "RUNNING":
                time.sleep(60)
                continue

            # Resource Guard
            state = resource_guard()
            if state == "pause":
                time.sleep(60)
                continue
            elif state == "throttle":
                delay = 60
            else:
                delay = 10

            # Budget
            if not check_budget(limit):
                log_error("SYSTEM", "budget", "Daily limit hit")
                time.sleep(3600)
                continue

            # Work item
            item = get_ready_item()
            if item:
                production_line(item, secrets)
                time.sleep(delay)
                backoff = 30
                continue

            # Auto-scout
            pending = get_pending_count()
            if pending == 0:
                items = run_scout_real("DTF Tools", pplx_key)
                for it in items:
                    app = find_app_link_real(it, pplx_key)
                    insert_scouted_product(it, "DTF Tools", app)
                time.sleep(60)
                continue

            # Pending items waiting for links
            time.sleep(300)
            backoff = 30

        except Exception as e:
            log_error("SYSTEM", "main_loop", str(e))
            time.sleep(backoff)
            backoff = min(backoff * 2, 900)

if __name__ == "__main__":
    # FIX: Only rotate logs when running as a script, not when imported
    rotate_log()
    autopilot_loop()
'''

# =========================
#  DASHBOARD CODE
# =========================
DASH_CODE = r'''import streamlit as st
import pandas as pd
import sqlite3
import os
import toml
import time
from datetime import date

# Import specific functions to avoid running the whole engine
try:
    from engine import run_backup, DB_FILE, update_status
except ImportError:
    st.error("Could not find engine.py. Please make sure it is in the same folder.")
    st.stop()

# -----------------------------------------
# SETUP & CONFIG
# -----------------------------------------
st.set_page_config(page_title="DTF Command", layout="wide")

# Load Secrets safely
try:
    SECRETS = dict(st.secrets)
except:
    if os.path.exists(".streamlit/secrets.toml"):
        SECRETS = toml.load(".streamlit/secrets.toml")
    else:
        SECRETS = {}

# -----------------------------------------
# DATABASE HELPERS (Dashboard Side)
# -----------------------------------------
def get_conn():
    # Timeout=30 matches the Engine to prevent locking
    return sqlite3.connect(DB_FILE, timeout=30)

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

def get_counts():
    conn = get_conn()
    c = conn.cursor()
    
    # Check if table exists first to avoid crash on fresh install
    try:
        c.execute("SELECT COUNT(*) FROM posts WHERE status='Pending'")
        pending = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'")
        ready = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM posts WHERE status='Published'")
        published = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM posts WHERE status='Failed'")
        failed = c.fetchone()[0]
    except sqlite3.OperationalError:
        return 0, 0, 0, 0
    finally:
        conn.close()
        
    return pending, ready, published, failed

def get_pending_posts():
    conn = get_conn()
    try:
        df = pd.read_sql_query("SELECT id,name,app_url,link FROM posts WHERE status='Pending'", conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_all_posts():
    conn = get_conn()
    try:
        df = pd.read_sql_query("SELECT id, name, niche, status, created_at FROM posts ORDER BY id DESC", conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def update_links_from_df(df):
    conn = get_conn()
    c = conn.cursor()
    for _, r in df.iterrows():
        link = (r.get("link") or "").strip()
        if not link:
            continue
        c.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?", (link, int(r["id"])))
    conn.commit()
    conn.close()

def get_error_stats():
    conn = get_conn()
    c = conn.cursor()
    today = str(date.today())
    try:
        c.execute("SELECT COUNT(*) FROM error_log WHERE created_at LIKE ?", (today+"%",))
        today_errors = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM error_log")
        total_errors = c.fetchone()[0]
        c.execute("SELECT created_at FROM error_log ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        last = row[0] if row else "None"
    except:
        return 0, 0, "None"
    finally:
        conn.close()
    return today_errors, total_errors, last

def get_recent_errors(limit=50):
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT item_name, stage, message, created_at FROM error_log ORDER BY id DESC LIMIT ?", 
            conn, params=(limit,)
        )
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

# -----------------------------------------
# AI TROUBLESHOOTER (Feature #2)
# -----------------------------------------
def explain_error_with_ai(error_message, api_key):
    if not api_key:
        return "⚠️ Missing OpenAI API Key."
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Python expert. Explain this error to a non-technical user in 1 simple sentence. Then, give 1 direct instruction on how to fix it."},
                {"role": "user", "content": f"Explain this error: {error_message}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

# -----------------------------------------
# UI LAYOUT
# -----------------------------------------
st.title("⚔️ DTF Content Command")

# Sidebar
with st.sidebar:
    st.header("Status")
    pending, ready, published, failed = get_counts()
    
    col1, col2 = st.columns(2)
    col1.metric("Pending", pending)
    col1.metric("Ready", ready)
    col2.metric("Published", published)
    col2.metric("Failed", failed, delta_color="inverse")
    
    st.markdown("---")
    
    # Engine Control
    curr_status = get_setting("system_status", "RUNNING")
    new_status = st.radio("Engine Status", ["RUNNING", "STOPPED"], 
                          index=0 if curr_status=="RUNNING" else 1)
    
    if new_status != curr_status:
        set_setting("system_status", new_status)
        st.success(f"System set to {new_status}")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    if st.button("Run Backup Now"):
        with st.spinner("Backing up..."):
            run_backup()
        st.success("Backup Complete!")

# Tabs
tab1, tab2, tab3 = st.tabs(["📝 Scouted Items", "📊 Activity Log", "⚠️ Errors"])

# Tab 1: Scouted Items
with tab1:
    st.subheader("Approve Scouted Items")
    st.info("The engine scouts items but waits for YOU to add affiliate links.")
    
    df_pending = get_pending_posts()
    
    if not df_pending.empty:
        edited_df = st.data_editor(
            df_pending,
            column_config={
                "link": st.column_config.LinkColumn("Affiliate Link (Edit Here)", required=True),
                "app_url": st.column_config.LinkColumn("App URL"),
            },
            hide_index=True,
            num_rows="fixed",
            key="editor"
        )
        
        if st.button("Save & Activate Ready Items", type="primary"):
            update_links_from_df(edited_df)
            st.success("Links updated! Items marked 'Ready'.")
            time.sleep(1)
            st.rerun()
    else:
        st.success("No pending items. The scout is hunting...")

# Tab 2: Activity
with tab2:
    st.subheader("Recent Activity")
    df_posts = get_all_posts()
    st.dataframe(df_posts, use_container_width=True)

# Tab 3: Errors & AI Fixer
with tab3:
    st.subheader("Error Logs")
    today_err, total_err, last_err = get_error_stats()
    
    col1, col2 = st.columns(2)
    col1.metric("Errors Today", today_err)
    col1.metric("Total Errors", total_err)
    
    df_err = get_recent_errors(50)
    
    if not df_err.empty:
        st.dataframe(df_err, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🤖 AI Troubleshooter")
        
        unique_errors = df_err["message"].unique()
        selected_err = st.selectbox("Select an error to investigate:", unique_errors)
        
        if st.button("Ask AI: How do I fix this?"):
            with st.spinner("Consulting..."):
                api_key = SECRETS.get("openai_key")
                explanation = explain_error_with_ai(selected_err, api_key)
                st.info(f"**AI Diagnosis:**\n\n{explanation}")
    else:
        st.success("No recent errors. System is healthy.")
'''

# =========================
#  REQUIREMENTS
# =========================
REQUIREMENTS = """streamlit
pandas
requests
moviepy<2.0
imageio
imageio-ffmpeg
toml
psutil
openai
"""

# =========================
#  LAUNCH.BAT
# =========================
LAUNCH_BAT = r"""@echo off
TITLE DTF Command HQ - Empire OS V52
ECHO =================================================
ECHO   DTF Command HQ - Design To Finish Contracting
ECHO   Empire OS V52 - Blue Collar Content Engine
ECHO =================================================
ECHO.

ECHO Installing Python dependencies (one-time / as needed)...
pip install -r requirements.txt

ECHO Starting DTF Engine in background...
start /B pythonw engine.py

ECHO Starting DTF Command Dashboard (Streamlit)...
streamlit run dtf_command_hq.py

ECHO.
ECHO If a browser does not open automatically, go to:
ECHO   http://localhost:8501
ECHO.
PAUSE
"""

# =========================
#  SECRETS TEMPLATE
# =========================
SECRETS_TEMPLATE = """# .streamlit/secrets.toml
# Fill these in before running launch.bat

openai_key   = "YOUR_OPENAI_API_KEY"
pplx_key     = "YOUR_PERPLEXITY_API_KEY"

wp_url       = "https://your-wordpress-site.com"
wp_user      = "your_wp_username"
wp_pass      = "your_wp_application_password"

daily_run_limit = 5
"""

def write_file(path, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    base = os.path.abspath(PROJECT_DIR)
    os.makedirs(base, exist_ok=True)

    print(f"Installing DTF Command HQ – Empire OS V52 into: {base}")

    logs_dir = os.path.join(base, "logs")
    packets_dir = os.path.join(base, "packets")
    backups_dir = os.path.join(base, "backups")
    streamlit_dir = os.path.join(base, ".streamlit")

    for d in [logs_dir, packets_dir, backups_dir, streamlit_dir]:
        os.makedirs(d, exist_ok=True)

    # Writing files
    print(f" - Writing engine.py...")
    write_file(os.path.join(base, "engine.py"), ENGINE_CODE)
    
    print(f" - Writing dtf_command_hq.py...")
    write_file(os.path.join(base, "dtf_command_hq.py"), DASH_CODE)
    
    print(f" - Writing requirements.txt...")
    write_file(os.path.join(base, "requirements.txt"), REQUIREMENTS)
    
    print(f" - Writing launch.bat...")
    write_file(os.path.join(base, "launch.bat"), LAUNCH_BAT)

    secrets_path = os.path.join(streamlit_dir, "secrets.toml")
    if not os.path.exists(secrets_path):
        print(f" - Writing secrets template...")
        write_file(secrets_path, SECRETS_TEMPLATE)
    else:
        print(f" - Secrets file already exists (skipping overwrite).")

    print()
    print("✅ Base DTF Command HQ V52 structure created.")
    print()
    print("Next steps:")
    print(f"1) Open a terminal/Command Prompt in: {base}")
    print("2) Run:  pip install -r requirements.txt")
    print("3) Edit .streamlit\\secrets.toml with your keys and WP info")
    print("4) Double-click launch.bat")
    print()
    print("The engine will start in the background and the dashboard will be at http://localhost:8501")

if __name__ == "__main__":
    main()

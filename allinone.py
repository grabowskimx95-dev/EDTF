import os
import textwrap
import sys

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

def rotate_log(max_bytes=5*1024*1024, backups=3):
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

rotate_log()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def get_conn():
    return sqlite3.connect(DB_FILE)

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

def produce_media(product, script, openai_key, base_dir):
    url_img = "https://api.openai.com/v1/images/generations"
    url_aud = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}

    img_url = None
    audio_bytes = None

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

    if audio_bytes:
        try:
            open(aud_path, "wb").write(audio_bytes)
        except:
            aud_path = None
    else:
        aud_path = None

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
            CompositeVideoClip([bg, ic]).set_audio(ac).write_videofile(
                vid_path, fps=24, verbose=False, logger=None
            )
        except Exception as e:
            log_error(product, "media_video", str(e))
            vid_path = None
    else:
        vid_path = None

    return img_path, aud_path, vid_path

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

def production_line(row, secrets):
    _id, name, niche, link, status, app = row

    if not link:
        log_error(name, "precheck", "Missing affiliate link")
        update_status(name, "Failed")
        return

    facts = get_product_facts(name, secrets.get("pplx_key", ""))
    raw = create_content(name, facts, secrets.get("openai_key", ""))
    if not raw:
        update_status(name, "Failed")
        return

    try:
        data = json.loads(raw)
    except Exception as e:
        log_error(name, "content", str(e))
        update_status(name, "Failed")
        return

    blog = data.get("blog_html", "")
    script = data.get("video_script", "")

    today = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(PACKET_ROOT, f"Daily_Packet_{today}")
    os.makedirs(folder, exist_ok=True)

    img, aud, vid = produce_media(name, script, secrets.get("openai_key", ""), folder)
    smart = create_smart_link(secrets.get("wp_url", ""), name, link)
    publish_to_wordpress(name, blog, smart, img, secrets)

    update_status(name, "Published")
    log_run(name)

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

def autopilot_loop():
    logging.info("=== DTF COMMAND ENGINE V52 ONLINE ===")
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

            if get_setting("system_status", "RUNNING") != "RUNNING":
                time.sleep(60)
                continue

            state = resource_guard()
            if state == "pause":
                time.sleep(60)
                continue
            elif state == "throttle":
                delay = 60
            else:
                delay = 10

            if not check_budget(limit):
                log_error("SYSTEM", "budget", "Daily limit hit")
                time.sleep(3600)
                continue

            item = get_ready_item()
            if item:
                production_line(item, secrets)
                time.sleep(delay)
                backoff = 30
                continue

            pending = get_pending_count()
            if pending == 0:
                items = run_scout_real("DTF Tools", pplx_key)
                for it in items:
                    app = find_app_link_real(it, pplx_key)
                    insert_scouted_product(it, "DTF Tools", app)
                time.sleep(60)
                continue

            time.sleep(300)
            backoff = 30

        except Exception as e:
            log_error("SYSTEM", "main_loop", str(e))
            time.sleep(backoff)
            backoff = min(backoff*2, 900)

if __name__ == "__main__":
    autopilot_loop()
'''

# =========================
#  DASHBOARD CODE
# =========================
DASH_CODE = r'''import os
import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st
import toml

from engine import run_backup, BACKUP_DIR

try:
    import psutil
except ImportError:
    psutil = None

DB_FILE = "empire.db"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "empire_activity.log")

def get_conn():
    return sqlite3.connect(DB_FILE)

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

    c.execute("""INSERT OR IGNORE INTO settings (key,value)
                 VALUES ('system_status','RUNNING')""")

    conn.commit()
    conn.close()

init_db()

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

def load_secrets():
    try:
        return dict(st.secrets)
    except:
        pass
    if os.path.exists(".streamlit/secrets.toml"):
        try:
            return toml.load(".streamlit/secrets.toml")
        except:
            return {}
    return {}

SECRETS = load_secrets()
DAILY_LIMIT = int(SECRETS.get("daily_run_limit", 5))

def get_counts():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts WHERE status='Pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'")
    ready = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='Published'")
    published = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='Failed'")
    failed = c.fetchone()[0]
    conn.close()
    return pending, ready, published, failed

def get_runs_today():
    today = str(date.today())
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date=?", (today,))
    ct = c.fetchone()[0]
    conn.close()
    return ct

def get_all_posts():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM posts ORDER BY id DESC", conn)
    conn.close()
    return df

def get_pending_posts():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id,name,app_url,link FROM posts WHERE status='Pending'", conn)
    conn.close()
    return df

def update_links_from_df(df):
    conn = get_conn()
    c = conn.cursor()
    for _, r in df.iterrows():
        link = (r.get("link") or "").strip()
        if not link:
            continue
        c.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?",
                  (link, int(r["id"])))
    conn.commit()
    conn.close()

def get_error_stats():
    conn = get_conn()
    c = conn.cursor()
    today = str(date.today())
    c.execute("SELECT COUNT(*) FROM error_log WHERE created_at LIKE ?", (today+"%",))
    today_errors = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM error_log")
    total_errors = c.fetchone()[0]
    c.execute("SELECT created_at FROM error_log ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    last = row[0] if row else None
    conn.close()
    return today_errors, total_errors, last

def get_recent_errors(limit=200):
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM error_log ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df

def build_notifications():
    pending, ready, published, failed = get_counts()
    df = get_recent_errors(50)
    notes = []
    for _, row in df.iterrows():
        stage = row["stage"] or ""
        item = row["item_name"] or "SYSTEM"
        msg = row["message"] or ""
        ts = row["created_at"]
        stg = stage.lower()
        if any(x in stg for x in ["main_loop","budget","system_load"]):
            sev = "critical"
        elif any(x in stg for x in ["wordpress","media","content"]):
            sev = "warning"
        else:
            sev = "info"
        notes.append({"severity":sev,"title":f"{stage} – {item}","message":msg,"created_at":ts})
    if pending > 0:
        notes.append({"severity":"info","title":"Pending items",
                      "message":f"{pending} need affiliate links",
                      "created_at":datetime.utcnow().isoformat()})
    if failed > 0:
        notes.append({"severity":"warning","title":"Failed items",
                      "message":f"{failed} failed in production",
                      "created_at":datetime.utcnow().isoformat()})
    order = {"critical":0,"warning":1,"info":2}
    notes.sort(key=lambda n:(order.get(n["severity"],3), n["created_at"]), reverse=True)
    return notes

def get_system_load():
    if not psutil:
        return (None, None)
    try:
        return psutil.cpu_percent(0.3), psutil.virtual_memory().percent
    except:
        return (None, None)

st.set_page_config(page_title="DTF Command HQ – Empire OS V52",
                   page_icon="🏗️",
                   layout="wide")

system_status = get_setting("system_status", "RUNNING")
pending, ready, published, failed = get_counts()
runs_today = get_runs_today()
today_errors, total_errors, last_error = get_error_stats()
notifications = build_notifications()
cpu_load, mem_load = get_system_load()

with st.sidebar:
    st.markdown("### 🏗️ DTF Command HQ — Empire OS V52")
    if system_status != "RUNNING":
        st.error("🔴 ENGINE: STOPPED")
    else:
        if cpu_load and mem_load and (cpu_load>80 or mem_load>85):
            st.warning("🟡 ENGINE: THROTTLED")
        else:
            st.success("🟢 ENGINE: RUNNING")
    st.metric("Jobs Today", f"{runs_today}/{DAILY_LIMIT}")
    st.metric("System Load", f"{cpu_load or 0:.0f}% CPU / {mem_load or 0:.0f}% RAM")
    st.metric("Published", published)
    crit = len([n for n in notifications if n["severity"]=="critical"])
    warn = len([n for n in notifications if n["severity"]=="warning"])
    st.markdown(f"🚨 **Notifications:** {crit} critical, {warn} warnings, {len(notifications)} total")
    st.markdown("---")
    st.subheader("Engine Control")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🛑 Stop"):
            set_setting("system_status","STOPPED")
            st.experimental_rerun()
    with col2:
        if st.button("▶ Resume"):
            set_setting("system_status","RUNNING")
            st.experimental_rerun()
    st.markdown("---")
    page = st.radio("Navigate",[
        "🏠 Command Center",
        "⚡ Link Input",
        "📊 Pipeline",
        "📜 Logs",
        "🧯 Error Center",
        "🚨 Notifications",
        "🩺 System Health",
        "☁ Backups"
    ])

def page_command_center():
    st.title("🏠 Command Center")
    if system_status != "RUNNING":
        st.error("ENGINE STOPPED — use sidebar to resume.")
    else:
        if pending>0: st.warning(f"{pending} items need affiliate links.")
        elif ready>0: st.info(f"{ready} items queued for production.")
        elif published>0: st.success("Engine idle: all work completed.")
        else: st.info("Engine ready. Waiting for scout.")
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Pending", pending)
    c2.metric("Ready", ready)
    c3.metric("Published", published)
    c4.metric("Failed", failed)
    c5.metric("Errors Today", today_errors)
    c6.metric("Jobs Today", f"{runs_today}/{DAILY_LIMIT}")
    st.markdown("---")
    st.subheader("🚨 Notification Center (Prioritized)")
    if not notifications:
        st.success("No active notifications.")
    else:
        filt = st.radio("Filter",["All","Critical","Warnings","Info"],horizontal=True)
        m = {"Critical":"critical","Warnings":"warning","Info":"info"}
        for note in notifications:
            if filt!="All" and note["severity"]!=m[filt]:
                continue
            if note["severity"]=="critical":
                st.error(f"🔥 {note['title']}\n{note['message']}")
            elif note["severity"]=="warning":
                st.warning(f"⚠ {note['title']}\n{note['message']}")
            else:
                st.info(f"ℹ {note['title']}\n{note['message']}")
    st.markdown("---")
    colA,colB = st.columns([2,1])
    with colA:
        st.subheader("🔧 Quick Actions")
        if st.button("Open Link Input"):
            st.session_state["goto"] = "⚡ Link Input"
        if st.button("Open Error Center"):
            st.session_state["goto"] = "🧯 Error Center"
    with colB:
        st.subheader("ℹ System Snapshot")
        st.text(f"Last Error: {last_error or 'None'}")
        st.text(f"CPU: {cpu_load or 0:.0f}%   RAM: {mem_load or 0:.0f}%")

def page_link_input():
    st.title("⚡ Link Input — Wire Your Affiliate Links")
    df = get_pending_posts()
    if df.empty:
        st.success("No pending items. Engine ready.")
        return
    edited = st.data_editor(df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Product", disabled=True),
            "app_url": st.column_config.LinkColumn("Application/Signup"),
            "link": st.column_config.TextColumn("Affiliate Link")
        },
        hide_index=True)
    if st.button("Save Links & Queue"):
        update_links_from_df(edited)
        st.success("Links saved.")
        st.experimental_rerun()

def page_pipeline():
    st.title("📊 Content Pipeline")
    df = get_all_posts()
    if df.empty:
        st.info("No items yet. Scout will populate soon.")
        return
    status = st.selectbox("Filter Status",["(All)","Pending","Ready","Published","Failed"])
    search = st.text_input("Search Name")
    if status!="(All)": df = df[df["status"]==status]
    if search: df = df[df["name"].str.contains(search,case=False)]
    st.dataframe(df, use_container_width=True)

def page_logs():
    st.title("📜 Engine Logs")
    if st.button("Refresh Logs"):
        st.experimental_rerun()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE,"r",encoding="utf-8",errors="ignore") as f:
            lines = f.readlines()
        st.code("".join(lines[-200:]), language="bash")
    else:
        st.info("No log file yet.")

def page_errors():
    st.title("🧯 Error Center")
    df = get_recent_errors()
    if df.empty:
        st.success("No errors logged.")
        return
    stage = st.selectbox("Stage Filter",["(All)"]+sorted(df["stage"].unique()))
    item  = st.selectbox("Item Filter", ["(All)"]+sorted(df["item_name"].unique()))
    if stage!="(All)": df = df[df["stage"]==stage]
    if item!="(All)": df = df[df["item_name"]==item]
    st.dataframe(df, use_container_width=True)

def page_notifications():
    st.title("🚨 Notifications")
    if not notifications:
        st.success("No notifications.")
        return
    filt = st.radio("Filter",["All","Critical","Warnings","Info"],horizontal=True)
    m = {"Critical":"critical","Warnings":"warning","Info":"info"}
    for note in notifications:
        if filt!="All" and note["severity"]!=m[filt]: continue
        if note["severity"]=="critical":
            st.error(f"🔥 {note['title']}\n{note['message']}")
        elif note["severity"]=="warning":
            st.warning(f"⚠ {note['title']}\n{note['message']}")
        else:
            st.info(f"ℹ {note['title']}\n{note['message']}")

def page_system():
    st.title("🩺 System Health & Resource Guard")
    c1,c2,c3 = st.columns(3)
    c1.metric("CPU Load", f"{cpu_load or 0:.0f}%")
    c2.metric("RAM Usage", f"{mem_load or 0:.0f}%")
    c3.metric("Errors Today", today_errors)
    st.markdown("---")
    st.subheader("Adjust Resource Guard Thresholds")
    tc = st.slider("Throttle CPU %",50,95,int(get_setting("throttle_cpu",75)))
    pc = st.slider("Pause CPU %",60,100,int(get_setting("pause_cpu",90)))
    tr = st.slider("Throttle RAM %",50,95,int(get_setting("throttle_ram",80)))
    pr = st.slider("Pause RAM %",60,100,int(get_setting("pause_ram",95)))
    if st.button("Save Thresholds"):
        set_setting("throttle_cpu",tc)
        set_setting("pause_cpu",pc)
        set_setting("throttle_ram",tr)
        set_setting("pause_ram",pr)
        st.success("Saved.")

def page_backups():
    st.title("☁ Backups")
    st.write("Create local backups of empire.db + secrets.toml")
    if st.button("Create Backup"):
        run_backup()
        st.success("Backup created.")
        st.experimental_rerun()
    st.subheader("Existing Backups")
    rows = []
    if os.path.exists(BACKUP_DIR):
        for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
            path = os.path.join(BACKUP_DIR, name)
            if os.path.isdir(path):
                rows.append({"backup":name,"path":path})
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.info("No backups yet.")

if "goto" in st.session_state:
    page = st.session_state.pop("goto")

if page=="🏠 Command Center":
    page_command_center()
elif page=="⚡ Link Input":
    page_link_input()
elif page=="📊 Pipeline":
    page_pipeline()
elif page=="📜 Logs":
    page_logs()
elif page=="🧯 Error Center":
    page_errors()
elif page=="🚨 Notifications":
    page_notifications()
elif page=="🩺 System Health":
    page_system()
elif page=="☁ Backups":
    page_backups()
else:
    page_command_center()
'''

# =========================
#  OTHER FILES
# =========================
REQUIREMENTS = """streamlit
pandas
requests
moviepy<2.0
imageio
imageio-ffmpeg
toml
psutil
"""

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

SECRETS_TEMPLATE = """# .streamlit/secrets.toml
# Fill these in before running launch.bat

openai_key   = "YOUR_OPENAI_API_KEY"
pplx_key     = "YOUR_PERPLEXITY_API_KEY"

wp_url       = "https://your-wordpress-site.com"
wp_user      = "your_wp_username"
wp_pass      = "your_wp_application_password"

daily_run_limit = 5
"""

OPTIMIZER_BAT = r"""@echo off
TITLE DTF System Optimizer - Empire OS V52
echo =================================================
echo   DTF System Optimizer - Empire OS V52
echo =================================================
echo.

echo [1/3] Disabling system sleep on AC power...
powercfg -change -standby-timeout-ac 0

echo [2/3] Setting High Performance power plan (if available)...
powercfg -setactive SCHEME_MIN

echo [3/3] Enabling Hardware-Accelerated GPU Scheduling (requires reboot)...
reg add "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d 2 /f

echo.
echo Done. For best results:
echo   - Disable unneeded startup apps in Task Manager
echo   - Plug into power (if laptop)
echo   - Reboot your PC now
echo.
pause
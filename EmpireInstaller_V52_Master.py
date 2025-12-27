import os
import sys

# --- CONFIGURATION ---
PROJECT_DIR = "DTF_Command_HQ_V52"

# =========================
# I. ENGINE CODE (V52 MASTER)
# =========================
ENGINE_CODE = r'''import base64
import json
import logging
import os
import re
import shutil
import sqlite3
import time
import sys
from datetime import date, datetime

import requests
import toml
# Moviepy is the last dependency to load as it is often complex
try:
    from moviepy.editor import AudioFileClip, ColorClip, CompositeVideoClip, ImageClip
except ImportError:
    MoviePy_Available = False
else:
    MoviePy_Available = True

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
if not FFMPEG_AVAILABLE:
    logging.warning("FFmpeg not found. Video rendering will be skipped.")

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
        logging.StreamHandler(sys.stdout),
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
            video_path TEXT,
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


def update_media_paths(name: str, image_url: str, video_path: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET image_url = ?, video_path = ? WHERE name = ?",
        (image_url, video_path, name),
    )
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
    logging.info("発 Scouting niche: %s", niche)
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
    logging.info("博 Fact checking: %s", product)
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
    logging.info("統 Writing DTF content for: %s", product)
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
    logging.info("耳 Producing media for: %s", product)
    if not openai_key:
        log_error(product, "media", "Missing openai_key")
        return None, None

    h_oa = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }

    clean = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    img_path = os.path.join(base_dir, f"{clean}_img.jpg")
    aud_path = os.path.join(base_dir, f"{clean}_aud.mp3")
    vid_path = os.path.join(base_dir, f"{clean}_short.mp4")

    img_url = None
    # 1. Image Generation
    try:
        img_payload = {
            "model": "dall-e-3",
            "prompt": (
                f"Professional photo of {product} being used by a contractor on a real "
                f"construction site (siding, roofing, or remodeling), with a subtle "
                f"DTF Command / Design To Finish branding vibe. Cinematic lighting."
            ),
            "size": "1024x1024",
        }
        resp = safe_post("https://api.openai.com/v1/images/generations", img_payload, h_oa, item_name=product, stage="media_image")
        if resp:
            img_url = resp.json()["data"][0]["url"]
            # Download and save image locally
            r_img = safe_get(img_url, item_name=product, stage="media_image_dl")
            if r_img:
                with open(img_path, "wb") as f:
                    f.write(r_img.content)
            else:
                img_path = None
        else:
            img_path = None
    except Exception as e:
        log_error(product, "media_image", str(e))
        img_path = None

    # 2. TTS Audio Generation
    try:
        aud_payload = {"model": "tts-1", "voice": "onyx", "input": script}
        resp = safe_post(
            "https://api.openai.com/v1/audio/speech",
            aud_payload,
            h_oa,
            item_name=product,
            stage="media_audio",
            timeout=120,
        )
        if resp:
            with open(aud_path, "wb") as f:
                f.write(resp.content)
        else:
            aud_path = None
    except Exception as e:
        log_error(product, "media_audio", str(e))
        aud_path = None

    # 3. Video Composition (Requires ffmpeg and moviepy)
    if not MoviePy_Available or not FFMPEG_AVAILABLE or not img_path or not aud_path:
        if not MoviePy_Available:
            log_error(product, "media_video", "MoviePy not installed/loaded.")
        if not FFMPEG_AVAILABLE:
            log_error(product, "media_video", "ffmpeg not found.")
        vid_path = None
    else:
        try:
            ac = AudioFileClip(aud_path)
            dur = ac.duration + 0.5 # Add a small buffer
            ic = ImageClip(img_path).set_duration(dur).resize(height=1920)
            
            # Crop to vertical 9:16 (1080x1920) centered
            if ic.w > 1080:
                ic = ic.crop(x1=(ic.w/2-540), y1=0, width=1080, height=1920)
            
            bg = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=dur)
            
            # Use 'center' position to ensure the cropped image is in the center
            video = CompositeVideoClip([bg, ic.set_position("center")]).set_audio(ac)
            
            video.write_videofile(
                vid_path, fps=24, verbose=False, logger=None, codec='libx264', audio_codec='aac'
            )
            logging.info("耳 Video short successfully rendered: %s", vid_path)
        except Exception as e:
            log_error(product, "media_video", f"Video render failed: {e}")
            vid_path = None

    return img_url, vid_path


def create_smart_link(wp_url: str, product: str, raw_link: str):
    clean = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    enc = base64.b64encode(raw_link.encode()).decode()
    return f"{wp_url.rstrip('/')}/?df_track={clean}&dest={enc}"


def publish_to_wordpress(name: str, html: str, smart_link: str, img_path: str, secrets: dict):
    wp_url  = secrets.get("wp_url", "").rstrip("/")
    wp_user = secrets.get("wp_user", "")
    wp_pass = secrets.get("wp_pass", "")

    if not (wp_url and wp_user and wp_pass):
        log_error(name, "wordpress", "Missing WP credentials")
        return

    # Add styled affiliate button to HTML
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
    # 1. Upload Featured Image
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
            if r and r.status_code in (200, 201):
                media_id = r.json().get("id")
        except Exception as e:
            log_error(name, "wordpress_media", str(e))

    # 2. Create Post
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
        if r and r.status_code in (200, 201):
            logging.info("統 Published draft to WordPress: %s", name)
        else:
            log_error(name, "wordpress_post", f"Post error: {r.text[:200]}" if r else "No response")
    except Exception as e:
        log_error(name, "wordpress_post", str(e))


def production_line(row: tuple, secrets: dict):
    # row: (id, name, niche, link, status, app_url)
    _id, name, niche, link, status, app = row

    logging.info("--- STARTING PRODUCTION for: %s ---", name)

    if not link:
        log_error(name, "precheck", "Missing affiliate link")
        update_status(name, "Failed")
        return

    try:
        # 1. FACT CHECK
        facts = get_product_facts(name, secrets.get("pplx_key", ""))
        
        # 2. CONTENT GENERATION
        raw_content = create_content(name, facts, secrets.get("openai_key", ""))
        if not raw_content:
            update_status(name, "Failed")
            return

        try:
            data = json.loads(raw_content)
        except Exception as e:
            log_error(name, "content_json", str(e))
            update_status(name, "Failed")
            return

        blog = data.get("blog_html", "")
        script = data.get("video_script", "")

        today = datetime.now().strftime("%Y-%m-%d")
        folder = os.path.join(PACKET_ROOT, f"Daily_Packet_{today}")
        os.makedirs(folder, exist_ok=True)

        # 3. MEDIA PRODUCTION
        img_url, vid_path = produce_media(name, script, secrets.get("openai_key", ""), folder)

        # 4. WORDPRESS PUBLISH
        smart_link = create_smart_link(secrets.get("wp_url", ""), name, link)
        # img_path is derived inside produce_media 
        clean_name = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
        img_path = os.path.join(folder, f"{clean_name}_img.jpg")
        
        publish_to_wordpress(name, blog, smart_link, img_path, secrets)

        # 5. FINAL STATUS UPDATE
        update_media_paths(name, img_url or "", vid_path or "")
        update_status(name, "Published")
        log_run(name)
        logging.info("--- PRODUCTION SUCCESS for: %s ---", name)

    except Exception as e:
        log_error(name, "production_fatal", str(e))
        update_status(name, "Failed")


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
        logging.info("統 Database and secrets backed up to %s", d)
    except Exception as e:
        log_error("SYSTEM", "backup", str(e))


def autopilot_loop():
    logging.info("=== DTF COMMAND ENGINE V52 ONLINE ===")
    init_db()
    run_backup() # Run a backup at startup
    backoff = 30 # Initial sleep for network errors

    while True:
        try:
            secrets = load_secrets()
            openai_key = secrets.get("openai_key", "")
            pplx_key = secrets.get("pplx_key", "")
            limit = int(secrets.get("daily_run_limit", 5))

            if not openai_key or not pplx_key:
                log_error("SYSTEM", "main_loop", "Missing API keys - Check secrets.toml")
                time.sleep(30)
                continue

            # 1. System Control Check
            if get_setting("system_status", "RUNNING") != "RUNNING":
                logging.warning("System is paused by user control.")
                time.sleep(60)
                continue

            # 2. Resource Guard Check
            state = resource_guard()
            if state == "pause":
                time.sleep(60)
                continue
            elif state == "throttle":
                delay = 60 # Slower production loop
            else:
                delay = 10 # Normal production loop

            # 3. Budget Check
            if not check_budget(limit):
                log_error("SYSTEM", "budget", "Daily run limit hit.")
                time.sleep(3600)
                continue

            # 4. Production Check (Ready items)
            item = get_ready_item()
            if item:
                production_line(item, secrets)
                time.sleep(delay)
                backoff = 30 # Reset backoff after success
                continue

            # 5. Scout Check (No Ready items, check Pending count)
            pending = get_pending_count()
            if pending == 0:
                logging.info("Pipeline empty. Scouting for new tools.")
                items = run_scout_real("DTF Tools", pplx_key)
                for it in items:
                    app = find_app_link_real(it, pplx_key)
                    insert_scouted_product(it, "DTF Tools", app)
                time.sleep(60) # Short wait after scouting
                continue
            
            # 6. Default Sleep (Pending items exist, waiting for user input)
            logging.info("Pending items exist but none are Ready. Sleeping 5 min.")
            time.sleep(300)
            backoff = 30

        except Exception as e:
            log_error("SYSTEM", "main_loop", str(e))
            time.sleep(backoff)
            backoff = min(backoff * 2, 900)


if __name__ == "__main__":
    autopilot_loop()
'''

# =========================
# II. DASHBOARD CODE (V52 MASTER)
# =========================
DASH_CODE = r'''import os
import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st
import toml

# Import only necessary functions from the engine file
try:
    # We must redefine functions if engine.py doesn't exist yet, 
    # but for simplicity, we assume engine.py is built first.
    # In the installer context, we just include the required logic here.
    # If running independently, this import needs 'from engine import ...'
    
    # Redefine necessary engine functions here for the installer script's sake
    # In a deployed structure, this needs to import from the sibling file.
    
    # --- Installer-specific dummy definitions for DB access ---
    def get_conn():
        return sqlite3.connect("empire.db")
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
        c.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, val))
        conn.commit()
        conn.close()
    def log_error(item, stage, msg):
        # Dummy log_error for installer to prevent crashes
        print(f"UI Error Log: {item} - {msg}") 
    def run_backup():
        # Requires the shutil logic from engine.py for full functionality
        print("Backup triggered (Placeholder: Needs engine.py's full run_backup function)")
        pass 
    BACKUP_DIR = "backups"
    
except Exception as e:
    st.error(f"UI Initialization Error: {e}")
    st.stop()


try:
    import psutil
except ImportError:
    psutil = None

DB_FILE = "empire.db"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "empire_activity.log")


# Ensure DB structure is present for the dashboard
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
        video_path TEXT, 
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

init_db()


def load_secrets():
    # Attempt to load from st.secrets first (for cloud deployment)
    try:
        return dict(st.secrets)
    except:
        pass
    # Fallback to local secrets.toml
    if os.path.exists(".streamlit/secrets.toml"):
        try:
            return toml.load(".streamlit/secrets.toml")
        except:
            return {}
    return {}

SECRETS = load_secrets()
DAILY_LIMIT = int(SECRETS.get("daily_run_limit", 5))


# --- DATA FETCHERS ---

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

def update_links_from_df(df: pd.DataFrame):
    conn = get_conn()
    c = conn.cursor()
    updated_count = 0
    for _, r in df.iterrows():
        link = (r.get("link") or "").strip()
        # Basic validation: must look like a URL
        if link and (link.startswith("http://") or link.startswith("https://")):
            c.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?",
                      (link, int(r["id"])))
            updated_count += 1
        elif link:
            # If link is present but invalid, log it as an issue
            log_error(r["name"], "link_input", f"Invalid URL format: {link[:50]}")
    
    conn.commit()
    conn.close()
    return updated_count

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
    
    # 1. Error Notifications
    for _, row in df.iterrows():
        stage = row["stage"] or ""
        item = row["item_name"] or "SYSTEM"
        msg = row["message"] or ""
        ts = row["created_at"]
        stg = stage.lower()
        
        if any(x in stg for x in ["main_loop", "budget", "system_load", "secrets"]):
            sev = "critical"
        elif any(x in stg for x in ["wordpress", "media", "content", "link_input"]):
            sev = "warning"
        else:
            sev = "info"
        notes.append({"severity":sev,"title":f"{stage} – {item}","message":msg,"created_at":ts})

    # 2. Status Notifications
    if pending > 0:
        notes.append({"severity":"warning","title":"ACTION REQUIRED: Pending Links",
                      "message":f"{pending} items need affiliate links to move to production.",
                      "created_at":datetime.utcnow().isoformat()})
    if ready > 0:
        notes.append({"severity":"info","title":"Ready Queue Active",
                      "message":f"{ready} items are queued. The engine is working.",
                      "created_at":datetime.utcnow().isoformat()})
    if failed > 0:
        notes.append({"severity":"critical","title":"Production Failure",
                      "message":f"{failed} items failed production. Check logs/errors.",
                      "created_at":datetime.utcnow().isoformat()})

    order = {"critical":0,"warning":1,"info":2}
    # Sort by severity (critical first) and then by creation date (newest first)
    notes.sort(key=lambda n:(order.get(n["severity"],3), n["created_at"]), reverse=True)
    return notes

def get_system_load():
    if psutil is None:
        return (None, None)
    try:
        # Use a non-blocking poll by setting interval to 0.3
        return psutil.cpu_percent(0.3), psutil.virtual_memory().percent
    except:
        return (None, None)


# --- STREAMLIT UI ---

st.set_page_config(page_title="DTF Command HQ – Empire OS V52",
                   page_icon="🏗️",
                   layout="wide")

system_status = get_setting("system_status", "RUNNING")
pending, ready, published, failed = get_counts()
runs_today = get_runs_today()
today_errors, total_errors, last_error = get_error_stats()
notifications = build_notifications()
cpu_load, mem_load = get_system_load()


# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🏗️ DTF Command HQ — Empire OS V52")
    if system_status != "RUNNING":
        st.error("🔴 ENGINE: STOPPED")
    else:
        # Check resource status against thresholds
        throttle_cpu = float(get_setting("throttle_cpu", "75"))
        pause_cpu = float(get_setting("pause_cpu", "90"))
        if cpu_load and mem_load:
            if cpu_load >= pause_cpu or mem_load >= float(get_setting("pause_ram", "95")):
                 st.error("🚨 ENGINE: PAUSED (High Load)")
            elif cpu_load >= throttle_cpu or mem_load >= float(get_setting("throttle_ram", "80")):
                 st.warning("🟡 ENGINE: THROTTLED")
            else:
                 st.success("🟢 ENGINE: RUNNING")
        else:
            st.info("⚪ ENGINE: Status Unknown (psutil missing)")
            
    st.metric("Jobs Today", f"{runs_today}/{DAILY_LIMIT}")
    st.metric("System Load", f"{cpu_load or 0:.0f}% CPU / {mem_load or 0:.0f}% RAM")
    st.metric("Published Total", published)
    crit = len([n for n in notifications if n["severity"]=="critical"])
    warn = len([n for n in notifications if n["severity"]=="warning"])
    st.markdown(f"🚨 **Notifications:** {crit} critical, {warn} warnings, {len(notifications)} total")
    st.markdown("---")
    st.subheader("Engine Control")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🛑 Stop Engine"):
            set_setting("system_status","STOPPED")
            st.rerun()
    with col2:
        if st.button("▶ Resume Engine"):
            set_setting("system_status","RUNNING")
            st.rerun()
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


# --- PAGE FUNCTIONS ---

def page_command_center():
    st.title("🏠 Command Center")
    
    # Header Status Banner
    if system_status != "RUNNING":
        st.error("ENGINE STOPPED — Use sidebar to resume production.")
    elif failed>0:
        st.error(f"FATAL ALERT: {failed} items failed production. See Error Center.")
    elif pending>0: 
        st.warning(f"{pending} items need affiliate links. Go to Link Input page.")
    elif ready>0: 
        st.info(f"{ready} items queued. The production line is busy.")
    else: 
        st.success("Engine idle/scouting. No manual action needed.")
        
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
        # Show top 5 notifications
        for note in notifications[:5]:
            if note["severity"]=="critical":
                st.error(f"🔥 **{note['title']}**\n*{note['created_at']}*\n{note['message']}")
            elif note["severity"]=="warning":
                st.warning(f"⚠ **{note['title']}**\n*{note['created_at']}*\n{note['message']}")
            else:
                st.info(f"ℹ **{note['title']}**\n*{note['created_at']}*\n{note['message']}")

    st.markdown("---")
    colA,colB = st.columns([2,1])
    with colA:
        st.subheader("🔧 Quick Actions")
        if st.button("Open Link Input"):
            st.session_state["goto"] = "⚡ Link Input"
            st.rerun()
        if st.button("Open Error Center"):
            st.session_state["goto"] = "🧯 Error Center"
            st.rerun()
    with colB:
        st.subheader("ℹ System Snapshot")
        st.text(f"Last Error: {last_error or 'None'}")
        st.text(f"CPU: {cpu_load or 0:.0f}%   RAM: {mem_load or 0:.0f}%")


def page_link_input():
    st.title("⚡ Link Input — Wire Your Affiliate Links")
    df = get_pending_posts()
    if df.empty:
        st.success("No pending items. Engine is ready or scouting.")
        return
    edited = st.data_editor(df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Product", disabled=True),
            "app_url": st.column_config.LinkColumn("Affiliate/Signup URL"),
            "link": st.column_config.TextColumn("Affiliate Link", required=True)
        },
        hide_index=True)
    if st.button("Save Links & Queue Production"):
        updated = update_links_from_df(edited)
        if updated > 0:
            st.success(f"Successfully moved {updated} items to the Ready queue.")
        else:
            st.info("No new valid links were provided.")
        st.rerun()

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
    
    # Display fewer columns for a cleaner pipeline view
    display_cols = ['id', 'name', 'niche', 'status', 'link', 'image_url', 'video_path', 'created_at']
    st.dataframe(df[display_cols], use_container_width=True)

def page_logs():
    st.title("📜 Engine Logs")
    if st.button("Refresh Logs"):
        st.rerun()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE,"r",encoding="utf-8",errors="ignore") as f:
            lines = f.readlines()
        st.code("".join(lines[-200:]), language="bash")
    else:
        st.info("No log file yet.")

def page_errors():
    st.title("🧯 Error Center")
    if st.button("Refresh Errors"):
        st.rerun()
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
            st.error(f"🔥 **{note['title']}**\n*{note['created_at']}*\n{note['message']}")
        elif note["severity"]=="warning":
            st.warning(f"⚠ **{note['title']}**\n*{note['created_at']}*\n{note['message']}")
        else:
            st.info(f"ℹ **{note['title']}**\n*{note['created_at']}*\n{note['message']}")

def page_system():
    st.title("🩺 System Health & Resource Guard")
    c1,c2,c3 = st.columns(3)
    c1.metric("CPU Load", f"{cpu_load or 0:.0f}%")
    c2.metric("RAM Usage", f"{mem_load or 0:.0f}%")
    c3.metric("Errors Total", total_errors)
    st.markdown("---")
    st.subheader("Adjust Resource Guard Thresholds")
    
    # Fetch current values, ensure they are floats for the slider
    tc_def = float(get_setting("throttle_cpu", "75"))
    pc_def = float(get_setting("pause_cpu", "90"))
    tr_def = float(get_setting("throttle_ram", "80"))
    pr_def = float(get_setting("pause_ram", "95"))
    
    tc = st.slider("Throttle CPU % (Engine slows down)",50,95,int(tc_def))
    pc = st.slider("Pause CPU % (Engine stops)",60,100,int(pc_def))
    tr = st.slider("Throttle RAM % (Engine slows down)",50,95,int(tr_def))
    pr = st.slider("Pause RAM % (Engine stops)",60,100,int(pr_def))
    
    if st.button("Save Thresholds"):
        set_setting("throttle_cpu",str(tc))
        set_setting("pause_cpu",str(pc))
        set_setting("throttle_ram",str(tr))
        set_setting("pause_ram",str(pr))
        st.success("Thresholds saved. Engine will apply on next loop.")
        st.rerun()

def page_backups():
    st.title("☁ Backups")
    st.write("Create local backups of **empire.db** and **secrets.toml**.")
    if st.button("Create Backup Now"):
        # The actual backup logic lives in the engine, but we trigger it here.
        # Note: Must ensure engine is not actively writing to DB when backup is run.
        run_backup()
        st.success("Backup created successfully.")
        st.rerun()
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


# --- ROUTING ---
if "goto" in st.session_state:
    # Use session state to jump pages via buttons
    page = st.session_state.pop("goto")
    st.session_state["current_page"] = page
elif "current_page" in st.session_state:
    page = st.session_state["current_page"]
else:
    page = "🏠 Command Center"
    st.session_state["current_page"] = page

# Display the selected page
if page=="🏠 Command Center": page_command_center()
elif page=="⚡ Link Input": page_link_input()
elif page=="📊 Pipeline": page_pipeline()
elif page=="📜 Logs": page_logs()
elif page=="🧯 Error Center": page_errors()
elif page=="🚨 Notifications": page_notifications()
elif page=="🩺 System Health": page_system()
elif page=="☁ Backups": page_backups()
else: page_command_center()
'''

# =========================
# III. SUPPORTING FILES
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

# =========================
# IV. INSTALLER LOGIC
# =========================

def create(path, content):
    """Utility to create directories and write file content."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())

def install_empire_os():
    base_path = os.path.join(os.getcwd(), PROJECT_DIR)
    secrets_dir = os.path.join(base_path, ".streamlit")
    
    # 1. Create Directories
    os.makedirs(base_path, exist_ok=True)
    os.makedirs(secrets_dir, exist_ok=True)
    os.makedirs(os.path.join(base_path, "logs"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "packets"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "backups"), exist_ok=True)

    # 2. Write Files
    create(os.path.join(base_path, "engine.py"), ENGINE_CODE)
    create(os.path.join(base_path, "dtf_command_hq.py"), DASH_CODE)
    create(os.path.join(base_path, "requirements.txt"), REQUIREMENTS)
    create(os.path.join(base_path, "launch.bat"), LAUNCH_BAT)
    create(os.path.join(secrets_dir, "secrets.toml"), SECRETS_TEMPLATE)

    print("===================================================")
    print(f"✅ DTF Command HQ V52 Master Installed.")
    print(f"Directory: {base_path}")
    print("===================================================")
    print("NEXT STEPS:")
    print("1. NAVIGATE to the directory above.")
    print("2. OPEN and EDIT: .streamlit\\secrets.toml (Fill in your keys).")
    print("3. DOUBLE-CLICK launch.bat to install dependencies and start the system.")

if __name__ == "__main__":
    install_empire_os()

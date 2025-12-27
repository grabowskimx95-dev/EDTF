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
    """
    Read thresholds from settings and decide:
    - return "pause" to pause processing
    - return "throttle" to slow down
    - return "ok" for normal operation
    """
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

    # Pause condition
    if cpu >= pause_cpu or mem >= pause_ram:
        msg = f"Resource guard pause: CPU={cpu:.0f}%, RAM={mem:.0f}%"
        log_error("SYSTEM", "system_load", msg)
        return "pause"

    # Throttle condition
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
            "size": "1024x1024",
        }
        resp_img = safe_post(
            "https://api.openai.com/v1/images/generations",
            img_payload,
            h_oa,
            timeout=60,
            item_name=product,
            stage="media_image",
        )
        if resp_img:
            img_url = resp_img.json()["data"][0]["url"]
    except Exception as e:
        log_error(product, "media_image", f"Image generation failed: {e}")

    aud_bytes = None
    try:
        aud_payload = {
            "model": "tts-1",
            "input": script,
            "voice": "onyx",
        }
        resp_aud = safe_post(
            "https://api.openai.com/v1/audio/speech",
            aud_payload,
            h_oa,
            timeout=60 * 3,
            item_name=product,
            stage="media_audio",
        )
        if resp_aud:
            aud_bytes = resp_aud.content
    except Exception as e:
        log_error(product, "media_audio", f"Audio generation failed: {e}")

    if not img_url or not aud_bytes:
        log_error(
            product,
            "media",
            f"Media partial failure: img_url={bool(img_url)}, audio={bool(aud_bytes)}",
        )

    clean_name = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    img_path = os.path.join(base_dir, f"{clean_name}.jpg")
    aud_path = os.path.join(base_dir, f"{clean_name}.mp3")
    vid_path = os.path.join(base_dir, f"{clean_name}.mp4")

    if img_url:
        resp_img_data = safe_get(
            img_url, timeout=60, item_name=product, stage="media_image"
        )
        if resp_img_data:
            try:
                with open(img_path, "wb") as f:
                    f.write(resp_img_data.content)
            except Exception as e:
                log_error(product, "media_image", f"Failed to save image: {e}")
                img_path = None
        else:
            img_path = None
    else:
        img_path = None

    if aud_bytes:
        try:
            with open(aud_path, "wb") as f:
                f.write(aud_bytes)
        except Exception as e:
            log_error(product, "media_audio", f"Failed to save audio: {e}")
            aud_path = None
    else:
        aud_path = None

    # Video rendering with ffmpeg guard
    if not FFMPEG_AVAILABLE:
        log_error(
            product,
            "media_video",
            "ffmpeg not found on system PATH. Skipping video render.",
        )
        vid_path = None
    elif img_path and aud_path:
        try:
            ac = AudioFileClip(aud_path)
            duration = ac.duration + 0.5
            ic = ImageClip(img_path).set_duration(duration).resize(height=1920)
            if ic.w > 1080:
                x1 = ic.w / 2 - 540
                ic = ic.crop(x1=x1, y1=0, width=1080, height=1920)
            bc = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=duration)
            CompositeVideoClip([bc, ic]).set_audio(ac).write_videofile(
                vid_path, fps=24, verbose=False, logger=None
            )
            logging.info("🎬 Video rendered for %s", product)
        except Exception as e:
            log_error(product, "media_video", f"Video render failed: {e}")
            vid_path = None
    else:
        vid_path = None

    return img_path, aud_path, vid_path


def create_smart_link(wp_url: str, product_name: str, raw_link: str):
    clean = re.sub(r"[^\w\s-]", "", product_name).strip().replace(" ", "_")
    encoded = base64.b64encode(raw_link.encode("utf-8")).decode("utf-8")
    return f"{wp_url.rstrip('/')}/?df_track={clean}&dest={encoded}"


def publish_to_wordpress(
    name: str,
    blog_html: str,
    smart_link: str,
    img_path: str,
    secrets: dict,
):
    wp_url = secrets.get("wp_url", "").rstrip("/")
    wp_user = secrets.get("wp_user", "")
    wp_pass = secrets.get("wp_pass", "")
    if not (wp_url and wp_user and wp_pass):
        msg = "Missing WP credentials or URL"
        logging.error(msg)
        log_error(name, "wordpress", msg)
        return None

    blog_html += (
        f"\\n\\n<div style='text-align:center;margin-top:30px;'>"
        f"<p><strong>Want the gear we trust on real DTF jobsites?</strong></p>"
        f"<a href='{smart_link}' "
        f"style='background:#c1121f;color:white;padding:15px 25px;"
        f"font-weight:bold;text-decoration:none;border-radius:4px;'>"
        f"CHECK CURRENT PRICING</a>"
        f"<p style='margin-top:10px;font-size:12px;'>"
        f"Recommended by Design To Finish Contracting (DTF Command).</p>"
        f"</div>"
    )

    auth = base64.b64encode(f"{wp_user}:{wp_pass}".encode("utf-8")).decode("utf-8")

    media_id = None
    if img_path and os.path.exists(img_path):
        headers_media = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "image/jpeg",
            "Content-Disposition": "attachment; filename=feature.jpg",
        }
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            resp_media = requests.post(
                f"{wp_url}/wp-json/wp/v2/media",
                data=img_bytes,
                headers_headers_media,
                timeout=60,
            )
            if resp_media.status_code in (200, 201):
                media_json = resp_media.json()
                media_id = media_json.get("id")
                image_url = media_json.get("source_url", "")
                logging.info("Image uploaded to WP for %s: id=%s", name, media_id)

                conn = get_conn()
                c = conn.cursor()
                c.execute(
                    "UPDATE posts SET image_url = ? WHERE name = ?",
                    (image_url, name),
                )
                conn.commit()
                conn.close()
            else:
                msg = f"Media upload failed ({resp_media.status_code}): {resp_media.text[:300]}"
                log_error(name, "wordpress_media", msg)
        except Exception as e:
            log_error(name, "wordpress_media", f"Media upload exception: {e}")

    headers_post = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    post_data = {
        "title": f"{name} – DTF Command Review",
        "content": blog_html,
        "status": "draft",
    }
    if media_id:
        post_data["featured_media"] = media_id

    try:
        resp_post = requests.post(
            f"{wp_url}/wp-json/wp/v2/posts",
            json=post_data,
            headers=headers_post,
            timeout=60,
        )
        if resp_post.status_code in (200, 201):
            logging.info("✅ Published (draft) to WordPress: %s", name)
        else:
            msg = f"Post failed ({resp_post.status_code}): {resp_post.text[:300]}"
            log_error(name, "wordpress_post", msg)
    except Exception as e:
        log_error(name, "wordpress_post", f"WP post exception: {e}")


# -----------------------------------------
# PRODUCTION LINE
# -----------------------------------------
def production_line(item_row, secrets):
    _, name, niche, link, status, app_url = item_row
    logging.info("🏗️ Manufacturing DTF content: %s (niche=%s)", name, niche)

    pplx_key = secrets.get("pplx_key", "")
    openai_key = secrets.get("openai_key", "")
    wp_url = secrets.get("wp_url", "")

    if not link:
        msg = "No affiliate link set"
        log_error(name, "precheck", msg)
        update_status(name, "Failed")
        return

    facts = get_product_facts(name, pplx_key)

    content_json = create_content(name, facts, openai_key)
    if not content_json:
        log_error(name, "content", "Content generation failed or empty.")
        update_status(name, "Failed")
        return

    try:
        assets = json.loads(content_json)
    except Exception as e:
        log_error(name, "content", f"JSON parse error: {e}")
        update_status(name, "Failed")
        return

    blog_html = assets.get("blog_html", "")
    social_caption = assets.get("social_caption", "")
    video_script = assets.get("video_script", "")

    if not blog_html:
        log_error(name, "content", "Missing blog_html in generated assets.")
        update_status(name, "Failed")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    day_dir = os.path.join(PACKET_ROOT, f"Daily_Packet_{today_str}")
    os.makedirs(day_dir, exist_ok=True)

    img_path, aud_path, vid_path = produce_media(
        name,
        video_script or f"{name} is built for real job sites in St. Louis.",
        openai_key,
        day_dir,
    )

    smart_link = create_smart_link(wp_url, name, link)

    publish_to_wordpress(name, blog_html, smart_link, img_path, secrets)

    update_status(name, "Published")
    log_run(name)
    logging.info("✅ Completed DTF Command production for %s", name)


# -----------------------------------------
# BACKUP HELPER
# -----------------------------------------
def run_backup():
    """Simple local backup of empire.db and secrets.toml into backups/ timestamped folder."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = os.path.join(BACKUP_DIR, f"backup_{ts}")
    os.makedirs(dest_dir, exist_ok=True)

    try:
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, os.path.join(dest_dir, "empire.db"))
        if os.path.exists(SECRETS_PATH):
            os.makedirs(os.path.join(dest_dir, ".streamlit"), exist_ok=True)
            shutil.copy2(
                SECRETS_PATH,
                os.path.join(dest_dir, ".streamlit", "secrets.toml"),
            )
        logging.info("☁ Backup completed at %s", dest_dir)
    except Exception as e:
        log_error("SYSTEM", "backup", f"Backup failed: {e}")


# -----------------------------------------
# MAIN AUTOPILOT LOOP
# -----------------------------------------
def autopilot_loop():
    logging.info("--- DTF COMMAND ENGINE V52 ONLINE ---")
    init_db()

    backoff = 30

    while True:
        try:
            secrets = load_secrets()
            openai_key = secrets.get("openai_key", "")
            pplx_key = secrets.get("pplx_key", "")
            daily_limit = int(secrets.get("daily_run_limit", 10))

            if not openai_key or not pplx_key:
                msg = "Missing API keys (openai_key or pplx_key)."
                logging.warning(msg)
                log_error("SYSTEM", "main_loop", msg)
                time.sleep(30)
                continue

            system_status = get_setting("system_status", "RUNNING")
            if system_status != "RUNNING":
                logging.info("🛑 Engine is stopped via dashboard. Sleeping 60s...")
                time.sleep(60)
                continue

            # Resource guard
            guard_state = resource_guard()
            if guard_state == "pause":
                logging.warning("🧯 Resource guard PAUSE – sleeping 60s.")
                time.sleep(60)
                continue
            elif guard_state == "throttle":
                logging.warning("🧯 Resource guard THROTTLE – adding extra delay.")

            if not check_budget(daily_limit):
                msg = f"Daily budget hit ({daily_limit})."
                logging.info("💤 " + msg + " Sleeping 1 hour...")
                log_error("SYSTEM", "budget", msg)
                time.sleep(3600)
                continue

            item = get_ready_item()
            if item:
                production_line(item, secrets)
                # If throttled, we already logged; add more delay
                if guard_state == "throttle":
                    time.sleep(60)
                else:
                    time.sleep(10)
                backoff = 30
                continue

            pending_count = get_pending_count()
            if pending_count == 0:
                logging.info("BLUE LIGHT - DTF pipeline empty. Auto-scouting tools...")
                items = run_scout_real("DTF Contractor Tools", pplx_key)
                for name in items:
                    app_url = find_app_link_real(name, pplx_key)
                    insert_scouted_product(name, "DTF Tools", app_url)
                    logging.info("🔭 Found DTF candidate: %s", name)
                time.sleep(60)
                backoff = 30
                continue

            logging.info(
                "RED LIGHT - %s DTF items pending affiliate links. Waiting 5 minutes.",
                pending_count,
            )
            time.sleep(300)
            backoff = 30

        except Exception as e:
            msg = f"System error in main loop: {e}"
            logging.error(msg)
            log_error("SYSTEM", "main_loop", msg)
            time.sleep(backoff)
            backoff = min(backoff * 2, 900)


if __name__ == "__main__":
    autopilot_loop()
'''


# =========================
#  DASHBOARD CODE
#  (dtf_command_hq.py – upgraded UI)
# =========================
DASH_CODE = '''import os
import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st
import toml

try:
    import psutil
except ImportError:
    psutil = None

from engine import run_backup, BACKUP_DIR

DB_FILE = "empire.db"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "empire_activity.log")


# -----------------------------
# DB HELPERS
# -----------------------------
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
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def get_counts():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Pending'")
    pending = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Ready'")
    ready = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Published'")
    published = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Failed'")
    failed = c.fetchone()[0]

    conn.close()
    return pending, ready, published, failed


def get_runs_today():
    today = str(date.today())
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date = ?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_all_posts():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM posts ORDER BY id DESC", conn)
    conn.close()
    return df


def get_pending_posts():
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, name, app_url, link FROM posts WHERE status = 'Pending' ORDER BY id DESC",
        conn,
    )
    conn.close()
    return df


def update_links_from_df(df):
    conn = get_conn()
    c = conn.cursor()
    for _, row in df.iterrows():
        link_val = (row.get("link") or "").strip()
        if not link_val:
            continue
        c.execute(
            "UPDATE posts SET link = ?, status = 'Ready' WHERE id = ?",
            (link_val, int(row["id"])),
        )
    conn.commit()
    conn.close()


def get_published_for_export():
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT name, image_url, link FROM posts WHERE status = 'Published'",
        conn,
    )
    conn.close()
    return df


def get_error_stats():
    conn = get_conn()
    c = conn.cursor()

    today_str = str(date.today())
    c.execute(
        "SELECT COUNT(*) FROM error_log WHERE created_at LIKE ?",
        (today_str + "%",),
    )
    today_errors = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM error_log")
    total_errors = c.fetchone()[0]

    c.execute("SELECT created_at FROM error_log ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    last_error_time = row[0] if row else None

    conn.close()
    return today_errors, total_errors, last_error_time


def get_recent_errors(limit=200):
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM error_log ORDER BY id DESC LIMIT ?",
        conn,
        params=(limit,),
    )
    conn.close()
    return df


# -----------------------------
# NOTIFICATIONS (PRIORITIZED)
# -----------------------------
def build_notifications():
    notifications = []

    pending, ready, published, failed = get_counts()
    runs_today = get_runs_today()

    df_err = get_recent_errors(limit=50)
    for _, row in df_err.iterrows():
        stage = row["stage"] or ""
        item = row["item_name"] or "SYSTEM"
        msg = row["message"] or ""
        created = row["created_at"] or ""

        stage_lower = stage.lower()
        if any(x in stage_lower for x in ["main_loop", "budget", "system_load"]):
            severity = "critical"
        elif any(x in stage_lower for x in ["wordpress", "media_video", "media_image", "media_audio", "content"]):
            severity = "warning"
        else:
            severity = "info"

        notifications.append(
            {
                "severity": severity,
                "title": f"{stage} – {item}",
                "message": msg,
                "created_at": created,
            }
        )

    if pending > 0:
        notifications.append(
            {
                "severity": "info",
                "title": "Pending tools need affiliate links",
                "message": f"{pending} items are waiting for your DTF affiliate link in Link Input.",
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    if failed > 0:
        notifications.append(
            {
                "severity": "warning",
                "title": "Failed items in pipeline",
                "message": f"{failed} tools failed during production. Check Error Center.",
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    notifications.sort(
        key=lambda n: (
            severity_rank.get(n["severity"], 3),
            n["created_at"],
        ),
        reverse=True,
    )

    return notifications


# -----------------------------
# SECRETS
# -----------------------------
def load_secrets():
    try:
        secrets = st.secrets  # type: ignore[attr-defined]
        return dict(secrets)
    except Exception:
        pass

    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        try:
            return toml.load(secrets_path)
        except Exception:
            return {}
    return {}


# -----------------------------
# SYSTEM HEALTH HELPERS
# -----------------------------
def get_system_load():
    if psutil is None:
        return None, None
    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory().percent
        return cpu, mem
    except Exception:
        return None, None


# -----------------------------
# STREAMLIT APP
# -----------------------------
init_db()
SECRETS = load_secrets()
DAILY_LIMIT = int(SECRETS.get("daily_run_limit", 5))

st.set_page_config(
    page_title="DTF Command HQ – Empire OS V52",
    page_icon="🏗️",
    layout="wide",
)

system_status = get_setting("system_status", "RUNNING")
pending_count, ready_count, published_count, failed_count = get_counts()
runs_today = get_runs_today()
today_errors, total_errors, last_error_time = get_error_stats()
notifications = build_notifications()

cpu_load, mem_load = get_system_load()

with st.sidebar:
    st.markdown("### 🏗️ DTF Command HQ")
    st.caption("Design To Finish Contracting – Empire OS V52")

    if system_status == "STOPPED":
        st.error("🔴 ENGINE: STOPPED")
    else:
        if cpu_load is not None and mem_load is not None and (cpu_load > 80 or mem_load > 85):
            st.warning("🟡 ENGINE: THROTTLED (High load)")
        else:
            st.success("🟢 ENGINE: RUNNING")

    st.metric("Jobs Today", f"{runs_today}/{DAILY_LIMIT}")
    st.metric("System Load", f"{cpu_load or 0:.0f}% CPU / {mem_load or 0:.0f}% RAM")
    st.metric("Published Items", published_count)

    crit_count = sum(1 for n in notifications if n["severity"] == "critical")
    warn_count = sum(1 for n in notifications if n["severity"] == "warning")
    total_notifs = len(notifications)
    if total_notifs > 0:
        st.markdown(
            f"**🚨 Notifications:** {crit_count} critical, {warn_count} warnings, {total_notifs} total"
        )
    else:
        st.markdown("**🚨 Notifications:** None")

    st.markdown("---")

    st.subheader("Engine Control")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🛑 Stop"):
            set_setting("system_status", "STOPPED")
            st.experimental_rerun()
    with col_btn2:
        if st.button("▶ Resume"):
            set_setting("system_status", "RUNNING")
            st.experimental_rerun()

    st.markdown("---")

    page = st.radio(
        "Navigate",
        [
            "🏠 Command Center",
            "⚡ Link Input",
            "📊 Pipeline",
            "📜 Logs",
            "🧯 Error Center",
            "🚨 Notifications",
            "🩺 System Health",
            "☁ Backups",
        ],
    )

    st.caption(
        "Tip: Use Command Center for top issues, Link Input for affiliate wiring, "
        "Error Center + Notifications to fix problems fast."
    )


def render_command_center():
    st.title("DTF Command – Command Center")

    if system_status == "STOPPED":
        st.error("🔴 Engine stopped. Use 'Resume' in the sidebar to restart.")
    else:
        if pending_count > 0:
            st.warning(f"🟡 {pending_count} items need affiliate links.")
        elif ready_count > 0:
            st.info(f"🟡 {ready_count} tools queued for production.")
        elif published_count > 0:
            st.success("🟢 Engine idle: all caught up, waiting for new tools.")
        else:
            st.info("🟢 Engine ready: no items yet, scout will run automatically.")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Pending", pending_count)
    with col2:
        st.metric("Ready", ready_count)
    with col3:
        st.metric("Published", published_count)
    with col4:
        st.metric("Failed", failed_count)
    with col5:
        st.metric("Errors (Total)", total_errors)
    with col6:
        st.metric("Jobs Today", f"{runs_today}/{DAILY_LIMIT}")

    st.markdown("---")

    st.subheader("🚨 Notification Center (Prioritized)")
    if not notifications:
        st.success("No active notifications. System is clean.")
    else:
        filt = st.radio(
            "Filter",
            ["All", "Critical", "Warnings", "Info"],
            horizontal=True,
        )

        severity_map = {
            "Critical": "critical",
            "Warnings": "warning",
            "Info": "info",
        }

        for note in notifications:
            sev = note["severity"]
            if filt != "All" and sev != severity_map[filt]:
                continue

            if sev == "critical":
                with st.container():
                    st.error(f"🔥 {note['title']}")
                    st.write(note["message"])
                    st.caption(note["created_at"])
            elif sev == "warning":
                with st.container():
                    st.warning(f"⚠ {note['title']}")
                    st.write(note["message"])
                    st.caption(note["created_at"])
            else:
                with st.container():
                    st.info(f"ℹ {note['title']}")
                    st.write(note["message"])
                    st.caption(note["created_at"])

    st.markdown("---")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("🔧 Quick Actions")
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            if st.button("⚡ Go to Link Input"):
                st.session_state["goto_page"] = "⚡ Link Input"
        with col_q2:
            if st.button("🧯 Go to Error Center"):
                st.session_state["goto_page"] = "🧯 Error Center"

        st.caption(
            "Use Quick Actions to jump straight into wiring affiliate links or fixing errors."
        )

    with col_right:
        st.subheader("ℹ System Snapshot")
        st.write(f"Last error: `{last_error_time or 'None'}`")
        st.write(f"CPU / RAM: `{cpu_load or 0:.0f}%` / `{mem_load or 0:.0f}%`")


def render_link_input():
    st.title("⚡ Link Input – Wire Your DTF Affiliate Links")

    df_pending = get_pending_posts()
    if df_pending.empty:
        st.success("✅ No pending items. The engine is ready or scouting.")
        return

    st.write(
        "These tools are scouted and waiting for **your DTF affiliate link** before they can go into production."
    )

    display_cols = ["id", "name", "app_url", "link"]
    edited_df = st.data_editor(
        df_pending[display_cols],
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Tool / Product", disabled=True),
            "app_url": st.column_config.LinkColumn(
                "Affiliate Program / Application",
                display_text="👉 Open Application",
            ),
            "link": st.column_config.TextColumn(
                "Your DTF Affiliate Link (Paste Here)", width="large", required=False
            ),
        },
        hide_index=True,
        key="pending_editor",
    )

    if st.button("✅ Save Links & Queue for Production"):
        update_links_from_df(edited_df)
        st.success("Links saved. Items moved to Ready.")
        st.experimental_rerun()


def render_pipeline():
    st.title("📊 DTF Content Pipeline")

    df_all = get_all_posts()
    if df_all.empty:
        st.info("No items in the pipeline yet. Once the engine scouts, they’ll appear here.")
        return

    status_filter = st.selectbox(
        "Filter by status",
        ["(All)", "Pending", "Ready", "Published", "Failed"],
    )
    search_name = st.text_input("Search by tool name")

    df_view = df_all.copy()
    if status_filter != "(All)":
        df_view = df_view[df_view["status"] == status_filter]

    if search_name:
        df_view = df_view[df_view["name"].str.contains(search_name, case=False, na=False)]

    st.dataframe(df_view, use_container_width=True)


def render_logs():
    st.title("📜 Engine Logs")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Refresh Logs"):
            st.experimental_rerun()
    with col_btn2:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()
            st.download_button(
                "⬇ Download Full Log",
                data=data,
                file_name="empire_activity.log",
                mime="text/plain",
            )

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        last_lines = "".join(lines[-150:])
        st.code(last_lines or "[log file empty]", language="bash")
    else:
        st.info("Log file not found yet. Start the engine first.")


def render_error_center():
    st.title("🧯 Error Center – Diagnostics & Triage")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Errors Today", today_errors)
    with col_b:
        st.metric("Total Errors", total_errors)
    with col_c:
        st.metric("Failed Items", failed_count)

    st.markdown("---")

    df_errors = get_recent_errors(limit=200)
    if df_errors.empty:
        st.success("No errors logged. System is clean.")
        return

    stages = sorted(df_errors["stage"].dropna().unique().tolist())
    items = sorted(df_errors["item_name"].dropna().unique().tolist())

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        stage_filter = st.selectbox(
            "Filter by stage", options=["(All)"] + stages, index=0
        )
    with col_f2:
        item_filter = st.selectbox(
            "Filter by item", options=["(All)"] + items, index=0
        )

    df_view = df_errors.copy()
    if stage_filter != "(All)":
        df_view = df_view[df_view["stage"] == stage_filter]
    if item_filter != "(All)":
        df_view = df_view[df_view["item_name"] == item_filter]

    st.caption("Showing the most recent errors (up to 200).")
    st.dataframe(df_view, use_container_width=True)

    with st.expander("How to use this"):
        st.write(
            """
- **stage** tells you where the failure happened:
  - `scout`, `affiliate_lookup`, `fact_check`, `content`,
    `media_image`, `media_audio`, `media_video`,
    `wordpress_post`, `budget`, `main_loop`, `system_load`, etc.
- **item_name** is either a tool/product or `SYSTEM`.

Start with `content`, `media_video`, or `wordpress_post` to fix DTF content issues the fastest.
"""
        )


def render_notifications_page():
    st.title("🚨 Notifications")

    if not notifications:
        st.success("No active notifications.")
        return

    filt = st.radio(
        "Filter",
        ["All", "Critical", "Warnings", "Info"],
        horizontal=True,
    )

    severity_map = {
        "Critical": "critical",
        "Warnings": "warning",
        "Info": "info",
    }

    for note in notifications:
        sev = note["severity"]
        if filt != "All" and sev != severity_map[filt]:
            continue

        if sev == "critical":
            with st.container():
                st.error(f"🔥 {note['title']}")
                st.write(note["message"])
                st.caption(note["created_at"])
        elif sev == "warning":
            with st.container():
                st.warning(f"⚠ {note['title']}")
                st.write(note["message"])
                st.caption(note["created_at"])
        else:
            with st.container():
                st.info(f"ℹ {note['title']}")
                st.write(note["message"])
                st.caption(note["created_at"])


def render_system_health():
    st.title("🩺 System Health & Resource Guard")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("CPU Load", f"{cpu_load or 0:.0f} %")
    with col2:
        st.metric("RAM Usage", f"{mem_load or 0:.0f} %")
    with col3:
        st.metric("Errors Today", today_errors)

    st.markdown("---")

    st.subheader("Resource Guard Thresholds")

    default_throttle_cpu = float(get_setting("throttle_cpu", "75"))
    default_pause_cpu = float(get_setting("pause_cpu", "90"))
    default_throttle_ram = float(get_setting("throttle_ram", "80"))
    default_pause_ram = float(get_setting("pause_ram", "95"))

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        throttle_cpu = st.slider("Throttle above CPU %", 50, 95, int(default_throttle_cpu))
        pause_cpu = st.slider("Pause above CPU %", 60, 100, int(default_pause_cpu))
    with col_t2:
        throttle_ram = st.slider("Throttle above RAM %", 50, 95, int(default_throttle_ram))
        pause_ram = st.slider("Pause above RAM %", 60, 100, int(default_pause_ram))

    if st.button("💾 Save Thresholds"):
        set_setting("throttle_cpu", str(throttle_cpu))
        set_setting("pause_cpu", str(pause_cpu))
        set_setting("throttle_ram", str(throttle_ram))
        set_setting("pause_ram", str(pause_ram))
        st.success("Thresholds saved. The engine will use these on next cycle.")

    if st.button("♻ Reset to Defaults"):
        set_setting("throttle_cpu", "75")
        set_setting("pause_cpu", "90")
        set_setting("throttle_ram", "80")
        set_setting("pause_ram", "95")
        st.success("Thresholds reset to defaults.")

    st.markdown("---")
    st.caption(
        "Note: The engine code reads these settings and adjusts behavior "
        "(throttle or pause) based on CPU/RAM. This page manages the values."
    )


def render_backups():
    st.title("☁ Backups")

    st.info(
        "Create and manage local backups of your DTF Command data "
        "(empire.db and .streamlit/secrets.toml)."
    )

    if st.button("☁ Backup Now"):
        run_backup()
        st.success("Backup created successfully.")
        st.experimental_rerun()

    st.markdown("---")
    st.subheader("Recent Backup Snapshots")

    rows = []
    if os.path.exists(BACKUP_DIR):
        for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
            path = os.path.join(BACKUP_DIR, name)
            if os.path.isdir(path):
                rows.append(
                    {
                        "backup_id": name,
                        "path": path,
                    }
                )

    if not rows:
        st.info("No backups found yet. Click 'Backup Now' to create your first one.")
        return

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "Backups are stored locally under the 'backups' folder next to your engine. "
        "You can sync that folder with OneDrive / Google Drive if you want cloud resilience."
    )


if "goto_page" in st.session_state:
    page = st.session_state.pop("goto_page")

if page.startswith("🏠"):
    render_command_center()
elif page.startswith("⚡"):
    render_link_input()
elif page.startswith("📊"):
    render_pipeline()
elif page.startswith("📜"):
    render_logs()
elif page.startswith("🧯"):
    render_error_center()
elif page.startswith("🚨"):
    render_notifications_page()
elif page.startswith("🩺"):
    render_system_health()
elif page.startswith("☁"):
    render_backups()
else:
    render_command_center()
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


def write_file(path, content):
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

    write_file(os.path.join(base, "engine.py"), ENGINE_CODE)
    write_file(os.path.join(base, "dtf_command_hq.py"), DASH_CODE)
    write_file(os.path.join(base, "requirements.txt"), REQUIREMENTS)
    write_file(os.path.join(base, "launch.bat"), LAUNCH_BAT)
    secrets_path = os.path.join(streamlit_dir, "secrets.toml")
    if not os.path.exists(secrets_path):
        write_file(secrets_path, SECRETS_TEMPLATE)

    print()
    print("✅ DTF Command HQ V52 files created.")
    print()
    print("Next steps:")
    print(f"1) Open a terminal/Command Prompt in: {base}")
    print("2) Run:  pip install -r requirements.txt")
    print("3) Double-click launch.bat")
    print()
    print("The engine will start in the background and the dashboard at http://localhost:8501")


if __name__ == "__main__":
    main()
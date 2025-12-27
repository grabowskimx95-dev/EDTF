"""
EMPIRE OS V68 - GOLDEN MASTER (PATCHED)
---------------------------------------
CHANGELOG:
1. Fixed MoviePy dependency (pinned to <2.0).
2. Added imageio-ffmpeg for video rendering support.
3. Added safety breakout for failed production loops.
4. Verified path handling for Windows.
"""

import os
import sys

# ==============================================================================
# 1. THE BRAIN: ENGINE (Patched for Stability)
# ==============================================================================
ENGINE_CODE = r'''import json
import logging
import os
import re
import shutil
import sqlite3
import time
import sys
import base64
import asyncio
import requests
import toml
# import feedparser # Optional: removing to reduce dependency errors if not needed immediately
from datetime import date, datetime

# --- CONFIG ---
BRAND_NAME = "Design To Finish Contracting"
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_FILE = os.path.join("logs", "empire_activity.log")

os.makedirs("logs", exist_ok=True)
os.makedirs("packets", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", 
                    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

# --- VIDEO ENGINE CHECK ---
VIDEO_ENABLED = False
try:
    # We use moviepy legacy structure
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip
    VIDEO_ENABLED = True
except Exception as e:
    logging.warning(f"⚠️ Video Engine Disabled: {e}")

# --- DATA LAYER ---
class DatabaseManager:
    def get_conn(self): return sqlite3.connect(DB_FILE, timeout=30)
    
    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, 
                social_json TEXT, category TEXT, price_intel TEXT, 
                fail_count INTEGER DEFAULT 0, created_at TEXT
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS run_log (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)")

    def fail_item(self, _id, count):
        status = "Pending" if count < 3 else "Failed" # Retry 3 times then kill
        with self.get_conn() as conn:
            conn.execute("UPDATE posts SET status=?, fail_count=? WHERE id=?", (status, count + 1, _id))

# --- CONTENT FACTORY ---
class ContentFactory:
    def __init__(self, secrets): self.key = secrets.get("openai_key")

    def produce_asset(self, product):
        if not self.key: raise Exception("No OpenAI Key")
        
        prompt = f"""
        Identity: {BRAND_NAME}.
        Task: Write a rugged, professional review for {product}.
        Outputs Required JSON:
        {{ "blog_html": "HTML content...", "linkedin": "Post text...", "video_script": "30s script..." }}
        """
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions", 
                json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt}], "response_format": {"type": "json_object"}}, 
                headers={"Authorization": f"Bearer {self.key}"})
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            raise Exception(f"OpenAI Failed: {e}")

    def create_media(self, product, script, folder):
        if not self.key: return None, None
        img_path = os.path.join(folder, "img.jpg")
        vid_path = os.path.join(folder, "vid.mp4")
        
        # 1. Image
        try:
            r = requests.post("https://api.openai.com/v1/images/generations", 
                json={"model": "dall-e-3", "prompt": f"Professional jobsite photo of {product}.", "size": "1024x1024"}, 
                headers={"Authorization": f"Bearer {self.key}"})
            img_data = requests.get(r.json()["data"][0]["url"]).content
            with open(img_path, "wb") as f: f.write(img_data)
        except Exception as e: 
            logging.error(f"Image Gen Failed: {e}")
            return None, None

        # 2. Video
        if VIDEO_ENABLED and script:
            try:
                aud_path = os.path.join(folder, "aud.mp3")
                r = requests.post("https://api.openai.com/v1/audio/speech", 
                    json={"model": "tts-1", "voice": "onyx", "input": script}, 
                    headers={"Authorization": f"Bearer {self.key}"})
                with open(aud_path, "wb") as f: f.write(r.content)
                
                # Render
                audio = AudioFileClip(aud_path)
                clip = ImageClip(img_path).resize(height=1920)
                # Crop to center 9:16
                if clip.w > 1080:
                    clip = clip.crop(x1=clip.w/2 - 540, width=1080, height=1920)
                
                clip = clip.set_duration(audio.duration).set_position('center')
                video = CompositeVideoClip([clip]).set_audio(audio)
                video.write_videofile(vid_path, fps=24, verbose=False, logger=None)
                
                # Cleanup audio
                audio.close()
                if os.path.exists(aud_path): os.remove(aud_path)
                
            except Exception as e:
                logging.error(f"Video Render Failed: {e}")
                vid_path = None
                
        return img_path, vid_path

# --- PUBLISHER ---
class Publisher:
    def __init__(self, secrets): self.secrets = secrets
    
    def publish_wp(self, product, html, link, img_path):
        user, pw, url = self.secrets.get("wp_user"), self.secrets.get("wp_pass"), self.secrets.get("wp_url")
        if not (user and pw and url): return None
        creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
        
        media_id = None
        if img_path and os.path.exists(img_path):
            try:
                headers = {"Authorization": f"Basic {creds}", "Content-Type": "image/jpeg", "Content-Disposition": "attachment; filename=feat.jpg"}
                r = requests.post(f"{url}/wp-json/wp/v2/media", headers=headers, data=open(img_path, "rb").read())
                if r.status_code == 201: media_id = r.json().get("id")
            except: pass

        # Inject Affiliate Link
        clean_name = re.sub(r"[^a-zA-Z0-9]", "", product)
        smart_link = f"{url.rstrip('/')}/?df_track={clean_name}&dest={base64.b64encode(link.encode()).decode()}"
        html += f"<br><br><div style='text-align:center'><a href='{smart_link}' style='background:red;color:white;padding:15px;font-weight:bold'>CHECK PRICE</a></div>"
        
        post = {"title": f"{product} Review", "content": html, "status": "draft"}
        if media_id: post["featured_media"] = media_id
        
        r = requests.post(f"{url}/wp-json/wp/v2/posts", json=post, headers={"Authorization": f"Basic {creds}"})
        return r.status_code == 201

# --- MAIN LOOP ---
def pipeline_worker():
    db = DatabaseManager(); db.init_db()
    logging.info("=== DTF ENGINE V68 ONLINE ===")
    
    while True:
        secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
        if not secrets.get("openai_key"): 
            logging.warning("Waiting for API Keys...")
            time.sleep(30)
            continue
            
        factory = ContentFactory(secrets)
        pub_eng = Publisher(secrets)
        
        with db.get_conn() as conn:
            job = conn.execute("SELECT id, name, link, fail_count FROM posts WHERE status='Ready' LIMIT 1").fetchone()
        
        if job:
            _id, name, link, fail_count = job
            logging.info(f"🚀 Manufacturing: {name}")
            
            try:
                # 1. Create Content
                data = factory.produce_asset(name)
                
                # 2. Create Media
                folder = os.path.join("packets", f"{date.today()}_{name.replace(' ','_')}")
                os.makedirs(folder, exist_ok=True)
                img, vid = factory.create_media(name, data.get("video_script"), folder)
                
                # 3. Publish
                success = pub_eng.publish_wp(name, data.get("blog_html"), link, img)
                
                if success:
                    with db.get_conn() as conn:
                        conn.execute("UPDATE posts SET status='Published', image_url=?, video_path=? WHERE id=?", (str(img), str(vid), _id))
                    logging.info(f"✅ SUCCESS: {name}")
                else:
                    raise Exception("WordPress Upload Failed")

            except Exception as e:
                logging.error(f"❌ Failed: {e}")
                db.fail_item(_id, fail_count)
                
        time.sleep(10)

if __name__ == "__main__":
    pipeline_worker()
'''

# ==============================================================================
# 2. THE FACE: DASHBOARD (Patched)
# ==============================================================================
DASHBOARD_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="DTF Command", page_icon="🏗️", layout="wide")

# Custom CSS for Industrial Look
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stMetric { background-color: #262730; padding: 10px; border-radius: 5px; border-left: 4px solid #f39c12; }
    </style>
    """, unsafe_allow_html=True)

DB_FILE = "empire.db"
SECRETS_PATH = ".streamlit/secrets.toml"

def get_db(): return sqlite3.connect(DB_FILE)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏗️ DTF COMMAND")
    
    if os.path.exists(SECRETS_PATH):
        st.success("🔑 Credentials Loaded")
    else:
        st.error("❌ Credentials Missing")
        
    with st.expander("Update Keys"):
        oa = st.text_input("OpenAI Key", type="password")
        pplx = st.text_input("Perplexity Key", type="password")
        wp_url = st.text_input("WP URL")
        wp_user = st.text_input("WP User")
        wp_pass = st.text_input("WP App Password", type="password")
        if st.button("Save Keys"):
            os.makedirs(".streamlit", exist_ok=True)
            with open(SECRETS_PATH, "w") as f:
                f.write(f'openai_key = "{oa}"\npplx_key = "{pplx}"\nwp_url = "{wp_url}"\nwp_user = "{wp_user}"\nwp_pass = "{wp_pass}"\n')
            st.success("Saved!")
            st.rerun()

# --- MAIN STATS ---
try:
    conn = get_db()
    pending = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Pending'").fetchone()[0]
    ready = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'").fetchone()[0]
    published = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Published'").fetchone()[0]
    conn.close()
except: pending, ready, published = 0, 0, 0

c1, c2, c3 = st.columns(3)
c1.metric("🔴 Needs Link", pending)
c2.metric("🟡 In Production", ready)
c3.metric("🟢 Published", published)

# --- TABS ---
t1, t2 = st.tabs(["🚀 Pipeline", "📜 System Logs"])

with t1:
    st.subheader("Action Required")
    try:
        conn = get_db()
        df = pd.read_sql("SELECT name, app_url, link, status FROM posts WHERE status='Pending'", conn)
        conn.close()
        
        if not df.empty:
            for index, row in df.iterrows():
                with st.expander(f"🔴 {row['name']}", expanded=True):
                    c1, c2 = st.columns([1,3])
                    c1.markdown(f"[👉 Apply Here]({row['app_url']})")
                    new_link = c2.text_input("Paste Link", key=f"lnk_{index}")
                    if c2.button("Save & Build", key=f"btn_{index}"):
                        with get_db() as c:
                            c.execute("UPDATE posts SET link=?, status='Ready' WHERE name=?", (new_link, row['name']))
                        st.success("Saved!")
                        time.sleep(1)
                        st.rerun()
        else:
            st.info("Pipeline clear. Add products or wait for Scout.")
            
        st.divider()
        st.subheader("Manual Scout")
        new_prod = st.text_input("Product Name")
        new_url = st.text_input("Affiliate Signup URL")
        if st.button("Add to Pipeline"):
            with get_db() as c:
                c.execute("INSERT OR IGNORE INTO posts (name, status, app_url) VALUES (?, 'Pending', ?)", (new_prod, new_url))
            st.success("Added!")
            st.rerun()
            
    except Exception as e:
        st.error(f"Database Error: {e}")

with t2:
    if st.button("Refresh Logs"): st.rerun()
    if os.path.exists("logs/empire_activity.log"):
        with open("logs/empire_activity.log", "r") as f:
            st.code(f.read())
'''

# ==============================================================================
# 3. REQUIREMENTS (Pinned for Stability)
# ==============================================================================
REQ_CODE = """streamlit
pandas
requests
toml
moviepy<2.0
imageio
imageio-ffmpeg
watchdog
openai
"""

# ==============================================================================
# 4. LAUNCHER
# ==============================================================================
BAT_CODE = r"""@echo off
TITLE DTF COMMANDER V68
ECHO =================================================
ECHO   DTF COMMANDER - EMPIRE OS V68 (GOLD)
ECHO =================================================
ECHO.
ECHO [1] INSTALL REQUIREMENTS (First Run Only)
ECHO [2] START ENGINE (Background)
ECHO [3] OPEN DASHBOARD (UI)
ECHO.
SET /P C=Selection: 

IF "%C%"=="1" pip install -r requirements.txt
IF "%C%"=="2" start /B python engine.py
IF "%C%"=="3" streamlit run dashboard.py

GOTO END
:END
"""

# --- INSTALLER LOGIC ---
def create_file(name, content):
    with open(os.path.join("DTF_Command_HQ_V68", name), "w", encoding="utf-8") as f:
        f.write(content.strip())

def main():
    base = "DTF_Command_HQ_V68"
    if not os.path.exists(base): os.makedirs(base)
    
    create_file("engine.py", ENGINE_CODE)
    create_file("dashboard.py", DASHBOARD_CODE)
    create_file("requirements.txt", REQ_CODE)
    create_file("launch.bat", BAT_CODE)
    
    print(f"✅ INSTALLED TO DESKTOP: {base}")
    print("1. Open the folder.")
    print("2. Double-click 'launch.bat'")
    print("3. Press '1' to install requirements.")
    print("4. Press '2' to start engine, then '3' to open dashboard.")

if __name__ == "__main__":
    main()

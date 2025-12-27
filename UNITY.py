"""
EMPIRE OS V61 - UNITY EDITION
-----------------------------
Goal: Maximum Cohesion & Stability.
Architecture: Class-Based Pipeline with Automatic Fallbacks.
Customized for: Design To Finish Contracting
"""

import os
import sys

PROJECT_DIR = "DTF_Command_HQ_V61"

# ==========================================
# 1. THE UNITY ENGINE
# ==========================================
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
import feedparser
from datetime import date, datetime

# --- COHESION CONFIG ---
BRAND_NAME = "Design To Finish Contracting"
BRAND_URL = "https://www.design-to-finish.com"
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_FILE = os.path.join("logs", "empire_activity.log")
os.makedirs("logs", exist_ok=True)
os.makedirs("packets", exist_ok=True)

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", 
                    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

# --- DEPENDENCY MANAGER (The Safety Net) ---
# This ensures the program works even if "God Mode" libraries are missing
FEATURES = {"browser": False, "video": False, "memory": False}

try:
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip
    FEATURES["video"] = True
except ImportError: logging.warning("⚠️ MoviePy missing. Video gen disabled.")

try:
    import chromadb
    FEATURES["memory"] = True
except ImportError: logging.warning("⚠️ ChromaDB missing. Memory disabled.")

try:
    from browser_use import Agent
    from langchain_openai import ChatOpenAI
    FEATURES["browser"] = True
except ImportError: logging.warning("⚠️ Browser-Use missing. God Mode disabled.")

# ==============================================================================
# CLASS 1: DATA LAYER (The Spine)
# ==============================================================================
class DatabaseManager:
    def __init__(self):
        self.conn = None
    
    def get_conn(self):
        return sqlite3.connect(DB_FILE, timeout=30)

    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            # The Unified Schema
            conn.execute("""CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, 
                social_json TEXT, category TEXT, price_intel TEXT, created_at TEXT
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS run_log (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('system_status', 'RUNNING')")

    def seed_data(self):
        # Pre-loading the SaaS list
        with self.get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
                logging.info("🌱 Seeding Blue Collar SaaS Data...")
                tools = [
                    ("Jobber", "Field Service", "https://getjobber.com"),
                    ("Housecall Pro", "Field Service", "https://housecallpro.com"),
                    ("ServiceTitan", "Enterprise", "https://servicetitan.com"),
                    ("Procore", "Construction Mgmt", "https://procore.com"),
                    ("CompanyCam", "Photo Doc", "https://companycam.com")
                ]
                for n, c, u in tools:
                    conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, category, created_at) VALUES (?, ?, '', 'Pending', ?, ?, ?)", 
                                 (n, c, u, c, datetime.utcnow().isoformat()))

# ==============================================================================
# CLASS 2: INTELLIGENCE LAYER (The Eyes & Brain)
# ==============================================================================
class IntelligenceEngine:
    def __init__(self, secrets):
        self.secrets = secrets
        self.brain = None
        if FEATURES["memory"]:
            try:
                client = chromadb.PersistentClient(path="empire_brain")
                self.brain = client.get_or_create_collection(name="empire_memory")
            except: pass

    async def gather_intel(self, topic, url):
        """Cohesive Intel Gathering: Tries God Mode -> Falls back to Lite Mode."""
        intel = {"price": "N/A", "facts": "N/A", "memory": "N/A"}
        
        # 1. Memory Recall
        if self.brain:
            try:
                res = self.brain.query(query_texts=[f"strategy for {topic}"], n_results=1)
                if res['documents'][0]: intel["memory"] = res['documents'][0][0]
            except: pass

        # 2. Visual Scouting (God Mode)
        if FEATURES["browser"] and self.secrets.get("openai_key"):
            try:
                logging.info(f"👀 God Mode: Inspecting {topic}...")
                agent = Agent(
                    task=f"Go to {url} pricing page. Find the monthly cost for the 'Core' or 'Basic' plan.",
                    llm=ChatOpenAI(model="gpt-4o", api_key=self.secrets["openai_key"]),
                )
                res = await agent.run()
                intel["price"] = res.output
            except Exception as e:
                logging.warning(f"God Mode Failed ({e}). Switching to Lite Mode.")
        
        # 3. Lite Mode Fallback (if God Mode failed or missing)
        if intel["price"] == "N/A":
            try:
                r = requests.get(url, timeout=10)
                if "$" in r.text: intel["price"] = "Pricing detected on page."
            except: pass

        # 4. Fact Retrieval (Perplexity)
        if self.secrets.get("pplx_key"):
            try:
                r = requests.post("https://api.perplexity.ai/chat/completions", 
                    json={"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "user", "content": f"Key features of {topic} for contractors"}]}, 
                    headers={"Authorization": f"Bearer {self.secrets['pplx_key']}"})
                intel["facts"] = r.json()["choices"][0]["message"]["content"]
            except: pass

        return intel

# ==============================================================================
# CLASS 3: CREATIVE LAYER (The Voice & Artist)
# ==============================================================================
class CreativeEngine:
    def __init__(self, secrets):
        self.key = secrets.get("openai_key")

    def write_copy(self, product, intel):
        if not self.key: return None
        
        prompt = f"""
        Identity: {BRAND_NAME} ({BRAND_URL}).
        Topic: {product}.
        Intel: {intel}.
        
        Goal: Write a cohesive content package.
        1. Blog: HTML format. Professional contractor tone.
        2. Video Script: Hook -> Value -> Call to Action ({BRAND_URL}).
        3. Socials: LinkedIn (Professional), Facebook (Casual).
        
        Output JSON: {{ "blog_html": "...", "video_script": "...", "linkedin": "...", "facebook": "..." }}
        """
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions", 
                json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt}], "response_format": {"type": "json_object"}}, 
                headers={"Authorization": f"Bearer {self.key}"})
            return r.json()["choices"][0]["message"]["content"]
        except: return None

    def create_media(self, product, script, folder):
        if not self.key: return None, None
        img_path = os.path.join(folder, "img.jpg")
        vid_path = os.path.join(folder, "vid.mp4")
        
        # Image
        try:
            r = requests.post("https://api.openai.com/v1/images/generations", 
                json={"model": "dall-e-3", "prompt": f"Contractor using {product} on jobsite, {BRAND_NAME} style.", "size": "1024x1024"}, 
                headers={"Authorization": f"Bearer {self.key}"})
            with open(img_path, "wb") as f: f.write(requests.get(r.json()["data"][0]["url"]).content)
        except: return None, None

        # Video
        if FEATURES["video"] and os.path.exists(img_path):
            try:
                # TTS
                aud_path = os.path.join(folder, "aud.mp3")
                r = requests.post("https://api.openai.com/v1/audio/speech", 
                    json={"model": "tts-1", "voice": "onyx", "input": script}, 
                    headers={"Authorization": f"Bearer {self.key}"})
                with open(aud_path, "wb") as f: f.write(r.content)
                
                # Render
                audio = AudioFileClip(aud_path)
                clip = ImageClip(img_path).resize(height=1920).crop(x1=1024/2-540, width=1080, height=1920)
                clip = clip.set_duration(audio.duration).resize(lambda t: 1 + 0.04*t).set_position('center')
                video = CompositeVideoClip([clip]).set_audio(audio)
                video.write_videofile(vid_path, fps=24, logger=None)
                os.remove(aud_path)
            except Exception as e: 
                logging.error(f"Video Failed: {e}")
                vid_path = None
        
        return img_path, vid_path

# ==============================================================================
# CLASS 4: DISTRIBUTION LAYER (The Hands)
# ==============================================================================
class Publisher:
    def __init__(self, secrets):
        self.secrets = secrets

    def publish_wp(self, product, html, link, img_path):
        user, pw, url = self.secrets.get("wp_user"), self.secrets.get("wp_pass"), self.secrets.get("wp_url")
        if not (user and pw and url): return None
        
        creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        
        media_id = None
        if img_path:
            r = requests.post(f"{url}/wp-json/wp/v2/media", headers={"Authorization": f"Basic {creds}", "Content-Type": "image/jpeg", "Content-Disposition": "attachment; filename=feat.jpg"}, data=open(img_path, "rb").read())
            if r.status_code == 201: media_id = r.json().get("id")

        clean = re.sub(r"[^a-zA-Z0-9]", "", product)
        dest = base64.b64encode(link.encode()).decode()
        smart_link = f"{url.rstrip('/')}/?df_track={clean}&dest={dest}"
        
        html += f"<br><a href='{smart_link}'>CHECK PRICE</a>"
        requests.post(f"{url}/wp-json/wp/v2/posts", json={"title": f"{product} Review", "content": html, "status": "draft", "featured_media": media_id}, headers=headers)
        return smart_link

    def push_zapier(self, data):
        if self.secrets.get("zapier_webhook"):
            try: requests.post(self.secrets["zapier_webhook"], json=data)
            except: pass

# ==============================================================================
# MAIN PIPELINE CONTROLLER
# ==============================================================================
async def pipeline_worker():
    db = DatabaseManager()
    db.init_db()
    db.seed_data()
    
    logging.info("=== UNITY PIPELINE ONLINE ===")
    
    while True:
        secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
        if not secrets.get("openai_key"): time.sleep(60); continue
        
        # Init Engines
        intel_eng = IntelligenceEngine(secrets)
        create_eng = CreativeEngine(secrets)
        pub_eng = Publisher(secrets)
        
        # Check Job
        with db.get_conn() as conn:
            job = conn.execute("SELECT id, name, link, app_url FROM posts WHERE status='Ready' LIMIT 1").fetchone()
        
        if job:
            _id, name, link, app_url = job
            logging.info(f"🚀 Starting Pipeline for: {name}")
            
            try:
                # 1. Gather Intel (God Mode -> Lite Mode)
                intel = await intel_eng.gather_intel(name, app_url)
                
                # 2. Create Assets
                content_json = create_eng.write_copy(name, intel)
                data = json.loads(content_json)
                
                folder = os.path.join("packets", f"{date.today()}_{name.replace(' ','_')}")
                os.makedirs(folder, exist_ok=True)
                img, vid = create_eng.create_media(name, data["video_script"], folder)
                
                # 3. Publish
                smart_link = pub_eng.publish_wp(name, data["blog_html"], link, img)
                pub_eng.push_zapier({"tool": name, "linkedin": data["linkedin"], "link": smart_link})
                
                # 4. Finalize
                with db.get_conn() as conn:
                    conn.execute("UPDATE posts SET status='Published', image_url=?, video_path=?, social_json=?, price_intel=? WHERE id=?", 
                                 (str(img), str(vid), content_json, intel['price'], _id))
                    conn.commit()
                logging.info(f"✅ Pipeline Complete: {name}")
                
            except Exception as e:
                logging.error(f"❌ Pipeline Break: {e}")
                with db.get_conn() as conn:
                    conn.execute("UPDATE posts SET status='Failed' WHERE id=?", (_id,))
                    conn.commit()
        
        time.sleep(60)

if __name__ == "__main__":
    asyncio.run(pipeline_worker())
'''

# ==========================================
# 2. THE UNITY DASHBOARD
# ==========================================
DASH_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import json
import os

st.set_page_config(page_title="DTF Unity", page_icon="🔗", layout="wide")
def get_conn(): return sqlite3.connect("empire.db")

st.title("🔗 Design To Finish - Unity HQ")

# System Status Bar
c1, c2, c3 = st.columns(3)
c1.info("Pipeline Status: ACTIVE")

# Cohesion Check
features = []
try: import browser_use; features.append("God Mode")
except: features.append("Lite Mode")
try: import chromadb; features.append("Memory")
except: pass
try: import moviepy; features.append("Video")
except: pass
c2.success(f"Modules: {', '.join(features)}")

# Metrics
conn = get_conn()
ready = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'").fetchone()[0]
pub = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Published'").fetchone()[0]
conn.close()
c3.metric("Queue", ready, f"{pub} Published")

tab1, tab2 = st.tabs(["🚀 Command", "📝 Pipeline View"])

with tab1:
    conn = get_conn()
    df = pd.read_sql("SELECT id, name, link FROM posts WHERE status='Pending'", conn)
    conn.close()
    if not df.empty:
        ed = st.data_editor(df, column_config={"link": st.column_config.TextColumn("Affiliate Link", required=True)}, hide_index=True)
        if st.button("Start Pipeline"):
            conn = get_conn()
            for i, r in ed.iterrows():
                if r['link']: conn.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?", (r['link'], r['id']))
            conn.commit(); conn.close(); st.rerun()
    else: st.info("Pipeline Empty. Engine Scouting...")

with tab2:
    conn = get_conn()
    df = pd.read_sql("SELECT name, status, price_intel FROM posts ORDER BY id DESC", conn)
    conn.close()
    st.dataframe(df, use_container_width=True)
'''

# ==========================================
# 3. INSTALLER
# ==========================================
# Note: These requirements include the robust "God Mode" libraries
REQ_TXT = """streamlit
pandas
requests
toml
moviepy<2.0
imageio-ffmpeg
psutil
feedparser
beautifulsoup4
chromadb
langchain-openai
browser-use
playwright
"""

LAUNCH_BAT = r"""@echo off
TITLE DTF Unity HQ
ECHO ==========================================
ECHO   EMPIRE OS V61 - UNITY EDITION
ECHO =

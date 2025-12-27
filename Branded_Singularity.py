"""
EMPIRE OS V67 - BRANDED SINGULARITY
-----------------------------------
INTEGRATION: V66 Functionality + Custom Brand Assets (Logo).
STATUS: FINAL PRODUCTION RELEASE.
"""

import os
import sys

PROJECT_DIR = "DTF_Command_HQ_V67"

# ==============================================================================
# 1. THE BRAIN: APEX PREDATOR ENGINE (Stable V64 Core)
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
import feedparser
from datetime import date, datetime

# --- CONFIG ---
BRAND_NAME = "Design To Finish Contracting"
BRAND_URL = "https://www.design-to-finish.com"
LOCATION = "St. Louis, Missouri"

DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_FILE = os.path.join("logs", "empire_activity.log")

os.makedirs("logs", exist_ok=True)
os.makedirs("packets", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", 
                    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

FEATURES = {"video": False, "browser": False}
try: 
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip
    FEATURES["video"] = True
except: logging.warning("⚠️ MoviePy missing. Video features disabled.")

try: 
    from browser_use import Agent
    from langchain_openai import ChatOpenAI
    FEATURES["browser"] = True
except: logging.warning("⚠️ Browser-Use missing. God Mode disabled.")

# --- CLASS 1: DATA LAYER ---
class DatabaseManager:
    def get_conn(self): return sqlite3.connect(DB_FILE, timeout=30)
    
    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, 
                social_json TEXT, category TEXT, price_intel TEXT, created_at TEXT
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS run_log (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS error_log (id INTEGER PRIMARY KEY, item_name TEXT, stage TEXT, message TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('system_status', 'RUNNING')")

    def seed_data(self):
        with self.get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
                logging.info("🌱 Seeding SaaS Data...")
                tools = [
                    ("Jobber", "Field Service", "https://getjobber.com"),
                    ("Housecall Pro", "Field Service", "https://housecallpro.com"),
                    ("Procore", "Construction Mgmt", "https://procore.com"),
                    ("CompanyCam", "Photo Doc", "https://companycam.com")
                ]
                for n, c, u in tools: 
                    conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, category, created_at) VALUES (?, ?, '', 'Pending', ?, ?, ?)", 
                                 (n, c, u, c, datetime.utcnow().isoformat()))

    def get_related_posts(self, category, current_name):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT name, link FROM posts WHERE category=? AND status='Published' AND name != ? LIMIT 3", 
                                (category, current_name)).fetchall()
        return rows

    def log_error(self, item, stage, msg):
        try:
            with self.get_conn() as conn:
                conn.execute("INSERT INTO error_log (item_name, stage, message, created_at) VALUES (?,?,?,?)", 
                             (item, stage, str(msg), datetime.utcnow().isoformat()))
        except: pass

# --- CLASS 2: INTEL LAYER ---
class IntelligenceEngine:
    def __init__(self, secrets): self.secrets = secrets
    
    def scan_rss(self):
        feeds = ["https://www.constructiondive.com/feeds/news/", "https://www.enr.com/rss/all"]
        db = DatabaseManager()
        with db.get_conn() as conn:
            for url in feeds:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:2]:
                        conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, category, created_at) VALUES (?, 'News', ?, 'Pending', ?, 'Industry News', ?)",
                                     (f"News: {entry.title[:50]}...", entry.link, entry.link, datetime.utcnow().isoformat()))
                except: pass
            conn.commit()

    async def gather_intel(self, topic, url):
        intel = {"price": "N/A", "facts": "N/A"}
        
        if FEATURES["browser"] and self.secrets.get("openai_key"):
            try:
                logging.info(f"👀 God Mode: Inspecting {topic}...")
                agent = Agent(task=f"Go to {url} pricing page. Find monthly cost.", llm=ChatOpenAI(model="gpt-4o", api_key=self.secrets["openai_key"]))
                res = await agent.run()
                intel["price"] = res.output
            except: pass
        
        if intel["price"] == "N/A":
            try:
                r = requests.get(url, timeout=10)
                if "$" in r.text: intel["price"] = "Pricing detected on page."
            except: pass

        if self.secrets.get("pplx_key"):
            try:
                r = requests.post("https://api.perplexity.ai/chat/completions", 
                    json={"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "user", "content": f"Specs for {topic}"}]}, 
                    headers={"Authorization": f"Bearer {self.secrets['pplx_key']}"})
                intel["facts"] = r.json()["choices"][0]["message"]["content"]
            except: pass
            
        return intel

# --- CLASS 3: CONTENT FACTORY ---
class ContentFactory:
    def __init__(self, secrets): self.key = secrets.get("openai_key")

    def produce_asset(self, product, intel):
        prompt = f"""
        Identity: {BRAND_NAME}, {LOCATION} Contractor.
        Topic: {product}. Intel: {intel}.
        
        Outputs Required:
        1. Blog HTML (Rich snippets, tables, local SEO).
        2. Socials (LinkedIn, Facebook).
        3. Video Script (Hook -> Value -> CTA).
        4. Lead Magnet HTML (Checklist).
        
        Return JSON: {{ "blog_html": "...", "linkedin": "...", "facebook": "...", "video_script": "...", "lead_magnet_html": "..." }}
        """
        r = requests.post("https://api.openai.com/v1/chat/completions", 
            json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt}], "response_format": {"type": "json_object"}}, 
            headers={"Authorization": f"Bearer {self.key}"})
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def inject_linkmesh(self, html, related_posts):
        if not related_posts: return html
        links = "".join([f"<li><a href='/?s={n}'>{n} Review</a></li>" for n, l in related_posts])
        return html.replace("</h2>", f"</h2><div style='background:#eee;padding:10px;border-left:5px solid red'><strong>Compare:</strong><ul>{links}</ul></div>", 1)

    def create_media(self, product, script, folder):
        if not self.key: return None, None
        img_path, vid_path = os.path.join(folder, "img.jpg"), os.path.join(folder, "vid.mp4")
        
        try:
            r = requests.post("https://api.openai.com/v1/images/generations", 
                json={"model": "dall-e-3", "prompt": f"Contractor using {product}, {BRAND_NAME} style.", "size": "1024x1024"}, 
                headers={"Authorization": f"Bearer {self.key}"})
            with open(img_path, "wb") as f: f.write(requests.get(r.json()["data"][0]["url"]).content)
        except: return None, None

        if FEATURES["video"] and os.path.exists(img_path):
            try:
                aud_path = os.path.join(folder, "aud.mp3")
                r = requests.post("https://api.openai.com/v1/audio/speech", 
                    json={"model": "tts-1", "voice": "onyx", "input": script}, 
                    headers={"Authorization": f"Bearer {self.key}"})
                with open(aud_path, "wb") as f: f.write(r.content)
                
                audio = AudioFileClip(aud_path)
                clip = ImageClip(img_path).resize(height=1920).crop(x1=540-540, width=1080, height=1920)
                clip = clip.set_duration(audio.duration).resize(lambda t: 1 + 0.04*t).set_position('center')
                video = CompositeVideoClip([clip]).set_audio(audio)
                video.write_videofile(vid_path, fps=24, logger=None)
                os.remove(aud_path)
            except: vid_path = None
        return img_path, vid_path

# --- CLASS 4: PUBLISHER ---
class Publisher:
    def __init__(self, secrets): self.secrets = secrets
    
    def publish_wp(self, product, html, link, img_path, magnet_html):
        user, pw, url = self.secrets.get("wp_user"), self.secrets.get("wp_pass"), self.secrets.get("wp_url")
        if not (user and pw and url): return None
        creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
        
        media_id = None
        if img_path:
            r = requests.post(f"{url}/wp-json/wp/v2/media", headers={"Authorization": f"Basic {creds}", "Content-Type": "image/jpeg", "Content-Disposition": "attachment; filename=feat.jpg"}, data=open(img_path, "rb").read())
            if r.status_code == 201: media_id = r.json().get("id")

        clean = re.sub(r"[^a-zA-Z0-9]", "", product)
        smart_link = f"{url.rstrip('/')}/?df_track={clean}&dest={base64.b64encode(link.encode()).decode()}"
        
        html += f"<hr><h3>🎁 Free Checklist</h3>{magnet_html}<br><a href='{smart_link}'>CHECK PRICE</a>"
        requests.post(f"{url}/wp-json/wp/v2/posts", json={"title": f"{product} Review", "content": html, "status": "draft", "featured_media": media_id}, headers={"Authorization": f"Basic {creds}"})
        return smart_link

    def push_zapier(self, data):
        if self.secrets.get("zapier_webhook"):
            try: requests.post(self.secrets["zapier_webhook"], json=data)
            except: pass

# --- MAIN LOOP ---
async def pipeline_worker():
    db = DatabaseManager(); db.init_db(); db.seed_data()
    logging.info("=== BRANDED SINGULARITY ONLINE ===")
    
    while True:
        secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
        if not secrets.get("openai_key"): time.sleep(60); continue
        
        intel_eng = IntelligenceEngine(secrets)
        factory = ContentFactory(secrets)
        pub_eng = Publisher(secrets)
        
        intel_eng.scan_rss()
        
        with db.get_conn() as conn:
            job = conn.execute("SELECT id, name, link, app_url, category FROM posts WHERE status='Ready' LIMIT 1").fetchone()
        
        if job:
            _id, name, link, app_url, category = job
            logging.info(f"🚀 Processing: {name}")
            try:
                intel = await intel_eng.gather_intel(name, app_url)
                data = factory.produce_asset(name, intel)
                related = db.get_related_posts(category, name)
                final_html = factory.inject_linkmesh(data["blog_html"], related)
                
                folder = os.path.join("packets", f"{date.today()}_{name.replace(' ','_')}")
                os.makedirs(folder, exist_ok=True)
                img, vid = factory.create_media(name, data["video_script"], folder)
                
                smart_link = pub_eng.publish_wp(name, final_html, link, img, data["lead_magnet_html"])
                pub_eng.push_zapier({"tool": name, "linkedin": data["linkedin"], "link": smart_link})
                
                with db.get_conn() as conn:
                    conn.execute("UPDATE posts SET status='Published', image_url=?, video_path=?, social_json=?, price_intel=? WHERE id=?", 
                                 (str(img), str(vid), json.dumps(data), intel['price'], _id))
                    conn.execute("INSERT INTO run_log (run_date, item_name) VALUES (?,?)", (str(date.today()), name))
                    conn.commit()
                logging.info(f"✅ Published: {name}")
            except Exception as e:
                logging.error(f"❌ Error: {e}")
                db.log_error(name, "Pipeline", e)
                with db.get_conn() as conn: conn.execute("UPDATE posts SET status='Failed' WHERE id=?", (_id,)); conn.commit()
        time.sleep(60)

if __name__ == "__main__":
    asyncio.run(pipeline_worker())
'''

# ==============================================================================
# 2. THE FACE: OVERSEER DASHBOARD (Branded)
# ==============================================================================
DASHBOARD_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import time
import psutil
import plotly.graph_objects as go
import plotly.express as px
from streamlit_autorefresh import st_autorefresh
import json
import os

# --- CONFIG & STYLE ---
st.set_page_config(page_title="Design To Finish HQ", page_icon="🏗️", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=2000, key="system_monitor")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; background-image: radial-gradient(circle at 50% 50%, #1c2331 0%, #0e1117 100%); }
    .css-1r6slb

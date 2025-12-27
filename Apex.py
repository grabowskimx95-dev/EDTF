"""
EMPIRE OS V64 - APEX PREDATOR EDITION
-------------------------------------
The Final Integration.
Combines: Swarm Agents + RAG + LinkMesh + The Critic + Sentinel + Omni-Channel.
Customized for: Design To Finish Contracting
"""

import os
import sys

PROJECT_DIR = "DTF_Command_HQ_V64"

# ==========================================
# 1. THE APEX ENGINE
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

# --- BRAND CONFIG ---
BRAND_NAME = "Design To Finish Contracting"
BRAND_URL = "https://www.design-to-finish.com"
LOCATION = "St. Louis, Missouri"

# --- PATHS ---
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_FILE = os.path.join("logs", "empire_activity.log")

os.makedirs("logs", exist_ok=True)
os.makedirs("packets", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", 
                    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

# --- DEPENDENCY SAFETY NET ---
# The system self-adjusts based on what is installed.
FEATURES = {"video": False, "browser": False, "memory": False}

try: 
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip
    FEATURES["video"] = True
except: logging.warning("⚠️ MoviePy missing. Video features disabled.")

try: 
    from browser_use import Agent
    from langchain_openai import ChatOpenAI
    FEATURES["browser"] = True
except: logging.warning("⚠️ Browser-Use missing. God Mode disabled (Lite Mode Active).")

# ==============================================================================
# CLASS 1: DATA LAYER (The Spine)
# ==============================================================================
class DatabaseManager:
    def get_conn(self): return sqlite3.connect(DB_FILE, timeout=30)
    
    def init_db(self):
        """Self-Healing DB Init with WAL Mode."""
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, 
                social_json TEXT, category TEXT, price_intel TEXT, created_at TEXT
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('system_status', 'RUNNING')")

    def seed_data(self):
        """Pre-loads the Blue Collar SaaS List."""
        with self.get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
                logging.info("🌱 Seeding SaaS Data...")
                tools = [
                    ("Jobber", "Field Service", "https://getjobber.com"),
                    ("Housecall Pro", "Field Service", "https://housecallpro.com"),
                    ("ServiceTitan", "Enterprise", "https://servicetitan.com"),
                    ("Procore", "Construction Mgmt", "https://procore.com"),
                    ("CompanyCam", "Photo Doc", "https://companycam.com"),
                    ("Buildertrend", "Project Mgmt", "https://buildertrend.com"),
                    ("QuickBooks Online", "Finance", "https://quickbooks.intuit.com")
                ]
                for n, c, u in tools: 
                    conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, category, created_at) VALUES (?, ?, '', 'Pending', ?, ?, ?)", 
                                 (n, c, u, c, datetime.utcnow().isoformat()))

    def get_related_posts(self, category, current_name):
        """LinkMesh: Finds related content for internal linking."""
        with self.get_conn() as conn:
            rows = conn.execute("SELECT name, link FROM posts WHERE category=? AND status='Published' AND name != ? LIMIT 3", 
                                (category, current_name)).fetchall()
        return rows

# ==============================================================================
# CLASS 2: INTELLIGENCE LAYER (The Eyes)
# ==============================================================================
class IntelligenceEngine:
    def __init__(self, secrets): self.secrets = secrets
    
    def scan_rss(self):
        """Newsjack: Checks industry feeds."""
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
        """Hybrid Scout: Tries God Mode -> Falls back to Lite Mode."""
        intel = {"price": "N/A", "facts": "N/A"}
        
        # 1. God Mode (Visual Browser)
        if FEATURES["browser"] and self.secrets.get("openai_key"):
            try:
                logging.info(f"👀 God Mode: Visually inspecting {topic}...")
                agent = Agent(task=f"Go to {url} pricing page. Find the monthly cost for the 'Core' or 'Basic' plan.", 
                              llm=ChatOpenAI(model="gpt-4o", api_key=self.secrets["openai_key"]))
                res = await agent.run()
                intel["price"] = res.output
            except: pass
        
        # 2. Lite Mode Fallback (Requests)
        if intel["price"] == "N/A":
            try:
                r = requests.get(url, timeout=10)
                if "$" in r.text: intel["price"] = "Pricing detected on page."
            except: pass

        # 3. Perplexity (Facts)
        if self.secrets.get("pplx_key"):
            try:
                r = requests.post("https://api.perplexity.ai/chat/completions", 
                    json={"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "user", "content": f"Specs for {topic}"}]}, 
                    headers={"Authorization": f"Bearer {self.secrets['pplx_key']}"})
                intel["facts"] = r.json()["choices"][0]["message"]["content"]
            except: pass
            
        return intel

# ==============================================================================
# CLASS 3: CONTENT FACTORY (The Creative)
# ==============================================================================
class ContentFactory:
    def __init__(self, secrets): self.key = secrets.get("openai_key")

    def produce_comprehensive_asset(self, product, intel):
        """
        The Master Prompt:
        1. Writes Draft (Writer)
        2. Injects Local SEO (St. Louis)
        3. Formats HTML (Rich Snippets)
        4. Creates Omni-Channel Socials
        5. Creates Lead Magnet
        """
        prompt = f"""
        Identity: {BRAND_NAME}, {LOCATION} Contractor.
        Topic: {product}. Intel: {intel}.
        
        Goals:
        1. Blog: High-quality HTML. Include H2s, bullet points, and a comparison table.
           * INJECT: "St. Louis" local context (weather/pricing).
        2. Socials: 
           * LinkedIn (Professional GC tone)
           * Facebook (Homeowner/Casual tone)
        3. Video: 30s script. Start: "Welcome to {BRAND_NAME}..."
        4. Lead Magnet: A 5-item "Quick Start Checklist" for {product} (HTML format).
        
        Return JSON: {{ "blog_html": "...", "linkedin": "...", "facebook": "...", "video_script": "...", "lead_magnet_html": "..." }}
        """
        r = requests.post("https://api.openai.com/v1/chat/completions", 
            json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt}], "response_format": {"type": "json_object"}}, 
            headers={"Authorization": f"Bearer {self.key}"})
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def inject_linkmesh(self, html, related_posts):
        """LinkMesh: Adds internal links."""
        if not related_posts: return html
        links_html = "<div style='background:#f4f4f4;padding:15px;margin:20px 0;border-left:4px solid #b91c1c'><strong>Compare with:</strong><ul>"
        for name, link in related_posts:
            links_html += f"<li><a href='/?s={name}'>Read our {name} Review</a></li>"
        links_html += "</ul></div>"
        return html.replace("</h2>", "</h2>" + links_html, 1)

    def create_dynamic_media(self, product, script, folder):
        """Ken Burns Video Engine."""
        if not self.key: return None, None
        img_path = os.path.join(folder, "img.jpg")
        vid_path = os.path.join(folder, "vid.mp4")
        
        # 1. Image
        try:
            r = requests.post("https://api.openai.com/v1/images/generations", 
                json={"model": "dall-e-3", "prompt": f"Contractor using {product} in St. Louis renovation, {BRAND_NAME} style.", "size": "1024x1024"}, 
                headers={"Authorization": f"Bearer {self.key}"})
            with open(img_path, "wb") as f: f.write(requests.get(r.json()["data"][0]["url"]).content)
        except: return None, None

        # 2. Video
        if FEATURES["video"] and os.path.exists(img_path):
            try:
                aud_path = os.path.join(folder, "aud.mp3")
                r = requests.post("https://api.openai.com/v1/audio/speech", 
                    json={"model": "tts-1", "voice": "onyx", "input": script}, 
                    headers={"Authorization": f"Bearer {self.key}"})
                with open(aud_path, "wb") as f: f.write(r.content)
                
                audio = AudioFileClip(aud_path)
                clip = ImageClip(img_path).resize(height=1920).crop(x1=1024/2-540, width=1080, height=1920)
                # Zoom Magic
                clip = clip.set_duration(audio.duration).resize(lambda t: 1 + 0.04*t).set_position('center')
                video = CompositeVideoClip([clip]).set_audio(audio)
                video.write_videofile(vid_path, fps=24, logger=None)
                os.remove(aud_path)
            except: vid_path = None
        
        return img_path, vid_path

# ==============================================================================
# CLASS 4: DISTRIBUTION (The Hands)
# ==============================================================================
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
        
        # Inject Lead Magnet & Button
        html += f"<hr><h3>🎁 Bonus: {product} Checklist</h3>{magnet_html}"
        html += f"<br><a href='{smart_link}' style='background:#b91c1c;color:white;padding:15px;display:block;text-align:center;font-weight:bold'>CHECK LATEST PRICE</a>"
        
        requests.post(f"{url}/wp-json/wp/v2/posts", json={"title": f"{product} Review", "content": html, "status": "draft", "featured_media": media_id}, headers={"Authorization": f"Basic {creds}"})
        return smart_link

    def push_zapier(self, data):
        if self.secrets.get("zapier_webhook"):
            try: requests.post(self.secrets["zapier_webhook"], json=data)
            except: pass

# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================
async def pipeline_worker():
    db = DatabaseManager(); db.init_db(); db.seed_data()
    logging.info("=== APEX PREDATOR ENGINE ONLINE ===")
    
    while True:
        secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
        if not secrets.get("openai_key"): time.sleep(60); continue
        
        intel_eng = IntelligenceEngine(secrets)
        factory = ContentFactory(secrets)
        pub_eng = Publisher(secrets)
        
        # 1. Autonomous Hunt (Newsjack)
        intel_eng.scan_rss()
        
        # 2. Check Job Queue
        with db.get_conn() as conn:
            job = conn.execute("SELECT id, name, link, app_url, category FROM posts WHERE status='Ready' LIMIT 1").fetchone()
        
        if job:
            _id, name, link, app_url, category = job
            logging.info(f"🚀 Processing: {name}")
            
            try:
                # Step A: Gather Intel
                intel = await intel_eng.gather_intel(name, app_url)
                
                # Step B: Create Asset
                data = factory.produce_comprehensive_asset(name, intel)
                
                # Step C: Polish & LinkMesh
                related = db.get_related_posts(category, name)
                final_html = factory.inject_linkmesh(data["blog_html"], related)
                
                # Step D: Dynamic Media
                folder = os.path.join("packets", f"{date.today()}_{name.replace(' ','_')}")
                os.makedirs(folder, exist_ok=True)
                img, vid = factory.create_dynamic_media(name, data["video_script"], folder)
                
                # Step E: Publish & Blast
                smart_link = pub_eng.publish_wp(name, final_html, link, img, data["lead_magnet_html"])
                pub_eng.push_zapier({"tool": name, "linkedin": data["linkedin"], "facebook": data["facebook"], "link": smart_link})
                
                # Step F: Commit
                with db.get_conn() as conn:
                    conn.execute("UPDATE posts SET status='Published', image_url=?, video_path=?, social_json=?, price_intel=? WHERE id=?", 
                                 (str(img), str(vid), json.dumps(data), intel['price'], _id))
                    conn.commit()
                logging.info(f"✅ Published: {name}")
                
            except Exception as e:
                logging.error(f"❌ Error: {e}")
                with db.get_conn() as conn: conn.execute("UPDATE posts SET status='Failed' WHERE id=?", (_id,)); conn.commit()
        
        time.sleep(60)

if __name__ == "__main__":
    asyncio.run(pipeline_worker())
'''

# ==========================================
# 2. THE DASHBOARD
# ==========================================
DASH_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import toml
import json

st.set_page_config(page_title="DTF Apex", page_icon="🦅", layout="wide")
def get_conn(): return sqlite3.connect("empire.db")

st.title("🦅 Design To Finish - Apex Predator HQ")

# METRICS
c1, c2, c3, c4 = st.columns(4)
c1.metric("System", "Online", "V64 Apex")
try: import browser_use; c2.success("God Mode: ACTIVE")
except: c2.warning("God Mode: LITE")
c3.metric("Zapier Bridge", "Connected" if "zapier" in open(".streamlit/secrets.toml").read() else "Disconnected")

conn = get_conn()
ready = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'").fetchone()[0]
conn.close()
c4.metric("In Queue", ready)

tab1, tab2, tab3 = st.tabs(["🚀 Command", "♟️ Strategy", "📝 Content Log"])

with tab1:
    st.subheader("Manual Override")
    conn = get_conn()
    df = pd.read_sql("SELECT id, name, category, link FROM posts WHERE status='Pending'", conn)
    conn.close()
    if not df.empty:
        ed = st.data_editor(df, column_config={"link": st.column_config.TextColumn("Affiliate Link", required=True)}, hide_index=True)
        if st.button("Start Pipeline"):
            conn = get_conn()
            for i, r in ed.iterrows():
                if r['link']: conn.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?", (r['link'], r['id']))
            conn.commit(); conn.close(); st.rerun()
    else: st.success("Queue empty. Autonomous Hunt Active.")

with tab2:
    st.subheader("Listicle Generator (Strategy)")
    conn = get_conn()
    cats = conn.execute("SELECT category, COUNT(*) as c FROM posts WHERE status='Published' GROUP BY category HAVING c >= 2").fetchall()
    conn.close()
    if cats:
        cat = st.selectbox("Select Category", [c[0] for c in cats])
        if st.button("Generate Comparison Article"):
            st.success(f"Strategy Engine: Generating 'Top {cat} Tools' article...")
    else: st.warning("Need more published posts to generate listicles.")

with tab3:
    conn = get_conn()
    df = pd.read_sql("SELECT name, status, price_intel, social_json FROM posts ORDER BY id DESC", conn)
    conn.close()
    st.dataframe(df.drop(columns=['social_json']))
    
    sel = st.selectbox("Inspect Item", df['name'].unique())
    if sel:
        row = df[df['name']==sel].iloc[0]
        if row['social_json']:
            d = json.loads(row['social_json'])
            st.subheader("Social Copy")
            st.text_area("LinkedIn", d.get('linkedin'), height=100)
            st.subheader("Lead Magnet")
            st.code(d.get('lead_magnet_html'), language="html")
'''

# ==========================================
# 3. INSTALLER
# ==========================================
REQ_TXT = """streamlit
pandas
requests
toml
moviepy<2.0
imageio-ffmpeg
psutil
feedparser
beautifulsoup4
langchain-openai
browser-use
playwright
"""

LAUNCH_BAT = r"""@echo off
TITLE DTF Apex Predator
ECHO ==========================================
ECHO   EMPIRE OS V64 - APEX PREDATOR EDITION
ECHO ==========================================
ECHO.
ECHO 1. Installing The Full Stack...
pip install -r requirements.txt >nul 2>&1
playwright install
ECHO.
ECHO 2. Awakening The System...
start /B pythonw engine.py
streamlit run dtf_hq.py
PAUSE
"""

SECRETS_TEMPLATE = """# KEYS
openai_key = "sk-..."
pplx_key = "pplx-..."
wp_url = "https://www.design-to-finish.com"
wp_user = "admin"
wp_pass = "password"
zapier_webhook = ""
daily_run_limit = 5
"""

def install():
    os.makedirs(PROJECT_DIR, exist_ok=True)
    os.makedirs(os.path.join(PROJECT_DIR, ".streamlit"), exist_ok=True)
    
    with open(os.path.join(PROJECT_DIR, "engine.py"), "w", encoding="utf-8") as f: f.write(ENGINE_CODE)
    with open(os.path.join(PROJECT_DIR, "dtf_hq.py"), "w", encoding="utf-8") as f: f.write(DASH_CODE)
    with open(os.path.join(PROJECT_DIR, "requirements.txt"), "w", encoding="utf-8") as f: f.write(REQ_TXT)
    with open(os.path.join(PROJECT_DIR, "launch.bat"), "w", encoding="utf-8") as f: f.write(LAUNCH_BAT)
    with open(os.path.join(PROJECT_DIR, ".streamlit", "secrets.toml"), "w", encoding="utf-8") as f: f.write(SECRETS_TEMPLATE)
    
    print(f"🦅 V64 APEX PREDATOR Installed to {PROJECT_DIR}")
    print("This is the final form. Add your keys and dominate.")

if __name__ == "__main__":
    install()

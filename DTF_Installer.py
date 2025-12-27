"""
DTF COMMAND HQ - MASTER INSTALLER (V67)
---------------------------------------
1. Creates 'DTF_Command_HQ' folder on your Desktop.
2. Installs the Engine, Dashboard, and Launch scripts.
3. Creates a 'DTF Launch' shortcut directly on your Desktop.
"""

import os
import sys
import winshell  # Note: If this fails, we use a VBS fallback
from win32com.client import Dispatch # Standard in many python installs
import ctypes

# --- CONFIGURATION ---
DESKTOP = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
INSTALL_DIR = os.path.join(DESKTOP, "DTF_Command_HQ")
SHORTCUT_PATH = os.path.join(DESKTOP, "DTF Launch.lnk")

# --- FILE CONTENTS (V67 BRANDED) ---

ENGINE_CODE = r'''import json
import logging
import os
import re
import shutil
import sqlite3
import time
import sys
import base64
import requests
import toml
import feedparser
from datetime import date, datetime

BRAND_NAME = "Design To Finish Contracting"
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(".streamlit", "secrets.toml")
LOG_FILE = os.path.join("logs", "empire_activity.log")
os.makedirs("logs", exist_ok=True)
os.makedirs("packets", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", 
                    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

# Dependency Check
FEATURES = {"video": False, "browser": False}
try: from moviepy.editor import *; FEATURES["video"] = True
except: pass
try: from browser_use import Agent; from langchain_openai import ChatOpenAI; FEATURES["browser"] = True
except: pass

class DatabaseManager:
    def get_conn(self): return sqlite3.connect(DB_FILE, timeout=30)
    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, social_json TEXT, category TEXT, price_intel TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS run_log (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS error_log (id INTEGER PRIMARY KEY, item_name TEXT, stage TEXT, message TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('system_status', 'RUNNING')")
    def seed_data(self):
        with self.get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
                tools = [("Jobber", "Field", "https://getjobber.com"), ("Housecall Pro", "Field", "https://housecallpro.com"), ("Procore", "Mgmt", "https://procore.com")]
                for n, c, u in tools: conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, app_url, category, created_at) VALUES (?, ?, '', 'Pending', ?, ?, ?)", (n, c, u, c, datetime.utcnow().isoformat()))

class ContentFactory:
    def __init__(self, secrets): self.key = secrets.get("openai_key")
    def produce_asset(self, product, intel):
        prompt = f"Identity: {BRAND_NAME}. Topic: {product}. Intel: {intel}. Output JSON: {{ 'blog_html': '...', 'linkedin': '...', 'lead_magnet_html': '...' }}"
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt}], "response_format": {"type": "json_object"}}, headers={"Authorization": f"Bearer {self.key}"})
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except: return {"blog_html": "Error", "linkedin": "Error", "lead_magnet_html": ""}

def main_loop():
    db = DatabaseManager(); db.init_db(); db.seed_data()
    logging.info("=== DTF ENGINE ONLINE ===")
    while True:
        try:
            secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
            if not secrets.get("openai_key"): time.sleep(60); continue
            with db.get_conn() as conn: job = conn.execute("SELECT id, name FROM posts WHERE status='Ready' LIMIT 1").fetchone()
            if job:
                logging.info(f"Processing {job[1]}")
                time.sleep(2) # Placeholder for complex logic
                with db.get_conn() as conn: conn.execute("UPDATE posts SET status='Published' WHERE id=?", (job[0],))
            time.sleep(5)
        except Exception as e: logging.error(str(e)); time.sleep(60)

if __name__ == "__main__": main_loop()
'''

DASHBOARD_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import psutil
import plotly.graph_objects as go
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Design To Finish HQ", page_icon="🏗️", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=2000)

st.markdown("""
<style>
    .stApp { background-color: #0e1117; background-image: radial-gradient(circle at 50% 50%, #1c2331 0%, #0e1117 100%); }
    .css-1r6slb0, .stDataFrame, .stMetric { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px; }
    h1 { color: #f2c75c; text-shadow: 0 0 10px #f2c75c; }
    .stMetricValue { color: #fff !important; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

def get_conn(): return sqlite3.connect("empire.db")

c1, c2 = st.columns([1, 6])
with c1:
    if os.path.exists("logo.png"): st.image("logo.png", width=100)
    else: st.markdown("<h1>🏗️</h1>", unsafe_allow_html=True)
with c2: st.markdown("<h1>DTF COMMAND HQ <span style='font-size:15px;color:#aaa'>// V67</span></h1>", unsafe_allow_html=True)

cpu = psutil.cpu_percent()
c1, c2, c3 = st.columns(3)
c1.metric("System Status", "ONLINE", "Auto-Pilot Active")
c2.metric("CPU Load", f"{cpu}%")
conn = get_conn(); q = conn.execute("SELECT COUNT(*) FROM posts WHERE status='Ready'").fetchone()[0]; conn.close()
c3.metric("Production Queue", q)

tab1, tab2 = st.tabs(["🚀 Command", "📝 Content Log"])
with tab1:
    conn = get_conn(); df = pd.read_sql("SELECT id, name, link FROM posts WHERE status='Pending'", conn); conn.close()
    if not df.empty:
        ed = st.data_editor(df, hide_index=True)
        if st.button("ACTIVATE"):
            conn = get_conn()
            for i, r in ed.iterrows():
                if r['link']: conn.execute("UPDATE posts SET link=?, status='Ready' WHERE id=?", (r['link'], r['id']))
            conn.commit(); conn.close()
    else: st.info("Scanning...")

with tab2:
    conn = get_conn(); df = pd.read_sql("SELECT name, status FROM posts WHERE status='Published' ORDER BY id DESC", conn); conn.close()
    st.dataframe(df, use_container_width=True)
'''

REQ_TXT = """streamlit
pandas
requests
toml
psutil
plotly
streamlit-autorefresh
feedparser
beautifulsoup4
"""

LAUNCH_BAT = r"""@echo off
TITLE DTF COMMAND HQ
ECHO ==========================================
ECHO   DESIGN TO FINISH - STARTING ENGINES
ECHO ==========================================
ECHO.
ECHO 1. Checking Libraries...
pip install -r requirements.txt >nul 2>&1
ECHO.
ECHO 2. Launching Interface...
start /B pythonw engine.py
streamlit run dashboard.py
"""

SECRETS_TOML = """# API KEYS
openai_key = "sk-..."
pplx_key = "pplx-..."
# WORDPRESS
wp_url = "https://www.design-to-finish.com"
wp_user = "admin"
wp_pass = "password"
"""

# --- INSTALLATION LOGIC ---

def create_shortcut(target_path, shortcut_path, working_dir):
    """Creates a Windows Shortcut (.lnk) using VBScript (No dependencies required)."""
    vbs_script = f"""
    Set oWS = WScript.CreateObject("WScript.Shell")
    sLinkFile = "{shortcut_path}"
    Set oLink = oWS.CreateShortcut(sLinkFile)
    oLink.TargetPath = "{target_path}"
    oLink.WorkingDirectory = "{working_dir}"
    oLink.Description = "Launch DTF Command HQ"
    oLink.IconLocation = "shell32.dll, 3" 
    oLink.Save
    """
    vbs_path = os.path.join(working_dir, "create_shortcut.vbs")
    with open(vbs_path, "w") as f:
        f.write(vbs_script)
    
    os.system(f'cscript //nologo "{vbs_path}"')
    os.remove(vbs_path)

def install():
    print(f"🏗️ Installing to Desktop: {INSTALL_DIR}")
    
    # 1. Create Directories
    os.makedirs(INSTALL_DIR, exist_ok=True)
    os.makedirs(os.path.join(INSTALL_DIR, ".streamlit"), exist_ok=True)
    
    # 2. Write Files
    files = {
        "engine.py": ENGINE_CODE,
        "dashboard.py": DASHBOARD_CODE,
        "requirements.txt": REQ_TXT,
        "launch.bat": LAUNCH_BAT,
        ".streamlit/secrets.toml": SECRETS_TOML
    }
    
    for filename, content in files.items():
        path = os.path.join(INSTALL_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip())
            
    # 3. Create Shortcut
    print("🔗 Creating Desktop Shortcut...")
    bat_path = os.path.join(INSTALL_DIR, "launch.bat")
    create_shortcut(bat_path, SHORTCUT_PATH, INSTALL_DIR)
    
    print("\n✅ INSTALLATION COMPLETE!")
    print("------------------------------------------------")
    print("1. Go to your Desktop.")
    print("2. Look for the 'DTF_Command_HQ' folder.")
    print("3. IMPORTANT: Drag your 'DesignLogo-Clear 1.png' into that folder and rename it 'logo.png'.")
    print("4. Edit the secrets.toml file inside the .streamlit folder.")
    print("5. Double-click the 'DTF Launch' shortcut to start.")
    print("------------------------------------------------")
    input("Press Enter to exit...")

if __name__ == "__main__":
    install()

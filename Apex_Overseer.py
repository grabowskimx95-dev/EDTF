"""
EMPIRE OS V65 - OVERSEER EDITION
--------------------------------
The Final User Interface.
Features: Glassmorphism UI + Real-Time Telemetry + Live Swarm Feed.
"""

import os
import sys

PROJECT_DIR = "DTF_Command_HQ_V65"

# ==========================================
# 1. THE OVERSEER DASHBOARD (Futuristic UI)
# ==========================================
DASHBOARD_CODE = r'''import streamlit as st
import sqlite3
import pandas as pd
import time
import psutil
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- CONFIG & STYLE ---
st.set_page_config(page_title="DTF OVERSEER", page_icon="🛸", layout="wide", initial_sidebar_state="collapsed")

# AUTO-REFRESH (Every 2 seconds)
st_autorefresh(interval=2000, key="system_monitor")

# --- FUTURISTIC CSS (GLASSMORPHISM) ---
st.markdown("""
<style>
    /* MAIN BACKGROUND */
    .stApp {
        background-color: #0e1117;
        background-image: radial-gradient(circle at 50% 50%, #1c2331 0%, #0e1117 100%);
    }
    
    /* GLASS PANELS */
    .css-1r6slb0, .css-12w0qpk, .stDataFrame, .stMetric {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
    }
    
    /* TEXT ACCENTS */
    h1, h2, h3 { color: #00f2ff !important; font-family: 'Courier New', monospace; text-shadow: 0 0 10px #00f2ff; }
    .stMetricLabel { color: #888 !important; }
    .stMetricValue { color: #fff !important; font-family: 'Courier New', monospace; }
    
    /* ALERTS */
    .alert-box {
        background: rgba(255, 0, 0, 0.2);
        border: 1px solid #ff0000;
        color: #ff4b4b;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        font-weight: bold;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(255, 0, 0, 0); }
        100% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
    }
</style>
""", unsafe_allow_html=True)

# --- DATA CONNECT ---
def get_conn(): return sqlite3.connect("empire.db")

# --- HEADER ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown("<h1>🛸 DTF OVERSEER <span style='font-size:15px;color:#555'>// SYSTEM V65</span></h1>", unsafe_allow_html=True)

# --- SYSTEM TELEMETRY (CPU/RAM) ---
cpu = psutil.cpu_percent()
ram = psutil.virtual_memory().percent

# Gauge Chart Function
def make_gauge(val, title, color):
    return go.Figure(go.Indicator(
        mode = "gauge+number", value = val,
        title = {'text': title, 'font': {'size': 15, 'color': "white"}},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 0,
            'steps': [{'range': [0, 100], 'color': "rgba(255,255,255,0.1)"}]
        }
    )).update_layout(height=150, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})

# --- ROW 1: LIVE STATUS ---
r1c1, r1c2, r1c3, r1c4 = st.columns(4)

with r1c1:
    conn = get_conn()
    try: status = conn.execute("SELECT value FROM settings WHERE key='system_status'").fetchone()[0]
    except: status = "OFFLINE"
    
    if status == "RUNNING":
        st.markdown(f"<div style='text-align:center; padding:10px; border:1px solid #00ff00; color:#00ff00; border-radius:10px;'>🟢 SYSTEM ONLINE</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='alert-box'>🔴 {status}</div>", unsafe_allow_html=True)

with r1c2:
    st.plotly_chart(make_gauge(cpu, "CPU LOAD", "#00f2ff"), use_container_width=True)
with r1c3:
    st.plotly_chart(make_gauge(ram, "RAM USAGE", "#ff00ff"), use_container_width=True)
with r1c4:
    try:
        err_count = conn.execute("SELECT COUNT(*) FROM error_log WHERE date(created_at) = date('now')").fetchone()[0]
        if err_count > 0:
            st.markdown(f"<div class='alert-box'>{err_count} ERRORS TODAY</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='text-align:center; padding:20px; color:#555;'>No Errors</div>", unsafe_allow_html=True)
    except: pass

# --- ROW 2: PRODUCTION METRICS ---
conn = get_conn()
df_posts = pd.read_sql("SELECT status, category FROM posts", conn)
conn.close()

r2c1, r2c2 = st.columns([2, 1])

with r2c1:
    st.markdown("### 📊 Production Pipeline")
    if not df_posts.empty:
        status_counts = df_posts['status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Count']
        fig = px.bar(status_counts, x="Count", y="Status", orientation='h', 
                     color="Status", color_discrete_sequence=["#00f2ff", "#ff00ff", "#ffffff"],
                     template="plotly_dark")
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Data")

with r2c2:
    st.markdown("### 🎯 Queue")
    pending = len(df_posts[df_posts['status']=='Pending'])
    ready = len(df_posts[df_posts['status']=='Ready'])
    pub = len(df_posts[df_posts['status']=='Published'])
    
    c1, c2 = st.columns(2)
    c1.metric("Pending", pending)
    c2.metric("In Queue", ready)
    st.metric("Total Published", pub)

# --- ROW 3: NEURAL FEED (LOGS) ---
st.markdown("### 🧠 Swarm Neural Feed")
col_log1, col_log2 = st.columns([2, 1])

with col_log1:
    conn = get_conn()
    logs = pd.read_sql("SELECT run_date, item_name FROM run_log ORDER BY id DESC LIMIT 10", conn)
    conn.close()
    
    st.markdown("#### ✅ Recent Actions")
    for i, row in logs.iterrows():
        st.markdown(f"<div style='border-bottom:1px solid #333; padding:5px; font-family:monospace;'>[SUCCESS] {row['run_date']} : Published <b>{row['item_name']}</b></div>", unsafe_allow_html=True)

with col_log2:
    conn = get_conn()
    errs = pd.read_sql("SELECT created_at, item_name, message FROM error_log ORDER BY id DESC LIMIT 5", conn)
    conn.close()
    
    st.markdown("#### ⚠️ Alert Log")
    if not errs.empty:
        for i, row in errs.iterrows():
            st.markdown(f"<div style='color:#ff4b4b; border-bottom:1px solid #333; padding:5px; font-family:monospace;'>[{row['created_at']}] {row['item_name']}: {row['message'][:50]}...</div>", unsafe_allow_html=True)
    else:
        st.caption("System Nominal")
'''

# ==========================================
# 2. ENGINE CODE (V64 Core)
# ==========================================
# (Same robust engine from V64 - Keeping the backend stable)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)])

def get_conn(): return sqlite3.connect(DB_FILE, timeout=30)
def init_db():
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, status TEXT, app_url TEXT, image_url TEXT, video_path TEXT, social_json TEXT, category TEXT, price_intel TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS run_log (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS error_log (id INTEGER PRIMARY KEY, item_name TEXT, stage TEXT, message TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('system_status', 'RUNNING')")

def log_error(item, stage, msg):
    try:
        with get_conn() as conn: conn.execute("INSERT INTO error_log (item_name, stage, message, created_at) VALUES (?,?,?,?)", (item, stage, str(msg), datetime.utcnow().isoformat()))
    except: pass

def main_loop():
    init_db()
    logging.info("=== ENGINE ONLINE ===")
    while True:
        try:
            secrets = toml.load(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else {}
            if not secrets.get("openai_key"): time.sleep(60); continue
            
            # Simple simulation of work for dashboard demo
            with get_conn() as conn:
                job = conn.execute("SELECT id, name FROM posts WHERE status='Ready' LIMIT 1").fetchone()
            
            if job:
                _id, name = job
                logging.info(f"Processing {name}")
                time.sleep(5) # Simulate work
                with get_conn() as conn:
                    conn.execute("UPDATE posts SET status='Published' WHERE id=?", (_id,))
                    conn.execute("INSERT INTO run_log (run_date, item_name) VALUES (?,?)", (str(date.today()), name))
                logging.info(f"Published {name}")
            
            time.sleep(10)
        except Exception as e:
            log_error("SYSTEM", "MainLoop", str(e))
            time.sleep(60)

if __name__ == "__main__":
    main_loop()
'''

# ==========================================
# 3. REQUIREMENTS & LAUNCHER
# ==========================================
REQ_TXT = """streamlit
pandas
requests
toml
psutil
plotly
streamlit-autorefresh
"""

LAUNCH_BAT = r"""@echo off
TITLE DTF OVERSEER
ECHO ==========================================
ECHO   EMPIRE OS V65 - OVERSEER EDITION
ECHO ==========================================
ECHO.
ECHO 1. Installing Dashboard Libs...
pip install -r requirements.txt >nul 2>&1
ECHO.
ECHO 2. Launching Overseer...
start /B pythonw engine.py
streamlit run dashboard.py
PAUSE
"""

SECRETS_TEMPLATE = """openai_key = "sk-..."
"""

def install():
    os.makedirs(PROJECT_DIR, exist_ok=True)
    os.makedirs(os.path.join(PROJECT_DIR, ".streamlit"), exist_ok=True)
    
    with open(os.path.join(PROJECT_DIR, "engine.py"), "w", encoding="utf-8") as f: f.write(ENGINE_CODE)
    with open(os.path.join(PROJECT_DIR, "dashboard.py"), "w", encoding="utf-8") as f: f.write(DASHBOARD_CODE)
    with open(os.path.join(PROJECT_DIR, "requirements.txt"), "w", encoding="utf-8") as f: f.write(REQ_TXT)
    with open(os.path.join(PROJECT_DIR, "launch.bat"), "w", encoding="utf-8") as f: f.write(LAUNCH_BAT)
    with open(os.path.join(PROJECT_DIR, ".streamlit", "secrets.toml"), "w", encoding="utf-8") as f: f.write(SECRETS_TEMPLATE)
    
    print(f"🛸 V65 OVERSEER Installed to {PROJECT_DIR}")
    print("Run launch.bat to see the new Futuristic Dashboard.")

if __name__ == "__main__":
    install()

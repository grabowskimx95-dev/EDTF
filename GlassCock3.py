import os

# --- CONFIGURATION ---
FOLDER_NAME = "Empire_HQ_V48_GLASS"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_PATH = os.path.join(DESKTOP, FOLDER_NAME)
SECRETS_DIR = os.path.join(BASE_PATH, ".streamlit")

# ==============================================================================
# 📦 FILE 1: THE DASHBOARD UI (Streamlit Cockpit)
# ==============================================================================
CODE_APP = r'''import streamlit as st
import pandas as pd
import json
import os
from datetime import date, datetime, timedelta
import toml
import zipfile
import io
import csv
import webbrowser
import platform
import subprocess
import re
import streamlit.components.v1 as components

DB_FILE = "empire_database.json"
LOG_FILE = "empire_activity.log"
ALERT_FILE = "alert_state.json"
SECRETS_FILE = os.path.join(".streamlit", "secrets.toml")

APP_DIR = os.path.dirname(__file__)
STAGING_DIR = os.path.join(APP_DIR, "staging_output")
YOUTUBE_DIR = os.path.join(APP_DIR, "youtube_scripts")
EXPORT_DIR = os.path.join(APP_DIR, "export_packs")
NEWSLETTER_DIR = os.path.join(APP_DIR, "newsletters")
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(NEWSLETTER_DIR, exist_ok=True)

# ---------- LIGHT STYLING FOR HYBRID EMERALD + SILVER THEME ----------

st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .stMetric > div {
        background: radial-gradient(circle at top left, rgba(0,255,180,0.12), transparent);
        border-radius: 0.8rem;
        padding: 0.6rem 0.8rem;
        border: 1px solid rgba(200,200,200,0.15);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px;
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------- HELPERS ----------

def safe_slug(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "item"))

def load_json(path):
    """Load JSON safely, with sane defaults if missing/corrupted."""
    default = {
        "niches": {},
        "db": [],
        "system_status": "RUNNING",
        "run_log": {},
        "stats": {
            "total_success": 0,
            "total_failed": 0,
            "avg_production_time_sec": 0.0,
            "last_success": None,
            "last_error": None,
            "consecutive_errors": 0,
            "last_scout": None
        },
        "health": {
            "broken_links": 0,
            "last_link_check": None
        }
    }
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults so older DBs keep working
        for k, v in default.items():
            if k not in data:
                data[k] = v
        data.setdefault("stats", default["stats"])
        data.setdefault("health", default["health"])
        data.setdefault("run_log", {})
        data.setdefault("db", [])
        data.setdefault("system_status", "RUNNING")
        return data
    except Exception:
        return default

def save_json(path, data):
    """Atomic JSON write."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)

def load_alert_state():
    """Read alert_state.json for beacon UI."""
    if not os.path.exists(ALERT_FILE):
        return {
            "level": "OK",
            "message": "All systems nominal.",
            "updated_at": None
        }
    try:
        with open(ALERT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("level", "OK")
        data.setdefault("message", "All systems nominal.")
        return data
    except Exception:
        return {
            "level": "OK",
            "message": "All systems nominal.",
            "updated_at": None
        }

def load_secrets():
    if not os.path.exists(SECRETS_FILE):
        return {}
    try:
        return toml.load(SECRETS_FILE)
    except Exception:
        return {}

def normalize_items(db_data):
    """Ensure each item has extended fields so UI doesn't break."""
    changed = False
    now = datetime.utcnow().isoformat()
    for item in db_data.get("db", []):
        if "id" not in item:
            item["id"] = f"{item.get('name','item')}_{int(datetime.utcnow().timestamp())}"
            changed = True
        item.setdefault("status", "Pending")
        item.setdefault("link", "")
        item.setdefault("created_at", now)
        item.setdefault("last_update", now)
        item.setdefault("fail_count", 0)
        item.setdefault("last_error", "")
        item.setdefault("channels", {})
        item.setdefault("link_status", "UNKNOWN")
        item.setdefault("link_last_check", None)
        item.setdefault("generated", {})
        # 🔒 Brand tag: this install is Digital Empire only
        item.setdefault("unit", "DigitalEmpire")
    return changed

def open_folder(path: str):
    """Attempt to open a folder in the OS file explorer."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:  # Linux / other
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass

# ---------- LOAD CORE STATE ----------

db = load_json(DB_FILE)
changed = normalize_items(db)
if changed:
    save_json(DB_FILE, db)

secrets = load_secrets()
daily_limit = int(secrets.get("daily_run_limit", 10))

# This dashboard is Digital Empire only, just wearing DTF branding
NICHES_LIVE = {"Digital Empire": {"icon": "🧬"}}

# ---------- SIDEBAR ----------

with st.sidebar:
    st.title("🏢 DTF Empire OS V48")

    # Kill switch status
    system_status = db.get("system_status", "RUNNING")
    if system_status == "RUNNING":
        st.success("🟢 ENGINE ACTIVE")
        if st.button("🛑 EMERGENCY STOP"):
            live_db = load_json(DB_FILE)
            live_db["system_status"] = "STOPPED"
            live_db.setdefault("stats", {}).setdefault("consecutive_errors", 0)
            save_json(DB_FILE, live_db)
            st.experimental_rerun()
    else:
        st.error("🔴 ENGINE STOPPED")
        if st.button("♻️ RESTART SIGNAL"):
            live_db = load_json(DB_FILE)
            live_db["system_status"] = "RUNNING"
            save_json(DB_FILE, live_db)
            st.info("Restart engine from launch.bat (Option 1).")
    
    st.markdown("---")

    today_str = str(date.today())
    day_log = db.get("run_log", {}).get(today_str, {})
    runs_today = int(day_log.get("total", 0))
    successes_today = int(day_log.get("success", 0))
    fails_today = int(day_log.get("failed", 0))
    success_rate = (successes_today / runs_today * 100) if runs_today > 0 else 0.0

    st.metric("Runs Today", f"{runs_today} / {daily_limit}")
    st.metric("Success Today", f"{successes_today} ok / {fails_today} fail")
    st.metric("Success Rate", f"{success_rate:.0f}%")

    st.markdown("**Unit:** 🧬 Digital Empire (DTF-branded)")

# ---------- ALERT BEACON & KPI STRIP ----------

alert = load_alert_state()
level = alert.get("level", "OK")
message = alert.get("message", "All systems nominal.")

if level == "CRITICAL":
    st.error(f"🚨 CRITICAL: {message}")
elif level == "WARNING":
    st.warning(f"⚠️ WARNING: {message}")
else:
    st.success(f"🟢 OK: {message}")

st.title("🏗️ DTF Empire OS – Digital Affiliate Command")

# KPI Row
items = db.get("db", [])
today_prefix = str(date.today())
published_today = sum(
    1 for x in items
    if x.get("status") == "Published" and str(x.get("last_update", ""))[:10] == today_prefix
)
pending_count = sum(1 for x in items if x.get("status") == "Pending")
ready_count = sum(1 for x in items if x.get("status") == "Ready")
failed_count = sum(1 for x in items if x.get("status") in ["Failed", "Review"])

stats = db.get("stats", {})
avg_time = float(stats.get("avg_production_time_sec", 0.0))
health = db.get("health", {})
broken_links = int(health.get("broken_links", 0))

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Published Today", published_today)
with col2:
    st.metric("Pending / Ready", f"{pending_count} / {ready_count}")
with col3:
    st.metric("Failed / Review", failed_count)
with col4:
    st.metric("Avg Prod Time (s)", f"{avg_time:.1f}")
with col5:
    st.metric("Broken Links", broken_links)

if broken_links > 0:
    st.caption("⚠️ Some links are broken. See link health details below.")

st.markdown("---")

# ---------- TABS ----------

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⚡ Link Input",
    "📜 Live Logs",
    "📊 Pipeline",
    "🧪 Failed / Review",
    "📄 Content Viewer",
    "🚀 Launchpad",
    "📧 DTF Newsweek"
])

# TAB 1: LINK INPUT
with tab1:
    pending = [x for x in db["db"] if x.get("status") == "Pending"]
    if pending:
        st.warning(f"{len(pending)} links needed.")
        df_edit = pd.DataFrame(pending)
        edited = st.data_editor(
            df_edit,
            column_config={
                "name": "Product",
                "link": st.column_config.TextColumn("Paste Link", width="large"),
                "status": st.column_config.TextColumn("Status", disabled=True),
            },
            disabled=[
                "name", "status", "id", "created_at", "last_update",
                "fail_count", "last_error", "channels",
                "link_status", "link_last_check", "generated", "unit"
            ],
            hide_index=True,
            key="editor_pending"
        )
        if st.button("✅ SAVE LINKS"):
            live_db = load_json(DB_FILE)
            live_db.setdefault("db", [])
            for _, row in edited.iterrows():
                link_val = (row.get("link") or "").strip()
                if not link_val:
                    continue
                for item in live_db["db"]:
                    if item.get("id") == row.get("id"):
                        item["link"] = link_val
                        item["status"] = "Ready"
                        item["last_update"] = datetime.utcnow().isoformat()
            save_json(DB_FILE, live_db)
            st.success("Saved & marked as Ready.")
            st.experimental_rerun()
    else:
        st.success("Pipeline clear. Engine is scouting / running.")

# TAB 2: LIVE LOGS
with tab2:
    st.subheader("🖥️ Background Engine Terminal (Last 50 lines)")
    if st.button("🔄 Refresh Logs"):
        st.experimental_rerun()
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            last_lines = "".join(lines[-50:])
            st.code
import os
import sys

# --- CONFIGURATION ---
FOLDER_NAME = "Empire_HQ_V51_ELITE"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_PATH = os.path.join(DESKTOP, FOLDER_NAME)
SECRETS_DIR = os.path.join(BASE_PATH, ".streamlit")

# ==============================================================================
# 📦 FILE 1: STREAMLIT DASHBOARD – V51 ELITE (FULL UI)
# ==============================================================================
CODE_APP = r'''import streamlit as st
import pandas as pd
import sqlite3
import toml
import os
import requests
import base64
import shutil
import zipfile
import io
from datetime import date, datetime, timedelta

st.set_page_config(page_title="Empire Commander V51 Elite", page_icon="🛡️", layout="wide")

DB_FILE = "empire.db"

# --- DB HELPERS ---
def get_conn():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Main content table
    c.execute(
        """CREATE TABLE IF NOT EXISTS posts (
               id INTEGER PRIMARY KEY,
               name TEXT UNIQUE,
               niche TEXT,
               link TEXT,
               status TEXT,
               created_at TEXT
           )"""
    )
    # Daily run log
    c.execute(
        """CREATE TABLE IF NOT EXISTS run_log (
               id INTEGER PRIMARY KEY,
               run_date TEXT,
               item_name TEXT
           )"""
    )
    # Newsletter log
    c.execute(
        """CREATE TABLE IF NOT EXISTS newsletters (
               id INTEGER PRIMARY KEY,
               created_at TEXT,
               title TEXT,
               filename TEXT
           )"""
    )
    conn.commit()
    conn.close()

def fetch_df(query, params=()):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def exec_db(query, params=()):
    conn = get_conn()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

init_db()

# --- LOAD SECRETS ---
try:
    SECRETS = st.secrets
except Exception:
    SECRETS = {}

DAILY_LIMIT = int(SECRETS.get("daily_run_limit", 10))

# --- LIVE STATS ---
today_str = str(date.today())
runs_today = fetch_df(
    "SELECT COUNT(*) as count FROM run_log WHERE run_date = ?", (today_str,)
)["count"].iloc[0]

pending_count = fetch_df(
    "SELECT COUNT(*) as count FROM posts WHERE status = 'Pending'"
)["count"].iloc[0]

ready_count = fetch_df(
    "SELECT COUNT(*) as count FROM posts WHERE status = 'Ready'"
)["count"].iloc[0]

failed_count = fetch_df(
    "SELECT COUNT(*) as count FROM posts WHERE status = 'Failed'"
)["count"].iloc[0]

# --- HEARTBEAT: LAST ENGINE ACTIVITY ---
df_last_run = fetch_df(
    "SELECT run_date FROM run_log ORDER BY id DESC LIMIT 1"
)
if df_last_run.empty:
    last_run_str = None
else:
    last_run_str = df_last_run["run_date"].iloc[0]

if last_run_str == today_str:
    HEARTBEAT_ICON = "🟢"
    HEARTBEAT_TEXT = f"Engine active today ({today_str})"
elif last_run_str is None:
    HEARTBEAT_ICON = "⚪"
    HEARTBEAT_TEXT = "Engine has not run yet"
else:
    HEARTBEAT_ICON = "🟡"
    HEARTBEAT_TEXT = f"Last active: {last_run_str}"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ COMMANDER V51 ELITE")

    # Tiny heartbeat indicator
    st.markdown(f"{HEARTBEAT_ICON} **Heartbeat:** {HEARTBEAT_TEXT} ")

    if pending_count > 0:
        st.error(f"🔴 ACTION: {pending_count} links needed")
    elif ready_count > 0:
        st.warning(f"🟡 QUEUED: {ready_count} items")
    else:
        st.success("🟢 IDLE / SCOUTING")

    st.metric("Daily Budget", f"{runs_today}/{DAILY_LIMIT}")

    st.markdown("---")
    if st.button("🗑️ Clear Failed Items"):
        exec_db("DELETE FROM posts WHERE status = 'Failed'")
        st.rerun()

st.title("🏗️ Empire OS V51 – Elite Production Suite")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🔴 Action Center",
    "📊 Pipeline",
    "💀 Graveyard",
    "🧭 Affiliate Finder",
    "📰 Weekly Newsletter",
    "✏️ AI Editor",
    "📈 Metrics & Health",
    "🤖 Empire Insights",
])

# ------------------------------------------------------------------------------
# TAB 1: ACTION CENTER – BULK LINK ENTRY
# ------------------------------------------------------------------------------
with tab1:
    if pending_count > 0:
        st.subheader("🔴 Paste Affiliate Links to Unlock Production")
        df_pending = fetch_df(
            "SELECT name, link FROM posts WHERE status = 'Pending' ORDER BY id DESC"
        )

        edited = st.data_editor(
            df_pending,
            column_config={
                "name": st.column_config.TextColumn("Product", disabled=True),
                "link": st.column_config.TextColumn(
                    "Affiliate Link", width="large", required=True
                ),
            },
            hide_index=True,
            num_rows="fixed",
            key="pending_editor",
        )

        if st.button("✅ SAVE & LAUNCH QUEUE", type="primary"):
            updated = 0
            for _, row in edited.iterrows():
                if row["link"] and str(row["link"]).strip():
                    exec_db(
                        "UPDATE posts SET link = ?, status = 'Ready' WHERE name = ?",
                        (row["link"].strip(), row["name"]),
                    )
                    updated += 1
            if updated:
                st.success(f"Queued {updated} items for Elite Engine.")
                st.rerun()
    else:
        st.success("✅ No manual actions required; Scout/Engine are in control.")

# ------------------------------------------------------------------------------
# TAB 2: PIPELINE – LIVE VIEW
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("📊 Live Pipeline")
    df_all = fetch_df("SELECT * FROM posts ORDER BY id DESC")
    if not df_all.empty:
        st.dataframe(df_all, use_container_width=True)
    else:
        st.info("No posts in the system yet. The engine will populate once keys are set.")

# ------------------------------------------------------------------------------
# TAB 3: GRAVEYARD – FAILED ITEMS
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("💀 Failed / Stuck Items")
    df_failed = fetch_df(
        "SELECT id, name, status FROM posts WHERE status = 'Failed' ORDER BY id DESC"
    )
    if df_failed.empty:
        st.info("No failures recorded. Clean operation.")
    else:
        st.dataframe(df_failed, use_container_width=True)
        if st.button("♻️ Retry All Failed"):
            exec_db("UPDATE posts SET status = 'Ready' WHERE status = 'Failed'")
            st.success("All failed items moved back to Ready.")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: AFFILIATE FINDER – MANUAL SCOUT TOOL
# ------------------------------------------------------------------------------
with tab4:
    st.subheader("🧭 Affiliate Finder Console")

    pplx_key = SECRETS.get("pplx_key", "")
    openai_key = SECRETS.get("openai_key", "")

    col_left, col_right = st.columns([2, 1])
    with col_left:
        product_name = st.text_input("Product / Tool Name")
        product_site = st.text_input("Official product URL (optional)")
    with col_right:
        niche = st.text_input("Niche tag (e.g. Tools, Garden)", value="Tools")

    if st.button("🔍 Find Affiliate Program"):
        if not pplx_key:
            st.error("Missing pplx_key in secrets.toml")
        elif not product_name:
            st.error("Enter at least a product name.")
        else:
            with st.spinner("Querying Perplexity for affiliate program..."):
                try:
                    url = "https://api.perplexity.ai/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {pplx_key}",
                        "Content-Type": "application/json",
                    }
                    user_content = f"Find the official affiliate/signup program URL for: {product_name}"
                    if product_site:
                        user_content += f" (official site: {product_site})"
                    payload = {
                        "model": "llama-3.1-sonar-large-128k-online",
                        "messages": [
                            {
                                "role": "system",
                                "content": "Return ONLY the URL of the most official affiliate or partner signup page.",
                            },
                            {"role": "user", "content": user_content},
                        ],
                    }
                    res = requests.post(url, json=payload, headers=headers, timeout=60)
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    st.code(content, language="text")

                    st.success("Affiliate URL candidate found.")
                    if st.button("➕ Add as Pending Item in Pipeline"):
                        created_at = datetime.utcnow().isoformat()
                        exec_db(
                            """INSERT OR IGNORE INTO posts (name, niche, link, status, created_at)
                               VALUES (?, ?, ?, 'Pending', ?)""",
                            (product_name, niche, "", created_at),
                        )
                        st.success("Added to pipeline as Pending (link still to be pasted in Tab 1).")
                except Exception as e:
                    st.error(f"Affiliate lookup failed: {e}")

# ------------------------------------------------------------------------------
# TAB 5: WEEKLY NEWSLETTER – CONTENT PACKET GENERATOR
# ------------------------------------------------------------------------------
with tab5:
    st.subheader("📰 Weekly Newsletter Generator")

    openai_key = SECRETS.get("openai_key", "")
    wp_url = SECRETS.get("wp_url", "")

    title = st.text_input("Newsletter Title", value="This Week in the Empire")
    intro_topic = st.text_area(
        "What should this issue focus on?",
        value="Affiliate tools, construction tech, and top-performing products this week.",
    )

    if st.button("📰 Generate Draft"):
        if not openai_key:
            st.error("Missing openai_key in secrets.toml")
        else:
            with st.spinner("Writing newsletter draft with OpenAI..."):
                try:
                    headers = {
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    }
                    sys_prompt = (
                        "You are a rugged but clear-headed blue-collar newsletter writer. "
                        "Write a weekly email-style newsletter in markdown with sections, short intros, and calls to action, "
                        "for an audience of contractors and tool nerds."
                    )
                    payload = {
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {
                                "role": "user",
                                "content": f"Newsletter title: {title}\nFocus: {intro_topic}",
                            },
                        ],
                    }
                    res = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=120,
                    )
                    md_content = res.json()["choices"][0]["message"]["content"]

                    os.makedirs("newsletters", exist_ok=True)
                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    slug = "".join(
                        c if c.isalnum() or c in "-_" else "_"
                        for c in title.lower().replace(" ", "_")
                    )
                    filename = f"newsletters/{timestamp}_{slug}.md"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"# {title}\n\n")
                        f.write(md_content)

                    exec_db(
                        "INSERT INTO newsletters (created_at, title, filename) VALUES (?, ?, ?)",
                        (datetime.utcnow().isoformat(), title, filename),
                    )

                    st.success("Newsletter draft generated and saved.")
                    st.download_button(
                        "⬇️ Download Markdown",
                        data=open(filename, "r", encoding="utf-8").read(),
                        file_name=os.path.basename(filename),
                        mime="text/markdown",
                    )
                except Exception as e:
                    st.error(f"Newsletter generation failed: {e}")

    st.markdown("### Previous Newsletters")
    df_news = fetch_df("SELECT * FROM newsletters ORDER BY id DESC")
    if df_news.empty:
        st.caption("No newsletters generated yet.")
    else:
        st.dataframe(df_news[["id", "created_at", "title", "filename"]], use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 6: AI EDITOR – INLINE CONTENT REWRITER
# ------------------------------------------------------------------------------
with tab6:
    st.subheader("✏️ AI Editor & Rewriter")

    openai_key = SECRETS.get("openai_key", "")

    mode = st.selectbox(
        "Editing Mode",
        ["Clean & Polish", "SEO Optimize", "More Rugged / Foreman Tone", "Shorten", "Expand"],
    )
    src_text = st.text_area(
        "Paste the content you want to edit",
        height=260,
        placeholder="Paste your blog section, social caption, or email here...",
    )

    if st.button("⚙️ Run AI Edit"):
        if not openai_key:
            st.error("Missing openai_key in secrets.toml")
        elif not src_text.strip():
            st.error("Paste some content first.")
        else:
            with st.spinner("Editing with OpenAI..."):
                try:
                    headers = {
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    }

                    if mode == "Clean & Polish":
                        instruction = "Rewrite this to be cleaner, clearer, and more professional, without changing meaning."
                    elif mode == "SEO Optimize":
                        instruction = "Rewrite this as an SEO-optimized web section with good headings and natural keyword use. Do NOT invent facts."
                    elif mode == "More Rugged / Foreman Tone":
                        instruction = "Rewrite this in the voice of a veteran construction foreman. Plain language, direct, a little gritty but still professional and PG-13."
                    elif mode == "Shorten":
                        instruction = "Condense this into a shorter, punchier version while keeping the core message."
                    else:
                        instruction = "Expand this with more useful detail and explanation while keeping the original intent."

                    payload = {
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": instruction},
                            {"role": "user", "content": src_text},
                        ],
                    }
                    res = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=120,
                    )
                    out = res.json()["choices"][0]["message"]["content"]
                    st.markdown("### ✨ Edited Output")
                    st.write(out)
                    st.text_area("Copyable Output", out, height=260)
                except Exception as e:
                    st.error(f"AI editor error: {e}")

# ------------------------------------------------------------------------------
# TAB 7: METRICS & HEALTH – COUNTERS, DIAGNOSTICS, LINK CHECK, ZIP EXPORT
# ------------------------------------------------------------------------------
with tab7:
    st.subheader("📈 Content Output & System Health")

    # 3) Content Output Counter
    conn = get_conn()
    c = conn.cursor()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date = ?", (today_str,))
    today_runs_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date >= ?", (week_ago,))
    week_runs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM run_log")
    total_runs = c.fetchone()[0]
    conn.close()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Runs Today (Posts/Shorts)", today_runs_count)
    with col2:
        st.metric("Last 7 Days", week_runs)
    with col3:
        st.metric("Lifetime Productions", total_runs)

    # 4) System Health Monitor
    st.markdown("---")
    st.markdown("### 🩺 System Health Monitor")

    openai_ok = bool(SECRETS.get("openai_key"))
    pplx_ok = bool(SECRETS.get("pplx_key"))
    wp_ok = bool(SECRETS.get("wp_url") and SECRETS.get("wp_user") and SECRETS.get("wp_pass"))
    db_ok = True  # if we got here, DB is responding

    disk = shutil.disk_usage(".")
    free_gb = disk.free / (1024 ** 3)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("OpenAI Key", "OK" if openai_ok else "Missing")
    with c2:
        st.metric("Perplexity Key", "OK" if pplx_ok else "Missing")
    with c3:
        st.metric("WP Config", "OK" if wp_ok else "Check")
    with c4:
        st.metric("Free Disk (GB)", f"{free_gb:0.1f}")

    # 5) Stuck Items Diagnostic
    st.markdown("---")
    st.markdown("### 🧪 Stuck Items Diagnostic")

    df_diag = fetch_df("SELECT * FROM posts ORDER BY id DESC")
    if df_diag.empty:
        st.caption("No items yet to diagnose.")
    else:
        mask_ready_no_link = (df_diag["status"] == "Ready") & (
            df_diag["link"].isnull() | (df_diag["link"].str.strip() == "")
        )
        ready_no_link = df_diag[mask_ready_no_link]

        valid_statuses = {"Pending", "Ready", "Published", "Failed"}
        mask_weird = ~df_diag["status"].isin(valid_statuses)
        weird_items = df_diag[mask_weird]

        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Ready but Missing Link", len(ready_no_link))
        with col_b:
            st.metric("Unknown Status Codes", len(weird_items))

        if not ready_no_link.empty:
            st.write("**Ready items missing links:**")
            st.dataframe(ready_no_link[["id", "name", "status"]], use_container_width=True)

        if not weird_items.empty:
            st.write("**Items with unknown statuses:**")
            st.dataframe(weird_items[["id", "name", "status"]], use_container_width=True)

        if not ready_no_link.empty:
            if st.button("🛠 Fix: Move broken Ready items back to Pending"):
                exec_db(
                    "UPDATE posts SET status = 'Pending' "
                    "WHERE status = 'Ready' AND (link IS NULL OR TRIM(link) = '')"
                )
                st.success("Broken Ready items moved back to Pending.")
                st.rerun()

    # 6) Affiliate Link Quality Checker
    st.markdown("---")
    st.markdown("### 🧪 Affiliate Link Quality Checker")

    df_links = fetch_df(
        "SELECT id, name, link, status FROM posts "
        "WHERE link IS NOT NULL AND TRIM(link) <> '' "
        "ORDER BY id DESC LIMIT 50"
    )

    colL, colR = st.columns([2, 3])
    selected_row = None
    with colL:
        if df_links.empty:
            st.caption("No links found yet in pipeline.")
        else:
            labels = {
                f"{row['id']}: {row['name']} ({row['status']})": row
                for _, row in df_links.iterrows()
            }
            label_choice = st.selectbox("Pick link from pipeline", list(labels.keys()))
            selected_row = labels[label_choice]
    with colR:
        manual_url = st.text_input(
            "Or paste any URL to test",
            value=selected_row["link"] if selected_row is not None else "",
        )

    if st.button("Run Link Check"):
        url_to_test = (manual_url or "").strip()
        if not url_to_test:
            st.error("Enter a URL first.")
        else:
            with st.spinner("Checking URL..."):
                try:
                    resp = requests.get(url_to_test, timeout=15, allow_redirects=True)
                    final_url = resp.url
                    status_code = resp.status_code
                    redirected = len(resp.history)
                    has_params = "Yes" if ("?" in final_url) else "No"

                    st.write("**Link Diagnostics:**")
                    st.write(f"- HTTP Status: `{status_code}`")
                    st.write(f"- Redirect Hops: `{redirected}`")
                    st.write(f"- Final URL: `{final_url}`")
                    st.write(f"- Has Query Parameters (likely affiliate tags): `{has_params}`")
                    if status_code >= 400:
                        st.error("🚨 This URL is returning an error status. Double-check it.")
                    else:
                        st.success("✅ URL responded successfully.")
                except Exception as e:
                    st.error(f"Link check failed: {e}")

    # 10) One-Click Daily Packet Export
    st.markdown("---")
    st.markdown("### 📦 One-Click Daily Packet Export")

    export_date = st.date_input("Choose a date", value=date.today())
    folder_name = f"Daily_Packet_{export_date.strftime('%Y-%m-%d')}"

    if st.button("Create ZIP for selected date"):
        if not os.path.exists(folder_name):
            st.error(f"No folder found for: {folder_name}")
        else:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(folder_name):
                    for file in files:
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, start=folder_name)
                        zf.write(filepath, arcname)
            buffer.seek(0)
            st.success(f"Packet ready from {folder_name}.")
            st.download_button(
                "⬇️ Download Daily Packet ZIP",
                data=buffer,
                file_name=f"{folder_name}.zip",
                mime="application/zip",
            )

# ------------------------------------------------------------------------------
# TAB 8: EMPIRE INSIGHTS – AI ADVISOR
# ------------------------------------------------------------------------------
with tab8:
    st.subheader("🤖 Empire Insights – AI Advisor")

    openai_key = SECRETS.get("openai_key", "")

    st.caption("Get a high-level read on what's working, what's stuck, and what to attack next.")

    if st.button("Generate Insights"):
        if not openai_key:
            st.error("Missing openai_key in secrets.toml")
        else:
            with st.spinner("Analyzing pipeline & history..."):
                try:
                    # Summarize statuses
                    df_status = fetch_df("SELECT status, COUNT(*) as c FROM posts GROUP BY status")
                    status_summary = df_status.to_dict(orient="records")

                    # Recent run history
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute(
                        "SELECT run_date, COUNT(*) FROM run_log "
                        "GROUP BY run_date ORDER BY run_date DESC LIMIT 14"
                    )
                    run_rows = c.fetchall()
                    conn.close()

                    summary = {
                        "status_counts": status_summary,
                        "recent_runs": [{"date": r[0], "count": r[1]} for r in run_rows],
                        "today_runs": runs_today,
                        "pending": int(pending_count),
                        "ready": int(ready_count),
                        "failed": int(failed_count),
                    }

                    headers = {
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    }
                    sys_prompt = (
                        "You are an operations and marketing strategist for an automated affiliate "
                        "content engine. Based on the JSON data, give concise, practical advice:\n"
                        "- What seems to be working?\n"
                        "- What might be stuck or risky?\n"
                        "- Which niche or product type should we double down on next?\n"
                        "- Any concrete tweaks to the pipeline or budget?"
                    )

                    payload = {
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": str(summary)},
                        ],
                    }
                    res = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=120,
                    )
                    out = res.json()["choices"][0]["message"]["content"]
                    st.markdown("### 🧠 Empire Insights")
                    st.write(out)
                except Exception as e:
                    st.error(f"Insights generation failed: {e}")
'''

# ==============================================================================
# 📦 FILE 2: ENGINE – V51 ELITE AUTOPILOT
# ==============================================================================
CODE_ENGINE = r'''import os
import time
import sqlite3
import requests
import base64
import toml
import re
from datetime import datetime, date
from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, ColorClip

DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def get_conn():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS posts (
               id INTEGER PRIMARY KEY,
               name TEXT UNIQUE,
               niche TEXT,
               link TEXT,
               status TEXT,
               created_at TEXT
           )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS run_log (
               id INTEGER PRIMARY KEY,
               run_date TEXT,
               item_name TEXT
           )"""
    )
    conn.commit()
    conn.close()

def load_secrets():
    try:
        return toml.load(SECRETS_PATH)
    except Exception:
        return {}

def budget_ok(limit: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    today = str(date.today())
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date = ?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count < limit

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

# -------------------- AI HELPERS --------------------

def scout_products(niche: str, pplx_key: str):
    log(f"🔭 Scouting niche: {niche}")
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {
                "role": "system",
                "content": (
                    "List 3 specific, trending high-ticket tools/products for this niche. "
                    "Return ONLY a comma-separated list of names. No bullets."
                ),
            },
            {
                "role": "user",
                "content": f"Best new tools for {niche} 2024-2025",
            },
        ],
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=90)
        content = res.json()["choices"][0]["message"]["content"]
        items = [x.strip() for x in content.split(",") if x.strip()]
        return items[:3]
    except Exception as e:
        log(f"❌ Scout Failed: {e}")
        return []

def fact_check_product(product: str, pplx_key: str) -> str:
    log(f"🔎 Fact Checking: {product}")
    url = "https://api.perplexity.ai/chat_completions"
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical researcher. Provide the top 5 technical specs "
                    "and pros/cons for this product as bullet points."
                ),
            },
            {"role": "user", "content": f"Technical details for: {product}"},
        ],
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=90)
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"Fact-check failed: {e}")
        return "General high-level overview of the product."

def create_content(product: str, facts: str, keys: dict) -> dict | None:
    log(f"📝 Writing content for: {product}")
    h_oa = {
        "Authorization": f"Bearer {keys['openai_key']}",
        "Content-Type": "application/json",
    }
    sys_prompt = f"""
    You are a veteran construction foreman content writer.

    Use the following FACTS to create content:

    FACTS:
    {facts}

    Return JSON ONLY with:
    - blog_html: 900-word rugged SEO review in HTML with H2 sections and pros/cons.
    - social_caption: Instagram caption with contractor-style tone.
    - video_script: 30s vertical short script (only spoken words, no scene directions).
    """
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Write review for {product}"},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=h_oa,
            timeout=180,
        )
        import json

        return json.loads(res.json()["choices"][0]["message"]["content"])
    except Exception as e:
        log(f"❌ Writer Failed: {e}")
        return None

def produce_media(product: str, script: str, keys: dict, base_dir: str):
    log(f"🎨 Visualizing: {product}")
    h_oa = {
        "Authorization": f"Bearer {keys['openai_key']}",
        "Content-Type": "application/json",
    }

    # 1. Image
    try:
        res_img = requests.post(
            "https://api.openai.com/v1/images/generations",
            json={
                "model": "dall-e-3",
                "prompt": (
                    f"Professional photo of {product} on a construction site, cinematic lighting, 4k."
                ),
                "size": "1024x1024",
            },
            headers=h_oa,
            timeout=180,
        )
        img_url = res_img.json()["data"][0]["url"]
    except Exception as e:
        log(f"Image generation failed: {e}")
        return None, None, None

    # 2. Audio
    try:
        res_aud = requests.post(
            "https://api.openai.com/v1/audio/speech",
            json={
                "model": "tts-1",
                "input": script,
                "voice": "onyx",
            },
            headers=h_oa,
            timeout=180,
        )
        aud_bytes = res_aud.content
    except Exception as e:
        log(f"TTS generation failed: {e}")
        return None, None, None

    # 3. Save assets
    safe = re.sub(r"[^\w\s-]", "", product).strip().replace(" ", "_")
    img_path = os.path.join(base_dir, f"{safe}_image.jpg")
    aud_path = os.path.join(base_dir, f"{safe}_audio.mp3")
    vid_path = os.path.join(base_dir, f"{safe}_short.mp4")

    try:
        with open(img_path, "wb") as f:
            f.write(requests.get(img_url).content)
        with open(aud_path, "wb") as f:
            f.write(aud_bytes)
    except Exception as e:
        log(f"Saving media failed: {e}")
        return None, None, None

    # 4. Video render
    try:
        ac = AudioFileClip(aud_path)
        duration = ac.duration + 0.5
        ic = ImageClip(img_path).set_duration(duration).resize(height=1920)
        ic = ic.crop(
            x1=max(0, ic.w / 2 - 540),
            y1=0,
            width=1080,
            height=1920,
        )
        video = CompositeVideoClip([ic]).set_audio(ac)
        video.write_videofile(vid_path, fps=24, verbose=False, logger=None)
        log("🎬 Short rendered successfully.")
    except Exception as e:
        log(f"Video render warning: {e}")

    return img_path, aud_path, vid_path

def create_smart_link(wp_url: str, product_name: str, raw_link: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", product_name).strip().replace(" ", "_")
    encoded = base64.b64encode(raw_link.encode()).decode()
    return f"{wp_url}/?df_track={clean}__BLOG&dest={encoded}"

def publish_to_wordpress(product: str, blog_html: str, img_path: str, link: str, keys: dict):
    try:
        smart_link = create_smart_link(keys["wp_url"], product, link)
        blog_html += (
            "\n\n<div style='text-align:center;'>"
            f"<a href='{smart_link}' "
            "style='background:red;color:white;padding:15px;font-weight:bold;text-decoration:none;'>"
            "CHECK PRICE</a></div>"
        )

        auth = base64.b64encode(
            f"{keys['wp_user']}:{keys['wp_pass']}".encode()
        ).decode()
        media_headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "image/jpeg",
            "Content-Disposition": "attachment; filename=feature.jpg",
        }
        with open(img_path, "rb") as f:
            media_res = requests.post(
                f"{keys['wp_url']}/wp-json/wp/v2/media",
                data=f.read(),
                headers=media_headers,
                timeout=180,
            )
        mid = media_res.json().get("id")

        post_headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }
        post_data = {
            "title": product,
            "content": blog_html,
            "status": "draft",
            "featured_media": mid,
        }
        res_p = requests.post(
            f"{keys['wp_url']}/wp-json/wp/v2/posts",
            json=post_data,
            headers=post_headers,
            timeout=180,
        )
        if res_p.status_code in (200, 201):
            log(f"✅ PUBLISHED draft to WordPress: {product}")
        else:
            log(f"❌ WordPress post error: {res_p.text}")
    except Exception as e:
        log(f"Publish error: {e}")

# -------------------- MAIN PRODUCTION LINE --------------------

def process_item(row, keys: dict):
    """
    row: tuple representing one row from posts table:
         (id, name, niche, link, status, created_at)
    """
    _, name, niche, link, status, created_at = row
    log(f"🏗️ Starting production for: {name}")

    try:
        facts = fact_check_product(name, keys["pplx_key"])
        assets = create_content(name, facts, keys)
        if not assets:
            raise RuntimeError("Content generation failed.")

        today = datetime.now().strftime("%Y-%m-%d")
        base_dir = os.path.join("Daily_Packet_" + today)
        os.makedirs(base_dir, exist_ok=True)

        img_path, aud_path, vid_path = produce_media(
            name, assets["video_script"], keys, base_dir
        )
        if not img_path:
            raise RuntimeError("Media generation failed.")

        publish_to_wordpress(name, assets["blog_html"], img_path, link, keys)
        update_status(name, "Published")
        log_run(name)
        log(f"✅ Completed production for: {name}")
    except Exception as e:
        log(f"❌ FATAL on {name}: {e}")
        update_status(name, "Failed")

# -------------------- AUTOPILOT LOOP --------------------

def autopilot_loop():
    log("--- V51 ELITE ENGINE ONLINE ---")
    init_db()

    while True:
        try:
            keys = load_secrets()
            if not keys.get("openai_key") or not keys.get("pplx_key"):
                log("Waiting for openai_key and pplx_key in secrets.toml...")
                time.sleep(15)
                continue

            daily_limit = int(keys.get("daily_run_limit", 10))

            conn = get_conn()
            c = conn.cursor()

            # 1) SCOUT if Pending is low
            c.execute("SELECT COUNT(*) FROM posts WHERE status = 'Pending'")
            pending_count = c.fetchone()[0]
            conn.close()

            if pending_count < 3:
                for niche in ["Construction Tools"]:
                    names = scout_products(niche, keys["pplx_key"])
                    for name in names:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute(
                            """INSERT OR IGNORE INTO posts
                               (name, niche, link, status, created_at)
                               VALUES (?, ?, ?, 'Pending', ?)""",
                            (name, "Tools", "", datetime.utcnow().isoformat()),
                        )
                        conn.commit()
                        conn.close()
                        log(f"🔭 Added candidate to Pending: {name}")

            # 2) PRODUCTION
            if not budget_ok(daily_limit):
                log("💤 Daily budget hit. Sleeping 1 hour...")
                time.sleep(3600)
                continue

            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "SELECT * FROM posts WHERE status = 'Ready' ORDER BY id LIMIT 1"
            )
            task = c.fetchone()
            conn.close()

            if task:
                process_item(task, keys)
            else:
                log("💤 No Ready items. Waiting 45s...")
                time.sleep(45)

        except Exception as e:
            log(f"ENGINE ERROR: {e}")
            time.sleep(60)

if __name__ == "__main__":
    autopilot_loop()
'''

# ==============================================================================
# 📦 FILE 3: REQUIREMENTS
# ==============================================================================
CODE_REQ = r'''streamlit
pandas
requests
moviepy<2.0
imageio
imageio-ffmpeg
toml
watchdog
'''

# ==============================================================================
# 📦 FILE 4: WINDOWS LAUNCHER
# ==============================================================================
CODE_BAT = r'''@echo off
TITLE Empire OS V51 Elite
ECHO.
ECHO ===========================================
ECHO   1. START ELITE ENGINE (Background)
ECHO   2. OPEN ELITE DASHBOARD (Streamlit UI)
ECHO ===========================================
ECHO.
SET /P CHOICE=Enter choice (1 or 2): 
IF "%CHOICE%"=="1" GOTO ENGINE
IF "%CHOICE%"=="2" GOTO DASH
GOTO END

:ENGINE
ECHO Installing Dependencies...
pip install -r requirements.txt >nul 2>&1
ECHO Starting Engine...
start /B pythonw engine.py
ECHO Elite Engine running in background.
PAUSE
GOTO END

:DASH
ECHO Installing Dependencies...
pip install -r requirements.txt >nul 2>&1
ECHO Opening Dashboard...
streamlit run empire_app.py
GOTO END

:END
'''

# ==============================================================================
# 📦 FILE 5: SECRETS TEMPLATE
# ==============================================================================
CODE_SECRETS = r'''openai_key = ""
pplx_key = ""
wp_url = "https://yourwebsite.com"
wp_user = "your_username"
wp_pass = "your_app_password"
gmail_user = ""
gmail_pass = ""
daily_run_limit = 5
'''

# ==============================================================================
# 📦 FILE 6: WORDPRESS TRACKER PLUGIN
# ==============================================================================
CODE_PLUGIN = r'''<?php
/* Plugin Name: Digital Foreman Tracker */
add_action('init', 'df_c');
function df_c() {
    if (isset($_GET['df_track']) && isset($_GET['dest'])) {
        $f = plugin_dir_path(__FILE__).'click_stats.csv';
        file_put_contents($f, date("Y-m-d H:i:s").",".sanitize_text_field($_GET['df_track'])."\n", FILE_APPEND);
        wp_redirect(base64_decode($_GET['dest'])); exit;
    }
}
?>
'''

# ==============================================================================
# 📦 FILE 7: QUICKSTART GUIDE
# ==============================================================================
CODE_QUICKSTART = r'''EMPIRE OS V51 ELITE – QUICKSTART GUIDE
====================================

What this is:
-------------
Empire OS V51 Elite is an automated content + affiliate engine.
It scouts tools, researches them, creates SEO blog posts, images, voiceovers,
and vertical shorts, and publishes drafts to WordPress using your affiliate links.

Folder contents:
----------------
- empire_app.py      -> The Streamlit dashboard UI
- engine.py          -> The background autopilot engine
- requirements.txt   -> Python dependencies
- launch.bat         -> Windows launcher menu
- .streamlit/
    - secrets.toml   -> Your private keys and config
- digital-foreman-capture.php -> WordPress tracking plugin

One-time setup:
---------------
1. Make sure you have Python 3.10+ installed on your machine.
2. Open this folder: Empire_HQ_V51_ELITE
3. Edit ".streamlit/secrets.toml" and fill in:
   - openai_key  -> OpenAI API key
   - pplx_key    -> Perplexity API key
   - wp_url      -> Your WordPress site URL (e.g., https://example.com)
   - wp_user     -> WordPress username for API auth
   - wp_pass     -> WordPress application password
   - gmail_user  -> (optional) Gmail address for alerts
   - gmail_pass  -> (optional) App password for that Gmail account
   - daily_run_limit -> How many items per day the engine is allowed to fully produce

4. WordPress plugin:
   - Upload "digital-foreman-capture.php" to your WordPress plugins folder
     (or as a new plugin via ZIP if you package it).
   - Activate the "Digital Foreman Tracker" plugin in wp-admin.

Running the system:
-------------------
1. Double-click "launch.bat"
2. Choose option:
   - 1 = Start Elite Engine (runs in the background)
   - 2 = Open Elite Dashboard (opens Streamlit in your browser)

Using the dashboard:
--------------------
- "Action Center": Paste affiliate links for items marked Pending.
- "Pipeline": See everything in the system (Pending, Ready, Published, Failed).
- "Graveyard": View and retry Failed items.
- "Affiliate Finder": Have the system search for affiliate signup URLs.
- "Weekly Newsletter": Auto-write a weekly email/newsletter in markdown.
- "AI Editor": Paste any content and rewrite/polish it using AI.
- "Metrics & Health": View production counts, system health, stuck items,
  check affiliate link quality, and export daily content packets as ZIP.
- "Empire Insights": Ask the AI to analyze recent activity and recommend
  what to focus on next.

Daily habit (simple version):
-----------------------------
1. Start the engine (launch.bat -> option 1).
2. Open the dashboard (launch.bat -> option 2).
3. Check the sidebar Heartbeat and Daily Budget.
4. Go to "Action Center" if there are Pending items and paste your affiliate links.
5. Let the engine run and publish drafts automatically.
6. Periodically:
   - Use "Metrics & Health" to export a Daily Packet ZIP.
   - Use "Empire Insights" to see what products/niches are working.

If something breaks:
--------------------
- Check "Graveyard" for Failed items and hit "Retry".
- Use the Link Checker in "Metrics & Health" to verify your links.
- Confirm your API keys and WordPress credentials in ".streamlit/secrets.toml".
'''

# ==============================================================================
# 🚀 INSTALLER LOGIC
# ==============================================================================
def create(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())

def main():
    if not os.path.exists(BASE_PATH):
        os.makedirs(BASE_PATH)
    if not os.path.exists(SECRETS_DIR):
        os.makedirs(SECRETS_DIR)

    create(os.path.join(BASE_PATH, "empire_app.py"), CODE_APP)
    create(os.path.join(BASE_PATH, "engine.py"), CODE_ENGINE)
    create(os.path.join(BASE_PATH, "requirements.txt"), CODE_REQ)
    create(os.path.join(BASE_PATH, "launch.bat"), CODE_BAT)
    create(os.path.join(SECRETS_DIR, "secrets.toml"), CODE_SECRETS)
    create(os.path.join(BASE_PATH, "digital-foreman-capture.php"), CODE_PLUGIN)
    create(os.path.join(BASE_PATH, "QUICKSTART.txt"), CODE_QUICKSTART)

    print(f"✅ EMPIRE V51 ELITE INSTALLED TO: {BASE_PATH}")
    print("1. Open that folder.")
    print("2. Read QUICKSTART.txt.")
    print("3. Edit .streamlit\\secrets.toml with your real keys.")
    print("4. Upload digital-foreman-capture.php as a plugin to your WordPress site.")
    print("5. Double-click launch.bat to start the engine and dashboard.")

if __name__ == "__main__":
    main()
import os
import sys

# --- CONFIGURATION ---
FOLDER_NAME = "Empire_HQ_PLATINUM_V50"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_PATH = os.path.join(DESKTOP, FOLDER_NAME)
SECRETS_DIR = os.path.join(BASE_PATH, ".streamlit")

# ==============================================================================
# 📦 FILE 1: THE DASHBOARD UI (SQLite Integrated)
# ==============================================================================
CODE_APP = r'''import streamlit as st
import pandas as pd
import sqlite3
import toml
from datetime import date

st.set_page_config(page_title="Empire Commander V50", page_icon="🛡️", layout="wide")

# --- DATABASE CONNECTION ---
DB_FILE = "empire.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Main Content Table
    c.execute('''CREATE TABLE IF NOT EXISTS posts 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                  status TEXT, created_at TEXT)''')
    # Budget Tracking Table
    c.execute('''CREATE TABLE IF NOT EXISTS run_log 
                 (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_data(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def execute_db(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

# --- CONFIG ---
try: SECRETS = st.secrets
except: SECRETS = {}
DAILY_LIMIT = SECRETS.get("daily_run_limit", 10)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ COMMANDER V50")
    
    # Live Analytics
    today = str(date.today())
    runs_today = get_data("SELECT COUNT(*) as count FROM run_log WHERE run_date = ?", (today,)).iloc[0]['count']
    
    pending_count = get_data("SELECT COUNT(*) as count FROM posts WHERE status = 'Pending'").iloc[0]['count']
    ready_count = get_data("SELECT COUNT(*) as count FROM posts WHERE status = 'Ready'").iloc[0]['count']
    failed_count = get_data("SELECT COUNT(*) as count FROM posts WHERE status = 'Failed'").iloc[0]['count']

    # HUD
    if pending_count > 0: st.error(f"🔴 ACTION: {pending_count} Links Needed")
    elif ready_count > 0: st.warning(f"🟡 QUEUED: {ready_count} Items")
    else: st.success(f"🟢 IDLE: System Monitoring")
    
    st.metric("Daily Budget", f"{runs_today}/{DAILY_LIMIT}")
    st.markdown("---")
    
    if st.button("🗑️ Clear Failed Items"):
        execute_db("DELETE FROM posts WHERE status = 'Failed'")
        st.rerun()

# --- MAIN UI ---
st.title("🏗️ Empire OS: Production Master")
tab1, tab2, tab3 = st.tabs(["🔴 Action Center", "📊 Pipeline", "💀 Graveyard"])

# --- TAB 1: BULK EDITOR ---
with tab1:
    if pending_count > 0:
        st.subheader("🔴 Action Required: Paste Affiliate Links")
        df_pending = get_data("SELECT name, link FROM posts WHERE status = 'Pending'")
        
        # Editable Grid
        edited_df = st.data_editor(
            df_pending,
            column_config={
                "name": st.column_config.TextColumn("Product", disabled=True),
                "link": st.column_config.TextColumn("Affiliate Link", width="large", required=True)
            },
            hide_index=True,
            num_rows="fixed",
            key="editor"
        )
        
        if st.button("✅ SAVE & LAUNCH"):
            count = 0
            for index, row in edited_df.iterrows():
                if row['link'] and str(row['link']).strip():
                    execute_db("UPDATE posts SET link = ?, status = 'Ready' WHERE name = ?", 
                              (row['link'], row['name']))
                    count += 1
            if count > 0:
                st.success(f"Launched {count} items into production queue!")
                st.rerun()
    else:
        st.success("✅ No manual actions required. The Scout is hunting...")

# --- TAB 2: PIPELINE ---
with tab2:
    st.subheader("Live Database View")
    df_all = get_data("SELECT * FROM posts ORDER BY id DESC")
    st.dataframe(df_all, use_container_width=True)

# --- TAB 3: GRAVEYARD ---
with tab3:
    if failed_count > 0:
        st.subheader("❌ Failed Items (Check Logs)")
        df_failed = get_data("SELECT name, status FROM posts WHERE status = 'Failed'")
        st.dataframe(df_failed)
        if st.button("♻️ Retry All Failed"):
            execute_db("UPDATE posts SET status = 'Ready' WHERE status = 'Failed'")
            st.rerun()
    else:
        st.info("No failures. Clean operation.")
'''

# ==============================================================================
# 📦 FILE 2: THE "REAL" ENGINE (Robust & Budget Aware)
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

# --- DATABASE SETUP ---
DB_FILE = "empire.db"
SECRETS_PATH = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def log_msg(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_secrets():
    try: return toml.load(SECRETS_PATH)
    except: return {}

# --- CRITICAL INTEGRITY CHECKS ---

def check_budget(limit):
    conn = get_db_connection()
    c = conn.cursor()
    today = str(date.today())
    c.execute("SELECT COUNT(*) FROM run_log WHERE run_date = ?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count < limit

def log_run(item_name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO run_log (run_date, item_name) VALUES (?, ?)", 
              (str(date.today()), item_name))
    conn.commit()
    conn.close()

def update_status(name, status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE posts SET status = ? WHERE name = ?", (status, name))
    conn.commit()
    conn.close()

# --- AI MODULES ---

def run_scout_real(niche, key):
    log_msg(f"🔭 Scouting niche: {niche}")
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "List 3 specific, trending high-ticket tools/products for this niche. Return ONLY a comma-separated list of names. No bullets."},
            {"role": "user", "content": f"Best new tools for {niche} 2024-2025"}
        ]
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        content = res.json()['choices'][0]['message']['content']
        items = [x.strip() for x in content.split(',') if x.strip()]
        return items[:3] # Limit to 3 to prevent spamming
    except Exception as e:
        log_msg(f"❌ Scout Failed: {e}")
        return []

def get_product_facts(product, key):
    # Step 2: Validation & Fact Check
    log_msg(f"🔎 Fact Checking: {product}")
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "You are a technical researcher. Provide a bulleted list of the top 5 technical specs and pros/cons for this product."},
            {"role": "user", "content": f"Technical specs for: {product}"}
        ]
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        return res.json()['choices'][0]['message']['content']
    except:
        return "General tool overview."

def create_content(product, facts, keys):
    # Step 3: Manufacturing
    log_msg(f"📝 Writing: {product}")
    h_oa = {"Authorization": f"Bearer {keys['openai_key']}", "Content-Type": "application/json"}
    
    # Prompt Chaining for Quality
    sys_prompt = f"""
    You are a veteran foreman. Use these facts to write content:
    FACTS: {facts}
    
    Output JSON ONLY:
    1. 'blog_html': 800-word review, H2 tags, pros/cons, rugged tone.
    2. 'social_caption': Instagram caption.
    3. 'video_script': 30-second narrator script (No scene directions, just speech).
    """
    
    try:
        res = requests.post("https://api.openai.com/v1/chat/completions", json={
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Write review for {product}"}],
            "response_format": {"type": "json_object"}
        }, headers=h_oa)
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        log_msg(f"❌ Writer Failed: {e}")
        return None

def produce_media(product, script, keys):
    log_msg(f"🎨 Visualizing: {product}")
    h_oa = {"Authorization": f"Bearer {keys['openai_key']}", "Content-Type": "application/json"}
    
    # 1. Image
    try:
        res_img = requests.post("https://api.openai.com/v1/images/generations", json={
            "model": "dall-e-3", 
            "prompt": f"Professional photography of {product} on a construction site, cinematic lighting, 8k, highly detailed.", 
            "size": "1024x1024"
        }, headers=h_oa)
        img_url = res_img.json()['data'][0]['url']
    except: return None, None

    # 2. Audio
    try:
        res_aud = requests.post("https://api.openai.com/v1/audio/speech", json={
            "model": "tts-1", "input": script, "voice": "onyx"
        }, headers=h_oa)
        aud_bytes = res_aud.content
    except: return None, None

    return img_url, aud_bytes

def create_smart_link(wp_url, product_name, raw_link):
    clean = re.sub(r'[^\w\s-]', '', product_name).strip().replace(' ', '_')
    encoded = base64.b64encode(raw_link.encode()).decode()
    return f"{wp_url}/?df_track={clean}&dest={encoded}"

# --- MAIN WORKER ---

def production_line(item, keys):
    name = item[1] # name
    link = item[3] # link
    
    try:
        # 1. Fact Check
        facts = get_product_facts(name, keys['pplx_key'])
        
        # 2. Write
        content_json = create_content(name, facts, keys)
        if not content_json: raise Exception("Content Gen Failed")
        import json
        assets = json.loads(content_json)
        
        # 3. Media
        img_url, aud_bytes = produce_media(name, assets['video_script'], keys)
        if not img_url: raise Exception("Media Gen Failed")
        
        # 4. Save Assets Locally
        today = datetime.now().strftime("%Y-%m-%d")
        base_dir = f"Daily_Packet_{today}/{re.sub(r'[^\w\s-]', '', name)}"
        os.makedirs(base_dir, exist_ok=True)
        
        img_path = f"{base_dir}/image.jpg"
        aud_path = f"{base_dir}/audio.mp3"
        vid_path = f"{base_dir}/video.mp4"
        
        with open(img_path, 'wb') as f: f.write(requests.get(img_url).content)
        with open(aud_path, 'wb') as f: f.write(aud_bytes)
        
        # 5. Render Video (Safe Mode)
        try:
            ac = AudioFileClip(aud_path)
            # Resize Logic: Crop to vertical 9:16 aspect ratio roughly
            ic = ImageClip(img_path).set_duration(ac.duration).resize(height=1920)
            ic = ic.crop(x1=ic.w/2 - 540, y1=0, width=1080, height=1920)
            
            # Composite
            video = CompositeVideoClip([ic]).set_audio(ac)
            video.write_videofile(vid_path, fps=24, verbose=False, logger=None)
        except Exception as vx:
            log_msg(f"⚠️ Video Render Warning: {vx}")

        # 6. Publish
        # Add Smart Link
        smart_link = create_smart_link(keys['wp_url'], name, link)
        assets['blog_html'] += f"\n\n\n<div class='wp-block-button'><a class='wp-block-button__link' href='{smart_link}' style='background:red;color:white;font-size:20px;padding:15px;'>👉 CHECK BEST PRICE</a></div>\n"
        
        # WP Upload
        h_wp = {"Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()}
        
        # Upload Media
        media_headers = h_wp.copy(); media_headers["Content-Type"] = "image/jpeg"
        media_headers["Content-Disposition"] = "attachment; filename=feature.jpg"
        with open(img_path, 'rb') as f: 
            mid = requests.post(f"{keys['wp_url']}/wp-json/wp/v2/media", data=f.read(), headers=media_headers).json().get('id')

        # Upload Post
        post_data = {
            "title": name, 
            "content": assets['blog_html'], 
            "status": "publish", 
            "featured_media": mid,
            "categories": [1] 
        }
        res_p = requests.post(f"{keys['wp_url']}/wp-json/wp/v2/posts", json=post_data, headers=h_wp)
        
        if res_p.status_code in [200, 201]:
            log_msg(f"✅ PUBLISHED: {name}")
            update_status(name, "Published")
            log_run(name)
        else:
            raise Exception(f"WP Publish Error: {res_p.text}")

    except Exception as e:
        log_msg(f"❌ FATAL ERROR on {name}: {e}")
        update_status(name, "Failed")

def autopilot_loop():
    print("--- ENGINE V50 (PLATINUM) ONLINE ---")
    
    # Ensure DB exists
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, niche TEXT, link TEXT, 
                  status TEXT, created_at TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS run_log 
                 (id INTEGER PRIMARY KEY, run_date TEXT, item_name TEXT)''')
    conn.close()

    while True:
        try:
            keys = load_secrets()
            if not keys.get('openai_key'):
                log_msg("Waiting for API keys in secrets.toml..."); time.sleep(10); continue
            
            daily_limit = keys.get('daily_run_limit', 10)
            
            # 1. SCOUTING (If Pending < 5)
            conn = get_db_connection()
            pending_count = conn.execute("SELECT COUNT(*) FROM posts WHERE status = 'Pending'").fetchone()[0]
            conn.close()
            
            if pending_count < 3:
                items = run_scout_real("Construction Tools", keys['pplx_key'])
                for i in items:
                    try:
                        conn = get_db_connection()
                        conn.execute("INSERT OR IGNORE INTO posts (name, niche, link, status, created_at) VALUES (?, ?, ?, ?, ?)", 
                                    (i, "Tools", "", "Pending", str(datetime.now())))
                        conn.commit()
                        conn.close()
                        log_msg(f"🔭 Found: {i}")
                    except: pass

            # 2. PRODUCTION
            if not check_budget(daily_limit):
                log_msg("💤 Daily Budget Hit. Sleeping 1 hour..."); time.sleep(3600); continue

            conn = get_db_connection()
            # Fetch one Ready item
            task = conn.execute("SELECT * FROM posts WHERE status = 'Ready' LIMIT 1").fetchone()
            conn.close()
            
            if task:
                production_line(task, keys)
            else:
                log_msg("💤 Queue Empty. Waiting..."); time.sleep(30)
                
        except Exception as e:
            log_msg(f"System Error: {e}"); time.sleep(60)

if __name__ == "__main__":
    autopilot_loop()
'''

# ==============================================================================
# 📦 FILE 3: REQUIREMENTS (Updated for Safety)
# ==============================================================================
CODE_REQ = r'''streamlit
pandas
requests
moviepy<2.0
imageio
imageio-ffmpeg
toml
watchdog'''

# ==============================================================================
# 📦 FILE 4: LAUNCHERS
# ==============================================================================
CODE_BAT = r'''@echo off
TITLE Empire OS Platinum
ECHO Installing Dependencies...
pip install -r requirements.txt >nul 2>&1
ECHO Starting Engine V50...
start /B pythonw engine.py
ECHO Starting Dashboard...
streamlit run empire_app.py
'''

CODE_SECRETS = r'''openai_key = ""
pplx_key = ""
wp_url = "https://"
wp_user = ""
wp_pass = ""
daily_run_limit = 5'''

# --- INSTALLER LOGIC ---
def create(p, c): 
    with open(p, 'w', encoding='utf-8') as f: f.write(c.strip())

def main():
    if not os.path.exists(BASE_PATH): os.makedirs(BASE_PATH)
    if not os.path.exists(SECRETS_DIR): os.makedirs(SECRETS_DIR)
    
    create(os.path.join(BASE_PATH, "empire_app.py"), CODE_APP)
    create(os.path.join(BASE_PATH, "engine.py"), CODE_ENGINE)
    create(os.path.join(BASE_PATH, "requirements.txt"), CODE_REQ)
    create(os.path.join(BASE_PATH, "launch.bat"), CODE_BAT)
    create(os.path.join(SECRETS_DIR, "secrets.toml"), CODE_SECRETS)
    
    print(f"✅ PLATINUM VERSION INSTALLED TO: {BASE_PATH}")
    print("1. Go to folder.")
    print("2. Edit secrets.toml")
    print("3. Run launch.bat")

if __name__ == "__main__":
    main()

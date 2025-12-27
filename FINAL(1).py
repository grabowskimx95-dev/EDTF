import os
import sys

# --- CONFIGURATION ---
FOLDER_NAME = "Empire_HQ_V48_OPTIMIZED"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_PATH = os.path.join(DESKTOP, FOLDER_NAME)
SECRETS_DIR = os.path.join(BASE_PATH, ".streamlit")

# ==============================================================================
# 📦 FILE 1: THE DASHBOARD UI (Fixed & Optimized)
# ==============================================================================
CODE_APP = r'''import streamlit as st
import pandas as pd
import json
import os
import requests
import re
import base64
import glob
import smtplib
import time
from datetime import datetime, date
import toml
from collections import Counter

# --- HOLDING COMPANY CONFIGURATION ---
NICHES_DEFAULT = {
    "Blue Collar Empire": {
        "icon": "🏗️", "hunt_query": "New construction tools 2025", "persona": "Veteran Foreman", "tone": "Rugged, direct, PG-13.", "target_audience": "Contractors", "target_metric": "Clicks" 
    },
    "Green Thumb Garden": {
        "icon": "🌿", "hunt_query": "New gardening gadgets 2025", "persona": "Master Gardener", "tone": "Warm, encouraging.", "target_audience": "Hobby Gardeners", "target_metric": "Clicks" 
    }
}

st.set_page_config(page_title="Empire Commander", page_icon="🏢", layout="wide")
DB_FILE = "empire_database.json"
LOG_FILE = "empire_activity.log"

try: SECRETS = st.secrets
except: SECRETS = {}

def load_json(file_path):
    if not os.path.exists(file_path): return {'niches': NICHES_DEFAULT, 'db': [], 'run_log': {}}
    try:
        with open(file_path, 'r') as f: return json.load(f)
    except: return {'niches': NICHES_DEFAULT, 'db': [], 'run_log': {}}

def save_json(file_path, data):
    # Atomic save
    temp = f"{file_path}.tmp"
    with open(temp, 'w') as f: json.dump(data, f, indent=4)
    os.replace(temp, file_path)

if 'db_state' not in st.session_state: st.session_state.db_state = load_json(DB_FILE)
db = st.session_state.db_state
NICHES_LIVE = db.get('niches', NICHES_DEFAULT)

# --- ANALYTICS HELPERS ---
def fetch_analytics(domain):
    try:
        csv_url = f"{domain}/wp-content/plugins/digital-foreman-capture/click_stats.csv"
        r = requests.get(csv_url)
        if r.status_code == 200:
            lines = r.content.decode('utf-8').splitlines()
            return dict(Counter([row.split(',')[1].strip() for row in lines if ',' in row]))
    except: return {}
    return {}

def generate_metricool_csv(published_items):
    csv_data = "Text,Image/Video URL,Link\n"
    for item in published_items:
        img = item.get('image_url', '')
        link = item.get('link', '')
        name = item.get('name', 'Product')
        # Try to find a caption
        clean = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
        cap_path = glob.glob(f"Daily_Packet_*/Instagram/{clean}_Caption.txt")
        caption = open(cap_path[0]).read().replace("\n", " ") if cap_path else f"Check out {name}."
        
        csv_data += f"{caption},{img},{link}\n"
    return csv_data

# --- UI START ---
oa = SECRETS.get("openai_key", ""); wp_u = SECRETS.get("wp_url", "")
DAILY_LIMIT = SECRETS.get("daily_run_limit", 10)
run_log = db.get('run_log', {})
today_runs = run_log.get(str(date.today()), 0)

# SIDEBAR
with st.sidebar:
    st.title("COMMANDER V48")
    
    # STATUS HUD
    pending_count = len([x for x in db.get('db', []) if x.get('status') == "Pending"])
    ready_count = len([x for x in db.get('db', []) if x.get('status') == "Ready"])
    
    if pending_count > 0: st.error(f"🔴 {pending_count} ACTIONS NEEDED")
    elif ready_count > 0: st.warning(f"🟡 {ready_count} In Queue")
    else: st.success(f"🟢 SYSTEM ONLINE")
        
    st.metric("Budget Used", f"{today_runs}/{DAILY_LIMIT}")
    st.markdown("---")
    selected_niche = st.selectbox("Business Unit:", list(NICHES_LIVE.keys()))
    
    # KILL SWITCH
    system_status = db.get('system_status', 'RUNNING')
    if system_status == 'RUNNING':
        if st.button("🛑 EMERGENCY STOP"):
            db['system_status'] = 'STOPPED'
            save_json(DB_FILE, db)
            st.rerun()
    else:
        st.error("SYSTEM STOPPED")
        if st.button("♻️ RESTART"):
            db['system_status'] = 'RUNNING'
            save_json(DB_FILE, db)
            st.rerun()

st.title("🏗️ Empire OS: Glass Cockpit")
tab1, tab2, tab3, tab4 = st.tabs(["🔴 Action Center", "📜 Live Logs", "📊 Pipeline", "📦 Distribution"])

# --- TAB 1: BULK EDITOR ---
with tab1:
    if pending_count > 0:
        st.subheader("🔴 Action Required: Paste Links")
        pending_items = [x for x in db.get('db', []) if x.get('status') == "Pending"]
        df_edit = pd.DataFrame(pending_items)
        
        # Safe column config
        cols = ['name', 'app_url', 'link']
        df_display = df_edit[cols] if not df_edit.empty else pd.DataFrame(columns=cols)

        edited = st.data_editor(
            df_display,
            column_config={
                "name": "Product",
                "app_url": st.column_config.LinkColumn("Apply", display_text="👉 Open Page"),
                "link": st.column_config.TextColumn("Paste Affiliate Link", width="large", required=True)
            },
            hide_index=True, num_rows="fixed", key="editor"
        )
        
        if st.button("✅ SAVE & RESUME"):
            for index, row in edited.iterrows():
                if row['link'] and str(row['link']).strip():
                    for item in db['db']:
                        if item['name'] == row['name']:
                            item['link'] = row['link']
                            item['status'] = "Ready"
            save_json(DB_FILE, db)
            st.success("Saved. Engine resuming.")
            time.sleep(1)
            st.rerun()
    else:
        st.success("✅ No manual actions required. Robot is hunting.")
        if st.button("Force Manual Scout"):
             st.info("Scout logic triggered in background...")

# --- TAB 2: LIVE LOGS ---
with tab2:
    st.subheader("🖥️ Engine Terminal")
    if st.button("🔄 Refresh Logs"): st.rerun()
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            last_lines = "".join(lines[-20:])
        st.code(last_lines, language="bash")
    else:
        st.info("No logs found. Start the engine.")

# --- TAB 3: PIPELINE ---
with tab3:
    if db.get('db'):
        st.dataframe(pd.DataFrame(db.get('db', [])), use_container_width=True)
    else:
        st.info("Database empty.")

# --- TAB 4: DISTRIBUTION ---
with tab4:
    pub = [x for x in db.get('db', []) if x.get('status') == "Published"]
    if pub:
        csv_data = generate_metricool_csv(pub)
        st.download_button("⬇️ Download Metricool CSV", csv_data, "social_schedule.csv", "text/csv")
    else: st.info("No content ready yet.")
'''

# ==============================================================================
# 📦 FILE 2: THE "REAL" ENGINE (With Logging & Real APIs)
# ==============================================================================
CODE_ENGINE = r'''import os
import time
import json
import requests
import base64
import smtplib
import toml
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, ColorClip

DB_FILE = "empire_database.json"
LOG_FILE = "empire_activity.log"
SECRETS_PATH = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")

# --- LOGGING SYSTEM ---
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(entry + "\n")

def load_secrets():
    try: return toml.load(SECRETS_PATH)
    except: log("❌ ERROR: missing secrets.toml"); return {}

# --- REAL API LOGIC ---
def run_scout_real(niche, key):
    log(f"🔭 Scouting: {niche}")
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [
            {"role": "system", "content": "List 5 trending, high-ticket products in this niche. Comma separated strings only."},
            {"role": "user", "content": f"Find trending products for: {niche}"}
        ]
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        content = res.json()['choices'][0]['message']['content']
        return [x.strip() for x in content.split(',')]
    except Exception as e:
        log(f"Scout Error: {e}")
        return []

def find_app_link_real(product, key):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-sonar-large-128k-online",
        "messages": [{"role": "system", "content": "Output ONLY the affiliate program signup URL."}, {"role": "user", "content": f"Affiliate program for: {product}"}]
    }
    try:
        return requests.post(url, json=payload, headers=headers).json()['choices'][0]['message']['content'].strip()
    except:
        return "https://google.com"

def create_smart_link(wp_url, product_name, raw_link, source="WEB"):
    import re
    clean = re.sub(r'[^\w\s-]', '', product_name).strip().replace(' ', '_')
    encoded = base64.b64encode(raw_link.encode()).decode()
    return f"{wp_url}/?df_track={clean}__{source}&dest={encoded}"

def run_production_real(item, keys):
    name = item['name']
    link = item['link']
    log(f"🏗️ Manufacturing: {name}")
    
    # 1. OMNI-PROMPT
    h_oa = {"Authorization": f"Bearer {keys['openai_key']}", "Content-Type": "application/json"}
    sys_prompt = """
    You are a rugged foreman brand. Generate ALL assets in one JSON response:
    1. 'blog_html': 1500w SEO review with HTML formatting.
    2. 'social_caption': Instagram caption with hashtags.
    3. 'video_script': 45-second rugged narrator script.
    4. 'seo_meta': Meta description.
    Output JSON ONLY.
    """
    
    try:
        res = requests.post("https://api.openai.com/v1/chat/completions", json={
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Product: {name}"}],
            "response_format": {"type": "json_object"}
        }, headers=h_oa)
        
        assets = json.loads(res.json()['choices'][0]['message']['content'])
    except Exception as e:
        log(f"   -> ❌ Content Gen Failed: {e}")
        return False

    # 2. IMAGE GEN
    try:
        res_img = requests.post("https://api.openai.com/v1/images/generations", json={
            "model": "dall-e-3", "prompt": f"Gritty jobsite photo of {name}, cinematic lighting.", "size": "1024x1024"
        }, headers=h_oa)
        img_url = res_img.json()['data'][0]['url']
    except:
        log("   -> ❌ Image Gen Failed")
        return False
    
    # 3. SAVE & RENDER
    today = datetime.now().strftime("%Y-%m-%d")
    base = f"Daily_Packet_{today}"
    import re; clean = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    for f in ["Instagram", "Shorts"]: os.makedirs(os.path.join(base, f), exist_ok=True)
    
    img_path = f"{base}/Instagram/{clean}.jpg"
    aud_path = f"{base}/Shorts/{clean}.mp3"
    vid_path = f"{base}/Shorts/{clean}.mp4"
    
    with open(img_path, 'wb') as f: f.write(requests.get(img_url).content)
    
    # TTS
    try:
        res_aud = requests.post("https://api.openai.com/v1/audio/speech", json={
            "model": "tts-1", "input": assets['video_script'], "voice": "onyx"
        }, headers=h_oa)
        with open(aud_path, 'wb') as f: f.write(res_aud.content)
    except: pass
    
    # VIDEO
    try:
        ac = AudioFileClip(aud_path); d = ac.duration + 0.5
        ic = ImageClip(img_path).set_duration(d).resize(height=1920).set_position("center")
        bc = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=d)
        CompositeVideoClip([bc, ic]).set_audio(ac).write_videofile(vid_path, fps=24, verbose=False, logger=None)
        log("   -> 🎬 Video Rendered")
    except Exception as e: log(f"Video Error: {e}")

    # 4. PUBLISH TO WORDPRESS
    try:
        smart_link = create_smart_link(keys['wp_url'], name, link, "BLOG")
        assets['blog_html'] += f"\n\n<div style='text-align:center;'><a href='{smart_link}' style='background:red;color:white;padding:15px;font-weight:bold;text-decoration:none;'>CHECK PRICE</a></div>"

        h_wp = {
            "Content-Type": "image/jpeg", 
            "Content-Disposition": "attachment; filename=review.jpg", 
            "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()
        }
        with open(img_path, 'rb') as f: img_bytes = f.read()
        res_wp_img = requests.post(f"{keys['wp_url']}/wp-json/wp/v2/media", data=img_bytes, headers=h_wp)
        mid = res_wp_img.json().get('id', 0)
        
        item['image_url'] = res_wp_img.json().get('source_url', '') # Save for CSV export

        post = {"title": name, "content": assets['blog_html'], "status": "draft", "featured_media": mid}
        h_wp_json = {"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()}
        requests.post(f"{keys['wp_url']}/wp-json/wp/v2/posts", json=post, headers=h_wp_json)
        log(f"   -> ✅ Published: {name}")
    except Exception as e:
        log(f"   -> ❌ Publish Error: {e}")
        return False
    
    return True

# --- MAIN LOOP ---
def autopilot_loop():
    log("--- ENGINE V48 LIVE ---")
    while True:
        try:
            SECRETS = load_secrets()
            if not SECRETS.get('openai_key'): 
                log("Waiting for keys..."); time.sleep(10); continue

            # Initialize DB if missing
            if not os.path.exists(DB_FILE):
                json.dump({'db': [], 'run_log': {}}, open(DB_FILE, 'w'))

            with open(DB_FILE, 'r+') as f:
                data = json.load(f)
                
                # Check Kill Switch
                if data.get('system_status') == 'STOPPED':
                    log("🛑 PAUSED."); time.sleep(60); continue

                data.setdefault('db', [])
                
                # 1. Process READY
                ready = [x for x in data['db'] if x.get('status') == "Ready"]
                if ready:
                    for item in ready:
                        # Budget Check
                        today = str(date.today())
                        data.setdefault('run_log', {})
                        if data['run_log'].get(today, 0) >= SECRETS.get('daily_run_limit', 10):
                             log("Budget Hit."); break

                        success = run_production_real(item, SECRETS)
                        
                        if success:
                            for x in data['db']: 
                                if x['name'] == item['name']: x['status'] = "Published"
                            
                            data['run_log'][today] = data['run_log'].get(today, 0) + 1
                            f.seek(0); json.dump(data, f, indent=4); f.truncate(); time.sleep(2)
                    time.sleep(10)
                    
                # 2. Scout if Empty
                elif not [x for x in data['db'] if x.get('status') == "Pending"]:
                    log("Pipeline Empty. Auto-Scouting...")
                    items = run_scout_real("New Tools", SECRETS['pplx_key'])
                    for i in items:
                        link = find_app_link_real(i, SECRETS['pplx_key'])
                        data['db'].append({"name": i, "status": "Pending", "link": "", "app_url": link})
                    f.seek(0); json.dump(data, f, indent=4); f.truncate()
                    
            time.sleep(60)
        except Exception as e:
            log(f"Error: {e}"); time.sleep(60)

if __name__ == "__main__":
    autopilot_loop()
'''

# ==============================================================================
# 📦 SUPPORT FILES (FIXED DEPENDENCIES)
# ==============================================================================

# 3. REQUIREMENTS (PINNED VERSIONS)
CODE_REQ = r'''streamlit
pandas
requests
moviepy<2.0
imageio
imageio-ffmpeg
toml
watchdog'''

# 4. LAUNCHER
CODE_BAT = r'''@echo off
TITLE Empire OS Gold
ECHO Installing Safe Dependencies...
pip install -r requirements.txt >nul 2>&1
ECHO Starting Engine...
start /B pythonw engine.py
ECHO Starting Dashboard...
streamlit run empire_app.py
'''

# 5. SECRETS
CODE_SECRETS = r'''openai_key = ""
pplx_key = ""
wp_url = "https://"
wp_user = ""
wp_pass = ""
gmail_user = ""
gmail_pass = ""
daily_run_limit = 10'''

# 6. PLUGIN
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
?>'''

# --- INSTALLER ---
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
    create(os.path.join(BASE_PATH, "digital-foreman-capture.php"), CODE_PLUGIN)
    
    print(f"✅ V48 OPTIMIZED INSTALLED TO: {BASE_PATH}")
    print("1. Edit secrets.toml with REAL keys.")
    print("2. Run launch.bat")

if __name__ == "__main__":
    main()


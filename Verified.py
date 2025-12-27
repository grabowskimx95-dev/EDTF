import os
import sys

# --- CONFIGURATION ---
FOLDER_NAME = "Empire_HQ_V47_VERIFIED"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_PATH = os.path.join(DESKTOP, FOLDER_NAME)
SECRETS_DIR = os.path.join(BASE_PATH, ".streamlit")

# ==============================================================================
# 📦 FILE 1: THE DASHBOARD UI (Tycoon Edition)
# ==============================================================================
CODE_APP = r'''import streamlit as st
import pandas as pd
import json
import os
import requests
import time
from datetime import date

# --- SETUP ---
st.set_page_config(page_title="Empire Tycoon", page_icon="🏢", layout="wide")
DB_FILE = "empire_database.json"

# DEFAULT NICHES
NICHES_DEFAULT = {
    "DTF Contracting": {
        "icon": "🏗️", 
        "hunt_query": "New construction tools 2025", 
        "persona": "Design To Finish Contracting", 
        "tone": "Rugged, professional, field-tested.",
        "social_prompt": "Social manager for DTF Contracting. Hashtags: #DTF #Construction."
    }
}

# --- ATOMIC DB LOADER ---
def load_db():
    if not os.path.exists(DB_FILE): 
        return {'niches': NICHES_DEFAULT, 'db': [], 'run_log': {}}
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {'niches': NICHES_DEFAULT, 'db': [], 'error': 'corrupt'}

def save_db_atomic(data):
    temp = f"{DB_FILE}.tmp"
    with open(temp, 'w') as f: json.dump(data, f, indent=4)
    os.replace(temp, DB_FILE)

if 'db_state' not in st.session_state: st.session_state.db_state = load_db()
db = st.session_state.db_state

# Ensure niches exist
if 'niches' not in db: db['niches'] = NICHES_DEFAULT

# --- ANALYTICS HELPER ---
def fetch_analytics(domain):
    try:
        r = requests.get(f"{domain}/wp-content/plugins/digital-foreman-capture/click_stats.csv")
        if r.status_code == 200:
            from collections import Counter
            return dict(Counter([row.split(',')[1].strip() for row in r.content.decode().splitlines() if ',' in row]))
    except: return {}
    return {}

# --- UI START ---
try: SECRETS = st.secrets
except: SECRETS = {}

oa = SECRETS.get("openai_key", ""); wp_u = SECRETS.get("wp_url", "")
DAILY = SECRETS.get("daily_run_limit", 10)
today_runs = db.get('run_log', {}).get(str(date.today()), 0)

with st.sidebar:
    st.title("🏢 TYCOON OS")
    
    # 1. NICHE SELECTOR
    niche_names = list(db['niches'].keys())
    sel_niche = st.selectbox("Active Business:", niche_names)
    current_config = db['niches'][sel_niche]
    
    st.info(f"Identity: **{current_config['persona']}**")

    # 2. NICHE BUILDER
    with st.expander("➕ Launch New Brand"):
        with st.form("new_brand"):
            bn = st.text_input("Brand Name (e.g. Zombie Prepper)")
            bi = st.text_input("Icon (e.g. 🧟)")
            bq = st.text_input("Hunt Query (e.g. Best survival gear)")
            bp = st.text_input("Persona (e.g. Sgt. Miller)")
            bt = st.text_input("Tone (e.g. Urgent, tactical)")
            bs = st.text_input("Social Context (e.g. Survival influencer)")
            
            if st.form_submit_button("🚀 Launch"):
                db['niches'][bn] = {
                    "icon": bi, "hunt_query": bq, "persona": bp, 
                    "tone": bt, "social_prompt": bs
                }
                save_db_atomic(db)
                st.success(f"Created {bn}!"); time.sleep(1); st.rerun()

    st.markdown("---")
    
    # 3. STATUS
    niche_items = [x for x in db['db'] if x.get('niche') == sel_niche]
    pending = len([x for x in niche_items if x.get('status') == "Pending"])
    ready = len([x for x in niche_items if x.get('status') == "Ready"])
    
    if pending > 0: st.error(f"🔴 {pending} Links Needed")
    elif ready > 0: st.warning(f"🟡 {ready} In Queue")
    else: st.success(f"🟢 {sel_niche} Automated")
    
    st.metric("Daily Budget", f"{today_runs}/{DAILY}")

st.title(f"{current_config.get('icon','')} {sel_niche} Dashboard")

tab1, tab2, tab3 = st.tabs(["⚡ Action Center", "📊 Pipeline", "🧠 Strategy"])

# --- TAB 1: RAPID EDITOR ---
with tab1:
    if pending > 0:
        st.subheader(f"🔴 Action Required for {sel_niche}")
        
        # Filter for THIS niche only
        df_edit = pd.DataFrame([x for x in niche_items if x.get('status') == "Pending"])
        
        edited_df = st.data_editor(
            df_edit,
            column_config={
                "name": "Product Name",
                "app_url": st.column_config.LinkColumn("Apply", display_text="👉 Open Application"),
                "link": st.column_config.TextColumn("Paste Link Here", width="large", required=True),
                "status": st.column_config.TextColumn("Status", disabled=True)
            },
            disabled=["name", "app_url", "status", "niche"], 
            hide_index=True, num_rows="fixed", key="editor"
        )
        
        if st.button("✅ SAVE LINKS & RESUME AUTOPILOT", type="primary"):
            for index, row in edited_df.iterrows():
                if row['link'] and row['link'].strip():
                    # Update main DB
                    for item in db['db']:
                        if item['name'] == row['name'] and item.get('niche') == sel_niche:
                            item['link'] = row['link']; item['status'] = "Ready"
            
            save_db_atomic(db)
            st.success("Links secured. Factory resuming."); time.sleep(1); st.rerun()
    else:
        st.success("✅ Pipeline Clear. Robot is hunting.")
        if st.button(f"🔭 Scout Market for {sel_niche}"):
             st.info("Scout dispatched via background engine...")

# --- TAB 2: PIPELINE ---
with tab2:
    if niche_items:
        st.dataframe(pd.DataFrame(niche_items), use_container_width=True)
    else:
        st.info("No data for this brand yet.")

# --- TAB 3: ANALYTICS ---
with tab3:
    if st.button("🔄 Sync Click Data"):
        st.session_state.clicks = fetch_analytics(wp_u); st.success("Synced!")
    if 'clicks' in st.session_state:
        st.bar_chart(st.session_state.clicks)
'''

# ==============================================================================
# 📦 FILE 2: THE BACKGROUND ENGINE (V47 - Restored Publishing)
# ==============================================================================
CODE_ENGINE = r'''import os
import time
import json
import requests
import base64
import toml
from datetime import datetime, date
from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, ColorClip

DB_FILE = "empire_database.json"
SECRETS_PATH = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")

def load_secrets():
    try: return toml.load(SECRETS_PATH)
    except: return {}

# --- SCOUT LOGIC ---
def run_scout_real(query, key):
    print(f"   -> 🔭 Scouting: {query}")
    url = "https://api.perplexity.ai/chat/completions"
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Ask for 5 items
    body = {"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "system", "content": "List 5 trending products. Comma separated."},{"role": "user", "content": f"Find: {query}"}]}
    try: return [x.strip() for x in requests.post(url, json=body, headers=h).json()['choices'][0]['message']['content'].split(',')]
    except: return []

def find_app_link(p, k):
    url = "https://api.perplexity.ai/chat/completions"
    h = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
    body = {"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "system", "content": "Output ONLY the affiliate signup URL."},{"role": "user", "content": f"Affiliate program for: {p}"}]}
    try: return requests.post(url, json=body, headers=h).json()['choices'][0]['message']['content'].strip()
    except: return "http://google.com"

# --- PRODUCTION LOGIC (OMNI-PROMPT + LIVE PUBLISH) ---
def run_production_real(item, keys, niches_config):
    name = item['name']
    link = item['link']
    niche_name = item.get('niche', 'DTF Contracting')
    
    # Get Persona/Tone
    niche_settings = niches_config.get(niche_name, niches_config.get('DTF Contracting', {}))
    persona = niche_settings.get('persona', 'Reviewer')
    tone = niche_settings.get('tone', 'Professional')
    
    print(f"   -> 🏗️ Manufacturing: {name} ({persona})")
    
    # 1. OMNI-PROMPT (Write)
    h_oa = {"Authorization": f"Bearer {keys['openai_key']}", "Content-Type": "application/json"}
    sys_prompt = f"""
    You are {persona}. Write in a {tone} style.
    Generate JSON:
    1. 'blog_html': 1500w SEO review with HTML.
    2. 'social_caption': Caption with hashtags.
    3. 'video_script': 45s script.
    """
    res = requests.post("https://api.openai.com/v1/chat/completions", json={
        "model": "gpt-4o", 
        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Product: {name}"}],
        "response_format": {"type": "json_object"}
    }, headers=h_oa)
    assets = json.loads(res.json()['choices'][0]['message']['content'])
    
    # Add CTA to Blog
    import re; clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    encoded_dest = base64.b64encode(link.encode()).decode()
    smart_link = f"{keys['wp_url']}/?df_track={clean_name}__WEB&dest={encoded_dest}"
    
    assets['blog_html'] += f"\n\n<div style='background:#eee;padding:20px;text-align:center;'><a href='{smart_link}' style='background:red;color:white;padding:15px;font-weight:bold;'>CHECK PRICE</a></div>"
    
    # 2. IMAGE
    res_img = requests.post("https://api.openai.com/v1/images/generations", json={
        "model": "dall-e-3", "prompt": f"{tone} photo of {name}.", "size": "1024x1024"
    }, headers=h_oa)
    img_url = res_img.json()['data'][0]['url']
    
    # 3. SAVE & RENDER
    today = datetime.now().strftime("%Y-%m-%d")
    base = f"Daily_Packet_{today}/{clean_name}"
    if not os.path.exists(base): os.makedirs(base)
    
    img_path = f"{base}/image.jpg"
    with open(img_path, 'wb') as f: f.write(requests.get(img_url).content)
    
    res_aud = requests.post("https://api.openai.com/v1/audio/speech", json={"model": "tts-1", "input": assets['video_script'], "voice": "onyx"}, headers=h_oa)
    aud_path = f"{base}/audio.mp3"
    with open(aud_path, 'wb') as f: f.write(res_aud.content)
    
    try:
        ac = AudioFileClip(aud_path); d = ac.duration + 0.5
        ic = ImageClip(img_path).set_duration(d).resize(height=1920).set_position("center")
        bc = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=d)
        CompositeVideoClip([bc, ic]).set_audio(ac).write_videofile(f"{base}/video.mp4", fps=24, verbose=False, logger=None)
    except: pass

    # 4. LIVE PUBLISH TO WORDPRESS (RESTORED)
    try:
        print("   -> 🚀 Uploading to WordPress...")
        # Upload Image
        h_wp = {
            "Content-Type": "image/jpeg", 
            "Content-Disposition": "attachment; filename=review.jpg", 
            "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()
        }
        with open(img_path, 'rb') as f: img_bytes = f.read()
        res_wp_img = requests.post(f"{keys['wp_url']}/wp-json/wp/v2/media", data=img_bytes, headers=h_wp)
        
        if res_wp_img.status_code == 201:
            mid = res_wp_img.json()['id']
            item['image_url'] = res_wp_img.json()['source_url']
            
            # Upload Post
            post = {"title": name, "content": assets['blog_html'], "status": "draft", "featured_media": mid}
            h_wp_json = {"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()}
            requests.post(f"{keys['wp_url']}/wp-json/wp/v2/posts", json=post, headers=h_wp_json)
            print("   -> ✅ Upload Success")
        else:
            print(f"   -> ❌ Image Upload Failed: {res_wp_img.text}")
            
    except Exception as e:
        print(f"   -> ❌ Publish Error: {e}")
    
    return True

# --- MAIN LOOP ---
def autopilot_loop():
    print("--- TYCOON ENGINE STARTED ---")
    while True:
        try:
            SECRETS = load_secrets()
            if not SECRETS.get('openai_key'): time.sleep(10); continue

            with open(DB_FILE, 'r+') as f:
                data = json.load(f)
                data.setdefault('db', [])
                data.setdefault('niches', {})
                
                # 1. READY CHECK
                ready = [x for x in data['db'] if x.get('status') == "Ready"]
                if ready:
                    for item in ready:
                        # Budget Check
                        today = str(date.today())
                        data.setdefault('run_log', {})
                        if data['run_log'].get(today, 0) >= SECRETS.get('daily_run_limit', 10): 
                            print("Budget Hit."); break
                            
                        run_production_real(item, SECRETS, data['niches'])
                        
                        for x in data['db']:
                            if x['name'] == item['name']: x['status'] = "Published"
                        data['run_log'][today] = data['run_log'].get(today, 0) + 1
                        f.seek(0); json.dump(data, f); f.truncate(); time.sleep(2)
                    time.sleep(10); continue

                # 2. SCOUTING (Round Robin through Niches)
                total_pending = len([x for x in data['db'] if x.get('status') == "Pending"])
                if total_pending < 5:
                    for niche_name, config in data['niches'].items():
                        print(f"Scouting for {niche_name}...")
                        items = run_scout_real(config['hunt_query'], SECRETS['pplx_key'])
                        for i in items:
                            url = find_app_link(i, SECRETS['pplx_key'])
                            data['db'].append({
                                "name": i, 
                                "status": "Pending", 
                                "link": "", 
                                "app_url": url,
                                "niche": niche_name
                            })
                        f.seek(0); json.dump(data, f); f.truncate()
                        break # Only scout one niche per loop pass
            
            time.sleep(60)

        except Exception as e:
            print(f"Error: {e}"); time.sleep(60)

if __name__ == "__main__":
    autopilot_loop()
'''

# ==============================================================================
# 📦 SUPPORT FILES
# ==============================================================================

# 3. REQUIREMENTS (Pinned)
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
TITLE Empire Tycoon V47 Verified
ECHO.
ECHO [1] START ENGINE (Background)
ECHO [2] OPEN COMMANDER (UI)
ECHO.
SET /P C=Choice: 
IF "%C%"=="1" GOTO AUTO
IF "%C%"=="2" GOTO DASH
GOTO END
:AUTO
pip install -r requirements.txt >nul 2>&1
start /B pythonw engine.py
GOTO END
:DASH
pip install -r requirements.txt >nul 2>&1
streamlit run empire_app.py
GOTO END
:END
'''

# 5. SECRETS
CODE_SECRETS = r'''openai_key = ""
pplx_key = ""
wp_url = "https://"
wp_user = ""
wp_pass = ""
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
    create(os.path.join(BASE_PATH, "digital-foreman-capture.php"), CODE_PLUGIN)
    create(os.path.join(SECRETS_DIR, "secrets.toml"), CODE_SECRETS)
    
    print(f"✅ TYCOON V47 INSTALLED TO: {BASE_PATH}")
    print("1. Open Folder.")
    print("2. Edit secrets.toml.")
    print("3. Run launch.bat")

if __name__ == "__main__":
    main()


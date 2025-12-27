import os
import platform

# ==============================================================================
# 📦 PAYLOAD: THE HOLDING COMPANY DASHBOARD (V23)
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
import csv
from collections import Counter
from datetime import datetime
from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, ColorClip

# --- HOLDING COMPANY CONFIGURATION ---
NICHES = {
    "Blue Collar Empire": {
        "icon": "🏗️",
        "hunt_query": "New construction tools 2025",
        "persona": "Veteran Foreman",
        "tone": "Rugged, direct, PG-13.",
        "social_prompt": "Blue collar influencer. Use emojis: 🏗️🍺🛠️."
    },
    "Green Thumb Garden": {
        "icon": "🌿",
        "hunt_query": "New gardening gadgets 2025",
        "persona": "Master Gardener",
        "tone": "Warm, helpful, encouraging.",
        "social_prompt": "Garden influencer. Aesthetic. Use emojis: 🌻🥕🏡."
    },
    "Tech Titan": {
        "icon": "💻",
        "hunt_query": "Trending AI software 2025",
        "persona": "Tech Reviewer",
        "tone": "Sharp, analytical, futuristic.",
        "social_prompt": "Tech influencer. Fast paced. Use emojis: 🚀🤖⚡."
    }
}

st.set_page_config(page_title="Empire Holding Co.", page_icon="🏢", layout="wide")
DB_FILE = "empire_database.json"

try: SECRETS = st.secrets
except: SECRETS = {}

def load_json(file_path):
    if not os.path.exists(file_path): return []
    with open(file_path, 'r') as f: return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w') as f: json.dump(data, f, indent=4)

if 'db' not in st.session_state: st.session_state.db = load_json(DB_FILE)
if 'click_data' not in st.session_state: st.session_state.click_data = {}

# ANALYTICS ENGINE
def fetch_analytics(domain):
    csv_url = f"{domain}/wp-content/plugins/digital-foreman-capture/click_stats.csv"
    try:
        response = requests.get(csv_url)
        if response.status_code == 200:
            lines = response.content.decode('utf-8').splitlines()
            raw_tools = [row.split(',')[1].strip() for row in lines if ',' in row]
            return dict(Counter(raw_tools))
    except: return {}
    return {}

def calculate_niche_performance(click_data, database):
    niche_stats = {k: 0 for k in NICHES.keys()}
    niche_stats["Unknown"] = 0
    for tool_name, clicks in click_data.items():
        clean_tool = tool_name.split('__')[0].replace('_', ' ')
        found = False
        for item in database:
            if clean_tool.lower() in item['name'].lower():
                niche = item.get('niche', 'Blue Collar Empire')
                if niche in niche_stats:
                    niche_stats[niche] += clicks
                    found = True
                    break
        if not found: niche_stats["Unknown"] += clicks
    return niche_stats

# FACTORY LOGIC
def run_scout(query, api_key):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "system", "content": "Identify 5 trending products. Output comma separated list."}, {"role": "user", "content": f"Find: {query}"}]}
    try: return [x.strip() for x in requests.post(url, json=payload, headers=headers).json()['choices'][0]['message']['content'].split(',')]
    except: return []

def run_production(item, link, keys, status_box, niche_config):
    name = item['name']
    status_box.info(f"🏗️ Manufacturing: {name}")
    persona = niche_config['persona']
    tone = niche_config['tone']
    
    # Research
    h_pplx = {"Authorization": f"Bearer {keys['pplx']}", "Content-Type": "application/json"}
    res = requests.post("https://api.perplexity.ai/chat/completions", json={"model": "llama-3.1-sonar-large-128k-online", "messages": [{"role": "system", "content": "Valid JSON Only."}, {"role": "user", "content": f"Analyze {name}. JSON keys: product_name, trade_focus, price_point, field_features, bs_factor, durability_rating, pros, cons."}]}, headers=h_pplx)
    data = json.loads(res.json()['choices'][0]['message']['content'].replace("```json", "").replace("```", ""))

    # Write
    h_oa = {"Authorization": f"Bearer {keys['oa']}", "Content-Type": "application/json"}
    sys_prompt = f"You are a {persona}. Write a blog review. Tone: {tone}. Markdown. Output JSON: {{ 'article_content': '...', 'seo_title': '...', 'seo_desc': '...' }}"
    res = requests.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Review {name}. Data: {json.dumps(data)}"}], "response_format": {"type": "json_object"}}, headers=h_oa)
    article = json.loads(res.json()['choices'][0]['message']['content'])
    
    clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    encoded_dest = base64.b64encode(link.encode()).decode()
    smart_link = f"{keys['wp_url']}/?df_track={clean_name}&dest={encoded_dest}"
    article['article_content'] += f"\n\n<div style='background:#eee;padding:20px;text-align:center;'><a href='{smart_link}' style='background:red;color:white;padding:15px;font-weight:bold;'>CHECK PRICE</a></div>"

    # Assets
    prompt_img = f"High quality editorial photo of {name}. Style: {tone} Context: {persona}'s workspace."
    res_img = requests.post("https://api.openai.com/v1/images/generations", json={"model": "dall-e-3", "prompt": prompt_img, "n": 1, "size": "1024x1024"}, headers=h_oa)
    img_url = res_img.json()['data'][0]['url']
    
    prompt_soc = f"{niche_config['social_prompt']} Output JSON keys: 'instagram', 'audio_script' (45s script in {tone} voice)."
    res_soc = requests.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "system", "content": prompt_soc}, {"role": "user", "content": f"Product: {name}"}], "response_format": {"type": "json_object"}}, headers=h_oa)
    assets = json.loads(res_soc.json()['choices'][0]['message']['content'])

    # Save
    today = datetime.now().strftime("%Y-%m-%d")
    base = f"Daily_Packet_{today}"
    for f in ["Instagram", "Shorts"]: os.makedirs(os.path.join(base, f), exist_ok=True)
    img_path = f"{base}/Instagram/{clean_name}.jpg"
    aud_path = f"{base}/Shorts/{clean_name}_Audio.mp3"
    vid_path = f"{base}/Shorts/{clean_name}_Video.mp4"
    
    with open(img_path, 'wb') as f: f.write(requests.get(img_url).content)
    with open(f"{base}/Instagram/{clean_name}_Caption.txt", 'w', encoding='utf-8') as f: f.write(assets['instagram'])
    res_aud = requests.post("https://api.openai.com/v1/audio/speech", json={"model": "tts-1", "input": assets['audio_script'], "voice": "onyx"}, headers=h_oa)
    with open(aud_path, 'wb') as f: f.write(res_aud.content)
    
    try:
        ac = AudioFileClip(aud_path); d = ac.duration + 0.5
        ic = ImageClip(img_path).set_duration(d).resize(height=1920).set_position("center")
        bc = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=d)
        CompositeVideoClip([bc, ic]).set_audio(ac).write_videofile(vid_path, fps=24, verbose=False, logger=None)
    except: pass

    status_box.info("🚀 Publishing...")
    h_wp = {"Content-Type": "image/jpeg", "Content-Disposition": "attachment; filename=review.jpg", "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()}
    with open(img_path, 'rb') as f: img_bytes = f.read()
    res_wp_img = requests.post(f"{keys['wp_url']}/wp-json/wp/v2/media", data=img_bytes, headers=h_wp)
    if res_wp_img.status_code == 201:
        mid = res_wp_img.json()['id']
        item['image_url'] = res_wp_img.json()['source_url']
        post = {"title": name, "content": article['article_content'], "status": "draft", "featured_media": mid}
        h_wp_json = {"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(f"{keys['wp_user']}:{keys['wp_pass']}".encode()).decode()}
        requests.post(f"{keys['wp_url']}/wp-json/wp/v2/posts", json=post, headers=h_wp_json)
        status_box.success(f"✅ Finished: {name}")

def find_affiliate_page(p, k):
    try: return requests.post("https://api.perplexity.ai/chat/completions", json={"model":"llama-3.1-sonar-large-128k-online","messages":[{"role":"system","content":"Output ONLY URL."},{"role":"user","content":f"Affiliate signup: {p}"}]}, headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"}).json()['choices'][0]['message']['content'].strip()
    except: return None

# UI
keys = {
    "oa": SECRETS.get("openai_key", ""),
    "pplx": SECRETS.get("pplx_key", ""),
    "wp_url": SECRETS.get("wp_url", ""),
    "wp_user": SECRETS.get("wp_user", ""),
    "wp_pass": SECRETS.get("wp_pass", "")
}

with st.sidebar:
    st.title("🏢 Empire Holdings")
    selected_niche_name = st.selectbox("Select Business Unit:", list(NICHES.keys()))
    current_config = NICHES[selected_niche_name]
    st.info(f"Target: {current_config['audience']}")
    st.markdown("---")
    def get_niche_items(): return [x for x in st.session_state.db if x.get('niche', 'Blue Collar Empire') == selected_niche_name]
    niche_items = get_niche_items()
    st.metric(f"Active Jobs", len(niche_items))
    with st.expander("🔑 Credentials"):
        keys['oa'] = st.text_input("OpenAI", value=keys['oa'], type="password")
        keys['pplx'] = st.text_input("Perplexity", value=keys['pplx'], type="password")
        keys['wp_url'] = st.text_input("WP URL", value=keys['wp_url'])
        keys['wp_user'] = st.text_input("WP User", value=keys['wp_user'])
        keys['wp_pass'] = st.text_input("WP Pass", value=keys['wp_pass'], type="password")

tab1, tab2, tab3 = st.tabs(["🚀 Pipeline", "🏭 Factory", "📊 CEO Analytics"])

with tab1:
    st.header(f"{current_config['icon']} Pipeline: {selected_niche_name}")
    c_hunt, c_niche = st.columns([1, 3])
    with c_hunt:
        if st.button("🔭 Scout Market"):
            with st.spinner(f"Scouting {current_config['hunt_query']}..."):
                res = run_scout(current_config['hunt_query'], keys['pplx'])
                for x in res:
                    url = find_affiliate_page(x, keys['pplx'])
                    st.session_state.db.append({"name": x, "status": "Pending", "link": "", "app_url": url, "niche": selected_niche_name})
                save_json(DB_FILE, st.session_state.db)
                st.rerun()
    pending = [x for x in niche_items if x['status'] == "Pending"]
    if not pending: st.info("Pipeline Clear.")
    for i, item in enumerate(pending):
        with st.expander(f"🔴 {item['name']}", expanded=True):
            c1, c2 = st.columns([1,2])
            with c1:
                if item.get('app_url'): st.link_button("👉 Apply Here", item['app_url'])
                else: st.warning("No URL")
            with c2:
                l = st.text_input("Link", key=f"l_{item['name']}")
                if st.button("Save", key=f"sv_{item['name']}"):
                    for x in st.session_state.db:
                        if x['name'] == item['name']: x['link'] = l; x['status'] = "Ready"
                    save_json(DB_FILE, st.session_state.db); st.rerun()

with tab2:
    st.header(f"{current_config['icon']} Manufacturing")
    ready = [x for x in niche_items if x['status'] == "Ready"]
    if st.button("🚀 MANUFACTURE BATCH", type="primary"):
        stat = st.empty(); prog = st.progress(0)
        for idx, item in enumerate(ready):
            run_production(item, item['link'], keys, stat, current_config)
            for db_item in st.session_state.db:
                if db_item['name'] == item['name']: db_item['status'] = "Published"
            save_json(DB_FILE, st.session_state.db); prog.progress((idx+1)/len(ready))
        st.success("Batch Complete!")
    for r in ready: st.write(f"🟡 Queued: {r['name']}")

with tab3:
    st.header("📊 Holding Company Performance")
    c_sync, c_metric = st.columns([1, 3])
    with c_sync:
        if st.button("🔄 Sync Click Data"):
            st.session_state.click_data = fetch_analytics(keys['wp_url'])
            st.success("Data Updated")
    if st.session_state.click_data:
        niche_performance = calculate_niche_performance(st.session_state.click_data, st.session_state.db)
        st.metric("Total Empire Clicks", sum(niche_performance.values()))
        st.subheader("Revenue Drivers by Niche")
        df = pd.DataFrame(list(niche_performance.items()), columns=['Niche', 'Clicks'])
        df = df[df['Clicks'] > 0]
        if not df.empty:
            st.bar_chart(df.set_index('Niche'))
            winner = df.sort_values('Clicks', ascending=False).iloc[0]
            st.success(f"🏆 Top Performer: **{winner['Niche']}**")
        else: st.warning("No clicks recorded yet.")
'''

# 📦 PAYLOAD: PLUGIN & EXTRAS
CODE_PLUGIN = r'''<?php
/* Plugin Name: Digital Foreman Tracker */
add_action('init', 'df_click');
function df_click() {
    if (isset($_GET['df_track']) && isset($_GET['dest'])) {
        $f = plugin_dir_path(__FILE__) . 'click_stats.csv';
        file_put_contents($f, date("Y-m-d H:i:s") . "," . sanitize_text_field($_GET['df_track']) . "\n", FILE_APPEND);
        wp_redirect(base64_decode($_GET['dest']));
        exit;
    }
}
function df_form() {
    if (isset($_POST['e'])) {
        file_put_contents(plugin_dir_path(__FILE__) . 'secure_db_x9z.csv', date("Y-m-d") . "," . sanitize_email($_POST['e']) . "\n", FILE_APPEND);
        echo '<div>✅ Joined.</div>';
    }
    return '<form method="post"><input type="email" name="e" placeholder="Email"><button>JOIN</button></form>';
}
add_shortcode('newsletter_form', 'df_form');
?>'''

CODE_REQ = r'''streamlit
pandas
requests
moviepy
imageio
imageio-ffmpeg
watchdog'''

CODE_BAT = r'''@echo off
TITLE Empire Dashboard
pip install -r requirements.txt >nul 2>&1
streamlit run empire_app.py
PAUSE'''

CODE_SECRETS = r'''openai_key = ""
pplx_key = ""
wp_url = "https://yourwebsite.com"
wp_user = "your_username"
wp_pass = "your_app_password"'''

# ==============================================================================
# 🚀 INSTALLATION LOGIC
# ==============================================================================
def create_file(path, content):
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"✅ Created: {path}")

def main():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base_path = os.path.join(desktop, "Empire_HQ")
    if not os.path.exists(base_path): os.makedirs(base_path)
    secrets_dir = os.path.join(base_path, ".streamlit")
    if not os.path.exists(secrets_dir): os.makedirs(secrets_dir)

    print(f"--- 🏗️ BUILDING EMPIRE V23 AT: {base_path} ---")
    create_file(os.path.join(base_path, "empire_app.py"), CODE_APP)
    create_file(os.path.join(base_path, "requirements.txt"), CODE_REQ)
    create_file(os.path.join(base_path, "launch.bat"), CODE_BAT)
    create_file(os.path.join(secrets_dir, "secrets.toml"), CODE_SECRETS)
    create_file(os.path.join(base_path, "digital-foreman-capture.php"), CODE_PLUGIN)

    print("\n--- 🏁 INSTALLATION COMPLETE ---")
    print("1. Open 'Empire_HQ' folder on Desktop.")
    print("2. Edit '.streamlit/secrets.toml' with your keys.")
    print("3. Double-click 'launch.bat'.")

if __name__ == "__main__":
    main()


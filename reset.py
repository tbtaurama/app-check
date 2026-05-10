import datetime
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt

# Database v4 untuk Mode Testing & Simulasi Admin
DB_NAME = "prod_tracker_v4.db"

# ==========================================
# 1. SETUP DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, full_name TEXT, password TEXT, role TEXT, goal TEXT, is_failed INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS check_ins 
                 (username TEXT, day_number INTEGER, status TEXT, timestamp DATETIME,
                  PRIMARY KEY (username, day_number))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    initial_users = [
        ("resetapp", "Super Admin (Anda)", "12345#", "admin", "Mengawal sistem produktivitas 60 hari", 0),
        ("azwa1", "Azwa", "12345#", "peserta", "", 0),
        ("iqbal2", "Iqbal", "12345#", "peserta", "", 0),
        ("habib3", "Habib", "12345#", "peserta", "", 0),
        ("pandu4", "Pandu", "12345#", "peserta", "", 0)
    ]
    c.executemany("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)", initial_users)
    
    # Settings default
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('app_status', 'active')")
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('test_mode', 'off')") # Mode testing default mati
    
    conn.commit()
    conn.close()

init_db()

# FUNGSI BANTU SETTINGS
def get_setting(key):
    conn = sqlite3.connect(DB_NAME)
    res = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return res[0] if res else None

def set_setting(key, val):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE system_settings SET value=? WHERE key=?", (val, key))
    conn.commit()
    conn.close()

# ==========================================
# 2. LOGIKA EVALUASI (GAGAL & BINTANG)
# ==========================================
def evaluate_participants():
    conn = sqlite3.connect(DB_NAME)
    users = pd.read_sql_query("SELECT * FROM users WHERE role='peserta'", conn)
    records = pd.read_sql_query("SELECT * FROM check_ins", conn)
    conn.close()
    
    leaderboard_data = []
    trajectory_records = []
    
    for _, user in users.iterrows():
        uname = user['username']
        name = user['full_name']
        is_failed = bool(user['is_failed'])
        
        user_records = records[records['username'] == uname].sort_values('day_number')
        records_dict = user_records.set_index('day_number')['status'].to_dict()
        
        cumulative_score = 0
        score_history = [{"Hari": 0, "Poin": 0, "Nama": name}]
        
        consecutive_misses = 0
        active_streak_for_stars = 0
        stars_earned = 0
        current_block_misses = 0
        
        max_day = max(records_dict.keys()) if records_dict else 0
        
        for day in range(1, max_day + 1):
            status = records_dict.get(day, "missed")
            
            if (day - 1) % 7 == 0: current_block_misses = 0
                
            if status == "holiday":
                score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
                continue
                
            if status == "checked_in":
                cumulative_score += day
                consecutive_misses = 0
                active_streak_for_stars += 1
                if active_streak_for_stars == 15:
                    if stars_earned < 4: stars_earned += 1
                    active_streak_for_stars = 0
            else:
                cumulative_score -= day
                consecutive_misses += 1
                current_block_misses += 1
                active_streak_for_stars = 0
                
                # Check Eliminasi
                if (consecutive_misses >= 2 or current_block_misses > 1) and not is_failed:
                    is_failed = True
                    conn_f = sqlite3.connect(DB_NAME)
                    conn_f.execute("UPDATE users SET is_failed=1 WHERE username=?", (uname,))
                    conn_f.commit()
                    conn_f.close()
                    
            score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
            
        trajectory_records.extend(score_history)
        
        leaderboard_data.append({
            "Nama": name, "Username": uname, "Tujuan": user['goal'],
            "Poin": cumulative_score, "Hari": max_day,
            "Bintang": "⭐" * stars_earned if stars_earned > 0 else "—",
            "Status": "❌ GAGAL" if is_failed else "🟢 AKTIF",
            "kemarin_bolos": (consecutive_misses == 1),
            "sisa_kuota": 1 - current_block_misses,
            "awal_blok": ((max_day // 7) * 7) + 1
        })
        
    return pd.DataFrame(leaderboard_data), pd.DataFrame(trajectory_records)

# ==========================================
# 3. SISTEM LOGIN
# ==========================================
st.set_page_config(page_title="Beta Test: Productivity Race", layout="centered")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'current_user': "", 'current_name': "", 'current_role': ""})

def login():
    u, p = st.session_state['l_u'].strip(), st.session_state['l_p'].strip()
    conn = sqlite3.connect(DB_NAME)
    res = conn.execute("SELECT full_name, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
    conn.close()
    if res: st.session_state.update({'logged_in': True, 'current_user': u, 'current_name': res[0], 'current_role': res[1]})
    else: st.error("Username/Password Salah")

if not st.session_state['logged_in']:
    st.title("🔒 Login Aplikasi")
    with st.form("l"):
        st.text_input("Username", key="l_u")
        st.text_input("Password", type="password", key="l_p")
        st.form_submit_button("Masuk", on_click=login, use_container_width=True)
    st.stop()

# ==========================================
# 4. DASHBOARD SUPER ADMIN (TOOLS TESTING)
# ==========================================
if st.session_state['current_role'] == "admin":
    st.title("👑 Super Admin Control")
    
    # TAB 1: Kontrol Sistem
    t1, t2 = st.tabs(["⚙️ Pengaturan & Testing", "📊 Pantau Peserta"])
    
    with t1:
        st.subheader("Beta Test Tools")
        mode_test = get_setting('test_mode')
        new_test = st.toggle("Buka Kunci Waktu (Mode Testing 24 Jam)", value=(mode_test == 'on'))
        if new_test != (mode_test == 'on'):
            set_setting('test_mode', 'on' if new_test else 'off')
            st.rerun()
            
        status_app = get_app_status = get_setting('app_status')
        if st.button("Toggle Libur Nasional", type="secondary"):
            set_setting('app_status', 'holiday' if status_app == 'active' else 'active')
            st.rerun()
        
        st.divider()
        st.subheader("🛠️ Simulasi Klik Peserta (Shadow Control)")
        st.write("Gunakan ini untuk tes kilat tanpa ganti akun.")
        
        df_l, _ = evaluate_participants()
        for _, p in df_l.iterrows():
            with st.expander(f"Aksi untuk {p['Nama']} ({p['Status']})"):
                c1, c2 = st.columns(2)
                h_next = p['Hari'] + 1
                if c1.button(f"Check-In H-{h_next}", key=f"in_{p['Username']}"):
                    sqlite3.connect(DB_NAME).execute("INSERT INTO check_ins VALUES (?,?,?,?)", (p['Username'], h_next, 'checked_in', datetime.datetime.now())).connection.commit()
                    st.rerun()
                if c2.button(f"Bolos H-{h_next}", key=f"ms_{p['Username']}"):
                    sqlite3.connect(DB_NAME).execute("INSERT INTO check_ins VALUES (?,?,?,?)", (p['Username'], h_next, 'missed', datetime.datetime.now())).connection.commit()
                    st.rerun()

    with t2:
        df_l, df_t = evaluate_participants()
        st.dataframe(df_l[['Nama', 'Status', 'Poin', 'Bintang']], use_container_width=True)
        if not df_t.empty:
            line = alt.Chart(df_t).mark_line().encode(x='Hari:Q', y='Poin:Q', color='Nama:N')
            st.altair_chart(line, use_container_width=True)
            
    if st.sidebar.button("Log Out"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.stop()

# ==========================================
# 5. DASHBOARD PESERTA
# ==========================================
df_leaderboard, df_trajectory = evaluate_participants()
my_data = df_leaderboard[df_leaderboard['Username'] == st.session_state['current_user']].iloc[0]

st.title("🚴 Productivity Race")
# (Visualisasi Grafik Balapan sama seperti versi sebelumnya)
if not df_trajectory.empty:
    chart = alt.Chart(df_trajectory).mark_line(strokeWidth=3).encode(
        x=alt.X('Hari:Q', scale=alt.Scale(domain=[0, 60])),
        y='Poin:Q', color='Nama:N'
    )
    st.altair_chart(chart.properties(height=300), use_container_width=True)

# Input Tujuan
with st.form("g"):
    g_text = st.text_input("Tujuan Utama (Maks 50 Karakter)", value=my_data['Tujuan'], max_chars=50)
    if st.form_submit_button("Update Tujuan"):
        sqlite3.connect(DB_NAME).execute("UPDATE users SET goal=? WHERE username=?", (g_text, st.session_state['current_user'])).connection.commit()
        st.rerun()

st.metric("Poin", f"{my_data['Poin']} Poin", f"Badge: {my_data['Bintang']}")

# Logic Presensi
is_test = (get_setting('test_mode') == 'on')
is_libur = (get_setting('app_status') == 'holiday')

wib = datetime.timezone(datetime.timedelta(hours=7))
t_now = datetime.datetime.now(wib)
is_time = (datetime.time(20,0) <= t_now.time() <= datetime.time(23,0))

if my_data['Status'] == "❌ GAGAL":
    st.error("💀 AKUN TERELIMINASI (Bolos beruntun/melebihi kuota)")
    st.stop()

# Bypass waktu jika mode testing ON
can_check = (is_time or is_test) and not is_libur

if is_libur: st.info("🏖️ Hari Libur Nasional")
elif is_test: st.warning("🛠️ MODE TESTING: Tombol dibuka 24 jam.")
elif is_time: st.success("✅ Jendela Presensi Terbuka")
else: st.warning("🔒 Presensi dibuka pukul 20.00 WIB")

# Tombol Presensi
conn = sqlite3.connect(DB_NAME)
user_logs = pd.read_sql_query("SELECT day_number FROM check_ins WHERE username=?", conn, params=(st.session_state['current_user'],))['day_number'].tolist()
h_target = max(user_logs) + 1 if user_logs else 1

if h_target <= 60:
    c1, c2 = st.columns(2)
    if c1.button(f"Check-In H-{h_target}", type="primary", disabled=not can_check, use_container_width=True):
        conn.execute("INSERT INTO check_ins VALUES (?,?,?,?)", (st.session_state['current_user'], h_target, 'checked_in', datetime.datetime.now())).connection.commit()
        st.rerun()
    if c2.button(f"Bolos H-{h_target}", type="secondary", disabled=not can_check, use_container_width=True):
        conn.execute("INSERT INTO check_ins VALUES (?,?,?,?)", (st.session_state['current_user'], h_target, 'missed', datetime.datetime.now())).connection.commit()
        st.rerun()
conn.close()

if st.sidebar.button("Log Out"):
    st.session_state['logged_in'] = False
    st.rerun()

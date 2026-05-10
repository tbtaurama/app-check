import datetime
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt

# Database v6 untuk Logic "3 Strikes" & Global Clock
DB_NAME = "prod_tracker_v6.db"

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
        ("resetapp", "Super Admin", "12345#", "admin", "", 0),
        ("azwa1", "Azwa", "12345#", "peserta", "", 0),
        ("iqbal2", "Iqbal", "12345#", "peserta", "", 0),
        ("habib3", "Habib", "12345#", "peserta", "", 0),
        ("pandu4", "Pandu", "12345#", "peserta", "", 0)
    ]
    c.executemany("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)", initial_users)
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('app_status', 'active')")
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('test_mode', 'off')")
    # Set tanggal mulai default hari ini jika belum ada
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime('%Y-%m-%d')
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('start_date', ?)", (today_str,))
    conn.commit()
    conn.close()

init_db()

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

# ====================================================================
# 2. LOGIKA EVALUASI KETAT (GLOBAL CLOCK & 3 STRIKES)
# ====================================================================
def evaluate_participants():
    conn = sqlite3.connect(DB_NAME)
    users = pd.read_sql_query("SELECT * FROM users WHERE role='peserta'", conn)
    records = pd.read_sql_query("SELECT * FROM check_ins", conn)
    conn.close()
    
    # Hitung Hari Program Saat Ini
    start_date_str = get_setting('start_date')
    start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    today_wib = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    current_prog_day = (today_wib - start_date).days + 1
    
    leaderboard_data = []
    trajectory_records = []
    
    for _, user in users.iterrows():
        uname, name = user['username'], user['full_name']
        is_failed = bool(user['is_failed'])
        
        user_records = records[records['username'] == uname].set_index('day_number')['status'].to_dict()
        
        cumulative_score = 0
        total_missed_days = 0 # Strike counter
        score_history = [{"Hari": 0, "Poin": 0, "Nama": name}]
        
        # Evaluasi dari Hari 1 sampai Hari Program Saat Ini
        # (Namun hari ini belum dianggap missed sampai jendela jam 23:00 WIB lewat)
        t_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        is_past_window = t_now.hour >= 23
        
        eval_until = current_prog_day if is_past_window else current_prog_day - 1
        eval_until = max(0, min(eval_until, 60))
        
        # Hitung skor berdasarkan data yang ada
        max_day_recorded = max(user_records.keys()) if user_records else 0
        loop_limit = max(eval_until, max_day_recorded)
        
        for day in range(1, loop_limit + 1):
            status = user_records.get(day)
            
            if status == "holiday":
                score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
                continue
            
            if status == "checked_in":
                cumulative_score += day
            else:
                # Jika status None (tidak login) atau 'missed' (pencet bolos)
                cumulative_score -= day
                if day <= eval_until: # Hanya hitung strike untuk hari yang sudah lewat
                    total_missed_days += 1
            
            score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})

        # LOGIKA ELIMINASI: Jika Missed > 2 (artinya 3 kali)
        if total_missed_days > 2 and not is_failed:
            is_failed = True
            conn_f = sqlite3.connect(DB_NAME)
            conn_f.execute("UPDATE users SET is_failed=1 WHERE username=?", (uname,))
            conn_f.commit()
            conn_f.close()
            
        trajectory_records.extend(score_history)
        leaderboard_data.append({
            "Nama": name, "Username": uname, "Poin": cumulative_score, 
            "Hari": max_day_recorded, "Strikes": f"{total_missed_days}/2",
            "Bintang": "⭐" * (cumulative_score // 100), # Sederhanakan untuk demo
            "Status": "❌ GAGAL" if is_failed else "🟢 AKTIF",
            "is_failed": is_failed
        })
        
    df_ldb = pd.DataFrame(leaderboard_data).sort_values("Poin", ascending=False).reset_index(drop=True)
    if not df_ldb.empty: df_ldb['Peringkat'] = df_ldb.index + 1
    return df_ldb, pd.DataFrame(trajectory_records), current_prog_day

# ==========================================
# 3. SISTEM LOGIN
# ==========================================
st.set_page_config(page_title="60 Days Race", layout="centered")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'current_user': "", 'current_name': "", 'current_role': ""})

def login():
    u, p = st.session_state['l_u'].strip(), st.session_state['l_p'].strip()
    conn = sqlite3.connect(DB_NAME)
    res = conn.execute("SELECT full_name, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
    conn.close()
    if res: st.session_state.update({'logged_in': True, 'current_user': u, 'current_name': res[0], 'current_role': res[1]})
    else: st.error("❌ Login Gagal")

if not st.session_state['logged_in']:
    st.title("🔒 Login")
    with st.form("l"):
        st.text_input("Username", key="l_u")
        st.text_input("Password", type="password", key="l_p")
        st.form_submit_button("Masuk", on_click=login, use_container_width=True)
    st.stop()

# ==========================================
# 4. DASHBOARD ADMIN
# ==========================================
if st.session_state['current_role'] == "admin":
    st.title("👑 Admin Control")
    # Setup Tanggal Mulai Program
    sd_current = get_setting('start_date')
    new_sd = st.date_input("Atur Tanggal Mulai Hari Ke-1:", value=datetime.datetime.strptime(sd_current, '%Y-%m-%d').date())
    if st.button("Simpan Tanggal Mulai"):
        set_setting('start_date', new_sd.strftime('%Y-%m-%d'))
        st.success("Tanggal disimpan! Database akan menghitung ulang strike.")
        st.rerun()

    st.divider()
    df_l, _, _ = evaluate_participants()
    st.subheader("Monitoring Peserta")
    st.dataframe(df_l[['Peringkat', 'Nama', 'Status', 'Strikes', 'Poin']], use_container_width=True, hide_index=True)
    
    for _, p in df_l.iterrows():
        with st.expander(f"Otoritas Reset: {p['Nama']}"):
            if st.button(f"♻️ Pulihkan {p['Username']}", key=f"rs_{p['Username']}", use_container_width=True):
                c = sqlite3.connect(DB_NAME)
                c.execute("DELETE FROM check_ins WHERE username=?", (p['Username'],))
                c.execute("UPDATE users SET is_failed=0 WHERE username=?", (p['Username'],))
                c.commit()
                st.rerun()
    st.stop()

# ==========================================
# 5. DASHBOARD PESERTA (ORDERED)
# ==========================================
df_leaderboard, df_trajectory, prog_day = evaluate_participants()
my_data = df_leaderboard[df_leaderboard['Username'] == st.session_state['current_user']].iloc[0]

# --- 1. PANEL PRESENSI (PALING ATAS) ---
st.title("📅 Panel Presensi Harian")

if my_data['is_failed']:
    st.error(f"💀 **ANDA GAGAL.**\n\nAbsen/Tidak Login Anda: {my_data['Strikes']}. Batas maksimal adalah 2 kali.")
    st.stop()

# Kondisi Waktu
is_test = (get_setting('test_mode') == 'on')
is_libur = (get_setting('app_status') == 'holiday')
wib_tz = datetime.timezone(datetime.timedelta(hours=7))
t_now = datetime.datetime.now(wib_tz)
is_time = (20 <= t_now.hour <= 22) # 20.00 - 23.00

if is_libur: st.info("🏖️ Hari Libur Nasional")
elif is_time or is_test: st.success(f"✅ Jendela Terbuka (Hari Ke-{prog_day})")
else: st.warning(f"🔒 Terkunci. Buka pukul 20.00 WIB (Sekarang: {t_now.strftime('%H:%M')})")

can_check = (is_time or is_test) and not is_libur

# Tombol Presensi dengan Key Unik
c1, c2 = st.columns(2)
lbl_in = f"✅ Check-In (H-{prog_day})" if can_check else "🔒 Terkunci"
lbl_ms = f"❌ Bolos (H-{prog_day})" if can_check else "🔒 Terkunci"

if c1.button(lbl_in, type="primary", disabled=not can_check, key="btn_in_main", use_container_width=True):
    sqlite3.connect(DB_NAME).execute("INSERT OR REPLACE INTO check_ins VALUES (?,?,?,?)", (st.session_state['current_user'], prog_day, 'checked_in', datetime.datetime.now())).connection.commit()
    st.rerun()
if c2.button(lbl_ms, type="secondary", disabled=not can_check, key="btn_ms_main", use_container_width=True):
    sqlite3.connect(DB_NAME).execute("INSERT OR REPLACE INTO check_ins VALUES (?,?,?,?)", (st.session_state['current_user'], prog_day, 'missed', datetime.datetime.now())).connection.commit()
    st.rerun()

st.info(f"📊 Status Kehadiran: **{my_data['Strikes']}** (Gagal jika > 2)")

# --- 2. BALAPAN (GRAFIK) ---
st.divider()
st.subheader("🚴 Balapan Produktivitas 60 Hari")
if not df_trajectory.empty:
    chart = alt.Chart(df_trajectory).mark_line(strokeWidth=3).encode(
        x=alt.X('Hari:Q', scale=alt.Scale(domain=[0, 60])),
        y='Poin:Q', color='Nama:N'
    )
    st.altair_chart(chart.properties(height=250), use_container_width=True)

# --- 3. LEADERBOARD ---
st.subheader("🏆 Klasemen Sementara")
st.dataframe(df_leaderboard[['Peringkat', 'Nama', 'Poin', 'Bintang', 'Status']], use_container_width=True, hide_index=True)

if st.sidebar.button("Log Out"):
    st.session_state['logged_in'] = False
    st.rerun()

import datetime
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt

# Tetap menggunakan DB v5 agar kompatibel dengan data yang sudah berjalan
DB_NAME = "prod_tracker_v5.db"

# ====================================================================
# 1. SETUP DATABASE
# ====================================================================
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
        ("resetapp", "Super Admin (Anda)", "12345#", "admin", "Mengelola 60 Hari Produktivitas", 0),
        ("azwa1", "Azwa", "12345#", "peserta", "", 0),
        ("iqbal2", "Iqbal", "12345#", "peserta", "", 0),
        ("habib3", "Habib", "12345#", "peserta", "", 0),
        ("pandu4", "Pandu", "12345#", "peserta", "", 0)
    ]
    c.executemany("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)", initial_users)
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('app_status', 'active')")
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('test_mode', 'off')")
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
# 2. LOGIKA EVALUASI (POIN, GAGAL, & BINTANG)
# ====================================================================
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
                
                # Pemicu Gagal: 2x bolos beruntun ATAU >1x bolos dalam 7 hari
                if (consecutive_misses >= 2 or current_block_misses > 1) and not is_failed:
                    is_failed = True
                    conn_f = sqlite3.connect(DB_NAME)
                    conn_f.execute("UPDATE users SET is_failed=1 WHERE username=?", (uname,))
                    conn_f.commit()
                    conn_f.close()
                    
            score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
            
        trajectory_records.extend(score_history)
        
        leaderboard_data.append({
            "Peringkat": 0, 
            "Nama": name, 
            "Username": uname, 
            "Total Poin": cumulative_score, 
            "Hari": max_day,
            "Bintang": "⭐" * stars_earned if stars_earned > 0 else "—",
            "Status": "❌ GAGAL" if is_failed else "🟢 AKTIF",
            "is_failed": is_failed,
            "kemarin_bolos": (consecutive_misses == 1),
            "sisa_kuota": 1 - current_block_misses,
            "awal_blok": ((max_day // 7) * 7) + 1
        })
        
    df_ldb = pd.DataFrame(leaderboard_data)
    if not df_ldb.empty:
        df_ldb = df_ldb.sort_values(by="Total Poin", ascending=False).reset_index(drop=True)
        df_ldb['Peringkat'] = df_ldb.index + 1
        
    return df_ldb, pd.DataFrame(trajectory_records)

# ====================================================================
# 3. SISTEM LOGIN
# ====================================================================
st.set_page_config(page_title="Productivity Race Tracker", layout="centered")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'current_user': "", 'current_name': "", 'current_role': ""})

def login():
    u, p = st.session_state['l_u'].strip(), st.session_state['l_p'].strip()
    conn = sqlite3.connect(DB_NAME)
    res = conn.execute("SELECT full_name, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
    conn.close()
    if res: st.session_state.update({'logged_in': True, 'current_user': u, 'current_name': res[0], 'current_role': res[1]})
    else: st.error("❌ Username atau Password salah.")

if not st.session_state['logged_in']:
    st.title("🔒 Portal Login Produktivitas")
    with st.form("l"):
        st.text_input("Username", key="l_u")
        st.text_input("Password", type="password", key="l_p")
        st.form_submit_button("Masuk", on_click=login, use_container_width=True)
    st.stop()

# ====================================================================
# 4. DASHBOARD SUPER ADMIN
# ====================================================================
if st.session_state['current_role'] == "admin":
    st.title("👑 Panel Super Admin (Live Sync)")
    
    mode_test = get_setting('test_mode')
    new_test = st.toggle("🔓 Buka Kunci Waktu 24 Jam (Mode Testing)", value=(mode_test == 'on'))
    if new_test != (mode_test == 'on'):
        set_setting('test_mode', 'on' if new_test else 'off')
        st.rerun()
        
    app_status = get_setting('app_status')
    if app_status == 'active':
        if st.button("Deklarasikan 🔴 LIBUR NASIONAL Hari Ini", type="primary", use_container_width=True):
            set_setting('app_status', 'holiday')
            st.rerun()
    else:
        if st.button("Kembalikan ke Mode 🟢 AKTIF", type="primary", use_container_width=True):
            set_setting('app_status', 'active')
            st.rerun()
            
    st.divider()
    
    st.subheader("📊 Papan Peringkat Live")
    df_l, df_t = evaluate_participants()
    
    if not df_l.empty:
        # Kolom Tujuan Utama dihapus dari tampilan agar bersih
        st.dataframe(
            df_l[['Peringkat', 'Nama', 'Status', 'Total Poin', 'Bintang']], 
            use_container_width=True, 
            hide_index=True
        )
        
        if not df_t.empty:
            line = alt.Chart(df_t).mark_line(strokeWidth=2).encode(
                x=alt.X('Hari:Q', scale=alt.Scale(domain=[0, 60])),
                y='Poin:Q', color='Nama:N'
            )
            st.altair_chart(line.properties(height=200), use_container_width=True)
            
    st.divider()
    
    st.subheader("🛠️ Simulasi Klik & Reset Otoritas")
    st.write("Perubahan di bawah ini akan langsung memperbarui tabel di atas secara instan.")
    
    for _, p in df_l.iterrows():
        with st.expander(f"Kelola: {p['Nama']} (Poin: {p['Total Poin']} | {p['Status']})"):
            h_next = p['Hari'] + 1
            c1, c2 = st.columns(2)
            
            if c1.button(f"✅ Input Check-In (H-{h_next})", key=f"in_{p['Username']}", use_container_width=True):
                conn_ex = sqlite3.connect(DB_NAME)
                conn_ex.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", 
                                (p['Username'], h_next, 'checked_in', datetime.datetime.now()))
                conn_ex.commit()
                conn_ex.close()
                st.rerun()
                
            if c2.button(f"❌ Input Bolos (H-{h_next})", key=f"ms_{p['Username']}", use_container_width=True):
                conn_ex = sqlite3.connect(DB_NAME)
                conn_ex.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", 
                                (p['Username'], h_next, 'missed', datetime.datetime.now()))
                conn_ex.commit()
                conn_ex.close()
                st.rerun()
                
            st.write("")
            if st.button(f"♻️ Reset Skor dari 0 & Pulihkan Status {p['Username']}", key=f"rst_{p['Username']}", type="secondary", use_container_width=True):
                conn_r = sqlite3.connect(DB_NAME)
                conn_r.execute("DELETE FROM check_ins WHERE username=?", (p['Username'],))
                conn_r.execute("UPDATE users SET is_failed=0 WHERE username=?", (p['Username'],))
                conn_r.commit()
                conn_r.close()
                st.success(f"Data {p['Nama']} di-reset!")
                st.rerun()

    st.divider()
    if st.button("Log Out Admin", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()
    st.stop()

# ====================================================================
# 5. DASHBOARD PESERTA (REORDERED & CLEANED)
# ====================================================================
df_leaderboard, df_trajectory = evaluate_participants()
my_data = df_leaderboard[df_leaderboard['Username'] == st.session_state['current_user']].iloc[0]

# --- BAGIAN A: PANEL PRESENSI HARIAN (DIPINDAHKAN KE PALING ATAS) ---
st.title("📅 Panel Presensi Harian")

if my_data['Status'] == "❌ GAGAL":
    st.error("💀 **ANDA TELAH TERELIMINASI DARI PROGRAM.**\n\nAnda telah melanggar batas toleransi absen. Akses presensi ditutup.")
    st.stop()

# Peringatan Kritis
if my_data['kemarin_bolos']:
    st.warning("⚠️ **KRITIS:** Anda bolos kemarin. Jika bolos lagi hari ini, Anda langsung GAGAL (Never Miss Twice).")
elif my_data['sisa_kuota'] <= 0:
    st.warning(f"⚠️ **KUOTA MINGGU INI HABIS:** Anda sudah bolos 1x di siklus minggu ini. Bolos lagi = GAGAL.")
else:
    st.info(f"💡 Kuota aman. Sisa hak bolos minggu ini: {my_data['sisa_kuota']} kali.")

is_test = (get_setting('test_mode') == 'on')
is_libur = (get_setting('app_status') == 'holiday')

wib = datetime.timezone(datetime.timedelta(hours=7))
t_now = datetime.datetime.now(wib)
is_time = (datetime.time(20,0) <= t_now.time() <= datetime.time(23,0))

t_str = t_now.strftime("%H:%M:%S WIB")

if is_libur: 
    st.success(f"📢 **HARI LIBUR NASIONAL** | Waktu: **{t_str}**\n\nPresensi diliburkan. Poin dan streak Bintang Anda aman.")
    conn = sqlite3.connect(DB_NAME)
    ulogs = pd.read_sql_query("SELECT day_number FROM check_ins WHERE username=?", conn, params=(st.session_state['current_user'],))['day_number'].tolist()
    ht = max(ulogs) + 1 if ulogs else 1
    if ht <= 60:
        conn.execute("INSERT OR IGNORE INTO check_ins VALUES (?, ?, ?, ?)", (st.session_state['current_user'], ht, "holiday", datetime.datetime.now())).connection.commit()
    conn.close()
    st.stop()
elif is_test: st.warning("🛠️ MODE TESTING: Tombol aktif 24 Jam.")
elif is_time: st.success(f"✅ JENDELA TERBUKA | Waktu: **{t_str}** (Batas: 20.00-23.00 WIB)")
else: st.warning(f"🔒 PRESENSI TERTUTUP | Waktu: **{t_str}**\n\nDibuka pukul 20.00-23.00 WIB.")

can_check = (is_time or is_test) and not is_libur

conn = sqlite3.connect(DB_NAME)
ulogs_dict = pd.read_sql_query("SELECT day_number, status FROM check_ins WHERE username=?", conn, params=(st.session_state['current_user'],)).set_index('day_number')['status'].to_dict()

h_target = 1
while h_target in ulogs_dict: h_target += 1

if h_target > 60:
    st.success("🎉 **SELAMAT! Anda telah menyelesaikan program 60 Hari!**")
else:
    c1, c2 = st.columns(2)
    if c1.button(f"✅ Check-In (H-{h_target})", type="primary", disabled=not can_check, use_container_width=True):
        conn.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (st.session_state['current_user'], h_target, 'checked_in', datetime.datetime.now())).connection.commit()
        st.rerun()
    if c2.button(f"❌ Bolos (H-{h_target})", type="secondary", disabled=not can_check, use_container_width=True):
        conn.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (st.session_state['current_user'], h_target, 'missed', datetime.datetime.now())).connection.commit()
        st.rerun()
conn.close()

# Riwayat Visual Grid
st.markdown("<br>**Riwayat Visual Anda:**", unsafe_allow_html=True)
gcols = st.columns(10)
for d in range(1, 61):
    icn = "⚪"
    if d in ulogs_dict:
        v = ulogs_dict[d]
        if v == "checked_in": icn = "🟢"
        elif v == "missed": icn = "🔴"
        elif v == "holiday": icn = "🔵"
    with gcols[(d-1)%10]: st.markdown(f"<div style='text-align:center; font-size:10px;'>H{d}<br>{icn}</div>", unsafe_allow_html=True)

# Tampilan Metrik Pribadi Tepat di Bawah Presensi
st.write("")
col_m1, col_m2 = st.columns(2)
with col_m1: st.metric("Total Poin Anda", f"{my_data['Total Poin']} Poin")
with col_m2: st.metric("Lencana Bintang ⭐", my_data['Bintang'])

st.divider()

# --- BAGIAN B: BALAPAN PRODUKTIVITAS 60 HARI ---
st.subheader("🚴 Balapan Produktivitas 60 Hari")

if not df_trajectory.empty:
    line_chart = alt.Chart(df_trajectory).mark_line(strokeWidth=3).encode(
        x=alt.X('Hari:Q', scale=alt.Scale(domain=[0, 60]), title="Lintasan Hari (Start ➔ Finish)"),
        y=alt.Y('Poin:Q', title="Akumulasi Poin"),
        color=alt.Color('Nama:N', legend=alt.Legend(orient="bottom", title=None))
    )
    
    idx_max = df_trajectory.groupby('Nama')['Hari'].idxmax()
    df_endpoints = df_trajectory.loc[idx_max]
    
    bicycles = alt.Chart(df_endpoints).mark_point(filled=True, size=150, shape="circle").encode(
        x='Hari:Q', y='Poin:Q', color='Nama:N'
    )
    
    labels = alt.Chart(df_endpoints).mark_text(
        align='left', dx=10, dy=-5, fontWeight='bold', fontSize=12
    ).encode(
        x='Hari:Q', y='Poin:Q', text='Nama:N', color='Nama:N'
    )
    
    st.altair_chart((line_chart + bicycles + labels).properties(height=280), use_container_width=True)

st.divider()

# --- BAGIAN C: KLASEMEN SEMENTARA (LEADERBOARD) ---
st.subheader("🏆 Klasemen Sementara (Leaderboard)")

# Menampilkan dataframe bersih tanpa kolom 'Tujuan Utama'
st.dataframe(
    df_leaderboard[['Peringkat', 'Nama', 'Total Poin', 'Bintang', 'Status']], 
    use_container_width=True, 
    hide_index=True
)

st.divider()
if st.button("Log Out Akun", use_container_width=True):
    st.session_state['logged_in'] = False
    st.rerun()


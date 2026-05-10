import datetime
import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. SETUP DATABASE & AKUN BARU
# ==========================================
def init_db():
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    
    # Tabel Pengguna (Username + Password + Role)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, full_name TEXT, password TEXT, role TEXT)''')
    
    # Tabel Log Check-in
    c.execute('''CREATE TABLE IF NOT EXISTS check_ins 
                 (username TEXT, day_number INTEGER, status TEXT, timestamp DATETIME,
                  PRIMARY KEY (username, day_number))''')
    
    # Tabel Pengaturan Sistem (Untuk fitur Libur Nasional)
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Input Data Akun Super Admin & 4 Peserta
    initial_users = [
        ("resetapp", "Super Admin (Anda)", "12345#", "admin"),
        ("azwa1", "Azwa", "12345#", "peserta"),
        ("iqbal2", "Iqbal", "12345#", "peserta"),
        ("habib3", "Habib", "12345#", "peserta"),
        ("pandu4", "Pandu", "12345#", "peserta")
    ]
    c.executemany("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", initial_users)
    
    # Set default status aplikasi aktif jika belum ada
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('app_status', 'active')")
    
    conn.commit()
    conn.close()

init_db()

# FUNGSI BANTU PENGATURAN SISTEM
def get_app_status():
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    c.execute("SELECT value FROM system_settings WHERE key='app_status'")
    res = c.fetchone()
    conn.close()
    return res[0] if res else "active"

def set_app_status(status):
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    c.execute("UPDATE system_settings SET value=? WHERE key='app_status'", (status,))
    conn.commit()
    conn.close()

# ==========================================
# 2. LOGIKA POIN ARITMATIKA
# ==========================================
def get_user_scores():
    conn = sqlite3.connect("prod_tracker.db")
    # Hanya hitung yang memiliki role 'peserta'
    users = pd.read_sql_query("SELECT * FROM users WHERE role='peserta'", conn)
    records = pd.read_sql_query("SELECT * FROM check_ins", conn)
    conn.close()
    
    trajectory_data = {}
    current_leaderboard = []
    
    for _, user in users.iterrows():
        uname = user['username']
        name = user['full_name']
        
        user_records = records[records['username'] == uname].set_index('day_number')['status'].to_dict()
        
        cumulative_score = 0
        score_history = [0] 
        
        max_day_for_user = max(user_records.keys()) if user_records else 0
        
        for day in range(1, max_day_for_user + 1):
            status = user_records.get(day, "missed") 
            if status == "checked_in":
                cumulative_score += day
            else:
                cumulative_score -= day
            score_history.append(cumulative_score)
            
        trajectory_data[name] = score_history
        current_leaderboard.append({
            "Nama": name, 
            "Username": uname, 
            "Total Poin": cumulative_score, 
            "Hari Terakhir": max_day_for_user
        })
        
    df_trajectory = pd.DataFrame.from_dict(trajectory_data, orient='index').transpose()
    df_trajectory.index.name = 'Hari'
    
    if current_leaderboard:
        df_leaderboard = pd.DataFrame(current_leaderboard).sort_values(by="Total Poin", ascending=False).reset_index(drop=True)
    else:
        df_leaderboard = pd.DataFrame(columns=["Nama", "Username", "Total Poin", "Hari Terakhir"])
        
    return df_leaderboard, df_trajectory

# ==========================================
# 3. SISTEM LOGIN (USERNAME & PASSWORD)
# ==========================================
st.set_page_config(page_title="Productivity Tracker", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['current_user'] = ""
    st.session_state['current_name'] = ""
    st.session_state['current_role'] = ""

def login():
    input_uname = st.session_state['login_uname'].strip()
    input_pass = st.session_state['login_pass'].strip()
    
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    c.execute("SELECT full_name, role FROM users WHERE username=? AND password=?", (input_uname, input_pass))
    result = c.fetchone()
    conn.close()
    
    if result:
        st.session_state['logged_in'] = True
        st.session_state['current_user'] = input_uname
        st.session_state['current_name'] = result[0]
        st.session_state['current_role'] = result[1]
    else:
        st.error("❌ Akses Ditolak: Username atau Password salah.")

if not st.session_state['logged_in']:
    st.title("🔒 Portal Login Produktivitas")
    st.markdown("Silakan masuk menggunakan **Username** dan **Password** Anda.")
    
    with st.form("login_form"):
        st.text_input("Username", key="login_uname")
        st.text_input("Password", type="password", key="login_pass")
        st.form_submit_button("Log In", on_click=login)
    st.stop()

# ====================================================
# 4. DASHBOARD KHUSUS SUPER ADMIN
# ====================================================
uname_aktif = st.session_state['current_user']
nama_aktif = st.session_state['current_name']
role_aktif = st.session_state['current_role']

st.sidebar.success(f"Masuk sebagai:\n**{nama_aktif}**")
if st.sidebar.button("Log Out"):
    st.session_state['logged_in'] = False
    st.rerun()

# JIKA YANG LOGIN ADALAH SUPER ADMIN
if role_aktif == "admin":
    st.title("👑 Dashboard Super Admin")
    st.divider()
    
    # KONTROL STATUS APLIKASI (LIBUR NASIONAL)
    st.subheader("🛑 Kontrol Operasional Sistem")
    status_sekarang = get_app_status()
    
    col_stat1, col_stat2 = st.columns([2, 2])
    with col_stat1:
        if status_sekarang == "active":
            st.info("Status Sistem Saat Ini: **🟢 AKTIF (Peserta wajib Check-In)**")
        else:
            st.warning("Status Sistem Saat Ini: **🔴 LIBUR NASIONAL (Check-in dikunci, bebas penalti)**")
            
    with col_stat2:
        if status_sekarang == "active":
            if st.button("Ubah ke Mode 🔴 LIBUR NASIONAL", type="primary"):
                set_app_status("holiday")
                st.rerun()
        else:
            if st.button("Ubah ke Mode 🟢 SISTEM AKTIF", type="primary"):
                set_app_status("active")
                st.rerun()
                
    st.divider()
    
    # MONITORING KINERJA PESERTA
    st.subheader("📊 Monitoring Kinerja Peserta")
    df_leaderboard, df_trajectory = get_user_scores()
    
    if not df_leaderboard.empty:
        st.dataframe(df_leaderboard[['Nama', 'Username', 'Total Poin', 'Hari Terakhir']], use_container_width=True, hide_index=True)
        st.line_chart(df_trajectory)
    else:
        st.write("Belum ada data check-in peserta.")
        
    st.stop() # Hentikan eksekusi di sini agar admin tidak melihat panel check-in peserta

# ====================================================
# 5. DASHBOARD PESERTA & PANEL CHECK-IN
# ====================================================
st.title("🚀 Dashboard Pemantauan 60 Hari Produktivitas")
st.divider()

# Cek apakah hari ini diliburkan oleh admin
app_status = get_app_status()
is_libur = (app_status == "holiday")

if is_libur:
    st.warning("📢 **PEMBERITAHUAN DARI SUPER ADMIN:** Hari ini ditetapkan sebagai **Libur Nasional**. Pengisian Check-In sementara dinonaktifkan. Poin Anda aman dan tidak akan terkena penalti pengurangan.")

df_leaderboard, df_trajectory = get_user_scores()
user_current_data = df_leaderboard[df_leaderboard['Username'] == uname_aktif]
poin_saya = user_current_data['Total Poin'].values[0] if not user_current_data.empty else 0
hari_terakhir_saya = user_current_data['Hari Terakhir'].values[0] if not user_current_data.empty else 0

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📈 Grafik Persaingan Poin")
    st.line_chart(df_trajectory)
with col2:
    st.metric(label="Total Poin Anda Saat Ini", value=f"{poin_saya} Poin", delta=f"Hari Aktif: {hari_terakhir_saya} / 60")
    st.subheader("🏆 Leaderboard")
    st.dataframe(df_leaderboard[['Nama', 'Total Poin']], use_container_width=True, hide_index=True)

st.divider()

# PANEL CHECK-IN HARIAN (DENGAN KUNCI WIB & KUNCI LIBUR)
st.subheader("📅 Panel Check-In Harian Anda")

wib_tz = datetime.timezone(datetime.timedelta(hours=7))
waktu_sekarang = datetime.datetime.now(wib_tz)
jam_sekarang = waktu_sekarang.time()

jam_mulai = datetime.time(20, 0)
jam_selesai = datetime.time(23, 0)
status_dalam_jendela = jam_mulai <= jam_sekarang <= jam_selesai

tampilan_waktu = waktu_sekarang.strftime("%H:%M:%S WIB")

# Tampilan informasi waktu/libur
if is_libur:
    st.info(f"🔒 **Check-In Terkunci (Mode Libur)** | Waktu Server: **{tampilan_waktu}**")
elif status_dalam_jendela:
    st.success(f"⏳ **Jendela Check-In TERBUKA** | Waktu Server: **{tampilan_waktu}** (Batas: 20.00 - 23.00 WIB)")
else:
    st.warning(f"🔒 **Jendela Check-In TERTUTUP** | Waktu Server: **{tampilan_waktu}**\n\n*Check-in hanya dapat dilakukan antara pukul **20.00 hingga 23.00 WIB**.*")

conn = sqlite3.connect("prod_tracker.db")
user_logs = pd.read_sql_query("SELECT day_number, status FROM check_ins WHERE username=?", conn, params=(uname_aktif,)).set_index('day_number')['status'].to_dict()

hari_target = 1
while hari_target in user_logs:
    hari_target += 1

if hari_target > 60:
    st.success("🎉 Selamat! Anda telah menyelesaikan program 60 Hari.")
else:
    st.markdown(f"**Target Hari Ini:** Anda berada di **Hari Ke-{hari_target}** (Bobot: **{hari_target} Poin**)")
    
    # Tombol hanya aktif jika BUKAN libur DAN DALAM jendela waktu WIB
    tombol_aktif = status_dalam_jendela and not is_libur
    
    if is_libur:
        label_btn = "🔒 Sistem Libur"
    elif not status_dalam_jendela:
        label_btn = "🔒 Check In Terkunci"
    else:
        label_btn = f"✅ Check In Hari Ke-{hari_target}"
        
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button(label_btn, type="primary", disabled=not tombol_aktif, use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", 
                      (uname_aktif, hari_target, "checked_in", datetime.datetime.now()))
            conn.commit()
            st.rerun()
            
    with col_btn2:
        if st.button(f"❌ Lewati / Bolos Hari Ke-{hari_target}", type="secondary", disabled=is_libur, use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", 
                      (uname_aktif, hari_target, "missed", datetime.datetime.now()))
            conn.commit()
            st.rerun()
            
conn.close()

st.markdown("### Riwayat 60 Hari Anda")
grid_cols = st.columns(10)
for d in range(1, 61):
    status_icon = "⚪" 
    if d in user_logs:
        status_icon = "🟢" if user_logs[d] == "checked_in" else "🔴"
    with grid_cols[(d-1) % 10]:
        st.markdown(f"<div style='text-align:center; padding:5px;'><b>H-{d}</b><br>{status_icon}</div>", unsafe_allow_html=True)

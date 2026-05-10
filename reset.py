import datetime
import sqlite3
import pandas as pd
import streamlit as st
import altair as alt

# Gunakan DB v3 untuk mengakomodasi penambahan kolom "goal" dan status kegagalan
DB_NAME = "prod_tracker_v3.db"

# ==========================================
# 1. SETUP DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabel Pengguna ditambah kolom "goal" dan "is_failed"
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
    c.execute("INSERT OR IGNORE INTO system_settings VALUES ('app_status', 'active')")
    
    conn.commit()
    conn.close()

init_db()

# FUNGSI BANTU DATABASE
def get_app_status():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM system_settings WHERE key='app_status'")
    res = c.fetchone()
    conn.close()
    return res[0] if res else "active"

def set_app_status(status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Catat hari libur ke tabel check_ins untuk semua peserta aktif agar sinkron
    c.execute("UPDATE system_settings SET value=? WHERE key='app_status'", (status,))
    conn.commit()
    conn.close()

def update_user_goal(username, goal_text):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET goal=? WHERE username=?", (goal_text[:50], username))
    conn.commit()
    conn.close()

def set_user_failed(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET is_failed=1 WHERE username=?", (username,))
    conn.commit()
    conn.close()

# ====================================================================
# 2. LOGIKA EVALUASI KETAT (BOLOS, GAGAL, & LENCANA BINTANG)
# ====================================================================
def evaluate_participants():
    """
    Menghitung poin, mengevaluasi status GAGAL (bolos berurutan / melebihi kuota blok 7 harian),
    serta menghitung lencana Bintang secara dinamis.
    """
    conn = sqlite3.connect(DB_NAME)
    users = pd.read_sql_query("SELECT * FROM users WHERE role='peserta'", conn)
    records = pd.read_sql_query("SELECT * FROM check_ins", conn)
    conn.close()
    
    leaderboard_data = []
    trajectory_records = []
    
    # Ambil status libur nasional dari sistem (hari-hari apa saja yang libur)
    # Untuk simulasi ini, kita anggap hari yang ditandai 'holiday' di logs adalah libur
    
    for _, user in users.iterrows():
        uname = user['username']
        name = user['full_name']
        goal = user['goal']
        is_failed = bool(user['is_failed'])
        
        user_records = records[records['username'] == uname].sort_values('day_number')
        records_dict = user_records.set_index('day_number')['status'].to_dict()
        
        cumulative_score = 0
        score_history = [{"Hari": 0, "Poin": 0, "Nama": name}]
        
        max_day = max(records_dict.keys()) if records_dict else 0
        
        # Variabel Evaluasi Gagal & Bintang
        consecutive_misses = 0
        active_streak_for_stars = 0
        stars_earned = 0
        
        # Evaluasi Blok 7-Harian (Hari 1-7, 8-14, dst)
        current_block_misses = 0
        
        for day in range(1, max_day + 1):
            status = records_dict.get(day, "missed")
            
            # Reset hitungan blok setiap kelipatan 7 hari (awal blok baru)
            if (day - 1) % 7 == 0:
                current_block_misses = 0
                
            if status == "holiday":
                # Libur nasional tidak menambah poin, tidak memotong poin, tidak mereset streak
                score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
                continue
                
            if status == "checked_in":
                cumulative_score += day
                consecutive_misses = 0
                
                # Hitung lencana bintang (setiap 15 hari aktif berturut-turut)
                active_streak_for_stars += 1
                if active_streak_for_stars == 15:
                    if stars_earned < 4: # Maksimal 4 badge dalam 60 hari
                        stars_earned += 1
                    active_streak_for_stars = 0 # Reset untuk mengejar bintang berikutnya
            else:
                # Status Missed / Bolos
                cumulative_score -= day
                consecutive_misses += 1
                current_block_misses += 1
                active_streak_for_stars = 0 # Runtuh sudah streak lencana bintang
                
                # PEMICU GAGAL 1: Bolos 2 hari berturut-turut
                # PEMICU GAGAL 2: Bolos > 1 kali dalam blok 7 hari yang sama
                if consecutive_misses >= 2 or current_block_misses > 1:
                    is_failed = True
                    set_user_failed(uname)
                    
            score_history.append({"Hari": day, "Poin": cumulative_score, "Nama": name})
            
        trajectory_records.extend(score_history)
        
        # Peringatan dini untuk dashboard: apakah kemarin bolos?
        kemarin_bolos = (consecutive_misses == 1)
        # Sisa kuota bolos di blok minggu ini
        sisa_kuota_blok = 1 - current_block_misses
        
        leaderboard_data.append({
            "Nama": name,
            "Username": uname,
            "Tujuan Utama": goal if goal else "🎯 Belum menetapkan tujuan",
            "Total Poin": cumulative_score,
            "Hari Terakhir": max_day,
            "Bintang": "⭐" * stars_earned if stars_earned > 0 else "—",
            "Status": "❌ GAGAL" if is_failed else "🟢 AKTIF",
            "is_failed": is_failed,
            "kemarin_bolos": kemarin_bolos,
            "sisa_kuota_blok": sisa_kuota_blok,
            "hari_blok_awal": ((max_day // 7) * 7) + 1
        })
        
    df_leaderboard = pd.DataFrame(leaderboard_data) if leaderboard_data else pd.DataFrame()
    df_trajectory = pd.DataFrame(trajectory_records) if trajectory_records else pd.DataFrame()
    
    return df_leaderboard, df_trajectory

# ====================================================================
# 3. SISTEM LOGIN UTAMA
# ====================================================================
st.set_page_config(page_title="Productivity Race Tracker", layout="centered") # Centered lebih bersahabat untuk Mobile

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'current_user': "", 'current_name': "", 'current_role': ""})

def login():
    uname = st.session_state['login_uname'].strip()
    pwd = st.session_state['login_pass'].strip()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT full_name, role FROM users WHERE username=? AND password=?", (uname, pwd))
    res = c.fetchone()
    conn.close()
    
    if res:
        st.session_state.update({'logged_in': True, 'current_user': uname, 'current_name': res[0], 'current_role': res[1]})
    else:
        st.error("❌ Username atau Password salah.")

if not st.session_state['logged_in']:
    st.title("🔒 Portal Login Produktivitas")
    with st.form("login_form"):
        st.text_input("Username", key="login_uname")
        st.text_input("Password", type="password", key="login_pass")
        st.form_submit_button("Log In", on_click=login, use_container_width=True)
    st.stop()

uname_aktif = st.session_state['current_user']
nama_aktif = st.session_state['current_name']
role_aktif = st.session_state['current_role']

# Sidebar minimalis untuk mobile
with st.sidebar:
    st.success(f"👤 **{nama_aktif}**")
    if st.button("Log Out", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()

# ====================================================================
# 4. DASHBOARD SUPER ADMIN
# ====================================================================
if role_aktif == "admin":
    st.title("👑 Panel Kontrol Super Admin")
    st.divider()
    
    status_sekarang = get_app_status()
    st.subheader("🛑 Kontrol Hari Libur Nasional")
    
    if status_sekarang == "active":
        st.info("Sistem: **🟢 AKTIF (Presensi Berjalan)**")
        if st.button("Deklarasikan 🔴 LIBUR NASIONAL Hari Ini", type="primary", use_container_width=True):
            set_app_status("holiday")
            st.rerun()
    else:
        st.warning("Sistem: **🔴 LIBUR NASIONAL (Presensi Dikunci)**")
        if st.button("Kembalikan ke Mode 🟢 AKTIF", type="primary", use_container_width=True):
            set_app_status("active")
            st.rerun()
            
    st.divider()
    st.subheader("📊 Monitoring Klasemen Peserta")
    df_ldb, _ = evaluate_participants()
    if not df_ldb.empty:
        st.dataframe(df_ldb[['Nama', 'Status', 'Total Poin', 'Bintang', 'Tujuan Utama']], use_container_width=True, hide_index=True)
    st.stop()

# ====================================================================
# 5. DASHBOARD PESERTA & GRAFIK BALAPAN SEPEDA (ALTAIR)
# ====================================================================
st.title("🚴 Grafik Balapan Produktivitas")

# Ambil data evaluasi terbaru
df_leaderboard, df_trajectory = evaluate_participants()
my_data = df_leaderboard[df_leaderboard['Username'] == uname_aktif].iloc[0]

# TAMPILAN GRAFIK BALAPAN (KIRI KE KANAN) MENGGUNAKAN ALTAIR
if not df_trajectory.empty:
    # 1. Garis lintasan (Trajectory)
    line_chart = alt.Chart(df_trajectory).mark_line(strokeWidth=3).encode(
        x=alt.X('Hari:Q', scale=alt.Scale(domain=[0, 60]), title="Lintasan Hari (Start ➔ Finish)"),
        y=alt.Y('Poin:Q', title="Akumulasi Poin"),
        color=alt.Color('Nama:N', legend=alt.Legend(orient="bottom", title=None))
    )
    
    # Ambil titik posisi terakhir setiap peserta sebagai ikon "Sepeda" yang sedang memimpin
    idx_max = df_trajectory.groupby('Nama')['Hari'].idxmax()
    df_endpoints = df_trajectory.loc[idx_max]
    
    # 2. Titik Sepeda (Marker di ujung garis)
    bicycles = alt.Chart(df_endpoints).mark_point(filled=True, size=150, shape="circle").encode(
        x='Hari:Q',
        y='Poin:Q',
        color='Nama:N'
    )
    
    # 3. Label Nama Peserta menempel di titik sepeda
    labels = alt.Chart(df_endpoints).mark_text(
        align='left', dx=10, dy=-5, fontWeight='bold', fontSize=12
    ).encode(
        x='Hari:Q',
        y='Poin:Q',
        text='Nama:N',
        color='Nama:N'
    )
    
    # Gabungkan layer grafik agar menjadi visual racing yang dinamis dan mobile friendly
    racing_chart = (line_chart + bicycles + labels).properties(height=300)
    st.altair_chart(racing_chart, use_container_width=True)

# PANEL INFORMASI PRIBADI (MOBILE FRIENDLY STACK)
st.divider()
st.subheader("🎯 North Star & Pencapaian Anda")

# INPUT TUJUAN UTAMA (Maksimal 50 Karakter)
with st.container():
    current_goal_db = sqlite3.connect(DB_NAME).cursor().execute("SELECT goal FROM users WHERE username=?", (uname_aktif,)).fetchone()[0]
    
    with st.form("goal_form"):
        input_goal = st.text_input(
            "Tujuan Utama Anda (Maks. 50 Karakter):", 
            value=current_goal_db if current_goal_db else "",
            max_chars=50,
            placeholder="Contoh: Turun 5kg & Rilis Aplikasi Klien"
        )
        if st.form_submit_button("Simpan Tujuan", use_container_width=True):
            update_user_goal(uname_aktif, input_goal)
            st.rerun()

# TAMPILAN METRIK PENCAPAIAN
col_m1, col_m2 = st.columns(2)
with col_m1:
    st.metric("Total Poin Anda", f"{my_data['Total Poin']} Poin")
with col_m2:
    st.metric("Lencana Bintang ⭐", my_data['Bintang'] if my_data['Bintang'] != "—" else "Belum ada")

st.divider()

# ====================================================================
# 6. PANEL CHECK-IN & PERINGATAN KRITIS
# ====================================================================
st.subheader("📅 Panel Presensi Harian")

# STATUS KEGAGALAN (JIKA SUDAH GAGAL, KUNCI TOTAL APLIKASI)
if my_data['Status'] == "❌ GAGAL":
    st.error("💀 **ANDA TELAH GAGAL DAN TERELIMINASI DARI PROGRAM.**\n\nAnda telah melanggar batas toleransi (bolos 2 hari berturut-turut ATAU melebihi kuota 1 kali bolos dalam blok minggu ini). Akses pengisian presensi Anda telah ditutup permanen.")
    st.stop()

# SISTEM PERINGATAN KETAT (WARNING SYSTEM)
if my_data['kemarin_bolos']:
    st.warning("⚠️ **PERINGATAN KRITIS:** Anda bolos/absen kemarin. Berdasarkan aturan sistem, **jika Anda bolos hari ini, Anda langsung GAGAL** (tereliminasi). Pastikan Anda melakukan Check-In malam ini!")
elif my_data['sisa_kuota_blok'] <= 0:
    st.warning(f"⚠️ **PERINGATAN KUOTA MINGGU INI:** Anda sudah menggunakan 1 kali hak bolos pada siklus minggu ini (H-{my_data['hari_blok_awal']} s.d H-{my_data['hari_blok_awal']+6}). **Bolos satu kali lagi pada minggu ini = GAGAL.**")
else:
    st.info(f"💡 Kuota bolos aman. Anda memiliki hak bolos **{my_data['sisa_kuota_blok']} kali** pada siklus minggu ini (H-{my_data['hari_blok_awal']} s.d H-{my_data['hari_blok_awal']+6}).")

# CEK WAKTU WIB & STATUS LIBUR NASIONAL
app_status = get_app_status()
is_libur = (app_status == "holiday")

wib_tz = datetime.timezone(datetime.timedelta(hours=7))
waktu_sekarang = datetime.datetime.now(wib_tz)
jam_sekarang = waktu_sekarang.time()

jam_mulai = datetime.time(20, 0)
jam_selesai = datetime.time(23, 0)
status_dalam_jendela = jam_mulai <= jam_sekarang <= jam_selesai

tampilan_waktu = waktu_sekarang.strftime("%H:%M:%S WIB")

if is_libur:
    st.success(f"📢 **HARI LIBUR NASIONAL** | Waktu Server: **{tampilan_waktu}**\n\nSuper Admin meliburkan presensi hari ini. Poin dan lencana Bintang Anda aman tanpa perlu Check-In.")
    # Otomatis catatkan status holiday ke database jika belum ada
    conn = sqlite3.connect(DB_NAME)
    user_logs = pd.read_sql_query("SELECT day_number FROM check_ins WHERE username=?", conn, params=(uname_aktif,))['day_number'].tolist()
    hari_target = max(user_logs) + 1 if user_logs else 1
    if hari_target <= 60:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO check_ins VALUES (?, ?, ?, ?)", (uname_aktif, hari_target, "holiday", datetime.datetime.now()))
        conn.commit()
    conn.close()
    st.stop()
    
elif status_dalam_jendela:
    st.success(f"⏳ **JENDELA PRESENSI TERBUKA** | Waktu: **{tampilan_waktu}** (Batas: 20.00 - 23.00 WIB)")
else:
    st.warning(f"🔒 **PRESENSI TERTUTUP** | Waktu Server: **{tampilan_waktu}**\n\nTombol aktif setiap pukul **20.00 - 23.00 WIB**.")

# LOGIKA TOMBOL INPUT PRESENSI
conn = sqlite3.connect(DB_NAME)
user_logs = pd.read_sql_query("SELECT day_number, status FROM check_ins WHERE username=?", conn, params=(uname_aktif,)).set_index('day_number')['status'].to_dict()

hari_target = 1
while hari_target in user_logs:
    hari_target += 1

if hari_target > 60:
    st.success("🎉 **LUAR BIASA! Anda telah menyelesaikan balapan 60 Hari!**")
else:
    st.markdown(f"**Tindakan untuk Hari Ke-{hari_target}:**")
    
    # Layout mobile-friendly: tombol di-stack vertikal jika di layar kecil, atau gunakan kolom responsif
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button(f"✅ Check-In (H-{hari_target})", type="primary", disabled=not status_dalam_jendela, use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (uname_aktif, hari_target, "checked_in", datetime.datetime.now()))
            conn.commit()
            st.rerun()
            
    with col_b2:
        if st.button(f"❌ Bolos (H-{hari_target})", type="secondary", disabled=not status_dalam_jendela, use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (uname_aktif, hari_target, "missed", datetime.datetime.now()))
            conn.commit()
            st.rerun()

conn.close()

# RIWAYAT VISUAL MINIMALIS (RESPONSIF)
st.markdown("<br>**Riwayat Visual Anda:**", unsafe_allow_html=True)
grid_cols = st.columns(10)
for d in range(1, 61):
    status_icon = "⚪" 
    if d in user_logs:
        val = user_logs[d]
        if val == "checked_in": status_icon = "🟢"
        elif val == "missed": status_icon = "🔴"
        elif val == "holiday": status_icon = "🔵"
        
    with grid_cols[(d-1) % 10]:
        st.markdown(f"<div style='text-align:center; font-size:10px;'>H{d}<br>{status_icon}</div>", unsafe_allow_html=True)

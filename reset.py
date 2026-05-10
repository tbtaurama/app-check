import datetime
import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. SETUP DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS allowed_users (email TEXT PRIMARY KEY, full_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS check_ins (email TEXT, day_number INTEGER, status TEXT, timestamp DATETIME, PRIMARY KEY (email, day_number))''')
    
    initial_users = [
        ("peserta1@gmail.com", "Andi (Peserta 1)"),
        ("peserta2@gmail.com", "Budi (Peserta 2)"),
        ("admin@domain.com", "Anda (Pemilik)")
    ]
    c.executemany("INSERT OR IGNORE INTO allowed_users VALUES (?, ?)", initial_users)
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. LOGIKA POIN ARITMATIKA
# ==========================================
def get_user_scores():
    conn = sqlite3.connect("prod_tracker.db")
    users = pd.read_sql_query("SELECT * FROM allowed_users", conn)
    records = pd.read_sql_query("SELECT * FROM check_ins", conn)
    conn.close()
    
    trajectory_data = {}
    current_leaderboard = []
    
    for _, user in users.iterrows():
        email = user['email']
        name = user['full_name']
        user_records = records[records['email'] == email].set_index('day_number')['status'].to_dict()
        
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
        current_leaderboard.append({"Nama": name, "Email": email, "Total Poin": cumulative_score, "Hari Terakhir": max_day_for_user})
        
    df_trajectory = pd.DataFrame.from_dict(trajectory_data, orient='index').transpose()
    df_trajectory.index.name = 'Hari'
    df_leaderboard = pd.DataFrame(current_leaderboard).sort_values(by="Total Poin", ascending=False).reset_index(drop=True)
    return df_leaderboard, df_trajectory

# ==========================================
# 3. LOGIN TERTUTUP
# ==========================================
st.set_page_config(page_title="Productivity Tracker", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['current_user_email'] = ""
    st.session_state['current_user_name'] = ""

def login():
    conn = sqlite3.connect("prod_tracker.db")
    c = conn.cursor()
    c.execute("SELECT full_name FROM allowed_users WHERE email=?", (st.session_state['login_email'].strip(),))
    result = c.fetchone()
    conn.close()
    if result:
        st.session_state['logged_in'] = True
        st.session_state['current_user_email'] = st.session_state['login_email'].strip()
        st.session_state['current_user_name'] = result[0]
    else:
        st.error("Akses Ditolak: Email tidak terdaftar.")

if not st.session_state['logged_in']:
    st.title("🔒 Login Peserta Produktivitas")
    with st.form("login_form"):
        st.text_input("Email Akses", key="login_email")
        st.form_submit_button("Log In", on_click=login)
    st.stop()

# ==========================================
# 4. DASHBOARD UTAMA
# ==========================================
email_aktif = st.session_state['current_user_email']
nama_aktif = st.session_state['current_user_name']

st.sidebar.success(f"Masuk sebagai:\n**{nama_aktif}**")
if st.sidebar.button("Log Out"):
    st.session_state['logged_in'] = False
    st.rerun()

st.title("🚀 Dashboard Pemantauan 60 Hari Produktivitas")
st.divider()

df_leaderboard, df_trajectory = get_user_scores()
user_current_data = df_leaderboard[df_leaderboard['Email'] == email_aktif]
poin_saya = user_current_data['Total Poin'].values[0] if not user_current_data.empty else 0
hari_terakhir_saya = user_current_data['Hari Terakhir'].values[0] if not user_current_data.empty else 0

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📈 Grafik Kinerja (Kumulatif Poin)")
    st.line_chart(df_trajectory)
with col2:
    st.metric(label="Total Poin Anda Saat Ini", value=f"{poin_saya} Poin", delta=f"Hari Aktif: {hari_terakhir_saya} / 60")
    st.subheader("🏆 Leaderboard")
    st.dataframe(df_leaderboard[['Nama', 'Total Poin']], use_container_width=True, hide_index=True)

st.divider()

# ==========================================
# 5. INPUT CHECK-IN DENGAN WAKTU WIB
# ==========================================
st.subheader("📅 Panel Check-In Harian Anda")

# Kunci Zona Waktu WIB (UTC+7)
wib_tz = datetime.timezone(datetime.timedelta(hours=7))
waktu_sekarang = datetime.datetime.now(wib_tz)
jam_sekarang = waktu_sekarang.time()

jam_mulai = datetime.time(20, 0)
jam_selesai = datetime.time(23, 0)
status_dalam_jendela = jam_mulai <= jam_sekarang <= jam_selesai

tampilan_waktu = waktu_sekarang.strftime("%H:%M:%S WIB")
if status_dalam_jendela:
    st.success(f"⏳ **Jendela Check-In TERBUKA** | Waktu Server: **{tampilan_waktu}** (Batas: 20.00 - 23.00 WIB)")
else:
    st.warning(f"🔒 **Jendela Check-In TERTUTUP** | Waktu Server: **{tampilan_waktu}**\n\n*Check-in hanya dapat dilakukan antara pukul **20.00 hingga 23.00 WIB**.*")

conn = sqlite3.connect("prod_tracker.db")
user_logs = pd.read_sql_query("SELECT day_number, status FROM check_ins WHERE email=?", conn, params=(email_aktif,)).set_index('day_number')['status'].to_dict()

hari_target = 1
while hari_target in user_logs:
    hari_target += 1

if hari_target > 60:
    st.success("🎉 Selamat! Anda telah menyelesaikan program 60 Hari.")
else:
    st.markdown(f"**Target Hari Ini:** Anda berada di **Hari Ke-{hari_target}** (Bobot: **{hari_target} Poin**)")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        label_btn = f"✅ Check In Hari Ke-{hari_target}" if status_dalam_jendela else f"🔒 Check In Terkunci"
        if st.button(label_btn, type="primary", disabled=not status_dalam_jendela, use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (email_aktif, hari_target, "checked_in", datetime.datetime.now()))
            conn.commit()
            st.rerun()
    with col_btn2:
        if st.button(f"❌ Lewati / Bolos Hari Ke-{hari_target}", type="secondary", use_container_width=True):
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO check_ins VALUES (?, ?, ?, ?)", (email_aktif, hari_target, "missed", datetime.datetime.now()))
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

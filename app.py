import base64
import hmac
import re
import uuid
from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import create_client

from mailer import booking_text, send_email

st.set_page_config(page_title="WIUT Bloomberg Lab | Terminal Booking", page_icon="📈", layout="wide")

# ---------- Settings (change here) ----------
TZ = ZoneInfo("Asia/Tashkent")
TERMINALS = list(range(1, 12))                      # 11 terminals
SLOT_MIN = 45
FIRST_START, LAST_START = time(9, 0), time(18, 0)   # lab closes 18:45
MAX_DAYS_AHEAD = 7
CLOSED_WEEKDAY = 6                                  # Sunday
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@(students\.)?wiut\.uz$", re.I)
ID_RE = re.compile(r"^\d{1,8}$")
BLOCK_KINDS = ["maintenance", "class", "training"]
MAJORS = [
    "Foundation", "BA (Hons) in International Relations and Law", "BSc (Hons) in Economics and its Pathways",
    "BSc (Hons) in Computer Science", "BA (Hons) in Commercial Law", "BSc (Hons) in Finance",
    "BA (Hons) in Business Management and its Pathways", "BSc (Hons) in Business Information Systems",
    "MBA and its Pathways", "MSc in Public Health and Healthcare Management",
    "LLM in International Commercial Law", "MBA in Finance", "MSc in Business Intelligence and Analytics",
    "MSc in Applied Economics", "MA in Creative Industries Management",
    "MA in Learning and Teaching (with TESOL pathway)", "MSc in Research Methods for Social Sciences",
    "Postgraduate Certificate in Research Methods for Social Sciences",
    "Postgraduate Certificate in Learning and Teaching", "PhD and DSc Programmes", "UK Degree PhD and MPhil",
]
CELL = {"free": "FREE", "booked": "BOOKED", "maintenance": "MAINT.", "class": "CLASS", "training": "TRAINING"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap');
:root{--amber:#FFA028;--panel:#0f1012;--line:#25272c;--mut:#8b8f96;--mono:'JetBrains Mono',ui-monospace,Consolas,monospace}
html,body,.stApp{font-family:'Inter',system-ui,sans-serif}
.stApp{background:radial-gradient(1100px 500px at 85% -10%,#1a1205 0%,#050505 60%)}
footer,#MainMenu{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.4rem;max-width:1450px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;border-bottom:2px solid var(--amber);padding-bottom:14px}
.brand{display:flex;align-items:center;gap:18px}
.logo{background:#fff;border-radius:8px;padding:6px 12px;display:flex;align-items:center}
.logo img{height:52px;display:block}
.brand h1{margin:0;font:700 1.55rem var(--mono);color:var(--amber);letter-spacing:.04em}
.brand p{margin:2px 0 0;color:var(--mut);font-size:.85rem}
.clock{font:700 .95rem var(--mono);color:var(--amber);text-align:right}
.clock small{display:block;color:var(--mut);font-weight:500}
.ticker{overflow:hidden;white-space:nowrap;background:#000;border-bottom:1px solid var(--line);margin-bottom:18px}
.ticker span{display:inline-block;padding-left:100%;animation:tick 55s linear infinite;color:var(--amber);font:500 .78rem var(--mono);line-height:30px}
@keyframes tick{to{transform:translateX(-100%)}}
.sec{font:700 .8rem var(--mono);letter-spacing:.14em;color:var(--amber);margin:22px 0 8px;display:flex;align-items:center;gap:10px}
.sec:after{content:"";flex:1;height:1px;background:var(--line)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:8px 0 6px}
.kpi{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--amber);border-radius:4px;padding:12px 16px}
.kpi i{display:block;font:500 .68rem var(--mono);letter-spacing:.12em;color:var(--mut);font-style:normal}
.kpi b{font:700 1.9rem var(--mono);color:var(--amber)}
.gridwrap{overflow-x:auto;border:1px solid var(--line);border-radius:4px;background:#000}
table.grid{border-collapse:collapse;width:100%;min-width:900px;font-family:var(--mono)}
table.grid th{padding:8px 6px;font-size:.72rem;color:var(--amber);background:#0b0b0c;border-bottom:1px solid var(--line);text-align:center}
table.grid th.time{text-align:left;padding-left:12px;color:#cfd2d6;white-space:nowrap;border-right:1px solid var(--line)}
table.grid td{padding:8px 4px;text-align:center;font-size:.68rem;font-weight:700;letter-spacing:.05em;border:1px solid #121316}
td.free{color:#3ddc84;background:rgba(61,220,132,.08)}
td.booked{color:#ff5d5d;background:rgba(255,93,93,.14)}
td.maintenance{color:#ffb84d;background:rgba(255,184,77,.14)}
td.class{color:#5ab0ff;background:rgba(90,176,255,.14)}
td.training{color:#c58bff;background:rgba(197,139,255,.14)}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0 10px;font:500 .72rem var(--mono);color:var(--mut)}
.legend em{font-style:normal;padding:2px 8px;border-radius:3px}
.ticket{background:var(--panel);border:1px solid var(--amber);border-radius:6px;padding:18px 22px;margin:10px 0}
.ticket h3{margin:0 0 8px;font:700 1rem var(--mono);color:#3ddc84;letter-spacing:.08em}
.ticket p{margin:3px 0;color:#d8d8d8}
[data-testid="stWidgetLabel"] p{font:600 .72rem var(--mono)!important;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)!important}
[data-testid="stForm"]{background:var(--panel);border:1px solid var(--line);border-radius:6px}
button[kind="primary"],button[kind="primaryFormSubmit"]{color:#000!important;font-weight:700!important;letter-spacing:.06em}
button[kind="primary"] p,button[kind="primaryFormSubmit"] p{color:#000!important}
.stTabs [data-baseweb="tab"]{font:700 .8rem var(--mono);letter-spacing:.1em}
@media(max-width:800px){.kpis{grid-template-columns:repeat(2,1fr)}.brand h1{font-size:1.15rem}}
</style>
"""


@st.cache_resource
def db():
    url = st.secrets["SUPABASE_URL"].strip().split("/rest/")[0].rstrip("/")
    return create_client(url, st.secrets["SUPABASE_KEY"].strip())


def now():
    return datetime.now(TZ)


def parse(s):
    return datetime.fromisoformat(s).astimezone(TZ)


def slots_for(d):
    t, last = datetime.combine(d, FIRST_START, tzinfo=TZ), datetime.combine(d, LAST_START, tzinfo=TZ)
    out = []
    while t <= last:
        out.append(t)
        t += timedelta(minutes=SLOT_MIN)
    return out


def label(t):
    return f"{t:%H:%M}–{t + timedelta(minutes=SLOT_MIN):%H:%M}"


def between(table, d1, d2, active_only=False):
    start = datetime.combine(d1, time(0, 0), tzinfo=TZ)
    end = datetime.combine(d2 + timedelta(days=1), time(0, 0), tzinfo=TZ)
    q = db().table(table).select("*").gte("start_time", start.isoformat()).lt("start_time", end.isoformat())
    if active_only:
        q = q.eq("status", "active")
    return q.order("start_time").execute().data


def status_map(d):
    m = {(r["terminal"], parse(r["start_time"])): r["kind"] for r in between("blocks", d, d)}
    m.update({(r["terminal"], parse(r["start_time"])): "booked" for r in between("bookings", d, d, True)})
    return m


# ---------- UI pieces ----------
def header():
    logo = Path(__file__).parent / "logo.png"
    img = ""
    if logo.exists():
        b64 = base64.b64encode(logo.read_bytes()).decode()
        img = f'<div class="logo"><img src="data:image/png;base64,{b64}"></div>'
    n = now()
    st.markdown(CSS + f"""<div class="topbar"><div class="brand">{img}<div><h1>TERMINAL BOOKING</h1>
<p>Westminster International University in Tashkent · Bloomberg Lab</p></div></div>
<div class="clock">{n:%H:%M} TASHKENT<small>{n:%a %d %b %Y}</small></div></div>
<div class="ticker"><span>LAB OPEN MON–SAT 09:00–18:45 &nbsp;■&nbsp; 11 BLOOMBERG TERMINALS &nbsp;■&nbsp; 45-MINUTE SESSIONS
&nbsp;■&nbsp; BOOK UP TO 7 DAYS AHEAD &nbsp;■&nbsp; ONE BOOKING PER PERSON PER DAY &nbsp;■&nbsp; CANCEL ANYTIME FROM YOUR EMAIL LINK
&nbsp;■&nbsp; CLOSED SUNDAY</span></div>""", unsafe_allow_html=True)


def section(text):
    st.markdown(f'<div class="sec">{text}</div>', unsafe_allow_html=True)


def grid_html(slots, state):
    head = "".join(f"<th>T{n}</th>" for n in TERMINALS)
    rows = "".join(
        f'<tr><th class="time">{label(t)}</th>'
        + "".join(f'<td class="{state.get((n, t), "free")}">{CELL[state.get((n, t), "free")]}</td>' for n in TERMINALS)
        + "</tr>" for t in slots)
    return f'<div class="gridwrap"><table class="grid"><tr><th></th>{head}</tr>{rows}</table></div>'


def kpis(items):
    st.markdown('<div class="kpis">' + "".join(f"<div class='kpi'><i>{k}</i><b>{v}</b></div>" for k, v in items) + "</div>",
                unsafe_allow_html=True)


LEGEND = ('<div class="legend"><em class="free" style="color:#3ddc84;background:rgba(61,220,132,.12)">FREE</em>'
          '<em style="color:#ff5d5d;background:rgba(255,93,93,.16)">BOOKED</em>'
          '<em style="color:#ffb84d;background:rgba(255,184,77,.16)">MAINTENANCE</em>'
          '<em style="color:#5ab0ff;background:rgba(90,176,255,.16)">CLASS</em>'
          '<em style="color:#c58bff;background:rgba(197,139,255,.16)">TRAINING</em></div>')


# ---------- Cancel page ----------
def cancel_page(token):
    section("CANCEL BOOKING")
    try:
        uuid.UUID(token)
        rows = db().table("bookings").select("*").eq("cancel_token", token).execute().data
    except Exception:
        rows = []
    if not rows:
        return st.error("This cancellation link is not valid.")
    b = rows[0]
    start = parse(b["start_time"])
    st.markdown(f'<div class="ticket"><h3>TERMINAL {b["terminal"]}</h3><p>{start:%A %d %B %Y} · {label(start)}</p></div>',
                unsafe_allow_html=True)
    if b["status"] == "cancelled":
        st.info("This booking is already cancelled.")
    elif start <= now():
        st.warning("This session has already started, so it can't be cancelled.")
    elif st.button("Yes, cancel my booking", type="primary"):
        db().table("bookings").update({"status": "cancelled"}).eq("id", b["id"]).execute()
        st.success("Your booking has been cancelled. The slot is free for other students.")


# ---------- Booking tab ----------
def booking_tab():
    today = now().date()
    section("1 · SELECT DATE")
    d = st.date_input("Date", value=today, min_value=today, max_value=today + timedelta(days=MAX_DAYS_AHEAD))
    if d.weekday() == CLOSED_WEEKDAY:
        return st.warning("The lab is closed on Sundays. Please choose another day.")
    state = status_map(d)
    slots = [t for t in slots_for(d) if t >= now()]
    if not slots:
        return st.info("No more slots today. Please choose another date.")

    cells = [state.get((n, t), "free") for t in slots for n in TERMINALS]
    free_n, booked_n = cells.count("free"), cells.count("booked")
    blocked_n = len(cells) - free_n - booked_n
    usable = len(cells) - blocked_n
    kpis([("FREE SLOTS", free_n), ("BOOKED", booked_n), ("BLOCKED", blocked_n),
          ("UTILISATION", f"{round(100 * booked_n / usable) if usable else 0}%")])

    section("2 · LIVE AVAILABILITY")
    st.markdown(LEGEND + grid_html(slots, state), unsafe_allow_html=True)

    free = {t: [n for n in TERMINALS if (n, t) not in state] for t in slots}
    open_slots = [t for t in slots if free[t]]
    if not open_slots:
        return st.error("Nothing is free on this day. Please choose another date.")

    section("3 · CHOOSE SLOT & TERMINAL")
    c1, c2 = st.columns(2)
    slot = c1.selectbox("Time slot (45 min)", open_slots, format_func=label)
    terminal = c2.selectbox("Terminal (free ones only)", free[slot], format_func=lambda n: f"Terminal {n}")

    section("4 · YOUR DETAILS")
    who = st.radio("I am a", ["Student", "Staff"], horizontal=True)
    with st.form("book"):
        if who == "Student":
            student_id = st.text_input("Student ID (up to 8 digits)")
            major = st.selectbox("Programme / major", MAJORS)
        else:
            full_name = st.text_input("Full name")
            position = st.text_input("Position")
            department = st.text_input("Department")
        email = st.text_input("Email", placeholder="name@students.wiut.uz or name@wiut.uz")
        purpose = st.text_area("Purpose of using the terminal")
        ok = st.form_submit_button("CONFIRM BOOKING", type="primary")
    if not ok:
        return

    email, purpose = email.strip().lower(), purpose.strip()
    row = {"terminal": terminal, "start_time": slot.isoformat(), "booking_date": d.isoformat(),
           "email": email, "purpose": purpose}
    if who == "Student":
        sid = student_id.strip()
        if not ID_RE.match(sid):
            return st.error("Student ID must be digits only (maximum 8).")
        row.update(user_type="student", student_id=sid, major=major, person_key=sid)
    else:
        if not (full_name.strip() and position.strip() and department.strip()):
            return st.error("Please fill in full name, position and department.")
        row.update(user_type="staff", full_name=full_name.strip(), position=position.strip(),
                   department=department.strip(), person_key="staff:" + email)
    if not EMAIL_RE.match(email):
        return st.error("Email must end with @wiut.uz or @students.wiut.uz.")
    if len(purpose) < 3:
        return st.error("Please write the purpose of using the terminal.")
    if slot < now():
        return st.error("That time has already passed.")
    if db().table("bookings").select("id").eq("person_key", row["person_key"]) \
            .eq("booking_date", d.isoformat()).eq("status", "active").execute().data:
        return st.error("You already have a booking on this day (limit: one per day).")
    if db().table("blocks").select("id").eq("terminal", terminal).eq("start_time", slot.isoformat()).execute().data:
        return st.error("That terminal was just blocked by the lab. Please choose another.")
    try:
        b = db().table("bookings").insert(row).execute().data[0]
    except Exception as e:
        if "uniq_person_day" in str(e):
            return st.error("You already have a booking on this day (limit: one per day).")
        return st.error("Sorry, someone has just booked that terminal at that time. Please choose another.")

    cancel_link = f"{st.secrets['APP_URL']}?cancel={b['cancel_token']}"
    st.markdown(f'<div class="ticket"><h3>✔ BOOKING CONFIRMED</h3><p><b>Terminal {terminal}</b> · {slot:%A %d %B %Y} · {label(slot)}</p>'
                f'<p>{email}</p></div>', unsafe_allow_html=True)
    try:
        subject, body = booking_text(b, st.secrets["APP_URL"])
        send_email(st.secrets["GMAIL_ADDRESS"], st.secrets["GMAIL_APP_PASSWORD"], email, subject, body)
        st.caption(f"A confirmation email was sent to {email}. If you can't find it, check Spam.")
    except Exception:
        st.warning("The confirmation email could not be sent.")
    st.caption("Keep this link to cancel your booking:")
    st.code(cancel_link)


# ---------- Admin ----------
def admin_tab():
    pw = st.text_input("Admin password", type="password")
    if not pw:
        return
    if not hmac.compare_digest(pw.encode(), st.secrets["ADMIN_PASSWORD"].encode()):
        return st.error("Wrong password.")
    t1, t2 = st.tabs(["BOOKINGS", "BLOCK SLOTS"])
    with t1:
        admin_bookings()
    with t2:
        admin_blocks()


def admin_bookings():
    today = now().date()
    a, b_ = st.columns(2)
    d1 = a.date_input("From", today, key="d1")
    d2 = b_.date_input("To", today + timedelta(days=MAX_DAYS_AHEAD), key="d2")
    rows = between("bookings", d1, d2)
    if not rows:
        return st.info("No bookings in this range.")
    out = pd.DataFrame([{
        "Date": f"{parse(r['start_time']):%Y-%m-%d}", "Time": f"{parse(r['start_time']):%H:%M}",
        "Terminal": r["terminal"], "Type": r["user_type"], "Student ID": r["student_id"],
        "Major": r["major"], "Full name": r["full_name"], "Position": r["position"],
        "Department": r["department"], "Email": r["email"], "Purpose": r["purpose"], "Status": r["status"],
    } for r in rows])
    act = out[out.Status == "active"]
    kpis([("ACTIVE BOOKINGS", len(act)), ("CANCELLED", len(out) - len(act)),
          ("STUDENTS", int((act.Type == "student").sum())), ("STAFF", int((act.Type == "staff").sum()))])
    st.dataframe(out, use_container_width=True, hide_index=True)
    if len(act):
        section("BOOKINGS PER DAY")
        st.bar_chart(act.groupby("Date").size(), color="#FFA028")
    buf = BytesIO()
    out.to_excel(buf, index=False)
    st.download_button("Download Excel", buf.getvalue(), "bloomberg_bookings.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    active = [r for r in rows if r["status"] == "active"]
    if active:
        pick = st.selectbox("Cancel a booking", active, format_func=lambda r: (
            f"{parse(r['start_time']):%Y-%m-%d %H:%M} · T{r['terminal']} · {r['student_id'] or r['full_name']}"))
        if st.button("Cancel selected booking"):
            db().table("bookings").update({"status": "cancelled"}).eq("id", pick["id"]).execute()
            st.success("Cancelled.")
            st.rerun()


def admin_blocks():
    today = now().date()
    d = st.date_input("Date", today, min_value=today, max_value=today + timedelta(days=60), key="bd")
    kind = st.selectbox("Reason", BLOCK_KINDS)
    terms = st.multiselect("Terminals", TERMINALS, format_func=lambda n: f"Terminal {n}")
    if st.checkbox("Select all terminals"):
        terms = TERMINALS
    sl = st.multiselect("Time slots", slots_for(d), format_func=label)
    if st.checkbox("Select the whole day"):
        sl = slots_for(d)
    note = st.text_input("Note (optional)")
    if st.button("Block selected", type="primary") and terms and sl:
        booked = {(r["terminal"], parse(r["start_time"])) for r in between("bookings", d, d, True)}
        rows = [{"terminal": n, "start_time": t.isoformat(), "kind": kind, "note": note}
                for n in terms for t in sl if (n, t) not in booked]
        if rows:
            db().table("blocks").upsert(rows, on_conflict="terminal,start_time").execute()
        skipped = len(terms) * len(sl) - len(rows)
        st.success(f"Blocked {len(rows)} slot(s)." + (f" Skipped {skipped} that already have a booking; cancel those first." if skipped else ""))
    st.divider()
    existing = between("blocks", today, today + timedelta(days=60))
    if existing:
        pick = st.multiselect("Remove blocks", existing, format_func=lambda r: (
            f"{parse(r['start_time']):%Y-%m-%d %H:%M} · T{r['terminal']} · {r['kind']}"))
        if st.button("Remove selected blocks") and pick:
            db().table("blocks").delete().in_("id", [r["id"] for r in pick]).execute()
            st.rerun()


# ---------- Main ----------
header()
token = st.query_params.get("cancel")
if token:
    cancel_page(token)
else:
    tab1, tab2 = st.tabs(["BOOK A TERMINAL", "ADMIN"])
    with tab1:
        booking_tab()
    with tab2:
        admin_tab()

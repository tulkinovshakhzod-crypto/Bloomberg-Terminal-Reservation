import hmac
import re
import uuid
from datetime import datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import create_client

from mailer import booking_text, send_email

st.set_page_config(page_title="WIUT Bloomberg Lab Booking", page_icon="📈", layout="wide")

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
    "Foundation",
    "BA (Hons) in International Relations and Law",
    "BSc (Hons) in Economics and its Pathways",
    "BSc (Hons) in Computer Science",
    "BA (Hons) in Commercial Law",
    "BSc (Hons) in Finance",
    "BA (Hons) in Business Management and its Pathways",
    "BSc (Hons) in Business Information Systems",
    "MBA and its Pathways",
    "MSc in Public Health and Healthcare Management",
    "LLM in International Commercial Law",
    "MBA in Finance",
    "MSc in Business Intelligence and Analytics",
    "MSc in Applied Economics",
    "MA in Creative Industries Management",
    "MA in Learning and Teaching (with TESOL pathway)",
    "MSc in Research Methods for Social Sciences",
    "Postgraduate Certificate in Research Methods for Social Sciences",
    "Postgraduate Certificate in Learning and Teaching",
    "PhD and DSc Programmes",
    "UK Degree PhD and MPhil",
]
STATE_TEXT = {"free": "✅ Free", "booked": "🔒 Booked", "maintenance": "🛠 Maintenance",
              "class": "🎓 Class", "training": "📚 Training"}
STATE_COLOR = {"Free": "#d4edda", "Booked": "#f8d7da", "Maintenance": "#ffe5b4",
               "Class": "#cfe2ff", "Training": "#e2d4f0"}


@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


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
    """{(terminal, slot_datetime): 'booked' | 'maintenance' | 'class' | 'training'}"""
    m = {(r["terminal"], parse(r["start_time"])): r["kind"] for r in between("blocks", d, d)}
    m.update({(r["terminal"], parse(r["start_time"])): "booked" for r in between("bookings", d, d, True)})
    return m


# ---------- Cancel page (link from email) ----------
def cancel_page(token):
    st.title("Cancel your booking")
    try:
        uuid.UUID(token)
        rows = db().table("bookings").select("*").eq("cancel_token", token).execute().data
    except Exception:
        rows = []
    if not rows:
        return st.error("This cancellation link is not valid.")
    b = rows[0]
    start = parse(b["start_time"])
    st.write(f"**Terminal {b['terminal']}**, {start:%A %d %B %Y}, {label(start)}")
    if b["status"] == "cancelled":
        st.info("This booking is already cancelled.")
    elif start <= now():
        st.warning("This session has already started, so it can't be cancelled.")
    elif st.button("Yes, cancel my booking", type="primary"):
        db().table("bookings").update({"status": "cancelled"}).eq("id", b["id"]).execute()
        st.success("Your booking has been cancelled. The slot is free for other students.")


# ---------- Booking tab ----------
def booking_tab():
    st.subheader("Book a terminal")
    today = now().date()
    d = st.date_input("Date", value=today, min_value=today, max_value=today + timedelta(days=MAX_DAYS_AHEAD))
    if d.weekday() == CLOSED_WEEKDAY:
        return st.warning("The lab is closed on Sundays. Please choose another day.")

    state = status_map(d)
    slots = [t for t in slots_for(d) if t >= now()]
    if not slots:
        return st.info("No more slots today. Please choose another date.")

    grid = pd.DataFrame(
        {f"T{n}": [STATE_TEXT[state.get((n, t), "free")] for t in slots] for n in TERMINALS},
        index=[label(t) for t in slots],
    )
    st.caption("Live availability: ✅ Free · 🔒 Booked · 🛠 Maintenance · 🎓 Class · 📚 Training")
    st.dataframe(grid.style.map(lambda v: "color:#000;background-color:" + next(
        (c for k, c in STATE_COLOR.items() if k in v), "#fff")), use_container_width=True)

    free = {t: [n for n in TERMINALS if (n, t) not in state] for t in slots}
    open_slots = [t for t in slots if free[t]]
    if not open_slots:
        return st.error("Nothing is free on this day. Please choose another date.")

    c1, c2 = st.columns(2)
    slot = c1.selectbox("Time slot (45 min)", open_slots, format_func=label)
    terminal = c2.selectbox("Terminal (free ones only)", free[slot], format_func=lambda n: f"Terminal {n}")
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
        ok = st.form_submit_button("Book", type="primary")
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

    try:
        subject, body = booking_text(b, st.secrets["APP_URL"])
        send_email(st.secrets["GMAIL_ADDRESS"], st.secrets["GMAIL_APP_PASSWORD"], email, subject, body)
        st.success(f"Booked Terminal {terminal}, {slot:%A %d %B}, {label(slot)}. Confirmation sent to {email}.")
    except Exception:
        st.warning("Booking saved, but the confirmation email failed. Save your cancel link:")
        st.code(f"{st.secrets['APP_URL']}?cancel={b['cancel_token']}")
    st.balloons()


# ---------- Admin tab ----------
def admin_tab():
    st.subheader("Admin")
    pw = st.text_input("Password", type="password")
    if not pw:
        return
    if not hmac.compare_digest(pw.encode(), st.secrets["ADMIN_PASSWORD"].encode()):
        return st.error("Wrong password.")
    t1, t2 = st.tabs(["Bookings", "Block slots (maintenance / class / training)"])
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
    st.dataframe(out, use_container_width=True, hide_index=True)
    buf = BytesIO()
    out.to_excel(buf, index=False)
    st.download_button("Download Excel", buf.getvalue(), "bloomberg_bookings.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    active = [r for r in rows if r["status"] == "active"]
    if active:
        pick = st.selectbox("Cancel a booking", active, format_func=lambda r: (
            f"{parse(r['start_time']):%Y-%m-%d %H:%M} · T{r['terminal']} · "
            f"{r['student_id'] or r['full_name']}"))
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
        st.success(f"Blocked {len(rows)} slot(s)." + (f" Skipped {skipped} that already have a booking; cancel those bookings first." if skipped else ""))

    st.divider()
    existing = between("blocks", today, today + timedelta(days=60))
    if existing:
        pick = st.multiselect("Remove blocks", existing, format_func=lambda r: (
            f"{parse(r['start_time']):%Y-%m-%d %H:%M} · T{r['terminal']} · {r['kind']}"))
        if st.button("Remove selected blocks") and pick:
            db().table("blocks").delete().in_("id", [r["id"] for r in pick]).execute()
            st.rerun()


# ---------- Main ----------
token = st.query_params.get("cancel")
if token:
    cancel_page(token)
else:
    st.title("📈 WIUT Bloomberg Lab Booking")
    st.caption("Open Mon–Sat, 09:00–18:45 · 45-minute sessions · book up to 7 days ahead · one booking per day")
    tab1, tab2 = st.tabs(["Book", "Admin"])
    with tab1:
        booking_tab()
    with tab2:
        admin_tab()

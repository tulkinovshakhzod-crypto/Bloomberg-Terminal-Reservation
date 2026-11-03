"""Sends a reminder to everyone whose session starts within the next hour.
Run every 10 minutes (see .github/workflows/reminders.yml)."""
import os
from datetime import datetime, timedelta, timezone

from supabase import create_client
from mailer import send_email, booking_text

db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
now = datetime.now(timezone.utc)

rows = (
    db.table("bookings").select("*")
    .eq("status", "active").eq("reminder_sent", False)
    .gte("start_time", now.isoformat())
    .lte("start_time", (now + timedelta(hours=1)).isoformat())
    .execute().data
)
for b in rows:
    subject, body = booking_text(b, os.environ["APP_URL"], reminder=True)
    try:
        send_email(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"], b["email"], subject, body)
        db.table("bookings").update({"reminder_sent": True}).eq("id", b["id"]).execute()
        print("reminded", b["email"])
    except Exception as e:
        print("failed", b["email"], e)

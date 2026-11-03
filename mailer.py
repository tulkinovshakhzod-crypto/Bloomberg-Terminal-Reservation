import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")


def send_email(sender: str, app_password: str, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = f"WIUT Bloomberg Lab <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(msg)


def booking_text(b: dict, app_url: str, reminder: bool = False) -> tuple[str, str]:
    start = datetime.fromisoformat(b["start_time"]).astimezone(TZ)
    when = start.strftime("%A, %d %B %Y, %H:%M")
    cancel_url = f"{app_url}?cancel={b['cancel_token']}"
    if reminder:
        subject = f"Reminder: Bloomberg Lab, Terminal {b['terminal']} at {start:%H:%M}"
        intro = "This is a reminder of your upcoming Bloomberg Lab session."
    else:
        subject = f"Booking confirmed: Terminal {b['terminal']}, {start:%d %b %H:%M}"
        intro = "Your Bloomberg Lab booking is confirmed."
    body = (
        f"{intro}\n\n"
        f"Terminal: {b['terminal']}\n"
        f"Time:     {when} (45 minutes)\n"
        f"Booked by: {b['student_id'] or b['full_name']}\n"
        f"Purpose:  {b['purpose']}\n\n"
        f"Can't make it? Please cancel so another student can use the slot:\n{cancel_url}\n\n"
        "WIUT Bloomberg Lab"
    )
    return subject, body

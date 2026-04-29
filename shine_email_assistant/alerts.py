"""Send operational alert emails on real failures.

Triggers (called from pipeline):
- Gmail auth revoked/expired
- KB files won't parse at startup
- Error rate >= threshold within window
"""
import os
import smtplib
from email.message import EmailMessage

from shine_email_assistant.log import get_logger

log = get_logger(__name__)


def send_alert(subject: str, body: str) -> None:
    """Best-effort alert. Logs and swallows on failure (don't take down the app on a smtp error)."""
    to_addr = os.getenv("ALERT_EMAIL_TO")
    from_addr = os.getenv("ALERT_EMAIL_FROM")
    host = os.getenv("SMTP_HOST")
    port_str = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not all([to_addr, from_addr, host, port_str, user, password]):
        log.warning("alert_skipped_missing_smtp_config", subject=subject)
        return

    msg = EmailMessage()
    msg["Subject"] = f"[shine-email-assistant] {subject}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, int(port_str)) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        log.info("alert_sent", subject=subject)
    except Exception as e:  # noqa: BLE001
        log.error("alert_send_failed", subject=subject, error=str(e))

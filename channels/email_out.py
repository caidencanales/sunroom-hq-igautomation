"""Email over SMTP (Google Workspace, Outlook, or any SMTP provider)."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from config import INCLUDE_EMAIL_FOOTER, SENDER_NAME, COMPANY


def footer():
    if not INCLUDE_EMAIL_FOOTER:
        return ""
    address = os.getenv("BUSINESS_ADDRESS", "")
    return f"\n\n--\n{SENDER_NAME}, {COMPANY}{' · ' + address if address else ''}\nNot for you? Reply \"no thanks\" and I won't email again."


class Mailer:
    def __enter__(self):
        self.user = os.environ["SMTP_USER"]
        self.from_addr = os.getenv("FROM_EMAIL", self.user)
        host, port = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))
        self.smtp = smtplib.SMTP(host, port, timeout=60)
        self.smtp.starttls(context=ssl.create_default_context())
        self.smtp.login(self.user, os.environ["SMTP_PASSWORD"])
        return self

    def __exit__(self, *exc):
        try:
            self.smtp.quit()
        except Exception:
            pass

    def send(self, to, subject, body, reply_to_msgid=None, attachment=None, add_footer=True):
        msg = EmailMessage()
        msg["From"] = f"{SENDER_NAME} <{self.from_addr}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self.from_addr.split("@")[-1])
        if reply_to_msgid:  # keeps follow-ups in the same thread
            msg["In-Reply-To"] = reply_to_msgid
            msg["References"] = reply_to_msgid
        msg.set_content(body + (footer() if add_footer else ""))
        if attachment:
            with open(attachment, "rb") as f:
                msg.add_attachment(f.read(), maintype="application", subtype="octet-stream",
                                   filename=os.path.basename(attachment))
        self.smtp.send_message(msg)
        return msg["Message-ID"]

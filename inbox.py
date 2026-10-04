"""Read the sending inbox over IMAP: mark replies, opt-outs and bounces."""
import email
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta
from email.utils import parseaddr

import db

log = logging.getLogger("sunroom")
OPT_OUT = ("no thanks", "unsubscribe", "remove me", "not interested", "stop emailing", "take me off")
BOUNCE_FROM = ("mailer-daemon", "postmaster", "mail delivery")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _body(msg):
    parts = msg.walk() if msg.is_multipart() else [msg]
    for p in parts:
        if p.get_content_type() == "text/plain":
            try:
                return p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
            except Exception:
                pass
    return ""


def _new_reply_text(body):
    """Drop the quoted original so 'no thanks' in OUR footer doesn't count as an opt-out."""
    keep = []
    for line in body.splitlines():
        if line.startswith(">") or re.match(r"^On .+ wrote:$", line.strip()):
            break
        keep.append(line)
    return "\n".join(keep).strip()


def check(days=10):
    host = os.getenv("IMAP_HOST")
    if not host:
        log.info("[inbox] IMAP_HOST not set, skipping reply check")
        return
    c = db.conn()
    contacted = {r["email"].lower(): r for r in c.execute("SELECT key, email, status, domain FROM leads "
                                                          "WHERE email_sent_at IS NOT NULL AND email IS NOT NULL")}
    by_domain = {r["domain"]: r for r in contacted.values() if r["domain"]}
    if not contacted:
        return

    imap = imaplib.IMAP4_SSL(host)
    imap.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
    imap.select("INBOX", readonly=True)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    _, ids = imap.search(None, f"(SINCE {since})")
    replies = bounces = 0

    for mid in ids[0].split():
        _, data = imap.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        sender = parseaddr(msg.get("From", ""))[1].lower()
        body = _body(msg)

        if any(b in (msg.get("From", "") + sender).lower() for b in BOUNCE_FROM):
            for addr in EMAIL_RE.findall(body):
                lead = contacted.get(addr.lower())
                if lead and lead["status"] != "bounced":
                    db.update(c, lead["key"], status="bounced")
                    bounces += 1
            continue

        lead = contacted.get(sender) or by_domain.get(sender.split("@")[-1])
        if not lead or lead["status"] in ("replied", "opted_out", "won", "done"):
            continue
        text = _new_reply_text(body)
        status = "opted_out" if any(o in text.lower() for o in OPT_OUT) else "replied"
        db.update(c, lead["key"], status=status, replied_at=db.now(), reply_channel="email",
                  reply_snippet=text[:300])
        replies += 1
        log.info(f"[inbox] {status}: {sender}")

    imap.logout()
    log.info(f"[inbox] {replies} new replies, {bounces} bounces")

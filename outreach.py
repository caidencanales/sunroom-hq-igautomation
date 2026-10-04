"""Send messages on each channel, highest score first, within daily limits.

Touch plan per lead:
  day 0  Instagram DM + email
  day 1+ LinkedIn connection request (sooner if it's the only channel we have)
  day 3  email followup1   (if EMAIL_FOLLOWUPS)
  day 7  email followup2   (if EMAIL_FOLLOWUPS)
Anyone who replied, opted out, or bounced is never contacted again.
"""
import logging
import os
from datetime import date, datetime, timedelta

import db
from channels import instagram, linkedin
from channels.browser import Blocked, LimitReached, Pacer, in_send_hours, pause
from channels.email_out import Mailer
from config import (DAILY_LIMIT, EMAIL_START_PER_DAY, EMAIL_RAMP_PER_DAY, EMAIL_MAX_PER_DAY,
                    EMAIL_FOLLOWUPS, EMAIL_GAP_SECONDS)

log = logging.getLogger("sunroom")
CONTACTABLE = "status IN ('qualified', 'active')"


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).isoformat()


def email_cap_today(c):
    first = db.first_email_date(c)
    days = (date.today() - first).days if first else 0
    return min(EMAIL_MAX_PER_DAY, EMAIL_START_PER_DAY + EMAIL_RAMP_PER_DAY * days)


# ---------------------------------------------------------------- instagram -----

def send_instagram(page, dry_run=False):
    c = db.conn()
    left = DAILY_LIMIT["instagram"] - db.sent_today(c, "ig_sent_at")
    rows = c.execute(
        f"SELECT * FROM leads WHERE {CONTACTABLE} AND ig_handle IS NOT NULL AND ig_message IS NOT NULL "
        "AND ig_sent_at IS NULL ORDER BY score DESC LIMIT ?", (max(left, 0),)
    ).fetchall()
    log.info(f"[instagram] {len(rows)} to send (left today: {left})")
    pacer = Pacer()
    for r in rows:
        if not in_send_hours():
            log.info("[instagram] outside send hours, stopping")
            break
        if dry_run:
            log.info(f"  @{r['ig_handle']}: {r['ig_message']!r}")
            continue
        try:
            instagram.send_dm(page, r["ig_handle"], r["ig_message"])
            db.update(c, r["key"], ig_sent_at=db.now(), status="active")
            log.info(f"  sent -> @{r['ig_handle']}")
        except Blocked as e:
            log.error(f"[instagram] STOPPED - platform warning: {e}. Check the account by hand.")
            return "blocked"
        except Exception as e:
            db.add_note(c, r["key"], f"IG send failed: {str(e)[:120]}")
            log.warning(f"  failed @{r['ig_handle']}: {str(e)[:100]}")
            pause((20, 40))
            continue
        pacer.after_send()


# ---------------------------------------------------------------- linkedin ------

def send_linkedin(page, dry_run=False):
    c = db.conn()
    left = DAILY_LIMIT["linkedin"] - db.sent_today(c, "li_sent_at")
    rows = c.execute(
        f"SELECT * FROM leads WHERE {CONTACTABLE} AND owner_linkedin LIKE '%/in/%' AND li_note IS NOT NULL "
        "AND li_sent_at IS NULL AND (COALESCE(ig_sent_at, email_sent_at) IS NULL "
        "OR COALESCE(ig_sent_at, email_sent_at) < ?) ORDER BY score DESC LIMIT ?",
        (_days_ago(1), max(left, 0)),
    ).fetchall()
    log.info(f"[linkedin] {len(rows)} to send (left today: {left})")
    pacer = Pacer()
    for r in rows:
        if not in_send_hours():
            break
        if dry_run:
            log.info(f"  {r['owner_linkedin']}: {r['li_note']!r}")
            continue
        try:
            linkedin.send_connect(page, r["owner_linkedin"], r["li_note"])
            db.update(c, r["key"], li_sent_at=db.now(), status="active")
            log.info(f"  sent -> {r['owner_linkedin']}")
        except LimitReached as e:
            log.warning(f"[linkedin] limit reached ({e}), done for today")
            return "limit"
        except Blocked as e:
            log.error(f"[linkedin] STOPPED - platform warning: {e}. Check the account by hand.")
            return "blocked"
        except Exception as e:
            db.add_note(c, r["key"], f"LI send failed: {str(e)[:120]}")
            db.update(c, r["key"], li_sent_at="skipped")  # don't retry a broken profile forever
            log.warning(f"  failed {r['owner_linkedin']}: {str(e)[:100]}")
            continue
        pacer.after_send()


# ---------------------------------------------------------------- email ---------

def send_email(dry_run=False):
    if not os.getenv("SMTP_HOST") and not dry_run:
        log.info("[email] SMTP not configured in .env, skipping email")
        return
    c = db.conn()
    cap = email_cap_today(c)
    left = cap - db.sent_today(c, "email_sent_at") - db.sent_today(c, "fu1_sent_at") - db.sent_today(c, "fu2_sent_at")

    jobs = []  # (row, kind)
    if EMAIL_FOLLOWUPS:
        for r in c.execute(f"SELECT * FROM leads WHERE {CONTACTABLE} AND email_sent_at < ? AND fu1_sent_at IS NULL",
                           (_days_ago(3),)):
            jobs.append((r, "fu1"))
        for r in c.execute(f"SELECT * FROM leads WHERE {CONTACTABLE} AND fu1_sent_at < ? AND fu2_sent_at IS NULL",
                           (_days_ago(4),)):
            jobs.append((r, "fu2"))
    for r in c.execute(f"SELECT * FROM leads WHERE {CONTACTABLE} AND email IS NOT NULL AND email_body IS NOT NULL "
                       "AND email_sent_at IS NULL ORDER BY score DESC"):
        jobs.append((r, "first"))
    jobs = jobs[:max(left, 0)]
    log.info(f"[email] {len(jobs)} to send (cap today {cap}, left {left})")
    if not jobs:
        return

    if dry_run:
        for r, kind in jobs:
            log.info(f"  {kind} -> {r['email']}: {r['email_subject']!r}")
        return

    with Mailer() as mail:
        for r, kind in jobs:
            if not in_send_hours():
                break
            try:
                if kind == "first":
                    mid = mail.send(r["email"], r["email_subject"], r["email_body"])
                    db.update(c, r["key"], email_sent_at=db.now(), email_msgid=mid, status="active")
                else:
                    body = r["followup1"] if kind == "fu1" else r["followup2"]
                    mail.send(r["email"], "Re: " + r["email_subject"], body, reply_to_msgid=r["email_msgid"])
                    db.update(c, r["key"], **{f"{kind}_sent_at": db.now()})
                log.info(f"  {kind} -> {r['email']}")
            except Exception as e:
                db.add_note(c, r["key"], f"email {kind} failed: {str(e)[:120]}")
                log.warning(f"  failed {r['email']}: {str(e)[:100]}")
            pause(EMAIL_GAP_SECONDS)

"""
Sunroom HQ outreach automation.

  python run.py login                 one-time: log into Instagram + LinkedIn in the bot browser
  python run.py daily                 the whole thing (what the scheduled task runs)
  python run.py daily --dry-run       everything except actually sending

  python run.py discover              find + enrich + qualify until the queue is full
  python run.py send [instagram|linkedin|email] [--dry-run]
  python run.py inbox                 check email replies / bounces
  python run.py tracker               rebuild tracker.xlsx
  python run.py                       quick stats
"""
import logging
import os
import sys
import threading
from datetime import date

import db
import discover
import enrich
import inbox
import outreach
import qualify
import tracker
from channels.browser import Blocked, Browser
from config import (DAILY_LIMIT, QUEUE_TARGET_MULTIPLIER, MAX_DISCOVERY_ROUNDS, WEB_SEARCHES_PER_ROUND,
                    IG_HASHTAGS_PER_ROUND, LOG_DIR, SENDER_NAME)

log = logging.getLogger("sunroom")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(f"{LOG_DIR}/{date.today()}.log", encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)


def queue_target(c):
    return int(max(DAILY_LIMIT["instagram"], DAILY_LIMIT["linkedin"], outreach.email_cap_today(c))
               * QUEUE_TARGET_MULTIPLIER)


def fill_queue(page):
    """Discover -> enrich -> qualify in rounds until there are enough leads ready to contact."""
    c = db.conn()
    target = queue_target(c)
    for rnd in range(1, MAX_DISCOVERY_ROUNDS + 1):
        have = db.queue_size(c)
        log.info(f"[queue] round {rnd}: {have}/{target} leads ready")
        if have >= target:
            break
        discover.run_web(WEB_SEARCHES_PER_ROUND)
        ig_ok = True
        try:
            discover.run_instagram(page, IG_HASHTAGS_PER_ROUND)
        except Blocked as e:
            log.error(f"[ig] discovery stopped - platform warning: {e}")
            ig_ok = False
        enrich.scrape_websites()
        if ig_ok:
            try:
                enrich.read_instagram_profiles(page)
            except Blocked as e:
                log.error(f"[ig] profile reading stopped - platform warning: {e}")
        enrich.mark_enriched()
        qualify.run()
    return db.queue_size(c)


def send_report(path, dry_run):
    to = os.getenv("REPORT_TO")
    if not to or not os.getenv("SMTP_HOST"):
        return
    from channels.email_out import Mailer
    c = db.conn()
    today = str(date.today())
    n = lambda col: c.execute(f"SELECT COUNT(*) FROM leads WHERE {col} LIKE ?", (f"{today}%",)).fetchone()[0]
    replies = c.execute("SELECT company, owner_name, reply_channel, reply_snippet FROM leads WHERE replied_at LIKE ?",
                        (f"{today}%",)).fetchall()
    lines = [
        f"Sunroom outreach - {today}{' (dry run)' if dry_run else ''}",
        "",
        f"Instagram DMs: {n('ig_sent_at')}",
        f"LinkedIn requests: {n('li_sent_at')}",
        f"Emails: {n('email_sent_at')} (+{n('fu1_sent_at') + n('fu2_sent_at')} follow-ups)",
        f"New leads found: {n('created_at')}",
        f"Ready for tomorrow: {db.queue_size(c)}",
        "",
        f"Replies today: {len(replies)}",
        *[f"- {r['company']} ({r['owner_name'] or '?'}, {r['reply_channel']}): {(r['reply_snippet'] or '')[:160]}" for r in replies],
        "",
        "Full log in the logs/ folder. Tracker attached.",
    ]
    with Mailer() as m:
        m.send(to, f"outreach report {today}", "\n".join(lines), attachment=path, add_footer=False)


def daily(dry_run=False):
    log.info(f"===== daily run ({'dry run' if dry_run else 'live'}) =====")
    inbox.check()
    tracker.sync_in()

    with Browser() as b:
        fill_queue(b.page)

        # Email doesn't need the browser, so it runs alongside Instagram/LinkedIn.
        mail = threading.Thread(target=outreach.send_email, kwargs={"dry_run": dry_run}, daemon=True)
        mail.start()
        outreach.send_instagram(b.page, dry_run)
        outreach.send_linkedin(b.page, dry_run)
        mail.join()

    inbox.check()
    path = tracker.export()
    try:
        send_report(path, dry_run)
    except Exception as e:
        log.warning(f"report email failed: {e}")
    log.info("===== done =====")


def login():
    with Browser() as b:
        b.page.goto("https://www.instagram.com/accounts/login/")
        b.ctx.new_page().goto("https://www.linkedin.com/login")
        input("Log into Instagram and LinkedIn in the browser window, then press Enter here...")


def stats():
    c = db.conn()
    for status, n in c.execute("SELECT status, COUNT(*) FROM leads GROUP BY status ORDER BY 2 DESC"):
        print(f"  {status:<11} {n}")
    print(f"  ready to contact: {db.queue_size(c)}")


if __name__ == "__main__":
    setup_logging()
    args = sys.argv[1:]
    cmd = args[0] if args else "stats"
    dry = "--dry-run" in args
    if not SENDER_NAME:
        sys.exit("Set SENDER_NAME in config.py first.")

    if cmd == "login":
        login()
    elif cmd == "daily":
        daily(dry)
    elif cmd == "discover":
        with Browser() as b:
            fill_queue(b.page)
        tracker.export()
    elif cmd == "send":
        chans = [a for a in args if a in ("instagram", "linkedin", "email")] or ["instagram", "linkedin", "email"]
        if "email" in chans:
            outreach.send_email(dry)
        if {"instagram", "linkedin"} & set(chans):
            with Browser() as b:
                if "instagram" in chans:
                    outreach.send_instagram(b.page, dry)
                if "linkedin" in chans:
                    outreach.send_linkedin(b.page, dry)
        tracker.export()
    elif cmd == "inbox":
        inbox.check()
    elif cmd == "tracker":
        tracker.sync_in()
        tracker.export()
    else:
        stats()

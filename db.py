"""SQLite store behind the tracker spreadsheet. One row per lead."""
import sqlite3
from datetime import datetime, date

from config import DB_PATH

COLUMNS = {
    "key": "TEXT PRIMARY KEY",       # domain, or ig:<handle> for Instagram-only leads
    "source": "TEXT",
    "company": "TEXT",
    "website": "TEXT",
    "domain": "TEXT",
    "instagram": "TEXT",
    "ig_handle": "TEXT",
    "ig_followers": "INTEGER",
    "ig_bio": "TEXT",
    "linkedin_company": "TEXT",
    "owner_name": "TEXT",
    "owner_linkedin": "TEXT",
    "email": "TEXT",
    "site_text": "TEXT",
    "score": "INTEGER",
    "score_reason": "TEXT",
    "hook": "TEXT",
    "ig_message": "TEXT",
    "li_note": "TEXT",
    "email_subject": "TEXT",
    "email_body": "TEXT",
    "followup1": "TEXT",
    "followup2": "TEXT",
    # new > enriched > qualified | rejected > active > replied | opted_out | bounced | done | won
    "status": "TEXT DEFAULT 'new'",
    "ig_sent_at": "TEXT",
    "li_sent_at": "TEXT",
    "email_sent_at": "TEXT",
    "email_msgid": "TEXT",
    "fu1_sent_at": "TEXT",
    "fu2_sent_at": "TEXT",
    "replied_at": "TEXT",
    "reply_channel": "TEXT",
    "reply_snippet": "TEXT",
    "manual": "TEXT",                # what you typed in the tracker's "Manual" column
    "notes": "TEXT",
    "created_at": "TEXT",
}

SENT_COLS = ("ig_sent_at", "li_sent_at", "email_sent_at")


def now():
    return datetime.now().isoformat(timespec="seconds")


def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    cols = ", ".join(f"{k} {v}" for k, v in COLUMNS.items())
    c.execute(f"CREATE TABLE IF NOT EXISTS leads ({cols})")
    have = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
    for k, v in COLUMNS.items():  # add columns introduced after the DB was created
        if k not in have:
            c.execute(f"ALTER TABLE leads ADD COLUMN {k} {v.replace('PRIMARY KEY', '')}")
    c.execute("CREATE TABLE IF NOT EXISTS searches (query TEXT PRIMARY KEY, ran_at TEXT)")
    c.commit()
    return c


def insert(c, key, **fields):
    """Add a lead if it's new. Returns False if we already have it."""
    if c.execute("SELECT 1 FROM leads WHERE key=?", (key,)).fetchone():
        return False
    fields.setdefault("created_at", now())
    cols = ", ".join(["key", *fields])
    c.execute(f"INSERT INTO leads ({cols}) VALUES ({', '.join('?' * (len(fields) + 1))})", (key, *fields.values()))
    c.commit()
    return True


def update(c, key, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE leads SET {cols} WHERE key=?", (*fields.values(), key))
    c.commit()


def add_note(c, key, text):
    c.execute("UPDATE leads SET notes = COALESCE(notes || ' | ', '') || ? WHERE key=?", (f"{date.today()}: {text}", key))
    c.commit()


def known_domain(c, domain):
    return bool(domain) and c.execute("SELECT 1 FROM leads WHERE domain=?", (domain,)).fetchone() is not None


def known_handle(c, handle):
    return bool(handle) and c.execute("SELECT 1 FROM leads WHERE lower(ig_handle)=?", (handle.lower(),)).fetchone() is not None


def sent_today(c, col):
    return c.execute(f"SELECT COUNT(*) FROM leads WHERE {col} LIKE ?", (f"{date.today()}%",)).fetchone()[0]


def first_email_date(c):
    row = c.execute("SELECT MIN(email_sent_at) FROM leads").fetchone()[0]
    return date.fromisoformat(row[:10]) if row else None


def queue_size(c):
    """Qualified leads that haven't been contacted on any channel yet."""
    return c.execute(
        "SELECT COUNT(*) FROM leads WHERE status='qualified' AND ig_sent_at IS NULL "
        "AND li_sent_at IS NULL AND email_sent_at IS NULL"
    ).fetchone()[0]

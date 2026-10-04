"""Fill in each new lead: scrape the website, read the Instagram profile."""
import logging

from playwright.sync_api import sync_playwright

import db
from channels import instagram
from channels.browser import Blocked
from scrape import scrape_site

log = logging.getLogger("sunroom")


def scrape_websites(limit=300):
    c = db.conn()
    rows = c.execute(
        "SELECT key, website, instagram, ig_handle, email, owner_linkedin FROM leads "
        "WHERE status='new' AND website IS NOT NULL AND site_text IS NULL LIMIT ?", (limit,)
    ).fetchall()
    if not rows:
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for r in rows:
            try:
                data = scrape_site(page, r["website"])
                # Don't overwrite details we already got from Instagram.
                for k in ("instagram", "ig_handle", "email", "owner_linkedin"):
                    if r[k]:
                        data.pop(k, None)
                data.pop("domain", None)
                db.update(c, r["key"], **{k: v for k, v in data.items() if v})
                log.info(f"[site] {r['key']}: ig={bool(data.get('instagram') or r['instagram'])} email={bool(data.get('email') or r['email'])}")
            except Exception as e:
                db.update(c, r["key"], site_text="(unreachable)")
                log.warning(f"[site] x {r['key']}: {str(e)[:80]}")
        browser.close()


def read_instagram_profiles(page, limit=150):
    c = db.conn()
    rows = c.execute(
        "SELECT key, ig_handle FROM leads WHERE status='new' AND ig_handle IS NOT NULL AND ig_bio IS NULL LIMIT ?",
        (limit,),
    ).fetchall()
    for r in rows:
        try:
            prof = instagram.read_profile(page, r["ig_handle"])
            prof.pop("website", None)
            db.update(c, r["key"], **prof)
        except Blocked:
            raise
        except Exception as e:
            db.update(c, r["key"], ig_bio="(unreadable)")
            log.warning(f"[ig] x @{r['ig_handle']}: {str(e)[:80]}")


def mark_enriched():
    c = db.conn()
    c.execute("UPDATE leads SET status='enriched' WHERE status='new' AND (site_text IS NOT NULL OR website IS NULL) "
              "AND (ig_bio IS NOT NULL OR ig_handle IS NULL)")
    c.commit()

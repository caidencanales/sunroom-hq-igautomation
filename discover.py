"""Find new agencies two ways:

1. web:  Claude web-searches "<niche> <city>" combos it hasn't tried yet -> agency homepages
2. ig:   browse Instagram hashtags agencies post client work under -> post owners -> profiles

Both only add raw leads; enrich.py fills in details and qualify.py decides who's worth it.
"""
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import db
import llm
from channels import instagram
from channels.browser import Blocked, pause
from config import (NICHES, CITIES, HASHTAGS, POSTS_PER_HASHTAG, HASHTAG_REUSE_DAYS, BROWSE_GAP_SECONDS,
                    IG_MIN_FOLLOWERS, IG_MAX_FOLLOWERS, IG_BIO_KEYWORDS, LLM_WORKERS)
from scrape import domain_of, is_skippable

log = logging.getLogger("sunroom")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


# ---------------------------------------------------------------- web ----------

def _fresh_queries(c, n):
    used = {r[0] for r in c.execute("SELECT query FROM searches")}
    fresh = [f"{niche} {city}" for niche in NICHES for city in CITIES if f"{niche} {city}" not in used]
    random.shuffle(fresh)
    return fresh[:n]


def _search(query):
    text = llm.web_search(
        f"Search the web for: {query}\n"
        "Find up to 12 independent small or mid-size agencies/studios that match. I want their OWN "
        "homepages - not directories, 'best of' listicles, Yelp, Clutch, Upwork, or social pages. "
        "Prefer businesses that show client work, testimonials, or client logos. Run a few searches "
        "if the first is thin. Reply with ONLY the homepage URLs, one per line."
    )
    urls = [u.rstrip(".,)") for u in URL_RE.findall(text)]
    return [u for u in dict.fromkeys(urls) if not is_skippable(u)]


def run_web(n_searches):
    c = db.conn()
    queries = _fresh_queries(c, n_searches)
    added = 0
    with ThreadPoolExecutor(LLM_WORKERS) as pool:
        for q, urls in zip(queries, pool.map(_search, queries)):
            c.execute("INSERT OR REPLACE INTO searches VALUES (?, ?)", (q, db.now()))
            c.commit()
            for url in urls:
                d = domain_of(url)
                if db.known_domain(c, d):
                    continue
                if db.insert(c, d, domain=d, website=f"https://{d}", source=f"web: {q}"):
                    added += 1
            log.info(f"[web] {q!r}: {len(urls)} results")
    log.info(f"[web] +{added} new leads")
    return added


# ---------------------------------------------------------------- instagram -----

def _fresh_hashtags(c, n):
    cutoff = (datetime.now() - timedelta(days=HASHTAG_REUSE_DAYS)).isoformat()
    recent = {r[0] for r in c.execute("SELECT query FROM searches WHERE query LIKE '#%' AND ran_at > ?", (cutoff,))}
    tags = [t for t in HASHTAGS if f"#{t}" not in recent]
    random.shuffle(tags)
    return tags[:n]


def looks_like_business(profile):
    f = profile["ig_followers"]
    if f is None or not (IG_MIN_FOLLOWERS <= f <= IG_MAX_FOLLOWERS):
        return False
    bio = profile["ig_bio"].lower()
    return any(k in bio for k in IG_BIO_KEYWORDS)


def run_instagram(page, n_hashtags):
    c = db.conn()
    added = 0
    for tag in _fresh_hashtags(c, n_hashtags):
        try:
            links = instagram.hashtag_post_links(page, tag, POSTS_PER_HASHTAG)
        except Blocked:
            raise
        except Exception as e:
            log.warning(f"[ig] #{tag} failed: {e}")
            continue
        log.info(f"[ig] #{tag}: {len(links)} posts")
        seen = set()
        for href in links:
            try:
                handle = instagram.post_owner(page, href)
                if not handle or handle in seen or db.known_handle(c, handle):
                    continue
                seen.add(handle)
                prof = instagram.read_profile(page, handle)
                if not looks_like_business(prof):
                    continue
                site = prof["website"]
                domain = domain_of(site) if site and not is_skippable(site) else None
                if domain and db.known_domain(c, domain):
                    db.update(c, domain, ig_handle=handle, instagram=f"https://www.instagram.com/{handle}/",
                              ig_followers=prof["ig_followers"], ig_bio=prof["ig_bio"])
                    continue
                db.insert(
                    c, domain or f"ig:{handle.lower()}", source=f"ig: #{tag}", domain=domain,
                    website=f"https://{domain}" if domain else None, ig_handle=handle,
                    instagram=f"https://www.instagram.com/{handle}/", ig_followers=prof["ig_followers"],
                    ig_bio=prof["ig_bio"], company=handle,
                )
                added += 1
                log.info(f"  + @{handle} ({prof['ig_followers']} followers)")
            except Blocked:
                raise
            except Exception as e:
                log.warning(f"  x {href}: {str(e)[:100]}")
        c.execute("INSERT OR REPLACE INTO searches VALUES (?, ?)", (f"#{tag}", db.now()))
        c.commit()
        pause(BROWSE_GAP_SECONDS)
    log.info(f"[ig] +{added} new leads")
    return added

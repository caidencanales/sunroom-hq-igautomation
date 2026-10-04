"""Pull the useful bits out of an agency website."""
import re
from urllib.parse import urlparse

IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})/?", re.I)
LI_RE = re.compile(r"linkedin\.com/(company|in)/([A-Za-z0-9_\-%]+)/?", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IG_NOT_PROFILES = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "sharer", "direct"}
GENERIC_INBOX = ("info@", "hello@", "contact@", "admin@", "support@", "team@", "office@", "studio@")
BAD_EMAIL = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", "sentry.io", "wixpress.com", "example.com")

# Directories, marketplaces and socials - not agency homepages.
SKIP_DOMAINS = (
    "yelp.", "clutch.co", "upwork.", "fiverr.", "linkedin.", "instagram.", "facebook.",
    "youtube.", "tiktok.", "x.com", "twitter.", "thumbtack.", "expertise.com", "designrush.",
    "goodfirms.", "indeed.", "glassdoor.", "reddit.", "wikipedia.", "google.", "bing.",
    "vimeo.", "behance.", "dribbble.", "sortlist.", "themanifest.", "bark.com", "linktr.ee",
    "weddingwire.", "theknot.", "zillow.", "mapquest.", "bbb.org", "angi.", "houzz.",
)


def domain_of(url):
    return urlparse(url if "//" in url else f"https://{url}").netloc.lower().removeprefix("www.")


def is_skippable(url):
    return any(s in url.lower() for s in SKIP_DOMAINS)


def pick_email(emails, domain):
    emails = [e for e in dict.fromkeys(emails) if not e.lower().endswith(BAD_EMAIL)]
    # A person's address at their own domain beats info@, which beats anything else.
    own = [e for e in emails if domain and e.lower().endswith("@" + domain)]
    personal = [e for e in own if not e.lower().startswith(GENERIC_INBOX)]
    return (personal or own or emails or [None])[0]


def scrape_site(page, url):
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    domain = domain_of(page.url)
    html = page.content()
    text = page.inner_text("body")[:4000]

    # About/Team pages are where owner names and client lists live.
    about = page.query_selector("a[href*='about'], a[href*='team'], a[href*='story'], a[href*='who-we-are']")
    if about:
        try:
            about.click(timeout=5000)
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            html += page.content()
            text += "\n\n--- ABOUT PAGE ---\n" + page.inner_text("body")[:3000]
        except Exception:
            pass

    html = html.replace("\\/", "/")  # links inside inline JSON are escaped
    ig = next((m for m in IG_RE.findall(html) if m.lower() not in IG_NOT_PROFILES), None)
    li_company = next((f"https://www.linkedin.com/company/{m[1]}/" for m in LI_RE.findall(html) if m[0] == "company"), None)
    li_person = next((f"https://www.linkedin.com/in/{m[1]}/" for m in LI_RE.findall(html) if m[0] == "in"), None)
    return {
        "company": (page.title() or "").split("|")[0].split(" - ")[0].strip()[:100],
        "domain": domain,
        "instagram": f"https://www.instagram.com/{ig}/" if ig else None,
        "ig_handle": ig,
        "linkedin_company": li_company,
        "owner_linkedin": li_person,
        "email": pick_email(EMAIL_RE.findall(html), domain),
        "site_text": text,
    }

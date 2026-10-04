"""Instagram: read profiles / hashtag pages, and send DMs."""
import re
from urllib.parse import urlparse, parse_qs, unquote

from channels.browser import check_blocked, pause
from config import BROWSE_GAP_SECONDS

POST_LINK_RE = re.compile(r"^/(?:[A-Za-z0-9_.]+/)?(p|reel)/[A-Za-z0-9_-]+/?$")
OWNER_RE = re.compile(r"-\s*([A-Za-z0-9_.]{2,30}) on [A-Z][a-z]+ \d")
FOLLOWERS_RE = re.compile(r"([\d.,]+)\s*([KkMm]?)\s+Followers")


def _count(num, suffix):
    n = float(num.replace(",", ""))
    return int(n * {"k": 1_000, "m": 1_000_000}.get(suffix.lower(), 1))


def _meta(page, prop):
    try:
        return page.get_attribute(f"meta[property='{prop}']", "content", timeout=3000) or ""
    except Exception:
        return ""


def hashtag_post_links(page, tag, limit):
    page.goto(f"https://www.instagram.com/explore/tags/{tag}/", timeout=30000)
    pause(BROWSE_GAP_SECONDS)
    check_blocked(page)
    page.mouse.wheel(0, 2500)
    pause((2, 4))
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    return list(dict.fromkeys(h for h in hrefs if h and POST_LINK_RE.match(h)))[:limit]


def post_owner(page, href):
    page.goto(f"https://www.instagram.com{href}", timeout=30000)
    pause(BROWSE_GAP_SECONDS)
    check_blocked(page)
    m = OWNER_RE.search(_meta(page, "og:description")) or OWNER_RE.search(_meta(page, "og:title"))
    if m:
        return m.group(1)
    # Fallback: first profile link in the post header.
    for h in page.eval_on_selector_all("header a[href], article a[href]", "els => els.map(e => e.getAttribute('href'))"):
        if h and re.fullmatch(r"/[A-Za-z0-9_.]{2,30}/", h) and h.strip("/") not in ("explore", "reels"):
            return h.strip("/")
    return None


def read_profile(page, handle):
    page.goto(f"https://www.instagram.com/{handle}/", timeout=30000)
    pause(BROWSE_GAP_SECONDS)
    check_blocked(page)
    desc = _meta(page, "og:description")
    fm = FOLLOWERS_RE.search(desc)
    header = ""
    if page.query_selector("header"):
        header = page.inner_text("header")[:900]

    website = None
    for h in page.eval_on_selector_all("header a[href]", "els => els.map(e => e.href)"):
        if "l.instagram.com" in h:  # IG wraps outbound links
            website = unquote(parse_qs(urlparse(h).query).get("u", [""])[0]) or None
        elif h.startswith("http") and "instagram.com" not in h:
            website = h
        if website:
            break

    return {
        "ig_followers": _count(*fm.groups()) if fm else None,
        "ig_bio": f"{desc}\n{header}".strip(),
        "website": website,
    }


def send_dm(page, handle, message):
    page.goto(f"https://www.instagram.com/{handle}/", timeout=30000)
    pause((3, 6))
    check_blocked(page)

    button = page.get_by_role("button", name="Message", exact=True)
    if not button.count():
        button = page.get_by_role("button", name=re.compile(r"^Message$", re.I))
    button.first.click(timeout=10000)

    box = page.get_by_role("textbox").last
    box.wait_for(timeout=20000)
    pause((1.5, 3))
    box.click()
    for i, line in enumerate(message.split("\n")):
        if i:
            page.keyboard.press("Shift+Enter")  # line break without sending
        page.keyboard.type(line, delay=35)
    pause((1, 2))
    page.keyboard.press("Enter")
    pause((2.5, 4))
    check_blocked(page)

    # Confirm the message actually landed in the thread.
    snippet = message.split("\n")[0][:40]
    if not page.get_by_text(snippet, exact=False).count():
        raise RuntimeError("message not visible in thread after sending")

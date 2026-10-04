"""Shared browser session + pacing.

Uses your own logged-in browser profile. If Instagram or LinkedIn shows a checkpoint,
captcha, or "action blocked" screen, Blocked is raised and the channel stops for the day.
"""
import random
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from config import BROWSER_PROFILE, SEND_GAP_SECONDS, BATCH_SIZE, BATCH_BREAK_SECONDS, SEND_HOURS


class Blocked(Exception):
    """The platform is asking us to slow down or verify. Stop and let a human look."""


class LimitReached(Exception):
    """A platform quota (e.g. LinkedIn's weekly invite limit) was hit."""


BLOCK_URL_SIGNS = ("challenge", "checkpoint", "/suspended", "captcha")
BLOCK_TEXT_SIGNS = (
    "action blocked", "try again later", "we restrict certain activity", "unusual activity",
    "confirm it's you", "verify your account", "your account has been temporarily",
    "let us do this check", "security verification",
)


def pause(span):
    time.sleep(random.uniform(*span))


def check_blocked(page):
    if any(s in page.url.lower() for s in BLOCK_URL_SIGNS):
        raise Blocked(page.url)
    try:
        body = page.inner_text("body", timeout=5000)[:4000].lower()
    except Exception:
        return
    hit = next((s for s in BLOCK_TEXT_SIGNS if s in body), None)
    if hit:
        raise Blocked(f'page says "{hit}"')


def in_send_hours():
    return SEND_HOURS[0] <= datetime.now().hour < SEND_HOURS[1]


class Pacer:
    """Spreads sends out: a gap between each message and a longer break every few."""

    def __init__(self):
        self.sent = 0

    def after_send(self):
        self.sent += 1
        pause(BATCH_BREAK_SECONDS if self.sent % BATCH_SIZE == 0 else SEND_GAP_SECONDS)


class Browser:
    def __init__(self, headless=False):
        self.headless = headless

    def __enter__(self):
        self.pw = sync_playwright().start()
        self.ctx = self.pw.chromium.launch_persistent_context(
            BROWSER_PROFILE, headless=self.headless, viewport={"width": 1280, "height": 860}
        )
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def __exit__(self, *exc):
        self.ctx.close()
        self.pw.stop()

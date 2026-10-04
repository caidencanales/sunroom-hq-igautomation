"""LinkedIn: connection request with a note to the founder's personal profile."""
from channels.browser import check_blocked, pause, LimitReached

LIMIT_SIGNS = ("weekly invitation limit", "you've reached the limit", "out of invitations",
               "monthly limit for custom invitations", "personalized invitations")


def _check_limits(page):
    body = page.inner_text("body", timeout=5000)[:5000].lower()
    hit = next((s for s in LIMIT_SIGNS if s in body), None)
    if hit:
        raise LimitReached(hit)


def send_connect(page, profile_url, note):
    if "/in/" not in profile_url:
        raise ValueError("not a personal /in/ profile")
    page.goto(profile_url, timeout=30000)
    pause((3, 6))
    check_blocked(page)

    main = page.locator("main")
    if main.get_by_role("button", name="Pending", exact=False).count():
        raise ValueError("invite already pending")

    connect = main.get_by_role("button", name="Connect", exact=False)
    if connect.count() and connect.first.is_visible():
        connect.first.click(timeout=10000)
    else:
        main.get_by_role("button", name="More", exact=False).first.click(timeout=10000)
        pause((1, 2))
        page.get_by_role("button", name="Connect", exact=False).last.click(timeout=10000)
    pause((1.5, 3))
    _check_limits(page)

    add_note = page.get_by_role("button", name="Add a note")
    add_note.click(timeout=10000)
    pause((1, 2))
    _check_limits(page)  # free accounts get a small monthly quota of notes

    page.locator("textarea").first.click()
    page.keyboard.type(note[:290], delay=30)
    pause((1, 2))
    page.get_by_role("button", name="Send", exact=False).last.click(timeout=10000)
    pause((2.5, 4))
    check_blocked(page)
    _check_limits(page)

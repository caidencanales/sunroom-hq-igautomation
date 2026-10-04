"""Decide who's worth messaging, find the founder, and write the messages.

Per lead:  score (cheap)  ->  if >= MIN_SCORE: find founder  ->  draft  ->  second-pass check
Leads below MIN_SCORE stop after the first call.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import anthropic
from pydantic import BaseModel, Field

import db
import llm
from config import OFFER, ICP, MIN_SCORE, SENDER_NAME, COMPANY, LLM_WORKERS

log = logging.getLogger("sunroom")


# ---------------------------------------------------------------- schemas ------

class Score(BaseModel):
    score: int = Field(description="0-100 fit/ROI score against the ideal customer profile")
    reason: str = Field(description="1-2 sentences citing the specific evidence behind the score")
    company: str = Field(description="Clean company/brand name")
    owner_name: str = Field(description="Founder/owner full name if it appears in the data, else empty")


class Messages(BaseModel):
    hook: str = Field(description="The one specific, true detail about them the messages are built on")
    ig_message: str = Field(description="Instagram DM")
    li_note: str = Field(description="LinkedIn connection note, under 280 characters")
    email_subject: str
    email_body: str
    followup1: str = Field(description="Short email follow-up, different angle")
    followup2: str = Field(description="Short final close-the-loop email")


class Review(BaseModel):
    send: bool = Field(description="False only if this lead clearly shouldn't be contacted at all")
    problems: str = Field(description="What was wrong with the drafts, or 'none'")
    messages: Messages = Field(description="Final versions, with every problem fixed")


# ---------------------------------------------------------------- prompts ------

SCORE_SYSTEM = f"""You qualify leads for {COMPANY}.

PRODUCT:
{OFFER}

IDEAL CUSTOMER:
{ICP}

Score how valuable this business would be as a customer. Be strict: most leads are not a fit.
Reward concrete evidence of paying clients and delivery volume. Penalize missing evidence."""

VOICE = f"""You write first-touch messages from {SENDER_NAME}, who runs {COMPANY}, to owners of creative agencies.

The goal is a real conversation, not a pitch. It should read like a note from one agency person
to another who noticed their work.

- Open with ONE concrete, true detail from the data (a client, a type of project, a recent post,
  their niche, their city). Never invent facts. If the data is thin, stay general but honest.
- Show you get their world: client feedback scattered across texts/email/Frame.io, "which version
  is final", chasing invoices, onboarding new clients.
- Mention {COMPANY} once, plainly and upfront - {SENDER_NAME} built/runs it. No feature lists.
- Banned: "revolutionize", "game-changer", "streamline", "solution", "leverage", "synergy",
  "I hope this finds you well", "quick question", fake compliments, fake familiarity, urgency.
- End with one easy question they can answer in a few words.
- Use their first name if known. Write like a person texts: short lines, contractions, lowercase
  is fine on IG.

Formats:
- ig_message: 2-4 short lines, under 350 characters, no links.
- li_note: under 280 characters, no links.
- email_subject: 2-5 words, lowercase, no clickbait.
- email_body: under 90 words, signed "{SENDER_NAME}". You may mention {COMPANY} by name; no link needed.
- followup1: under 50 words, new angle (e.g. one specific pain or the free trial).
- followup2: under 35 words, polite close-the-loop.
Every message must be obviously written for THIS agency - if it could be sent to anyone, rewrite it."""

REVIEW_SYSTEM = f"""You are the last check before outreach goes out under {SENDER_NAME}'s name. Nobody
else will read these before they're sent, so be demanding.

{VOICE}

Check every draft against the lead data:
1. Any claim not supported by the data? Remove or fix it.
2. Generic/template-sounding? Rewrite around the hook.
3. Salesy words, hype, or pressure? Remove.
4. Over length limits? Cut.
5. Wrong name, wrong company, or awkward phrasing? Fix.
Return the corrected final versions. Set send=false only if the lead is clearly not a creative
agency, is a competitor, or contacting them would be inappropriate."""


# ---------------------------------------------------------------- steps --------

def lead_text(r):
    return (
        f"Company: {r['company']}\nWebsite: {r['website']}\nInstagram: {r['instagram']} "
        f"({r['ig_followers'] or '?'} followers)\nLinkedIn (company): {r['linkedin_company']}\n"
        f"Owner name (if known): {r['owner_name'] or '?'}\nFound via: {r['source']}\n\n"
        f"Instagram bio/header:\n{r['ig_bio'] or 'n/a'}\n\nWebsite text:\n{(r['site_text'] or 'n/a')[:6000]}"
    )


def find_founder(company, website, ig_handle, known_name):
    text = llm.web_search(
        f"Find the founder or owner of this creative agency: {company} "
        f"(website: {website or 'unknown'}, Instagram: @{ig_handle or 'unknown'}"
        f"{', possibly named ' + known_name if known_name else ''}).\n"
        "I need their personal LinkedIn profile URL (linkedin.com/in/...) and a business email "
        "ONLY if it is publicly listed. Make sure it's the right person at the right company.\n"
        "Answer in exactly this format, writing none when unknown:\n"
        "NAME: ...\nLINKEDIN: ...\nEMAIL: ...",
        max_uses=4,
    )
    get = lambda label: (re.search(rf"{label}:\s*(\S.*)", text) or [None, ""])[1].strip()
    name, li, email = get("NAME"), get("LINKEDIN"), get("EMAIL")
    return {
        "owner_name": name if name.lower() != "none" else None,
        "owner_linkedin": li if "linkedin.com/in/" in li else None,
        "email": email if "@" in email and email.lower() != "none" else None,
    }


def qualify_one(key):
    c = db.conn()
    r = c.execute("SELECT * FROM leads WHERE key=?", (key,)).fetchone()
    data = lead_text(r)

    s = llm.parse(Score, SCORE_SYSTEM, data, effort="low", max_tokens=3000)
    if not s:
        db.update(c, key, status="rejected", notes="model declined")
        return key, None, "declined"
    db.update(c, key, score=s.score, score_reason=s.reason, company=s.company or r["company"],
              owner_name=s.owner_name or r["owner_name"])
    if s.score < MIN_SCORE:
        db.update(c, key, status="rejected")
        return key, s.score, "rejected"

    if not (r["owner_linkedin"] and r["email"]):
        f = find_founder(s.company, r["website"], r["ig_handle"], s.owner_name)
        db.update(c, key, **{k: v for k, v in f.items() if v and not r[k]})
    r = c.execute("SELECT * FROM leads WHERE key=?", (key,)).fetchone()
    data = lead_text(r) + f"\n\nOwner name: {r['owner_name'] or 'unknown'}\nWhy they fit: {s.reason}"

    draft = llm.parse(Messages, VOICE, data, effort="medium")
    if not draft:
        db.update(c, key, status="rejected", notes="model declined to draft")
        return key, s.score, "declined"
    review = llm.parse(Review, REVIEW_SYSTEM, f"LEAD DATA:\n{data}\n\nDRAFTS:\n{draft.model_dump_json(indent=2)}",
                       effort="medium")
    if not review or not review.send:
        db.update(c, key, status="rejected", notes=f"review: {review.problems if review else 'declined'}")
        return key, s.score, "rejected by review"

    m = review.messages
    db.update(c, key, status="qualified", hook=m.hook, ig_message=m.ig_message, li_note=m.li_note[:290],
              email_subject=m.email_subject, email_body=m.email_body, followup1=m.followup1, followup2=m.followup2)
    return key, s.score, "qualified"


def run(limit=200):
    c = db.conn()
    keys = [r[0] for r in c.execute("SELECT key FROM leads WHERE status='enriched' LIMIT ?", (limit,))]
    if not keys:
        return 0
    qualified = 0

    def safe(key):
        try:
            return qualify_one(key)
        except anthropic.APIError as e:
            return key, None, f"api error: {e}"

    with ThreadPoolExecutor(LLM_WORKERS) as pool:
        for key, score, outcome in pool.map(safe, keys):
            qualified += outcome == "qualified"
            log.info(f"[qualify] {str(score or '-'):>3}  {key:<40} {outcome}")
    return qualified

# Sunroom HQ outreach automation

Finds creative agencies that would get the most out of [Sunroom](https://www.sunroomhq.com), writes each one a personal message, and reaches out on Instagram, email, and LinkedIn every day. It runs on its own each morning, and everything is tracked in one spreadsheet.

```
            ┌── web: Claude searches "<niche> <city>" it hasn't tried ──┐
discover ───┤                                                           ├──> enrich ──> qualify ──> send ──> inbox ──> tracker.xlsx
            └── instagram: hashtags -> post owners -> business profiles ┘   (site +     (score,     (IG, email,  (replies,   + daily
                                                                             IG bio)     founder,     LinkedIn)    bounces)    report email
                                                                                         messages,
                                                                                         2nd check)
```

## How it finds the right people
- **Instagram hashtags** that agencies post client work under (`#realestatevideo`, `#videoproductioncompany`, ...). It opens the top posts, goes to each post owner's profile, and keeps business-looking accounts (follower range plus bio keywords).
- **Web search**: Claude searches combinations of niche and city across 12 niches and 35 cities. It never repeats a search, so every day brings new agencies.
- **Enrichment**: scrapes each website and About page for client logos, testimonials, Instagram, LinkedIn and email.
- **Scoring**: Claude scores each agency 0–100 against the ideal-customer description in `config.py`. Proof of paying clients and delivery volume count the most. Only leads scoring 70 or higher continue.
- **Founder lookup**: Claude web-searches for the owner's name, personal LinkedIn and public email.

## How the messages are written
Each one is written by one agency person to another: it opens with one real detail about their work, names a problem they actually have, mentions Sunroom once and plainly, and ends with an easy question. A second Claude pass checks every message against the lead's data. It removes invented claims, template phrasing and sales language, and enforces length limits before anything goes out.

## Sending
| Channel | Default per day | Notes |
|---|---|---|
| Instagram DM | 25 | `DAILY_LIMIT` in config |
| LinkedIn invite + note | 15 | LinkedIn caps invites at about 100 a week; free accounts get only a few custom notes a month |
| Email | 20, rising by 10 a day to 100 | Gradual ramp protects deliverability. Follow-ups are off by default (`EMAIL_FOLLOWUPS`) |

Sends are spaced 1.5–4 minutes apart, with a 15–35 minute break every 8 messages, and only between 9am and 8pm. If Instagram or LinkedIn shows a checkpoint, captcha or "action blocked" screen, that channel stops for the day and the report tells you.

## tracker.xlsx
- **Dashboard**: totals, and sends and reply rate per channel.
- **Leads**: score, owner, links, every message, send times and replies.
- **Daily**: activity by day.
- **Replies**: everyone who answered.

Type `replied`, `won`, `skip` or `not interested` in the **Manual** column and the next run picks it up. Email replies, opt-outs and bounces are detected automatically over IMAP.

## Setup
```
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env          # fill in API key, SMTP/IMAP, address, report email
python run.py login             # log into Instagram + LinkedIn once in the bot browser
python run.py daily --dry-run   # full run without sending, then check tracker.xlsx
python run.py daily             # live
powershell -ExecutionPolicy Bypass -File schedule_windows.ps1   # every morning at 8:30
```

## Cost
Rough estimate: $10–25 a day in Claude API usage at full volume. That covers about 4 calls per qualified lead plus web searches at $10 per 1,000. To spend less, lower `MAX_DISCOVERY_ROUNDS` or change `MODEL` in config.

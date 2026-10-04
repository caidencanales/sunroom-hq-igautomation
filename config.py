"""Everything you'd want to tune lives here. Secrets go in .env (see .env.example)."""
from dotenv import load_dotenv

load_dotenv()

# --- Who is sending -------------------------------------------------------------
SENDER_NAME = "Caiden"
COMPANY = "Sunroom"
COMPANY_URL = "sunroomhq.com"

MODEL = "claude-opus-5-5"

OFFER = """
Sunroom (sunroomhq.com) is an all-in-one branded client portal for creative agencies:
media review with frame-specific feedback and version tracking, invoicing and payments,
contract signing, project management, shared calendars, file delivery, and a light CRM.
Built for video agencies by an agency owner. 14-day free trial, no card, 90-day money-back
guarantee. It replaces the Frame.io + Dropbox + HoneyBook + email/text mess.
"""

# --- Who we want ----------------------------------------------------------------
ICP = """
Highest ROI: small-to-mid creative SERVICE agencies (2-30 people) that deliver client work
in rounds of revisions - video production, editing agencies, SMMAs producing short-form
video, real estate media companies, photo studios, design studios.

Strong signals (each one raises the score):
- Proof of PAYING clients: client logos, testimonials, case studies, tagged brand work,
  "trusted by", retainers, many different clients in recent posts
- Volume: multiple projects a week, ongoing content packages, monthly retainers
- Pain signals: mentions Frame.io, Dropbox, Google Drive, WeTransfer, HoneyBook, Dubsado,
  "revisions", "turnaround", "deliverables"
- Owner-operated: founder is visible and is the buyer
- Active: posted in the last 30 days
- Sells to businesses (brands, realtors, restaurants, B2B) or high-volume weddings

Low ROI (score under 40): solo hobbyists, students, influencers selling courses,
big production houses with in-house tooling, software/product companies, agencies with no
creative deliverables, accounts with no posts in 3+ months, non-English markets.
"""
MIN_SCORE = 70

# --- Where to look --------------------------------------------------------------
NICHES = [
    "video production company", "video editing agency", "real estate videography",
    "real estate media company", "short form content agency", "social media agency video",
    "commercial videographer", "brand video agency", "podcast production studio",
    "wedding videography company", "corporate video production", "photo and video studio",
]
CITIES = [
    "Austin", "Dallas", "Houston", "San Antonio", "Miami", "Orlando", "Tampa", "Atlanta",
    "Nashville", "Charlotte", "Denver", "Phoenix", "Scottsdale", "Las Vegas", "Los Angeles",
    "San Diego", "San Francisco", "Seattle", "Portland", "Salt Lake City", "Chicago",
    "Minneapolis", "Detroit", "Columbus", "New York", "Brooklyn", "Boston", "Philadelphia",
    "Washington DC", "Raleigh", "Toronto", "Vancouver", "London", "Manchester", "Sydney",
]
# Instagram hashtags agencies actually post their client work under.
HASHTAGS = [
    "realestatevideo", "realestatevideography", "realestatemedia", "videoproductioncompany",
    "videoproductionagency", "commercialvideography", "brandvideo", "contentagency",
    "videoeditingservices", "shortformcontent", "socialmediaagency", "corporatevideo",
    "videomarketingagency", "listingvideo", "restaurantcontent", "productvideography",
    "podcastproduction", "weddingfilmmaker", "creativeagency", "contentcreationagency",
]
IG_MIN_FOLLOWERS = 400
IG_MAX_FOLLOWERS = 150_000
IG_BIO_KEYWORDS = [
    "video", "film", "media", "production", "content", "creative", "agency", "studio",
    "editing", "photo", "visual", "real estate", "brand", "marketing", "book", "inquir",
]
POSTS_PER_HASHTAG = 15
HASHTAG_REUSE_DAYS = 10        # top posts rotate, so a tag can be revisited after this

# --- Daily volume ---------------------------------------------------------------
DAILY_LIMIT = {"instagram": 25, "linkedin": 15}
# LinkedIn caps invitations at roughly 100 per week, so more than ~15/day just fails.

EMAIL_START_PER_DAY = 20       # new sending domain: start low...
EMAIL_RAMP_PER_DAY = 10        # ...add this many per day...
EMAIL_MAX_PER_DAY = 100        # ...up to this cap.
EMAIL_FOLLOWUPS = False        # True = send followup1 on day 3 and followup2 on day 7
INCLUDE_EMAIL_FOOTER = True    # opt-out line + business address (US CAN-SPAM requires it)

# --- Pacing (keeps sends spread out at a normal person's pace) -------------------
SEND_GAP_SECONDS = (90, 240)          # between two messages
BATCH_SIZE = 8                        # after this many sends...
BATCH_BREAK_SECONDS = (900, 2100)     # ...take a 15-35 minute break
BROWSE_GAP_SECONDS = (4, 10)          # between page loads while discovering
SEND_HOURS = (9, 20)                  # only send between 9am and 8pm local time
EMAIL_GAP_SECONDS = (30, 120)

# --- Discovery budget per daily run -------------------------------------------
QUEUE_TARGET_MULTIPLIER = 1.3   # keep this many x the daily cap in qualified leads
MAX_DISCOVERY_ROUNDS = 6
WEB_SEARCHES_PER_ROUND = 6
IG_HASHTAGS_PER_ROUND = 3
LLM_WORKERS = 6                 # parallel Claude calls when qualifying

# --- Files ----------------------------------------------------------------------
BROWSER_PROFILE = "./browser_profile"
DB_PATH = "./leads.db"
TRACKER_PATH = "./tracker.xlsx"
LOG_DIR = "./logs"

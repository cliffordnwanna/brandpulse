# Platform Limitations

BrandPulse currently monitors the platforms where a connector can be built
without a paid API tier or a manually-granted access token. Several major
social platforms are excluded from MVP for reasons outside engineering
effort — each requires either a paid subscription, an approval process with
an unpredictable timeline, or credentials tied to a specific page/account
that only the brand itself can grant.

This is not a coverage gap we're unaware of — it's a deliberate MVP scope
decision, documented here so it's visible in every report rather than a
silent absence.

| Platform | Status | Reason | Official docs |
|---|---|---|---|
| X/Twitter | Paid API required | Basic tier ~$100/month minimum | https://developer.twitter.com/en/docs/twitter-api |
| Instagram | Page admin access required | Meta Graph API needs page access token | https://developers.facebook.com/docs/instagram-api |
| Facebook | Page admin access required | Meta Graph API needs page access token | https://developers.facebook.com/docs/graph-api |
| TikTok | Research API approval required | Application review process, not instant | https://developers.tiktok.com/doc/overview |
| Apple App Store | Blocked by robots.txt | `itunes.apple.com/robots.txt` disallows `/*/rss/*` — the only working public reviews source found (see below) | https://itunes.apple.com/robots.txt |

### Apple App Store — a documented, deliberate block, not a bug

The `app-store-scraper` PyPI package (the obvious library choice) is
non-functional as of this milestone: it authenticates by scraping a bearer
token out of the app's `apps.apple.com` landing-page HTML, and Apple has
since restructured that page so the token is no longer present — every
review request the library makes fails with a 401, unrelated to robots.txt.

The alternative found and validated against live data during this
milestone — Apple's public customer-reviews RSS/JSON feed at
`itunes.apple.com/{country}/rss/customerreviews/...` — works and requires
no authentication, but `itunes.apple.com/robots.txt` explicitly disallows
`/*/rss/*`. BrandPulse checks `robots.txt` programmatically before every
request (Engineering Design §17) and respects it — this connector
deliberately does not scrape a path Apple's own robots.txt disallows, so it
is left disabled by default (returns `FAILED`/`disallowed_by_robots_txt`)
rather than silently ignoring the block.

Closing this gap legitimately requires either an official App Store
Connect API integration (Apple-sanctioned, requires developer account
access to the app's own App Store Connect listing) or explicit written
permission from Apple to use the RSS feed outside its robots.txt terms —
not a code change.

## What this means for interpreting a report

Sentiment and complaint volume in this report reflect only the platforms
BrandPulse currently connects to (Google Play, and others as they're added
in future milestones). A spike or lull in a given category should be read
as "what we can see," not "the complete picture of customer sentiment
everywhere." If a customer-facing incident is trending heavily on X/Twitter
or TikTok, this report will not show it until those connectors exist.

## Path to closing the gap

Each excluded platform's connector is buildable once its access
prerequisite is met:

- **X/Twitter**: requires a paid developer account at the Basic tier or above.
- **Instagram / Facebook**: requires the brand to grant a Meta Graph API
  page access token for its own official page(s).
- **TikTok**: requires submitting and being approved for TikTok's Research
  API program, which is not instant and not guaranteed.

None of these are architecture blockers — `BaseConnector` (Engineering
Design §3) is designed so any of these can be added as a new connector
module without touching the orchestrator, storage, classification, or
reporting layers.

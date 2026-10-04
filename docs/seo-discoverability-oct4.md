# Public content and discovery — October 4, 2026

This rebuild adds server-rendered product content at `/` and eight explanatory pages: `/about`, `/how-it-works`, `/pricing`, `/evidence`, `/ai-detector-guide`, `/document-cleanup`, `/privacy`, and `/terms`.

The homepage describes the three providers' actual roles, document inputs and exports, language limits, quoted pricing, detector assessment, and the scope of metadata/invisible-character cleanup. It uses existing txtzi branding and animations, with reduced-motion support. The anonymous homepage remains readable after JavaScript initializes; `/#studio`, account/reset/setup/checkout flows and existing signed-in routes continue into the app. Returning to the public root preserves the in-memory writing draft. Public resource links from the studio open separately to retain the current draft.

Each page has a distinct title and description, a canonical built from trusted `APP_URL`, absolute social metadata, and factual Organization/WebSite/WebPage structured data. The root includes SoftwareApplication data; subpages include breadcrumbs. No invented reviews, ratings, endorsements, success rates or guaranteed outcomes are included. Pricing, payment availability, promotional grants and retention are derived from deployment settings. UI language is English; editing languages and English-only detector eligibility are described separately.

Only existing preserved evidence is linked: the stored live-app example and the ten-trial research record. Lost unpublished experiment artifacts are not recreated or represented as independently inspectable results. The original archived research is served with a trusted canonical; its content is unchanged.

The sitemap includes only existing public pages and the archived research page. Robots permits public search discovery, including OAI-SearchBot and Bingbot, while each group excludes private APIs, health/schema endpoints and account-related query URLs. API and account-query responses carry `X-Robots-Tag: noindex, nofollow` and `Cache-Control: no-store`. The unused static HTML template URL redirects to `/`.

## Verification

- HTTP tests inspect complete server HTML, canonical host independence, JSON-LD, current settings, private noindex headers, robots exclusions, reachable sitemap paths and preserved evidence claims.
- Node tests exercise anonymous landing preservation, early studio clicks, signed-in/deep routes, setup/reset/checkout exceptions, return navigation, server errors and skip-link focus.
- Existing result rendering tests remain in the verification run.
- No claim of browser visual QA is made: browser access to this deployment was blocked by the available browser environment in the preceding session.

Search-engine eligibility does not imply indexing, ranking or a recommendation by an AI chat system. Search Console/Bing ownership reporting is not connected by this change.

## IndexNow after deployment

`python scripts/submit_indexnow.py --origin https://txtzi.onrender.com` produces an offline payload. Add `--check` for read-only live verification. Add `--submit --receipt docs/indexnow-submission.json` to verify then send one notification, with no automatic retries. The tool checks the ownership key, sitemap membership, Bingbot permission, direct HTML status, canonical and noindex signals before posting. Only the fixed IndexNow endpoint is used. A receipt means the notification was received, not that pages were indexed.

Protocol reference checked October 4, 2026: https://www.indexnow.org/documentation

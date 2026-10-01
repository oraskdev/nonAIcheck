# txtzi release status

Live application: https://txtzi.onrender.com/

Deployed to Render on 1 October 2026. GitHub main contains the application and brand refresh.

## Verified on 1 October 2026

- DOCX upload, text extraction and a fixed quote through the application API.
- Registration immediately receives 500 promotional credits; repeated weekly housekeeping does not grant twice.
- Repeated Generate requests deduct the quote only once.
- A real application job completed with Anthropic claude-sonnet-4-5-20250929, OpenAI gpt-4.1-mini and xAI grok-4.3.
- The output changed while protected numeric values remained intact. The synthetic sample had 199 source words and 193 revised words, including its title, with one changed block.
- PDF, DOCX, PPTX and TXT downloads succeeded. An export fix prevents a repeated source title in PDF, DOCX and TXT.
- Unauthenticated document access was rejected.
- Chromium checks passed against the local running application at desktop and mobile sizes: navigation, editor focus, sample loading, no horizontal page overflow, reduced motion and no JavaScript exceptions.
- Word/PDF samples and all pages of the new media kit were rendered and visually reviewed.

## Live Render verification

- Public health check and PostgreSQL connection
- New account immediately receives 500 weekly credits
- DOCX upload, extraction and upfront 399-credit quote
- Repeated generation request charges only once
- Claude, OpenAI and Grok completed on live Render worker
- Live PDF, DOCX, PPTX and TXT exports downloaded
- Unauthenticated document access rejected

The second live sample revised two blocks and retained protected numbers. The first fluent sample completed all three passes without wording changes. See `docs/live-acceptance.json` for the latest result. Administrator dashboard access was separately verified.

## Product positioning

The homepage now explicitly describes AI-generated text rewriting, natural phrasing, three AI providers, the current detector-availability status and fresh-document metadata cleanup. It does not advertise guaranteed undetectability or universal hidden-watermark removal.

## Brand and interface

A custom three-stroke X replaces the earlier logo. Outlined vector wordmarks include primary, reversed and monochrome versions. The interface uses midnight blue, mint and violet, with a floating document, scan highlight and sequential provider animations. The homepage and How it works explain the three different editorial roles. Completed documents identify the model versions actually used.

## Outstanding production work

- txtzi.com registration and DNS are not completed. Spaceship returned a Cloudflare 1010 client-signature block; no purchase was made.
- Resend is configured using the approved existing key and sender. Delivery is not verified: direct validation from the deployment workspace was blocked by the provider.
- Stripe checkout code exists but no Stripe credentials or live/test webhook integration has been validated. Purchases remain disabled when payment configuration is absent.
- The interface is English. Document language selection covers English, Hebrew, Arabic, Spanish, French, German and Other. This is not a fully translated user interface.
- Scanned-document OCR packages are configured in Docker but production OCR has not yet been tested on Render.

## Deployment continuation

Render service `srv-davaltfpn0mc73ca26ng` uses Docker Starter in Frankfurt, with dedicated PostgreSQL `dpg-davaleflk1mc739asf3g-a` on Basic 256 MB and 1 GB storage. Estimated base hosting is $13.30/month before usage; billing recurs and is not a lifetime $50 cap. The domain has not incurred a charge. Three AI keys and Resend are configured as server-only secrets. Verify email delivery and password recovery. Configure Stripe and a signed webhook before enabling paid checkout. Add the selected domain only after its registration and the service hostname are known.

Never commit .env files, credentials, databases, test accounts or local runtime folders.

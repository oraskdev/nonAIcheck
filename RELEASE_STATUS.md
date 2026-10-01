# txtzi release status

The local application and brand refresh are ready for deployment review. This is not a claim that the public service is live.

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

## Brand and interface

A custom three-stroke X replaces the earlier logo. Outlined vector wordmarks include primary, reversed and monochrome versions. The interface uses midnight blue, mint and violet, with a floating document, scan highlight and sequential provider animations. The homepage and How it works explain the three different editorial roles. Completed documents identify the model versions actually used.

## Outstanding production work

- GitHub rejected a create-file request for oraskdev/nonAIcheck with HTTP 403: Resource not accessible by integration. The connection needs repository content write access before upload can proceed.
- No Render deployment or public application URL has been verified.
- txtzi.com registration and DNS are not completed.
- Resend is not connected or tested in this application. The available Render tools do not expose existing secret values for copying.
- Stripe checkout code exists but no Stripe credentials or live/test webhook integration has been validated. Purchases remain disabled when payment configuration is absent.
- The interface is English. Document language selection covers English, Hebrew, Arabic, Spanish, French, German and Other. This is not a fully translated user interface.
- Scanned-document OCR packages are configured in Docker but production OCR has not yet been tested on Render.

## Deployment continuation

Publish this repository to oraskdev/nonAIcheck once its connected GitHub integration permits writes. Deploy the existing render.yaml with PostgreSQL, configure provider secrets and APP_URL, verify health and repeat one end-to-end job on the deployed service. Set a verified Resend sender and test password recovery. Configure Stripe and a signed webhook before enabling paid checkout. Add the selected domain only after its registration and the service hostname are known.

Never commit .env files, credentials, databases, test accounts or local runtime folders.

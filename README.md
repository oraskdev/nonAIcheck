# txtzi

Live studio: https://txtzi.onrender.com/

txtzi is a small document studio for turning a user's own draft into a clearer, newly exported document. It accepts PDF, DOC, DOCX, PPTX, TXT, and pasted text, then runs a bounded editorial pipeline through the configured language-model providers.

The app is designed for legitimate self-use: it preserves facts, figures, links, and table separators; it does not promise to bypass AI detectors; it does not strip authorship or rights notices; and it shows any detector result as an estimate. Users must acknowledge the self-use declaration before processing.

## Local setup

1. Copy `.env.example` to `.env` and set `APP_SECRET` plus the provider keys you want to use.
2. Install system tools for PDF OCR/export (`poppler-utils`, `tesseract-ocr`) and legacy `.doc` extraction (`antiword`), or use the included Dockerfile.
3. Install Python dependencies with `pip install -r requirements.txt`.
4. Start the service with `uvicorn app.main:app --reload`.

The app creates its SQLite database in development. Production requires `DATABASE_URL` to point to PostgreSQL. `render.yaml` provisions a Render web service and managed database; provider, Stripe, email, and admin values are intentionally marked as dashboard secrets.

## Payments

Stripe is optional in development. When configured, quotes are calculated from the word count and checkout is settled through a signed webhook. Credits are ledger entries and are refunded automatically when a queued job fails.

Each account receives 500 promotional credits once per ISO week by default. This grant never removes purchased credits; set `WEEKLY_FREE_CREDITS=0` to disable it or change the amount in Render.

## Deployment

Push this repository to GitHub and create a Render Blueprint from `render.yaml`. After the first deploy, set `APP_URL` if a custom host is used, add the provider and Stripe secrets, and configure the Stripe webhook URL as `/api/billing/webhook`.

For password recovery, set `RESEND_API_KEY`, `EMAIL_FROM`, and `SUPPORT_EMAIL` in the txtzi Render service. The deployed service reuses the approved Resend key from the existing Render workspace. Email delivery still needs verification. Keep the key out of GitHub and rotate any key that has been shared in chat or committed accidentally.

The Render service only reports `recovery_ready` as true when both the Resend key and a verified `EMAIL_FROM` address are present. Use a sender on a domain verified in Resend before testing password recovery.

## Brand and validation

The homepage explains the distinct Claude, OpenAI and Grok passes. Model versions are reported from completed jobs. See `RELEASE_STATUS.md` for verified behavior and the exact remaining production blockers.

## Self-hosted detector

The Docker image builds a pinned Desklib English detector into `/opt/txtzi/detector`. `DETECTOR_PROVIDER=local` uses it without an API key. Allow 2 GB RAM and one CPU for the web service; the Blueprint uses Standard. Keep one application process and one job worker so model memory is not duplicated. The model runs offline at runtime.

For local development, install CPU PyTorch 2.14.1 and the requirements, then run `python scripts/prepare_detector.py /your/model/path` and set `DETECTOR_MODEL_DIR` accordingly. Numerical and integration smoke tests are documented in `RELEASE_STATUS.md`; this detector is an English beta, not an authorship certificate. Model licensing is in `THIRD_PARTY_NOTICES.md`.

The optional legacy adapter remains available with `DETECTOR_PROVIDER=gptzero` and `GPTZERO_API_KEY`. No job silently switches providers.

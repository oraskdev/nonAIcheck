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
- Scanned-document OCR was verified on Render: one scanned PDF page produced 187 words and the correct 20-credit OCR surcharge.

## Deployment continuation

Render service `srv-davaltfpn0mc73ca26ng` uses Docker Standard (2 GB) in Frankfurt, with dedicated PostgreSQL `dpg-davaleflk1mc739asf3g-a` on Basic 256 MB and 1 GB storage. Estimated base hosting is $31.30/month before usage; billing recurs and is not a lifetime $50 cap. The domain has not incurred a charge. Three AI keys and Resend are configured as server-only secrets. Verify email delivery and password recovery. Configure Stripe and a signed webhook before enabling paid checkout. Add the selected domain only after its registration and the service hostname are known.

Never commit .env files, credentials, databases, test accounts or local runtime folders.

## Detector-guided revision and hidden-format cleanup

- Added a bounded workflow: measure the original, revise through three providers, measure the revision, optionally make one additional three-provider revision, and retain the lowest-scoring eligible version. No fabricated scores or unlimited retries.
- Added a before/output Unicode-format inventory and optional removal of BOM, soft hyphen and word joiner. Language joiners and bidirectional controls remain. This does not detect statistical watermarks.
- The result displays attempted assessments, selected version, and whether a measured reduction occurred. Unavailable assessments return the detector fee as credits.
- Eight mocked pipeline tests cover selection, fallback, failure and language-safe cleanup. These are not live detector accuracy tests.
- The earlier external-detector dependency is superseded by the self-hosted integration below. GPTZero credentials are unnecessary for the current configuration. No third-party detector purchase was made.

## Self-hosted detector integration (2 October 2026)

- Added a pinned, MIT-licensed Desklib English detector. Detection runs locally; no third-party detector key or subscription is required. Model weights are prepared during Docker build and inference runs offline.
- Full-document coverage uses overlapping 512-token sections and a token-weighted mean. Scores are estimates, not percentages of AI-written words. Model revision, coverage and sections are included in the report.
- Compact matrix storage with float32 computation avoids slow bfloat16 emulation on Render CPUs. A full two-section CPU smoke test peaked at about 1.34 GiB and completed in 11.5 seconds, including cold loading. A numerical comparison with float32 on four stored sample versions (three distinct synthetic texts) is recorded below. This is not an accuracy benchmark. See `docs/selfhost-model-smoke.json`.
- Thirteen automated tests cover selection, failure, whole-document token coverage, no silent external-detector fallback, and exact credit refunds.
- Detector choice is pinned at quotation and included in the processing notice; legacy quotations remain pinned to GPTZero.
- The first live integration test completed with three real assessments, two passes through all three writing APIs, exactly one credit charge and all four exports. It produced only a negligible score reduction; this is not evidence of bypassing an independent checker.
- An initial smoke test during Render deployment overlap was picked up by the outgoing worker. The detector fee was refunded. Acceptance tests now run after the old instance has retired.
- Optimized inference was verified on live Render: the 493-word example completed two three-model revisions and three full-document assessments in 77.7 seconds. All four exports downloaded, protected numbers remained, and the 499-credit charge occurred once. See `docs/live-detector-acceptance.json`.
- Measured score: 99.93 to 99.88 out of 100. This negligible reduction does not meet a claim of reliable detector evasion. No independent detector or statistical watermark removal was validated.
- The public sample preview now shows the actual stored before/after text, model versions, processing time and detector results.
- Live browser checks confirmed the sample now has 325 words, the detector is enabled, and switching to Hebrew turns off English-only scoring and updates the quote.

## Meaning-based recomposition update (3 October 2026)

- Added bounded prose recomposition with a source-linked meaning inventory, new paragraph boundaries, and explicit source corrections. Unresolved discrepancies retain the source section. Structured layouts use the existing path.
- Upgraded configured models to Claude Sonnet 5.5, GPT-6.1 Sol and Grok 4.7. Claude uses native JSON schemas; OpenAI uses JSON mode. The application rejects incomplete responses.
- Fixed signed/percentage/currency numeric protection, embedded-list preservation, sentence-initial correction casing, selected-version report metadata, full-document comparison display and recovery from a failed optional second attempt.
- Independent detector experiments did not demonstrate reliable evasion. Specialized BART rewrites were rejected for invented facts, reversed instructions and broken text. Neither detector thresholds nor score formulas were changed. See `docs/rewrite-validation-oct3.md`.
- No additional Render service, instance upgrade or detector subscription was purchased. Domain, email-delivery and Stripe limitations above remain.

Release verification: 50 Python tests and four browser-view JavaScript tests passed, including signed values, embedded lists, selected-version metadata, missing assessments, optional failures, source-review rejection, native output formats and complete 12,000-word before/after rendering. These are application tests, not proof of detector avoidance.

Live acceptance on 3 October: the garden sample completed two revisions through all three current APIs, three full-document assessments, exactly one 499-credit charge despite repeated Generate requests, and PDF/DOCX/PPTX/TXT downloads with all selected text present. Unauthenticated document access was rejected. Total test time was 139.9 seconds. The txtzi detector measured 99.9959 → 99.6954/100; the independent Vanguard research check measured 99.2344 → 65.1145/100. The built-in score remains near 100; the independent estimate fell, but one synthetic example does not establish a reliable pass rate. The first weekly sample retained its original. See `docs/live-recomposition-acceptance.json` and `docs/live-recomposition-weekly.json`; the public demo shows the garden source, selected output, every measured attempt and text downloads.

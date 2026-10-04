# Bounded prose workflow — 4 October 2026

`bounded-patch-v1` is implemented as an explicitly versioned workflow. It is **not enabled in new production quotes**. Existing paid/funded quotes retain the previous workflow: up to two three-provider revisions and three detector assessments. A later release must disclose the different limits before users request or fund a new quote.

## What the new workflow does

The first version accepts 80–450 words and at most 6,500 characters of plain prose. Headings remain unchanged; lists, tables and slide content use the established workflow. It uses the existing local detector singleton, without adding another detector model to the Render process.

1. Claude extracts a source-linked meaning inventory and proposes exact-span edits.
2. OpenAI compares the proposed inventory and edits with the authoritative source.
3. The app scores up to 12 unique, locally validated variants. Numeric literals, format characters, immutable headings and modal verbs have deterministic guards. Combinations must contain nonoverlapping replacements.
4. Grok compares the best measured candidate against the complete original in both directions. Every source point must survive and every output claim must have source support. Its review must identify the exact source and candidate hashes and every inventory item.
5. A concrete source discrepancy may receive one repair composed only of verbatim source spans. A separate Grok review and fresh measurement of the exact repaired text are required. An unapproved candidate cannot replace the original, regardless of its detector score.

The final source comparison is a model review, not proof that the wording preserves every nuance. Users still need to review their document. A lower detector estimate does not establish human authorship or remove a statistical AI watermark.

## Cost and runtime boundaries

- Maximum four writing-provider requests; automatic retries disabled.
- Maximum 4,000 output tokens per request.
- Maximum fourteen local measurements, including original, optional cleanup comparison and repair.
- Conservative cost reservation before every request; maximum estimated or reserved writing-provider spend $0.45 per workflow. The pinned models and rate ceilings are explicit in code. An unrecognized model cannot start an unbudgeted request. Missing usage keeps the full reservation.
- A 300-second admission deadline prevents another stage from starting after the deadline. Provider read/connect timeouts are at most 60/15 seconds. This is **not an absolute end-to-end wall-clock guarantee**: an in-flight provider request or local model inference may finish later.
- Worker ownership is checked before processing, renewed independently every thirty seconds and verified at progress boundaries and completion. A stale, expired or reassigned job cannot begin paid work or renew another owner's lease.

Provider failures enter the existing worker refund path. Incomplete or failed final meaning checks retain the original with an explanation. Failed provider reservations are separated from completed provider receipts. Research evidence is recorded before parsing provider JSON and before any later request.

## Validation and evidence

The offline suite exercises source review failure, incorrect hashes, omitted inventory items, exact repair rescoring, rejection of invented repairs, numeric and hidden-character edits, missing detectors, cost reservation and nonretry behavior, legacy quote isolation and stale-job ownership. Test mocks validate these contracts; they do not establish editing effectiveness.

Live validation records are under `test-artifacts/recovery-oct4/production-e2e-*` while running. The first test ($0.030212 estimated provider spend) exposed a complete factual inventory that omitted the immutable title. The app retained the original. The title handling and provider schema/accounting problems were corrected before the second test. The first test is retained as a failed experiment, not counted as an improved output.

The second test completed on the original 373-word garden-plan source using all three providers and thirteen local measurements (original plus twelve variants). Grok approved the selected output against all 21 inventory items, with no repairs. Its exact hash was `c24dadb4a2ada35c7be49f73962ea4d9706518314bcabb94b6c9dab4cbbfb26f`.

| Measurement | Local detector estimate |
| --- | ---: |
| Original | 0.9999592304229736 |
| Selected output | 0.9999356269836426 |

Both are approximately 99.99%. The difference is too small to present as a useful improvement. **The new bounded workflow did not meet the under-30 or under-10 performance goal, and remains disabled for production quotes.** This test validates the calls, source review, exact-text measurement and failure boundaries, not effectiveness at reducing this detector's estimate.

The second test took 125.253 seconds in the shared research workspace (not a Render performance measurement) and used an estimated $0.054144 in provider tokens. Total new live workflow validation spend across both tests was $0.084356, excluding the independent research series and infrastructure.

This production workflow selects against **one** local detector. Earlier research selected across **two** detectors with many more variants on one garden-plan source. Its scores cannot be assigned to this workflow, to different text, or to ordinary customer documents. Neither the historical experiment nor one successful live workflow test establishes a general success rate or an under-10 guarantee.

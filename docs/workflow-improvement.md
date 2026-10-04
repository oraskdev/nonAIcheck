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

| Provider | Input tokens | Output tokens | Estimated USD |
| --- | ---: | ---: | ---: |
| Claude | 1,857 | 1,747 | 0.021184 |
| OpenAI | 2,269 | 1,637 | 0.020908 |
| Grok | 3,698 | 776 | 0.012052 |

A separate reviewer inspected the exact original/output pair without seeing detector scores and approved all 32 substantive source points. This is additional source-fidelity evidence, not detector-performance evidence.

This production workflow selects against **one** local detector. Earlier research selected across **two** detectors with many more variants on one garden-plan source. Its scores cannot be assigned to this workflow, to different text, or to ordinary customer documents. Neither the historical experiment nor one successful live workflow test establishes a general success rate or an under-10 guarantee.

## Why the bounded experiment missed the research gains

The research and live workflow started from different text. The recovered research parent was already a complete rewording of the original, including a different paragraph sequence. It was independently measured at 79.34 / 55.98 before this research phase began. Its best reviewed descendant followed this exact chain:

| Parent | Applied patches at that step | Desklib | Vanguard |
| --- | ---: | ---: | ---: |
| `recovery-baseline` | 0 | 79.34 | 55.98 |
| `r02-c121` | 4 | 61.97 | 26.49 |
| `r05-c042` | 3 | 36.11 | 15.25 |
| `r06-c150` | 3 | 23.18 | 14.44 |

Each descendant inherited previous accepted changes; the broader research series searched 1,000 distinct texts and selected using both detectors. Its initial parent also inherited work from earlier development and is not an automatically generated fresh-input baseline.

The live workflow started directly from the 99.9959 original. OpenAI retained seven minor wording proposals from Claude's eight. The selected candidate applied four patches whose find-spans covered 397 of the source's 2,096 characters; it preserved the original paragraph sequence and most wording. Examples of the proposal types were replacing “allow me to learn” with “let me learn” and shortening repeated nouns. That is a materially different search space from the research chain. This comparison does not isolate whether the research gains came from its initial rewriting, repeated selection, paragraph order, detector overfitting or a combination.

## One prospective change recommended for evaluation

**Test a fresh, source-reviewed full-draft starting point before the existing small patch search.** This changes initialization rather than adding hundreds of evaluations:

- Claude creates one fresh draft and source-linked inventory from the complete original, preserving the original language, genre, point of view and all qualifications. No prewritten garden text, chosen phrases or historical winner is supplied.
- OpenAI compares that draft with the entire original, explicitly approves or rejects it, and proposes a small patch bank against the approved draft. A rejected starting draft cannot enter the search.
- The existing exact-text measurement, protected-value guards and final Grok comparison remain. Retain the original unless the chosen exact text clears meaning checks and improves its measured score.
- Keep the current four-provider-call and fourteen-assessment ceilings: original, one new starting draft, at most eleven patch variants and an optional repaired version (reduce variants by one when a separate cleanup baseline also needs scoring). Keep the same cost reservation and admission deadline. No new model, infrastructure or production flag is needed for a research-only test.

This is a proposal, not an implemented or validated improvement. It directly tests the initialization difference observed above; it may still fail because a single automatic draft cannot reproduce a manually developed, adaptively selected research parent. Do not enable it or advertise a score target based on the garden example.

Before any general-performance claim, freeze this workflow and evaluate it from original input on genuinely new documents from multiple genres, lengths and authors. Include independently sourced human-written controls, avoid choosing only favorable outputs, review source fidelity without detector scores, and keep at least one detector out of the selection loop. Report the complete success/fallback/error rates, meaning changes, provider cost and measured Render latency. The current work provides none of that source-independent effectiveness evidence.

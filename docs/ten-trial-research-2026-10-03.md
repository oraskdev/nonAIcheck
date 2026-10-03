# Ten additional rewrite trials — 3 October 2026

Completed ten new three-provider revisions and measured each exact final text with both pinned detectors. Trial 8 had one transient HTTP520 request, retried successfully; the failed request was not counted as a generated trial.

## Result

Selected: **09-repaired — Trial 9 · source-fidelity correction**.

| Version | Desklib / 100 | Vanguard / 100 |
|---|---:|---:|
| Original | 100.00 | 99.23 |
| Previous live output | 99.70 | 65.11 |
| Selected corrected research draft | 61.61 | 46.18 |

## All attempts

| Trial | Strategy | Desklib / 100 | Vanguard / 100 | Eligible |
|---|---|---:|---:|---|
| 1 | Watering first | 99.54 | 27.38 | Yes |
| 2 | Budget first | 99.79 | 99.98 | No |
| 3 | Balcony first | 99.99 | 100.00 | Yes |
| 4 | Tentative plant choices | 99.97 | 99.38 | Yes |
| 5 | Conditional start date | 90.23 | 31.28 | No |
| 6 | Maintenance before expansion | 99.98 | 100.00 | Yes |
| 7 | Pair decisions with limits | 99.91 | 12.47 | No |
| 8 | Continuous personal note | 99.98 | 100.00 | Yes |
| 9 | Conversational explanation | 65.48 | 49.26 | No |
| 10 | Unfinished working thought | 99.96 | 99.98 | Yes |
| 05-repaired | Trial 5 · source-fidelity correction | 88.81 | 29.18 | Yes |
| 07-repaired | Trial 7 · source-fidelity correction | 99.89 | 12.31 | Yes |
| 09-repaired | Trial 9 · source-fidelity correction | 61.61 | 46.18 | Yes |

## Method and limits

This is a local experiment on one synthetic English document. The three corrected variants replace “expect to need another” with the source-faithful “expect to buy another”; their exact final texts were measured again. All original attempts remain visible. Both detectors were used to select the result, so neither is a held-out evaluation. No general detector avoidance or watermark-removal claim follows from these measurements.

Each trial used Claude Sonnet 5.5, GPT-6.1 Sol, and Grok 4.7. Claude and OpenAI exchanged planning/writing roles across trials; Grok reviewed against the original. An additional review, blind to candidate scores, checked 32 source claims and output quality. Raw trial 2 had broken punctuation; raw trials 5, 7 and 9 shifted a purchase expectation into a need expectation. Those raw variants are excluded. The latter three received only the recorded source-fidelity correction, with no additional generation call.

The fixed model revisions were Desklib `5fdea974cd4287c61674951ec78803aa274e2fb7` and Vanguard `823061be63b90f2b42f64ac1e1f82772e872533b`. Both saw the exact same final text, joined with two newlines and including the title once. SHA-256 hashes are recorded for every text. No truncation or invisible-character substitutions were used.

Consider only candidates that clear source-fidelity audit and protected-value checks. Prefer candidates strictly lower than the previous-best baseline on BOTH fixed detectors. Among those minimize max(Desklib/baselineDesklib,Vanguard/baselineVanguard). Otherwise retain baseline and report single-detector changes separately. Scores do not establish authorship or guarantee other detector outcomes.

Estimated list-rate cost of the 30 completed writing/review calls using returned token usage; not an invoice. Hosting and the failed HTTP520 request are excluded. No additional infrastructure or subscription was purchased. Estimated completed-call cost: **$0.4708**.

The production writing workflow remains unchanged: these experimental prompts and manual corrections are not yet automated product behavior. This one-source search is insufficient to choose a new general default. Published results are at `/static/research-ten-trials.html`, linked from the live example.

Complete prompts, returned token usage, raw provider output, audits, protected values, exact text and scores: [JSON evidence](ten-trial-research-2026-10-03.json).

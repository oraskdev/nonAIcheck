# Recovery study: phase A completed

Phase A tested **1,000 distinct revisions of one previously published synthetic English document**. Every exact candidate received complete-document measurements from both fixed detectors. The best eligible result scored **23.18 / 14.44**, and two separate, score-blind agent reviews approved all 32 source claims and whole-document meaning and prose quality without changing the measured text.

| Exact measured document | Desklib score | Vanguard score |
|---|---:|---:|
| Original source reference | 100.00 | 99.23 |
| Corrected starting draft | 79.34 | 55.98 |
| Selected phase A revision | 23.18 | 14.44 |

These are model estimates displayed on a 0–100 scale. They are not percentages of AI-written words, calibrated authorship probabilities, or scores from every available checker. Both detectors were used to select candidates, so this is an adaptive in-sample experiment, with no held-out evaluation.

**Below 30 on both detectors was reached and source-verified. Below 10 and below 2 on both were not reached in phase A.** This result does not establish performance on other texts, languages or authors, and it does not demonstrate universal hidden-watermark removal or guaranteed undetectability.

Seven shared editing banks used Claude for proposals, OpenAI for refinement and Grok for source and patch review. The banks generated at most 150 distinct, seeded combinations each, with the final bank limited to 100. The study therefore completed **21 provider requests**, not 1,000 independent three-provider rewrites. Exact-span edits could not overlap, change protected numbers or the title, replace local uncertainty words, or introduce invisible/control characters. Final eligibility required separate complete-source reviews of the exact combined text.

The configured list-rate estimate for completed provider requests was **$0.821574**. An additional **$0.103268** remained conservatively reserved after a local HTTP-client initialization failure, giving **$0.924842** estimated or reserved against the experiment's $1.50 limit. These figures are not a provider invoice. Local inference did not use a paid detector API.

The original source reference was freshly scored and reproduced the previously saved values at the pinned revisions. Selected text SHA-256: `a11ea02ef60c551ad6e94318dd06ee320c360bb271ad2e6f1e2d92273dd838a6`. Desklib revision: `5fdea974cd4287c61674951ec78803aa274e2fb7`. Vanguard revision: `823061be63b90f2b42f64ac1e1f82772e872533b`. Both detectors covered the entire document; no truncation was used.

Phase B is a separately declared continuation: up to 1,000 additional unique combinations from the strongest eligible existing banks, with no additional writing-provider calls. Measured single-patch logit differences rank which combinations to test; those predictions are never reported as measured scores. New phase B texts require fresh exact full-document inference and the same two source reviews before any threshold can qualify. Phase B results must be reported separately from this frozen phase A count.

The scripts and aggregate protocol are publishable project files. Raw synthetic source texts, provider requests/responses and the complete private evidence archive are stored separately. This experiment does not enable or validate a new general production rewrite method by itself.

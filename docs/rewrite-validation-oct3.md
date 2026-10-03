# Rewrite research — 3 October 2026

**Reliable detector avoidance was not demonstrated.** These are local development experiments, not production acceptance or an accuracy benchmark. Some rewrites lowered the existing detector's score, but the improvement did not transfer to the independent checker. All six specialized BART outputs failed factual or writing-quality review.

## Fixed checks

The existing Desklib detector and independent Vanguard detector retained their published weights and scoring methods. No thresholds, score formulas or labels were changed to manufacture improvement. Tables below show raw scores multiplied by 100 for readability; they are not validated authorship probabilities or percentages of AI-written words.

| Detector | Pinned revision | Use |
|---|---|---|
| `desklib/ai-text-detector-v1.01` | `5fdea974cd4287c61674951ec78803aa274e2fb7` | Existing production algorithm, exercised locally |
| `ShantanuT01/vanguard-ai-text-detector` | `823061be63b90f2b42f64ac1e1f82772e872533b` | Independent research checker |

## Known-human sanity controls

These public-domain excerpts were selected before scoring. Their age and possible training-set overlap limit what this check establishes.

| Source | Words | Desklib score ×100 | Vanguard score ×100 |
|---|---:|---:|---:|
| [Lewis Carroll, 1865](https://www.gutenberg.org/files/11/11-h/11-h.htm) | 399 | 3.1263 | 0.0016 |
| [Charles Darwin, 1872](https://www.gutenberg.org/files/2009/2009-h/2009-h.htm) | 348 | 1.0163 | 0.0001 |
| [John F. Kennedy and presidential speechwriting staff, 1961](https://www.archives.gov/milestone-documents/president-john-f-kennedys-inaugural-address) | 381 | 34.9473 | 0.3319 |

This result rules out an obvious always-positive failure on these three inputs. It does not calibrate either detector.

## General-model writing experiments

Real API drafts used the synthetic weekly-plan document. Source facts, numbers and original language were required; paragraph reorganization was allowed.

| Writer | Desklib score ×100 | Vanguard score ×100 |
|---|---:|---:|
| `claude-opus-5-5` | 97.5039 | 100.0000 |
| `gpt-6-astra` | 99.1031 | 100.0000 |
| `gpt-6.1-sol` | 99.3684 | Not measured |

Four additional agent-written development drafts also failed the independent check:

| Draft | Desklib score ×100 | Vanguard score ×100 |
|---|---:|---:|
| weekly-plan-recomposed-a | 76.6655 | 100.0000 |
| weekly-plan-recomposed-b | 99.3625 | 100.0000 |
| weekly-plan-recomposed-c | 17.3908 | 99.9983 |
| weekly-plan-recomposed-d | 34.3876 | 99.9953 |

Styles from the weekly-plan experiment were then tried on the synthetic garden and team-update documents. All four API outputs remained between 99.0210 and 99.9120 on Desklib and between 99.8775 and 100 on Vanguard. Asking for plain prose instead of JSON also failed to resolve this: the two additional Claude outputs scored 99.9175 and 98.5552 on Desklib, and 99.9762 and 100 on Vanguard. Exact values and text hashes are in the companion JSON.

These were transfer checks on additional development examples, not a statistically held-out benchmark. No reliable pass rate follows from them.

## Specialized local BART trial — rejected

`rudra496/stealthhumanizer-bart`, revision `425b1eeef7f88e6db3d49014ff397ae2fffdcc99`, was downloaded and converted locally to CTranslate2 4.8.2 INT8 with remote code disabled. Its model card declares MIT, and the `facebook/bart-large` base declares Apache-2.0. License-source links and file sizes are recorded in the JSON.

Two sampled candidates per document were generated from pieces of at most 150 words. No content was silently truncated before inference. Output-length limits and numeric changes were recorded as failures.

| Measurement | Result |
|---|---|
| Synthetic documents / candidates | 3 / 6 |
| Eligible candidates | 0 |
| CPU threads | 1 |
| Full-document elapsed time | 14.45–25.54 seconds |
| Peak process RSS | 486.67 MiB |
| INT8 model file | 415,083,072 bytes |

The resource footprint is plausible for the existing service, but output quality is unacceptable. Failures included invented four-year goals, a teacher friend and container sizes; missing dates and budgets; changing a 150-word maximum to a minimum; reversing the instruction to keep a phone away; and random-letter text. Lower detector scores would not make these candidates acceptable.

A separate greedy generation using the original FP32 weights also invented content and produced malformed contractions. Quantization changes the output, but the source model already exhibits the relevant fidelity failure. This specialized model was **not deployed**.

## Software checks

Six tests in `tests/test_pipeline_selection.py` passed. They verify that the selected revision retains its own method, structure flag and correction flags; original fallback clears rewrite metadata; detector input matches the complete cleaned output; provider usage aggregates across attempts; and a failed optional retry or invalid score cannot replace the best completed result. These use mocked providers and establish software behavior, not detector avoidance.

## Scope of conclusions

The evidence supports preserving honest measured results and rejecting damaged rewrites. It does not demonstrate a finished detection-avoidance product, commercial-checker acceptance, human authorship or universal watermark removal. Local timing is not a Render latency guarantee. The three development documents and historical controls are too small and unrepresentative for general accuracy claims.

Machine-readable values, model revisions, source hashes, provenance and limitations: [rewrite-validation-oct3.json](rewrite-validation-oct3.json).

## Integrated prototype cross-check

The recomposition prototype was also run through all three newer APIs and checked with the independent detector. This was before native structured output was added for Claude: the second attempt failed formatting validation on the team and weekly examples, so the completed first result or original was retained. The guarded failure behavior worked, but this is not evidence of a fully successful two-revision run.

| Synthetic sample | Desklib original → selected | Vanguard original → selected |
|---|---:|---:|
| garden | 99.9959 → 99.8385 | 99.2344 → 99.9737 |
| team_update | 99.9948 → 99.9353 | 100.0000 → 100.0000 |
| weekly_plan | 99.9293 → 99.9293 | 100.0000 → 100.0000 |

Scores remained high. In particular, the garden rewrite measured lower on Desklib but higher on Vanguard. Reliable detector evasion is still unproven.

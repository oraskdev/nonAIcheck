# Recovery study: final phase G completed

The final 1,000-text expansion did not improve the best result from phase F. **The overall selected text remains at 7.69 on Desklib and 4.99 on Vanguard**, on their displayed 0–100 scales, with two complete-source reviews. **Below 2 on both was not reached.** This bounded research run is finished; no further phase or provider calls are scheduled.

| Final phase G result | Count or value |
|---|---:|
| New distinct candidate texts | 1,000 |
| Exact full-document detector measurements | 2,000 |
| Previously approved edits in the merged pool | 29 |
| Concrete unused texts in the bounded ranking pool | 38,204 |
| Highest-ranked / seeded alternative selections | 800 / 200 |
| New provider requests | 0 |
| Best eligible G Desklib / Vanguard score | 7.73 / 5.73 |
| Verified below 2 on both | No |

G merged and deduplicated already approved E/F edits on the same exact, previously reviewed phase D parent. It reused the edits' actual Claude, OpenAI and Grok provenance; it did not make fresh model calls. Measured single-edit changes ranked nonoverlapping combinations of two to ten edits within a deterministic bounded beam. Predicted ranks selected tests and were never reported as measured scores. Previously tested texts, source/reference texts and known parents were excluded by exact hash.

Every new selected text received both unchanged, pinned detectors on the complete document. G's best text is `g01-c0003`, SHA-256 `aae6e16625c7cccfd0c631169a684b44eaa631a6c38e23afb286ea4a51f06e9a`, with exact scores **0.07733166962862015** and **0.05730028077960014**. Two separate, score-blind agent reviews approved all 32 source claims and the complete document's conditions, uncertainty, causality, timing and prose quality. No text changed after measurement.

Phase F's selected `f01-c003` remains better on both detectors: exact scores **0.07694776356220245** and **0.04985560104250908**, SHA-256 `cd7925228ec50d3f7f8b9338ae908926bc5557c096fc75c93ca908717b74d3d3`. Its two complete-source reviews remain valid. The first verified below-10 checkpoint from phase D is preserved separately.

| Completed phase | New distinct texts | Exact detector measurements |
|---|---:|---:|
| A | 1,000 | 2,000 |
| B | 1,000 | 2,000 |
| C | 1 | 2 |
| D | 450 | 900 |
| E | 58 | 116 |
| F | 300 | 600 |
| G | 1,000 | 2,000 |
| **Total** | **3,809** | **7,618** |

These are shared-bank candidate texts, not 3,809 independent three-provider rewrites. Original/reference measurements and the separate frozen business holdout are excluded from these counts. All G scoring processes were stopped after completion.

There were **41 completed writing/review-provider requests**, plus one earlier retained failure reservation. Global research accounting remains **$1.425372** in configured list-rate usage and conservative reservations against the unchanged **$1.50** cap. It includes the earlier **$0.103268** failure reservation and is not a provider invoice. **$0.074628** remains uncommitted; G added no provider cost.

This is an adaptive experiment on one synthetic English source, with both detectors used for selection. Detector scores are not calibrated authorship probabilities. The results do not establish performance on unseen documents or languages, universal detector avoidance, or watermark removal. The separate frozen production holdout remained negative and was not retuned. This research result is separate from live product behavior.

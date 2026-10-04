# Recovery study: phase F completed

Phase F's best eligible result scored **7.69 on Desklib and 4.99 on Vanguard**, on their displayed 0–100 scales. Both complete-source reviews passed for the exact measured text. **Below 2 on both was not reached.** The first verified below-10 result from phase D remains preserved.

| Phase F result | Count or value |
|---|---:|
| New distinct candidate texts | 300 |
| Exact full-document detector measurements | 600 |
| New single-patch texts | 20 |
| New combined-patch texts | 280 |
| New provider requests | 2 |
| New Claude requests | 0 |
| Best eligible Desklib / Vanguard score | 7.69 / 4.99 |
| Verified below 2 on both | No |

This phase repaired a specific coverage gap in phase E. Across two frozen Claude responses, 26 formally valid proposal records had been omitted from OpenAI's returned subsets. These represented 23 distinct exact edits on the same previously reviewed parent. F reused that real Claude provenance and required an explicit OpenAI accept, repair or reject decision with a reason for every proposal ID. OpenAI accepted all 23; Grok reviewed every edit and approved 21. Twenty single-patch texts were new, while one exact known text reused its valid measurements without increasing the count.

Measured single-patch logit differences ranked nonoverlapping combinations of two to eight approved edits. A deterministic alternative sample supplemented the highest predicted ranks. Predicted ranks selected tests; they were never reported as measurements. All 300 exact texts received complete-document inference at the unchanged model revisions and precision settings.

The selected text is `f01-c003`, SHA-256 `cd7925228ec50d3f7f8b9338ae908926bc5557c096fc75c93ca908717b74d3d3`. Exact scores are 0.07694776356220245 and 0.04985560104250908. Two separate, score-blind agent reviews approved all 32 source claims, full-document conditions, uncertainty, causal relationships, timing and prose quality. No text changed after measurement.

The two new calls used a real 4,500-token response ceiling. Grok was admitted only after OpenAI's actual usage reconciled to its saved complete response and sufficient conservative budget headroom remained. No request retried. F added **$0.049422** in configured list-rate usage, bringing global research accounting to **$1.425372** estimated or reserved against the unchanged $1.50 cap. The total includes the earlier $0.103268 retained failure reservation and is not a provider invoice. **$0.074628** remains uncommitted.

Across A–F, the distinct candidate counts are **1,000 + 1,000 + 1 + 450 + 58 + 300 = 2,809**, with **5,618** exact detector measurements. There were **41 completed writing/review-provider requests**, plus one retained failure reservation. Original/reference measurements and the separate frozen business holdout are excluded. These are shared-bank candidates, not 2,809 independent three-provider rewrites.

The result remains an adaptive experiment on one synthetic English source, using both detectors for selection. It does not establish authorship, general performance on unseen documents or languages, or universal watermark removal. The separate frozen production holdout retained its negative performance result and was not retuned. This research result is separate from live product behavior.

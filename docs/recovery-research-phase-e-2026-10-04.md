# Recovery study: phase E completed

Phase E did **not** reach below 2 on both fixed detectors. Its best source-verified candidate scored **8.48 on Desklib and 8.70 on Vanguard**, so the overall best remains phase D's **8.11 / 8.22** result. Both results passed separate, score-blind agent reviews of all 32 source claims and whole-document meaning and prose quality.

| Phase E result | Count or value |
|---|---:|
| New distinct candidate texts | 58 |
| Exact full-document detector measurements | 116 |
| New single-patch texts | 7 |
| New combined-patch texts | 51 |
| Shared three-provider banks | 2 |
| Completed provider requests | 6 |
| Best eligible Desklib / Vanguard score | 8.48 / 8.70 |
| Verified below 2 on both | No |

The prospective limit was at most 300 new texts, not a promised count. Each bank retained five approved alternatives; the first yielded 31 distinct texts and the second 27 after exact duplicate exclusion. Three known single-patch texts reused their existing exact full-coverage receipts and were not counted as new tests. No duplicate or filler tests were added to reach the ceiling.

The selected E text is `e02-s002`, SHA-256 `6ae39415061d592122957234e3a5285841fb5310bc64ebd49580eb7029af0e26`. Exact detector values are 0.08484228700399399 and 0.08702921122312546. Every generated text received complete-document measurements at the unchanged pinned revisions and precision settings.

A read-only proposal-retention audit found the same pattern in both banks: Claude supplied 18 proposals and all 18 passed the local span, title, number, modal-word, length and character guards. OpenAI returned five IDs and omitted 13 without per-ID explanations. Both responses completed normally, using 605 and 476 output tokens respectively against the real 4,500-token cap. All five returned alternatives passed local validation and Grok review. The reduction therefore occurred in OpenAI's returned subset, not truncation or downstream rejection. The reasons for individual omissions cannot be inferred from the saved response.

Phase E added **$0.131752** in configured list-rate usage. Global research accounting is **$1.375950** estimated or reserved against the unchanged $1.50 cap, leaving **$0.124050** uncommitted. The total includes the earlier $0.103268 retained failure reservation; it is not a provider invoice. The declared E limit of two banks and six requests is complete, and no further E request is authorized.

Across A–E, the distinct candidate counts are 1,000 + 1,000 + 1 + 450 + 58 = **2,509**, with **5,018** exact detector measurements. Original/reference documents and the separate frozen business holdout are excluded. These are shared-bank candidates, not 2,509 independent three-provider rewrites. The first verified below-10 checkpoint remains preserved from phase D.

Both models guided adaptive selection on one synthetic English source. The lower scores do not establish authorship, performance on unseen documents or languages, or universal watermark removal. The separate frozen production holdout was not retuned and must retain its own negative result.

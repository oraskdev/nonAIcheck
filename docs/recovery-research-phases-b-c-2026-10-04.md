# Recovery study: phases B and C

Phase B completed **1,000 additional distinct revisions** of the same synthetic English source used in phase A. All 1,000 received exact, full-document measurements from both pinned detectors. The best twice-source-reviewed text scored **20.67 on Desklib and 12.17 on Vanguard**, on their displayed 0–100 scales. Below 10 on both, and therefore below 2 on both, was not reached.

| Phase | New distinct texts | Exact detector measurements | New provider requests | Best eligible Desklib / Vanguard |
|---|---:|---:|---:|---:|
| A | 1,000 | 2,000 | 21 completed, 1 retained failed reservation | 23.18 / 14.44 |
| B | 1,000 | 2,000 | 0 | 20.67 / 12.17 |
| C | 1 | 2 | 3 | 99.99 / 92.94 |

Phase B reused two existing, source-reviewed editing banks. Exact measured single-patch logit differences ranked nonoverlapping combinations of two to eight patches, with a deterministic alternative sample. Predicted ranks selected tests; they were never reported as detector measurements. Of the 1,000 new texts, 832 used one bank and 168 the other. These were distinct combinations, not 1,000 fresh three-provider rewrites. Both detectors guided selection, so these results remain adaptive and in-sample.

The best phase B text, `b01-c0001`, has SHA-256 `1c44c62a86e13e30c6e25839c31fae467e6118faeffddcfc06ddf895c21fc5c2`. Its exact detector values are 0.20672067999839783 and 0.12170825153589249. Two separate score-blind agent reviews approved all 32 source claims, full-source conditions, causal relationships, uncertainty and prose quality without changing the measured text.

Phase C was a separately authorized diagnostic: Claude drafted a fresh structure from the original, OpenAI repaired source fidelity and Grok reviewed the complete final draft. The one distinct output passed both independent complete-source reviews, but scored **99.99 / 92.94**, a negative performance result. Its optional editing bank required both exact scores to be at most 35; the gate failed, so no optional bank or additional phase C provider calls ran. The result is retained rather than omitted.

The global configured list-rate estimate and conservative reservations after A, B and C total **$0.966116** against the same $1.50 research limit. This includes the $0.103268 retained reservation from the earlier local HTTP-client initialization failure. The remaining research allowance is $0.533884; these accounting figures are estimates, not an invoice. Local detector inference used no paid detector service.

Desklib revision remains `5fdea974cd4287c61674951ec78803aa274e2fb7`; Vanguard revision remains `823061be63b90f2b42f64ac1e1f82772e872533b`. Every reported measurement covers its entire exact document at the fixed precision and inference settings. Counts are separate by prospectively defined phase. The original and corrected starting draft are reference measurements, not new candidate counts.

No phase here demonstrates general detector avoidance, calibrated authorship probabilities, effectiveness across languages, or universal watermark removal. The results do not by themselves validate a production rewrite strategy. A separate frozen production holdout is documented separately and is not part of these candidate counts or selection data.

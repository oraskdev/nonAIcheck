# Recovery research protocol

This is an isolated experiment on the synthetic English garden note already published with the ten-trial report. It does not change the production rewrite workflow. Earlier unpublished experimental texts and receipts were unavailable after the workspace reset; their scores are not assigned to new texts or counted as recovered evidence.

The starting draft received three conservative meaning clarifications: learning maintenance remains a tentative benefit before a larger commitment; work travel is joined to the neighbor-availability concern without adding a new causal claim; and owning a watering can explicitly explains the expectation of not buying another. The changed draft is measured again. Original source, initial draft, claim checklist, and every candidate are identified by SHA-256.

Each editing bank uses three shared provider calls: Claude proposes exact-span alternatives, OpenAI refines them against the source, and Grok reviews the complete parent and each proposed patch. At most 150 seeded, distinct combinations are produced from a bank. These are 150 different candidate texts, not 150 independent three-provider rewrites. Overlapping patches are never combined. Protected numbers, title, local uncertainty words, and Unicode controls are checked before scoring.

Every candidate is scored in full by the fixed Desklib and Vanguard revisions identified in the machine-readable protocol. Scores are uncalibrated model estimates. Both detectors guide selection, so neither supplies held-out evidence of general effectiveness. The selection criterion minimizes the larger of the two scores. Intermediate targets are strictly below 30, then 10, then 2 on the displayed 0–100 scales; a target is verified only after two separate complete source reviews pass for the exact measured text.

New adaptive parents require two distinct reviews of all 32 source claims, complete-source relationships, uncertainty, unsupported additions, and prose quality. A changed text requires a new hash, measurement, and review. The initial exploratory bank had one independent review plus Grok's source audit; its unchanged parent subsequently passed a second independent source review before further banks.

The experiment stops at 1,000 new distinct candidates or $1.50 of estimated/reserved new provider usage. Every request reserves a conservative input/output maximum. Raw provider responses are saved before JSON parsing; unknown failures retain their reservation and are not automatically retried. The accounting uses configured provider list rates rather than an invoice. Local detector inference has no per-request provider charge.

Run `python scripts/research/recovery.py status` for current counts and verified results. `archive` creates an atomic private evidence checkpoint under the ignored experiment directory. Raw requests, responses, candidate texts and source reviews are preserved privately; they must not be mistaken for an approved public upload. The runner's offline integrity tests use `python -m unittest scripts.research.test_recovery`.

One selected result cannot establish performance on other documents, languages, authors, or detectors. These tests do not demonstrate universal watermark removal, establish human authorship, or guarantee undetectability.

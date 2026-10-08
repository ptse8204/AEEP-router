# AEEP development stack

**Synthetic fixtures. Real model benefit: NOT ASSESSED.**

The pinned external evaluator ran both arms. AEEP independently checked each fixture output.

| Case | Arm | Verified fixture output | Candidate exposed |
|---|---|---|---|
| format | Control | Fail | False |
| format | Treatment | Pass | True |
| adjacent | Control | Pass | False |
| adjacent | Treatment | Pass | True |

The formatting difference is engineered into upstream's fake harness; it is not a measured skill benefit.
Model tokens, model time and actual billing are unavailable. Upstream fixture constants remain only in raw artifacts.
The batch has a canonical coordinator receipt; per-trial model accounting, Docker worker conformance and live trials remain unestablished.

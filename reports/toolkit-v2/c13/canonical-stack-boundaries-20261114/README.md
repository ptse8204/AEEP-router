# C13 Cisco and native scheduler boundary results

The approved paired review ran once. Cisco Skill Scanner 2.2.1 completed through
the ordinary CLI on the retained image. Four analyzers returned one INFO finding
for a missing license declaration. The scan reported zero analyzer failures and
verified container cleanup. The standalone and wrapper operations both settled.
The managed ledger accepted the two scanner checks and now verifies **35 of 39**.

The native agent-skill-eval check exited 1 after creating its Git test directory.
The terminal journal and one charged operation are retained. The restricted Git
wrapper still required the old scheduler workspace, so it rejected the fresh
probe directory before Git initialization. The driver did not retain the error
text. The diagnosis follows from the wrapper's exact path guard and the empty
Git directory. The earlier successful controlled scheduler execution remains
bound to its original launcher and plan.

| Item | Status | Evidence |
| --- | --- | --- |
| Paired review | Terminal, three operations settled, zero model turns and $0 authorized | [Result and measurements](boundary-result.json) |
| Cisco readiness | Two checks accepted | [Reviewed scanner record](skill-scanner-record.json) |
| Native scheduler boundary | Exact repeat awaits approval | [Workspace correction](ase-workspace-review.json) and [preflight](ase-workspace-preflight.json) |
| Waza | Protected Copilot sign-in and supported backend grade pending | [Operator sign-in](../waza-native-backend-20261104/operator-setup-20261113/README.md) |

The native-only correction uses a fresh workspace and a copy of the same Git
wrapper with its path binding updated. First-party preparation confirmed that
the wrapper accepts the owned workspace, rejects its parent, and denies clone
and credential configuration. The review expires November 15 at 8:22 p.m.
Vancouver time. It permits one operation and 35 reserved seconds on the existing
grant. The [readiness snapshot](stack-status.json) still blocks comparisons.

The reviewed code remains on the same working checkout fingerprint as the
[full source verification](../canonical-stack-receipts-20261114/source-verification.json).
The matched live receipts are integration evidence. Candidate usefulness,
selection usefulness and release require separate evidence and authority.

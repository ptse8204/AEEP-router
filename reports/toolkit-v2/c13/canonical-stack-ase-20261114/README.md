# C13 agent-skill-eval readiness

The managed ledger verifies **37 of 39 readiness checks** across 18 of 19
components. Both composed workflows remain verified. Waza's supported backend
and live protected grade are the two open checks. Comparisons remain paused.

## Native boundary receipt

Exact review `70397da2` ran once. The probe verified denied outside reads,
outside writes, candidate writes, response writes and networking. Local Git
initialization passed in the reviewed scratch workspace. The operation settled
in 0.410 seconds, with zero model calls and $0 spending authority. The previous
failed operation and two unrelated reservations were preserved. The probe
required no grant amendment, install, network contact or model replay.

- [Operator approval](operator-approval.json)
- [Exact review](../canonical-stack-boundaries-20261114/ase-workspace-review.json)
- [Settlement, journal and six observations](ase-boundary-settlement.json)
- [Registered evidence definition](agent-skill-eval-record.json)

The CLI proves compatibility for the retained controlled run using the new
launcher receipt and the original protected scheduler grade. The original
plan, run binding and grade keep their historical fingerprints. New scheduler
dispatch continues to require the regular live dependency checks.

## Canonical readiness

[Copied-ledger verification](copied-ledger-result.json) accepted all 37
checks on the updated source. It rejected missing launcher evidence, a swap
to the prior failed operation and an unbound receipt. Revoking the new
evidence review in the copy blocked both scheduler checks.

[Managed registration](registration-result.json) added exact evidence and
review records. Its ledger audit verified that all prior rows were preserved
during registration. The [CLI snapshot](stack-status.json) shows the accepted
checks and evidence references. The registered source fingerprint includes
the existing working-tree CI and test edits. Those unrelated files stay
outside the readiness commit.

## Waza handoff

The [read-only audit](waza-readiness-audit.json) verified the protected
login input pins, the retained Waza runtime tree and the one-task fixture
used by the offline grader. That grader scored a synthetic reference
1/1 and a wrong reply 0/1. Waza's supported backend remains unverified.

1. Complete [protected operator sign-in](../waza-native-backend-20261104/operator-setup-20261113/README.md)
   if free access is available. Report success, interruption or unavailable
   free access. This review expires November 16 at 8:22 p.m. Vancouver time.
2. Confirm the approved Copilot runtime recognizes the operator session and
   exposes an exact zero-cash eligible model. Review the supported destinations
   and one-task public inputs before asking for live execution approval.
3. Run one approved uncached Waza task with the protected grader. Validate
   the returned grade, usage, settled charge and cleanup before recording
   either remaining check. Assemble stack completion only after both pass.

The offline documentation check remains bound to its previous 72 inputs.

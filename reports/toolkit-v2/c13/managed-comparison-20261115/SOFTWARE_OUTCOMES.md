# Software grades and LibCST evidence

All four GPT-6.1 Sol software trials delivered a patch that met the
transport and patch contracts. The protected graders ran successfully
and returned the verified reason `test_failure` for each 0/1 grade.
The [read-only audit](software-outcome-audit.json) links each grade to
its trial receipt, patch hash and settled grader operation.

| Workload | Required test identities observed in each arm | Control | Treatment |
| --- | ---: | --- | --- |
| Canopen 613 | 8 | 0/1, `test_failure` | 0/1, `test_failure` |
| Xsdata 1126 | 29 | 0/1, `test_failure` | 0/1, `test_failure` |

Under the [protected grader contract](../../../../src/aeep/assessment/repository_suites.py),
`test_failure` follows successful validation of the grader response
and the presence of every required test identity. It means pytest
returned a nonzero exit code or at least one required test did not
pass. The patch bytes and per-test response were transient. The
retained receipts have hashes and the coarse grade reason, so the
individual failing assertions and their causes cannot be recovered.

The treatment made the reviewed LibCST skill available. The catalog
kept five skills in each treatment and four in each control. Neither
treatment's retained catalog had a LibCST-specific injection
observation, and delivery completeness was unverified. Tool records
retain digests and counts. They contain no LibCST import or command
evidence that can establish actual use, including use through a
normal shell command. Historical LibCST use therefore remains unknown.

This audit used the original trial and grader evidence with zero
software trial replays.

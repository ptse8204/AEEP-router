# AEEP development stack

Build the pinned external evaluator and follow a complete synthetic trial through
to an inspectable HTML/Markdown report. This directory is the reproducible local
foundation for the V2 integration. Its demo executes agent-skill-eval itself;
the agent and task outcomes are synthetic.

```text
stack.py → agent-skill-eval 0.7.0 → upstream artifacts
                                       ↓
                            AEEP fixture verification
                                       ↓
                          evidence.json + HTML/Markdown
```

## Build and run

Tested on macOS arm64, Python 3.13.1, with Apple's Command Line Tools installed.
Run from the repository root. Setup downloads the 24 reviewed wheels into a new,
private environment. It leaves the host Python installation unchanged. Keep the
repository under your user home for the synthetic home-read-denial probe; choose
a runtime directory that does not already exist.

```bash
python3 integrations/toolkit/stack.py plan
python3 integrations/toolkit/stack.py setup --runtime /tmp/aeep-toolkit-runtime
PYTHONPATH=src python3 integrations/toolkit/stack.py demo --runtime /tmp/aeep-toolkit-runtime --output /tmp/aeep-toolkit-report
```

The coordinator uses the repository's existing Python dependencies, while the
external evaluator stays in its private locked runtime. Verify saved results
without running the evaluator again:

```bash
PYTHONPATH=src python3 integrations/toolkit/stack.py verify --output /tmp/aeep-toolkit-report
```

Open `/tmp/aeep-toolkit-report/index.html`. The Markdown report, normalized fixture
evidence, original upstream artifacts and hashes sit beside it. An existing output
directory is never overwritten; use another name for a repeat run.

Setup requires 500 MiB above the 50 GiB host reserve. The tested isolated runtime
occupied about 68 MiB. Dependency versions, wheel hashes, source URLs and license
metadata are in `requirements-macos-arm64-py313.lock` and `packages.json`.
The agent-skill-eval wheel matches all 16 Python files at source revision
`59de161f657b82bfaf8f6abe83dfff38552deb21`.

## What runs

The upstream CLI schedules two fixed cases in both arms, exposes the synthetic
skill only in treatment, and uses its existing fake harness and deterministic
graders. AEEP checks all four records, the exact candidate hash, exposure, terminal
status and independent fixture outputs before generating a report. A zero CLI
exit alone is insufficient: the pinned upstream can return zero when all trials
error. That observed failure is retained in the C04 evidence.

The child uses a fresh home, disabled dotenv/global Git configuration and a
macOS sandbox denying network connections, home reads and writes outside scratch.
Synthetic probes must pass before upstream runs. Each command has a timeout;
timeout stops its process group. The script accepts only the pinned synthetic
suite, not arbitrary candidates, hooks, model choices or provider credentials.

The report excludes upstream fake token/time/cost constants from model
measurements. Fixture outcomes cannot establish skill benefit. This local sandbox
does not establish the separate-container boundary required for real comparisons.

## Files and future integration points

| File | Responsibility |
|---|---|
| `stack.json` | Selected components, source/fixture pins and connection status |
| `requirements-macos-arm64-py313.lock` | Complete wheel dependency closure for this host |
| `packages.json` | Package source, version, hash and declared license metadata |
| `stack.py` | Standard venv/pip bootstrap and a thin bridge to the upstream CLI |
| `fixtures/` | Synthetic skill and two cases; not real benchmark evidence |
| `report.html` | Static local showcase template; no remote fonts or scripts |
| `receipts.py` | Existing executor/store bridge and C02 fixture normalization |
| `test_stack.py`, `test_receipts.py` | Failure, provenance, exposure, output and read-only verification checks |

The fixture batch now uses the existing `CommandExecutor`, execution journal,
`ExecutionReceipt`, `ReceiptStore` and `AssessmentRepository`. No Router instance
or routing configuration is created. A fixed-executor selection decision is stored before dispatch, without route
ranking. Its immutable snapshot binds the coordinator receipt, which is referenced by the
four C02 `EvaluationRun` records in `toolkit-evidence.json`. `toolkit-comparison.json`
remains `NOT_ASSESSED`. Process resources in the receipt are not individual model
measurements. Failed/timed-out commands retain their receipt without retrying.

`receipts.py` normalizes only checked synthetic records. The `verify` command
resolves the bundle against stored definitions, its selection and receipt snapshots, and artifact
hashes through a read-only SQLite connection. It refuses an unfinished WAL and
does not create a missing database. These are local provenance checks, not signed
third-party attestations or production assessment authorization.

The next connections are the existing controlled workers and reviewed live
assessment dispatch, followed by the general comparison/report engine. Keep this fixed
development demo separate from approved live assessment dispatch. Do not grow it
into a second experiment runner or approval system.

The [architecture record](../../docs/aeep-toolkit/ARCHITECTURE_LOCK.md) maps the
Essentials, Evaluation Toolkit and Full Toolkit profiles. Optional scanner,
discovery, benchmark, observability and workflow packages are not installed here.
Linux/Windows locks, live hosts and release qualification remain open.

## Verify and remove

```bash
PYTHONPATH=src python3 -m unittest discover -s integrations/toolkit -p 'test_*.py' -v
python3 -m ruff check integrations/toolkit
```

CI runs the bridge's offline checks on its existing Linux/macOS matrix. These
checks use local subprocess fixtures; they do not install or invoke the external
evaluator. The actual upstream demo remains qualified only on the recorded Mac.

Successful demos remove only their newly created worker scratch directory.
Failed demos retain it and write `failure.json` for inspection. To remove a
development installation, remove only the runtime and report directories you
created after confirming their ownership. There are no persistent services,
global configuration edits or model credentials in this stack.


Earlier receipt showcases retain the weaker pre-selection-binding format and the
source revision that verified it. They remain historical synthetic artifacts.
The current verifier requires a stored matching selection decision; use the
recorded older bridge revision when reproducing an earlier validation result.

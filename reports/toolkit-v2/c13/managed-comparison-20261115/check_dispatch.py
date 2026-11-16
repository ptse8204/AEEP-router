"""Exercise dispatch gates with copied evidence and first-party stand-ins."""

import asyncio
import runpy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_dispatch as dispatch
from dispatch_tasks import bind_tasks
from prepare_renewal import snapshot
from prepare_runtime import WORK, sha, write

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits
from aeep.assessment.service import AssessmentService
from aeep.hosts import codex_pair_inspection as inspection
from aeep.store import ReceiptStore
from aeep_toolkit.worker_readiness import _Document


async def check():
    production = snapshot()
    original = production[0]
    with tempfile.TemporaryDirectory(prefix="gate-check-", dir=WORK) as directory:
        folder = Path(directory)
        approval = folder / "approval.json"
        review = folder / "review.json"
        write(review, {"fixture": True})
        with patch.multiple(dispatch, REVIEW=review, APPROVAL=approval):
            try:
                await dispatch.execute(sha(review))
            except RuntimeError as error:
                assert str(error) == "exact dispatch approval required"
            else:
                raise AssertionError("dispatch without approval")
            write(approval, {"approved": True, "review_sha256": "0" * 64})
            try:
                dispatch.explicit_approval(sha(review))
            except RuntimeError:
                pass
            else:
                raise AssertionError("mismatched approval was accepted")

        rejected_pair_dispatches = []

        async def deny_pair(service, control, treatment):
            _, requests, _, probes = inspection.authorize_pair(service, control, treatment)
            assert len(requests) == 2 and all(len(probe) == 11 for probe in probes)
            rejected_pair_dispatches.append((control, treatment))
            return {"probes_match": False, "model_turns": 0}

        with (
            ReceiptStore(WORK / "renewal-copy.sqlite3", read_only=True) as source,
            ReceiptStore(folder / "ledger.sqlite3") as copied,
            patch.object(inspection, "execute_pair", deny_pair),
        ):
            source._connection.backup(copied._connection)
            service = AssessmentService(SimpleNamespace(store=copied), folder)
            repo = service.repository
            subject = dispatch.store_doc(repo, "subject", _Document(value={"fixture": True}))
            seen = 0
            entries = bind_tasks()
            for task, recipe, _, _, _, pair, shared, _ in entries:
                case_folder = folder / task["id"]
                case_folder.mkdir()
                try:
                    await dispatch.authenticate_pair(
                        service,
                        original,
                        task,
                        recipe,
                        pair,
                        shared,
                        subject,
                        case_folder,
                        lambda: None,
                    )
                except AssertionError:
                    assert not (case_folder / "authenticated-readiness.json").exists()
                    seen += 1
                else:
                    raise AssertionError("failed readiness admitted")

            assert len(rejected_pair_dispatches) == seen == 4
            task, recipe, _, _, _, _, _, _ = entries[0]
            stamp = "fixture-managed-sol-development"
            support = dispatch.request(
                repo,
                stamp,
                subject,
                dispatch.store_doc(repo, "recipe", recipe),
                AssessmentEnvironment(
                    environment_id=stamp, kind="trusted_local", identity={"task": task["id"]}
                ),
            )
            dispatch.scope(repo, original, [support], folder, "fixture")
            fixture_op = stamp + "-operation"
            repo.reserve(
                support,
                fixture_op,
                AssessmentLimits(max_operations=1, max_elapsed_seconds=4),
                stage="local_interruption_fixture",
            )
            assert fixture_op in dispatch.reservations(repo)
            assert len(repo.operation_ledger(stamp).operations) == 1
            repo.finish_operation(fixture_op, elapsed_seconds=0.01)
            assert fixture_op not in dispatch.reservations(repo)

        trial = runpy.run_path(str(dispatch.TRIAL))["require_complete"]
        evidence = {
            "canonical_trial_complete": True,
            "worker_cleanup_confirmed": True,
            "independent_grader_observed": True,
            "task_prompt_bound": True,
            "token_capture": {"status": "verified"},
            "task_grade": False,
        }
        trial(evidence)
        for key in evidence:
            try:
                trial(evidence | {key: None})
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"missing {key} admitted")

        dispatch.render_result(
            {
                "review_sha256": "0" * 64,
                "tasks": [
                    {
                        "task": "first-party-formatter-fixture",
                        "arms": [
                            {"arm": "control", "score": 0, "agent_wall_seconds": 2},
                            {"arm": "treatment", "score": 1, "agent_wall_seconds": 3},
                        ],
                        "treatment_minus_control_tokens": {"input_tokens": -20, "output_tokens": 4},
                    }
                ],
            },
            folder,
        )
        assert "| 0 | 1 | -20 | 4 | 1 |" in (folder / "report.md").read_text()
        assert "<td>-20</td>" in (folder / "report.html").read_text()
    assert production == snapshot()
    write(
        WORK / "dispatch-gate-verification.json",
        {
            "missing_and_wrong_approval_rejected": True,
            "real_pair_authorizations_followed_by_synthetic_probe_failure": seen,
            "missing_evidence_rejections": len(evidence),
            "settled_zero_score_accepted": True,
            "interrupted_reservation_visible_on_copy": True,
            "score_token_timing_report_fixture": True,
            "production_grant_and_reservations_unchanged": True,
            "proxy_starts": 0,
            "provider_requests": 0,
        },
    )


if __name__ == "__main__":
    asyncio.run(check())

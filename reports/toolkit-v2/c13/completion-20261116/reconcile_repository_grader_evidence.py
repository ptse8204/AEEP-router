"""Verify prospective repository cases against retained protected runs and read-only receipts."""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from contextlib import closing
from inspect import getsourcefile
from pathlib import Path

from audit_formal_inputs import HERE, PREVIOUS, ROOT, digest

from aeep.assessment.containment import container_name
from aeep.assessment.models import AssessmentEnvironment, RecipeDefinition, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttemptState
from aeep.economic.prepared import deterministic_digest
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.models import ActionConstraints, ExecutionReceipt, ExecutionStatus
from aeep_toolkit.workflow_evidence import _settled, open_store


class EvidenceMismatch(ValueError):
    """A reviewed binding differs from the retained evidence."""


def require(condition, reason):
    if not condition:
        raise EvidenceMismatch(reason)


def bound_json(path, expected):
    data = path.read_bytes()
    require(digest(data) == expected, "file binding differs")
    return json.loads(data)


def index(rows, field):
    result = {row[field]: row for row in rows}
    require(len(result) == len(rows), "duplicate evidence key")
    return result


def case_binding(case):
    return case.model_dump(
        mode="json", exclude={"split", "used_for_development", "license", "provenance", "origin_kind"}
    )


def verify_expectation(reply, grade, expected):
    statuses = reply["statuses"]
    require(reply["exit_code"] == expected["exit_code"], "observer exit differs")
    require(grade["valid"] is expected["valid"] and grade["detail"] == expected["detail"], "grade differs")
    require(
        all(statuses.get(test) == status for test, status in expected["statuses"].items()),
        "declared test outcome differs",
    )
    if "required_identities" in expected:
        require(set(statuses) == set(expected["required_identities"]), "observed identity set differs")
    if "at_least_one_failed" in expected:
        tests = expected["at_least_one_failed"]
        require(
            any(statuses.get(test) == "FAILED" for test in tests)
            and all(statuses.get(test) in {"PASSED", "FAILED"} for test in tests),
            "partial repair lacks a complete observed failure",
        )


def verify_receipt(ledger, database_root, request, row, spec, payload):
    operation_id = row["operation_id"]
    operation = _settled(ledger, operation_id)
    require(operation.plan_id == request["plan_id"], "operation came from another plan")
    require(
        operation.reserved.max_model_turns == 0
        and operation.reserved.max_cash_usd == 0
        and operation.accounting is not None
        and not operation.accounting.model_usage
        and not operation.accounting.subscription_usage
        and not operation.accounting.cash.components,
        "operation model or cash boundary differs",
    )
    path = database_root / request["plan_id"] / "recipe-operations" / (operation_id + ".sqlite3")
    with closing(open_store(str(path))) as store:
        receipt = store.get_receipt(row["receipt_id"])
        require(receipt is not None and content_digest(receipt) == row["receipt_ref"], "receipt binding differs")
        require(
            ExecutionReceipt.model_validate(ledger.get("recipe_receipt", row["receipt_id"])) == receipt,
            "operation and assessment receipts differ",
        )
        attempt_id = receipt.metadata["attempt_id"]
        attempt = store.get_execution_attempt(attempt_id)
        require(
            attempt is not None
            and attempt.state is ExecutionAttemptState.COMPLETED
            and receipt.status is ExecutionStatus.SUCCESS
            and receipt.receipt_id in attempt.terminal_receipt_ids
            and receipt.executor_id == attempt.executor_id == spec.id
            and receipt.executor_fingerprint == attempt.executor_fingerprint,
            "execution identity differs or is not terminal",
        )
        require(attempt.action_digest == deterministic_digest({
            "capability": spec.capability,
            "input": payload,
            "constraints": ActionConstraints(allowed_executor_ids=[spec.id]),
        }), "invoked payload differs")
        require(
            container_name(attempt_id) == row["container_name"] and row["container_removed"] is True
            and row["environment_digest"] == request["environment_digest"],
            "container evidence differs",
        )
        journal_ref = receipt.metadata["execution_evidence_digest"]
        journal = ExecutionEvidence.model_validate(AssessmentRepository(store).get("execution_evidence", journal_ref))
        require(
            content_digest(journal) == journal_ref and journal.complete and journal.attempt_id == attempt_id
            and journal.events[-1].kind == "execution.completed",
            "terminal journal binding differs",
        )
    return {
        "receipt_id": row["receipt_id"], "receipt_sha256": row["receipt_ref"],
        "attempt_id": attempt_id, "action_digest": attempt.action_digest, "journal_sha256": journal_ref,
        "operation_id": operation_id, "measurement_sha256": content_digest(operation),
        "elapsed_seconds": operation.elapsed_seconds, "executor_fingerprint": attempt.executor_fingerprint,
        "original_cleanup_confirmed": True,
    }


async def verify_variant(case, variant, observation, retained_grade, expected, assets, directory):
    payload_path = ROOT / variant["payload"]
    require(assets[str(payload_path)] == variant["sha256"], "payload was outside the reviewed asset set")
    payload = bound_json(payload_path, variant["sha256"])
    raw_path = directory / observation["raw_file"]
    require(raw_path.parent == directory, "observer evidence path differs")
    raw = bound_json(raw_path, observation["raw_sha256"])
    require(
        raw["name"] == observation["name"] and raw["operation_id"] == observation["operation_id"]
        and raw["execution_error_type"] is None and observation["execution_error_type"] is None
        and raw.get("profile") == observation.get("profile"),
        "observer identity differs or the original execution failed",
    )
    output = raw["output"]
    require(isinstance(output, dict), "observer output missing or invalid")
    reply = output["evaluation"] if set(output) == {"evaluation", "failure_log_tail_b64"} else output
    called = False

    async def retained_probe(current_payload):
        nonlocal called
        require(not called and current_payload == payload, "current callback reconstructs a different payload")
        called = True
        return reply

    grade = (await grade_suite_output(
        case.input.model_dump(mode="json"), case.truth.model_dump(mode="json"), variant["artifact"], retained_probe,
    )).model_dump(mode="json")
    require(
        called and grade == retained_grade["grade"] and retained_grade["passed"] is True
        and not retained_grade["discrepancies"],
        "current callback grade differs from the retained outcome",
    )
    verify_expectation(reply, grade, expected)
    return payload, reply, {
        "grade": grade, "variant": variant["variant"], "declared_outcome_count": len(expected["statuses"]),
        "test_outcome_counts": dict(sorted(Counter(reply["statuses"].values()).items())),
        "observed_exit_code": reply["exit_code"], "payload_sha256": variant["sha256"],
        "archive_sha256": payload["archive_sha256"], "raw_observation_sha256": observation["raw_sha256"],
        "raw_observation_path": str(raw_path.relative_to(ROOT)),
    }


async def reconcile(case, result_path, result, row, ledger, database_root):
    directory = result_path.parent
    review = bound_json(directory / "operation-review.json", result["review_sha256"])
    require(
        result["source_digest"] == review["source_digest"] and result["model_turns"] == 0
        and all(result[name] is True for name in ("batch_completed", "elapsed_complete", "containers_removed", "source_unchanged")),
        "historical batch accounting, containment or source did not close",
    )
    retained = review
    if derived_ref := result.get("derived_review_sha256"):
        retained = bound_json(directory / "derived-review.json", derived_ref)
        require(
            retained["parent_operation_review_sha256"] == result["review_sha256"]
            and retained["source_digest"] == result["source_digest"]
            and retained["frozen_before_any_body_trial"] is True,
            "runtime-derived case is not bound to the original review",
        )
    assets = retained["assets"]
    cases_path = ROOT / retained["cases_file"]
    variants_path = ROOT / retained["variants_file"]
    original_cases = bound_json(cases_path, assets[str(cases_path)])
    original = RepositorySuiteCase.model_validate(index(original_cases, "independent_case_id")[case.independent_case_id])
    require(case_binding(original) == case_binding(case), "current case definition differs from the observed definition")
    variants = index([
        variant for variant in bound_json(variants_path, assets[str(variants_path)])
        if variant["case"] == case.independent_case_id
    ], "variant")
    grades = index(row["variants"], "variant")
    expectations = retained["expectations"][case.independent_case_id]
    require(set(variants) == set(grades) == set(expectations), "reviewed variant set differs")
    require(
        {"reference", "counterexample"} <= variants.keys()
        and variants["reference"]["artifact"] == json.loads(case.reference.read()),
        "reference artifact differs or no reviewed counterexample",
    )
    observations = index(result["observations"], "name")
    receipts = index(result["receipts"], "name")
    request = review["request"]
    recipe = RecipeDefinition.model_validate(ledger.get("recipe", request["recipe_digest"]))
    environment = AssessmentEnvironment.model_validate(ledger.get("environment", request["environment_digest"]))
    require(
        content_digest(recipe) == request["recipe_digest"] and recipe.extension is not None
        and content_digest(environment) == request["environment_digest"] and environment.kind == "container"
        and not environment.network and not environment.read_only_roots,
        "historical recipe or environment changed",
    )
    verified = []
    negative_payloads = {}
    for label, variant in variants.items():
        name = case.independent_case_id + "-" + label
        observation, receipt = observations[name], receipts[name]
        require(
            receipt["operation_id"] == observation["operation_id"] and receipt.get("profile") == observation.get("profile"),
            "observer and receipt operation differs",
        )
        payload, reply, evidence = await verify_variant(
            case, variant, observation, grades[label], expectations[label], assets, directory,
        )
        spec = recipe.extension.reference if observation.get("profile") == "default" else recipe.extension.grader
        require(spec is not None, "historical executor is missing")
        evidence.update(verify_receipt(ledger, database_root, request, receipt, spec, payload))
        verified.append(evidence)
        if label != "reference":
            negative_payloads[content_digest(payload)] = (label, reply)
    require(
        next(row for row in verified if row["variant"] == "reference")["grade"]["quality_score"] == 1.0
        and all(row["grade"]["quality_score"] == 0.0 for row in verified if row["variant"] != "reference"),
        "missing reference success or meaningful counterexample rejection",
    )
    faults = []
    for fault in case.fault_outputs:
        matched = None

        async def match_negative(payload):
            nonlocal matched
            matched = negative_payloads.get(content_digest(payload))
            if matched is None:
                raise EvidenceMismatch("current fault has no matching historical payload")
            return matched[1]

        try:
            grade = await grade_suite_output(
                case.input.model_dump(mode="json"), case.truth.model_dump(mode="json"), fault, match_negative,
            )
        except EvidenceMismatch:
            grade = None
        faults.append({
            "artifact_sha256": content_digest(fault), "matching_variant": (
                matched[0] if matched and grade is not None and grade.valid is False else None
            ),
        })
    return {
        "historical_source_digest": result["source_digest"], "environment_sha256": request["environment_digest"],
        "container_image": environment.container_image, "recipe_sha256": request["recipe_digest"],
        "execution_result_path": str(result_path.relative_to(ROOT)),
        "execution_result_sha256": digest(result_path.read_bytes()),
        "review_sha256": result["review_sha256"], "derived_review_sha256": result.get("derived_review_sha256"),
        "variants": verified, "current_fault_bindings": faults,
    }


async def audit(ledger, database_root):
    prepared = json.loads((HERE / "formal-transport-preparation.json").read_bytes())
    pool = bound_json(ROOT / prepared["prepared_pool_relative_path"], prepared["prepared_pool_sha256"])
    cases = index([RepositorySuiteCase.model_validate(item).model_dump(mode="json") for item in pool], "independent_case_id")
    eligible = defaultdict(list)
    for result_path in sorted(PREVIOUS.glob("repository-*/**/execution-result.json")):
        result = json.loads(result_path.read_bytes())
        for row in result.get("results", []):
            if isinstance(row, dict) and row.get("case_id") in cases and row.get("reproduction_eligible") is True:
                eligible[row["case_id"]].append((result_path, result, row))
    accepted, gaps = {}, {}
    for case_id, value in cases.items():
        case = RepositorySuiteCase.model_validate(value)
        reasons = []
        for path, result, row in reversed(eligible[case_id]):
            try:
                accepted[case_id] = {
                    "case_sha256": content_digest(case), "source_revision": case.source_revision,
                    **await reconcile(case, path, result, row, ledger, database_root),
                }
                break
            except (EvidenceMismatch, ConfigurationError, OSError, KeyError) as exc:
                reason = str(exc) if isinstance(exc, EvidenceMismatch) else type(exc).__name__
                reasons.append({"execution_result": str(path.relative_to(ROOT)), "reason": reason})
        if case_id not in accepted:
            gaps[case_id] = reasons or [{"reason": "no eligible historical run for this exact case identity"}]
    return {
        "schema_version": "aeep.c13.retained-grader-evidence.v1",
        "prepared_pool_sha256": prepared["prepared_pool_sha256"],
        "current_callback_source_sha256": verification_source_digest(Path(getsourcefile(grade_suite_output)).parents[3]),
        "prospective_cases_checked": len(cases),
        "protected_cases_reconciled": len(accepted),
        "protected_observations_reconciled": sum(len(item["variants"]) for item in accepted.values()),
        "cases_with_all_current_faults_observed": sum(
            all(fault["matching_variant"] is not None for fault in item["current_fault_bindings"])
            for item in accepted.values()
        ),
        "cases_with_verified_observations": accepted,
        "unresolved_cases": gaps,
        "scope": (
            "Historical offline observations linked to current callback interpretation and original settled receipts. "
            "Raw observer outputs are bound by the original execution record. The canonical journal binds the "
            "invocation, environment and terminal attempt. It does not contain the raw observer output hash."
        ),
        "formal_stage_assignments": 0, "new_operation_reservations": 0, "new_model_turns": 0,
        "current_common_runtime_verified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--operation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with closing(open_store(str(args.ledger))) as store:
        report = asyncio.run(audit(AssessmentRepository(store), args.operation_root))
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print({key: report[key] for key in (
        "prospective_cases_checked", "protected_cases_reconciled", "protected_observations_reconciled",
        "cases_with_all_current_faults_observed",
    )})

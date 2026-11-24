"""Recover truncated Django Bird selectors and verify the protected pair."""

import ast
import asyncio
import os
from datetime import timedelta
from pathlib import Path

import check_cohort_software_batch as batch
import check_eos_case_repair as checked
from check_linux_install import Scope, get, put
from repository_offline_pair_batch import context, expected_statuses, verify_probe

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output
from aeep.models import utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-django-bird-complete-20261124"
COLLECTION = batch.WORK.parent / "django-bird-complete"
WORK = batch.WORK.parent / "django-bird-grading"
REVIEW = WORK / "operation-review.json"


def selector_map(truth, ids, issue):
    seen = set()
    maps = {}
    for field in ("fail_to_pass", "pass_to_pass"):
        group = {}
        for selector in truth[field]:
            matches = [node for node in ids if node == selector]
            if not matches and "[" in selector and "]" not in selector.rsplit("[", 1)[1]:
                matches = [node for node in ids if node.startswith(selector + " ")]
            if field == "fail_to_pass":
                matches = [node for node in matches if node == issue]
            if not matches:
                raise ValueError("missing selector or ambiguous issue test")
            if seen.intersection(matches):
                raise ValueError("two publisher roles bind the same native identity")
            seen.update(matches)
            group[selector] = sorted(matches)
        maps[field] = group
    return maps


async def capture(entry, role):
    value = {}
    expected = expected_statuses(entry["truth"], role)

    async def project(payload):
        value.update(payload)
        return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
            "exit_code": int(role == "original"),
            "statuses": expected,
        }

    score = await grade_suite_output(entry["input"], entry["truth"], entry["roles"][role], project)
    if score.quality_score != int(role == "reference"):
        raise ValueError("rehearsal differs from protected grade protocol")
    return value


async def main():
    os.umask(0o077)
    previous = batch.WORK / "execution" / "result.json"
    failed = [x for x in get(previous)["observations"] if batch.BIRD in x["operation"]]
    if (
        len(failed) != 1
        or failed[0]["contract_matched"]
        or not failed[0]["operation"].endswith(":reference")
    ):
        raise ValueError("expected one settled unresolved Bird reference")
    batch.runner.CARRIER = get(batch.GUARDIAN)["environment"]["container_image"]
    base_spec, environment, cases = batch.definitions()
    (bird,) = [row for row in cases if row["case_id"] == batch.BIRD]
    executor = ContainerExecutor(environment)
    payload = await capture(bird, "reference")
    prior_review = get(batch.WORK / "operation-review.json")
    (prior_launch,) = [
        item for item in prior_review["launches"] if item["operation"] == failed[0]["operation"]
    ]
    if content_digest(payload) != prior_launch["payload_sha256"]:
        raise ValueError("reviewed reference payload changed")
    prior = get(COLLECTION / "result.json")["collection"]
    (charge,) = get(COLLECTION / "ledger.json")["operations"]
    ids = get(COLLECTION / "native-test-ids.json")
    if prior["status"] != "success" or prior["exit_code"] or charge["elapsed_seconds"] is None:
        raise ValueError("retained protected collection is not settled")
    if len(ids) != len(set(ids)) or any(
        not name.startswith("tests/templatetags/test_bird.py::") for name in ids
    ):
        raise ValueError("retained collection escaped the published test module")
    oracle = SuiteTruthV6.model_validate(bird["truth"])
    base = archive_files(oracle.source.read(), large=True)
    protected = archive_files(oracle.tests.read(), large=True)

    def published_descriptions(content):
        return {
            node.value.value
            for node in ast.walk(ast.parse(content))
            if isinstance(node, ast.keyword)
            and node.arg == "description"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }

    (module,) = oracle.test_paths
    (description,) = published_descriptions(protected[module]) - published_descriptions(
        base[module]
    )
    (issue,) = [node for node in ids if node.endswith(f"::test_only_flag[{description}]")]
    maps = selector_map(bird["truth"], ids, issue)
    truth = {
        **bird["truth"],
        **{
            field: sorted(name for matches in group.values() for name in matches)
            for field, group in maps.items()
        },
    }
    related = [name for name in ids if "::test_only_flag[" in name and name != issue]
    truth["pass_to_pass"] = sorted(set(truth["pass_to_pass"]) | set(related))
    cases = {}
    for role in ("reference", "original"):
        inputs = await capture(bird | {"truth": truth}, role)
        attempt = context(base_spec, NAME + ":" + role, inputs)
        cmd, owned = executor.command(attempt)
        cases[role] = (inputs, attempt, cmd, owned)

    WORK.mkdir(mode=0o700)
    put(WORK / "selector-map.json", maps | {"other_preexisting_issue_prefix_matches": related})
    expiry = utc_now() + timedelta(hours=2)
    scope = {
        "prior_result": file_digest(previous),
        "source": batch.CURRENT_SOURCE,
        "collection": {
            **prior,
            "native_ids_sha256": file_digest(COLLECTION / "native-test-ids.json"),
        },
        "carrier_layers": batch.runner.inspect_carrier(),
        "driver_sha256": file_digest(Path(__file__)),
        "grade_spec_sha256": content_digest(base_spec),
        "original_case_sha256": content_digest(bird),
        "selector_mapping_sha256": file_digest(WORK / "selector-map.json"),
        "mapping_rule": "Require the only new issue-test row in the protected publisher overlay. Keep all other matches as preservation.",
        "launches": {
            role: {"argv_sha256": content_digest(cmd), "payload_sha256": content_digest(payload)}
            for role, (payload, _, cmd, _) in cases.items()
        },
        "minimum_free_bytes": 52 * 2**30,
        "maximum_operations": 2,
        "maximum_reserved_seconds": 190,
        "models": 0,
        "cash_usd": 0,
        "retries": 0,
        "authority": "Finite C13 correction using already settled collection and a source-diff-proven issue test.",
    }
    put(REVIEW, scope)
    checked.REVIEW = REVIEW
    exact = file_digest(REVIEW)
    definition = Scope(review_sha256=exact)
    ref = content_digest(definition)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=ref,
        recipe_digest=ref,
        environment_digest=ref,
        mapping_digest=ref,
        definition_digests=[ref],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        allowed_destinations=["local"],
        limits=AssessmentLimits(max_operations=2, max_model_turns=0, max_elapsed_seconds=190),
        expires_at=expiry,
        remote_disclosure=False,
    )
    result = {
        "collection": prior | {"native_count": len(ids)},
        "prior_counts": {key: len(group) for key, group in maps.items()},
        "required_native_counts": {field: len(truth[field]) for field in maps},
    }
    with ReceiptStore(WORK / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_django_bird_selector_scope", ref, definition)
        repo.approve_bundle(grant, {ref: definition.model_dump(mode="json")})
        try:
            for role, (inputs, attempt, cmd, owned) in cases.items():
                expected = expected_statuses(truth, role)
                if (
                    executor.command(attempt) != (cmd, owned)
                    or batch.runner.inspect_carrier() != scope["carrier_layers"]
                ):
                    raise ValueError("retained grader boundary changed")
                raw, receipt = await checked.run_checked(
                    repo,
                    store,
                    request,
                    scope | {"launch": {"container": owned}},
                    exact,
                    executor,
                    attempt,
                )
                results = raw.output if isinstance(raw.output, dict) else {}
                valid = raw.status.value == "success" and verify_probe(
                    results, inputs, expected, int(role == "original")
                )
                result[role] = {
                    "accepted": valid,
                    "receipt": receipt.receipt_id,
                    "exit_code": results.get("exit_code"),
                    "score": None,
                }
                if not valid:
                    break

                async def return_observed(current, inputs=inputs, results=results):
                    if current != inputs:
                        raise ValueError("grade payload changed")
                    return results

                grade = await grade_suite_output(
                    bird["input"], truth, bird["roles"][role], return_observed
                )
                result[role]["score"] = grade.quality_score
        finally:
            put(WORK / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
            put(WORK / "result.json", result)


if __name__ == "__main__":
    asyncio.run(main())

"""Locate retained protected grades by exact carrier and test layer ancestry."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import audit_software_reproduction_pool as pool
from check_linux_install import docker
from stage_repository_transport import HERE, ROOT, digest, read

IMAGE = re.compile(r"sha256:[a-f0-9]{64}")
STABLE_POOL = "software-reproduction-pool-20261117.json"


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def load(name):
    return json.loads((HERE / name).read_bytes())


def result_review(result, key="review_sha256"):
    value = pool.artifact(result)
    path = ROOT / result["path"]
    review = (
        next(
            candidate
            for candidate in (path.parent, path.parent.parent)
            if (candidate / "operation-review.json").is_file()
        )
        / "operation-review.json"
    )
    return (
        value,
        pool.artifact({"path": str(review.relative_to(ROOT)), "sha256": value[key]}),
        ref(review),
    )


def verify_image(image):
    # Read only immutable identifiers, platform and filesystem layers.
    raw = docker(
        "image",
        "inspect",
        image,
        "--format",
        "{{.Id}} {{.Os}}/{{.Architecture}} {{json .RootFS.Layers}}",
    )
    found, platform, layers_json = raw.split(" ", 2)
    layers = json.loads(layers_json)
    if (
        found != image
        or platform != "linux/arm64"
        or not layers
        or not all(IMAGE.fullmatch(value) for value in layers)
    ):
        raise ValueError("local image differs from the historical Linux ARM64 pin")
    return {"platform": platform, "layers": layers}


def historical_rows(add):
    report = load("retained-grader-evidence.json")
    for case, result in report["cases_with_verified_observations"].items():
        env = result["environment_sha256"]
        evidence = {
            "path": result["execution_result_path"],
            "sha256": result["execution_result_sha256"],
        }
        pool.artifact(evidence)
        roles = {
            "reference",
            *(fault["matching_variant"] for fault in result["current_fault_bindings"]),
        }
        for role in result["variants"]:
            if role["variant"] in roles:
                add(case, role["receipt_id"], result["container_image"], env, evidence)


def first_ordinary_rows(add):
    group = load("offline-group-result-20261117.json")["software_evidence"]
    cached, descriptor, evidence = result_review(group["cached_result"])
    environment = descriptor["environment"]
    if not cached["verified"] or environment["network"]:
        raise ValueError("cached protected result is no longer verified offline")
    for role in cached["observations"]:
        _, case, _ = role["operation"].split(":")
        if not role["contract_matched"]:
            raise ValueError("cached role did not settle")
        add(
            case,
            role["receipt_id"],
            environment["container_image"],
            digest_json(environment),
            evidence,
        )

    staged, descriptor, evidence = result_review(group["staged_result"])
    environment = descriptor["environment"]
    if environment["container_image"] != descriptor["image"] or environment["network"]:
        raise ValueError("staged reviewed runtime differs")
    for role in staged["results"]:
        if role["contract_matched"]:
            add(
                role["case"],
                role["receipt"]["receipt_id"],
                descriptor["image"],
                digest_json(environment),
                evidence,
            )

    correction = load("software-correction-result-20261117.json")
    evidence = correction["review"]
    descriptor = pool.artifact(evidence)
    environment = descriptor["environment"]
    if environment["container_image"] != correction["retained_runtime"] or environment["network"]:
        raise ValueError("correction execution used a different carrier")
    for role in correction["observations"]:
        if (
            role["ordinary_callback_grade"]["trust"] != "verified"
            or not role["container_absent_now"]
        ):
            raise ValueError("failed or uncertain correction observation")
        add(
            role["case"],
            role["receipt_id"],
            correction["retained_runtime"],
            digest_json(environment),
            evidence,
        )

    pyserde = load("pyserde-ordinary-result.json")
    evidence = {
        "path": str((HERE / "pyserde-ordinary-operation-review.json").relative_to(ROOT)),
        "sha256": pyserde["review_sha256"],
    }
    pool.artifact(evidence)
    folder = (ROOT / pyserde["receipt_ledger_path"]).parent
    execution = json.loads(read(folder / "result.json", pyserde["retained_result_sha256"]))
    if (
        (folder / "image-id").read_text().strip() != pyserde["built_image"]["image_id"]
        or not pyserde["protected_ordinary_verification_passed"]
        or not isinstance(execution, dict)
    ):
        raise ValueError("retained Pyserde runtime or graded scope changed")
    for role in pyserde["roles"]:
        add(pyserde["case"], role["receipt_id"], pyserde["built_image"]["image_id"], None, evidence)


def additional_rows(add):
    group = load("offline-completion-results-20261118.json")
    rows = group["software_reproduction_pool"]["additional_rows"]
    arta, returnn = rows
    book = pool.artifact(group["initial_group"])["results"]["arta-protected-grading"]
    book = pool.artifact(book["result"])
    evidence = {
        "path": str((HERE / "arta-protected-pair-review-20261117.json").relative_to(ROOT)),
        "sha256": book["review_sha256"],
    }
    descriptor = pool.artifact(evidence)
    environment = descriptor["environment"]
    if (
        set(arta["receipt_ids"]) != {row["receipt_id"] for row in book["observations"]}
        or not book["verified"]
    ):
        raise ValueError("Arta receipt set changed")
    for receipt in arta["receipt_ids"]:
        add(
            arta["case"],
            receipt,
            environment["container_image"],
            digest_json(environment),
            evidence,
        )

    settled = group["returnn"]
    book = pool.artifact(settled["result"])
    pool.artifact(settled["review"])
    if (
        book["review_sha256"] != settled["review"]["sha256"]
        or book["imported"]["image"] != settled["runtime"]["image"]
        or not book["verified"]
        or set(returnn["receipt_ids"])
        != {
            row["receipt_id"]
            for row in book["observations"]
            if row["role"] in ("reference", "original") and row["container_absent"]
        }
    ):
        raise ValueError("RETURNN runtime or receipt set changed")
    for receipt in returnn["receipt_ids"]:
        add(returnn["case"], receipt, settled["runtime"]["image"], None, settled["review"])

    guardian = load("expansion-contract-audit-results-20261118.json")
    row = guardian["software_reproduction_pool"]["new_row"]
    evidence = guardian["django_guardian"]["scope_review"]
    environment = pool.artifact(evidence)["environment"]
    for role in guardian["django_guardian"]["observations"]:
        receipt = pool.artifact(role["receipt"])["receipt_id"]
        if receipt not in row["receipt_ids"]:
            raise ValueError("Django Guardian receipt changed")
        add(
            row["case"], receipt, environment["container_image"], digest_json(environment), evidence
        )

    for name, evidence_field, image_field, result_field in (
        (
            "raygun-protected-audit-results-20261118.json",
            "exact_review",
            "retained_image",
            "protected_result",
        ),
        ("djpress-protected-result-20261118.json", "review", "carrier", "result"),
    ):
        result = load(name)
        row = result["software_reproduction_pool"]["new_row"]
        evidence = result[evidence_field]
        environment = pool.artifact(evidence)["environment"]
        executed = pool.artifact(result[result_field])
        if (
            environment["container_image"] != result[image_field]
            or environment["network"]
            or executed["review_sha256"] != evidence["sha256"]
            or not executed["verified"]
            or [item["receipt_id"] for item in executed["observations"]] != row["receipt_ids"]
            or [item["score"] for item in executed["observations"]] != [1.0, 0.0]
        ):
            raise ValueError("reported protected runtime or observations differ from review")
        for receipt in row["receipt_ids"]:
            add(row["case"], receipt, result[image_field], digest_json(environment), evidence)


def digest_json(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def expected_rows():
    baseline = pool.audit()
    if baseline != {k: v for k, v in load(STABLE_POOL).items() if k != "verification"}:
        raise ValueError("earlier protected case pool no longer replays")
    rows = [*baseline["rows"]]
    for name in (
        "offline-completion-results-20261118.json",
        "expansion-contract-audit-results-20261118.json",
        "raygun-protected-audit-results-20261118.json",
        "djpress-protected-result-20261118.json",
    ):
        result = load(name)["software_reproduction_pool"]
        rows.extend(
            result["additional_rows"] if "additional_rows" in result else [result["new_row"]]
        )
        _, _, excluded = pool.previous_repositories()
        if pool.assess(rows, excluded) != result["capacity"]:
            raise ValueError("protected pool totals changed")
    return rows


def image_coverage(cases, inventory):
    plans = {}
    for image, details in sorted(inventory.items()):
        layers = details["layers"]
        exact, inherited, other = set(), set(), set()
        for case, source_image in cases.items():
            prefix = inventory[source_image]["layers"]
            if image == source_image:
                exact.add(case)
            elif layers[: len(prefix)] == prefix:
                inherited.add(case)
            else:
                other.add(case)
        plans[image] = {
            "exact": exact,
            "layer_prefix_only": inherited,
            "outside_layer_lineage": other,
        }
    return plans


def audit():
    rows = expected_rows()
    by_case = {row["case"]: row for row in rows}
    all_receipts = {receipt for row in rows for receipt in row["receipt_ids"]}
    bindings = defaultdict(dict)

    def add(case, receipt, image, environment_digest, evidence):
        if (
            case not in by_case
            or receipt not in by_case[case]["receipt_ids"]
            or not IMAGE.fullmatch(image)
            or receipt in bindings[case]
        ):
            raise ValueError(
                "evidence changed grade ownership, duplicated a role, or lacks a carrier pin"
            )
        bindings[case][receipt] = {
            "carrier": image,
            "review_environment_identity_sha256": environment_digest,
            "evidence": evidence,
        }

    historical_rows(add)
    first_ordinary_rows(add)
    additional_rows(add)
    if (
        bindings.keys() != by_case.keys()
        or {receipt for entries in bindings.values() for receipt in entries} != all_receipts
    ):
        raise ValueError("at least one evidence role is unbound")
    sole_images = {}
    multi = {}
    for case, entries in bindings.items():
        image_set = {entry["carrier"] for entry in entries.values()}
        if len(image_set) == 1:
            sole_images[case] = image_set.pop()
        else:
            multi[case] = sorted(image_set)

    inventory = {image: verify_image(image) for image in sorted(set(sole_images.values()))}
    coverage = image_coverage(sole_images, inventory)
    contenders = {}
    for image, partitions in coverage.items():
        contenders[image] = {
            "platform": inventory[image]["platform"],
            "layer_count": len(inventory[image]["layers"]),
            "ordered_layer_sha256": digest_json(inventory[image]["layers"]),
            "counts": {name: len(cases) for name, cases in partitions.items()},
            "family_coverage": {
                key: dict(Counter(by_case[row]["family"] for row in value))
                for key, value in partitions.items()
            },
        }
    best = max(
        contenders,
        key=lambda image: (
            contenders[image]["counts"]["exact"] + contenders[image]["counts"]["layer_prefix_only"],
            contenders[image]["counts"]["exact"],
        ),
    )
    return {
        "schema_version": "aeep.c13.protected-case-carrier-audit.v1",
        "driver": ref(Path(__file__)),
        "latest_pool": ref(HERE / "djpress-protected-result-20261118.json"),
        "previous_carrier_audit": ref(HERE / "grader-evidence-runtime-map.json"),
        "preferred_prefix_only_cases": sorted(coverage[best]["layer_prefix_only"]),
        "preferred_outside_lineage_cases": sorted(coverage[best]["outside_layer_lineage"]),
        "preferred_exact_image_cases": sorted(coverage[best]["exact"]),
        "case_count": len(rows),
        "receipt_count": len(all_receipts),
        "images": contenders,
        "case_bindings": bindings,
        "multi_carrier_cases": multi,
        "preferred_next_candidate_by_layer_lineage": best,
        "scope": "Carrier lineage only. Exact rows ran on the same image but may have different source, grader, dependencies or environment. A matching ordered parent layer prefix cannot establish application-level compatibility.",
        "profile_needs": "Freeze a reviewed common grader, compare actual per-case import origins, and check the exact protected reference and all required counterexamples before accepting a consolidated set.",
        "new_upstream_executions": 0,
        "new_image_or_volume_changes": 0,
        "new_model_turns": 0,
        "formal_cases_adopted": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))

"""Freeze the verified economic task into the ordinary contained recipe contract."""

import base64
import json
import runpy

from check_linux_install import DOCKER, HERE, IMAGE, SOCKET, WORK, get, put
from run_economic_reference import MOUNT, REVIEW, expected_outcomes

from aeep.assessment.extensions import bounded_batches, grader_name, require_environment
from aeep.assessment.models import (
    AssessmentEnvironment,
    IntegrationCaseSet,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.recipes import faulty_outputs
from aeep.benchmarking import BenchmarkCase
from aeep.models import ActionRequest, ValidationSpec
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.install_runtime import file_digest

TASK_ID = "econ-detrending-correlation"
OUT = WORK / "economic-ordinary-recipe"
BUILDER = HERE.parent / "skillsbench-contained-graders-20261105/prepare-recipes.py"
PROTECTED_RESULT = HERE / "protected-reference-group-result.json"


def definitions():
    intake = get(HERE / "independent-document-pack-intake.json")
    root = WORK / "independent-document-pack"
    pack_file = root / "pack.json"
    if file_digest(pack_file) != intake["manifest_file_sha256"]:
        raise ValueError("independent document pack changed")
    pack = BenchmarkPack.model_validate_json(pack_file.read_bytes())
    value = task_input(pack, root / "pack-assets", TASK_ID)
    if (
        value["benchmark_pack_sha256"] != intake["pack_sha256"]
        or value["task_archive_sha256"] != intake["tasks"][TASK_ID]["archive_sha256"]
    ):
        raise ValueError("economic worker input changed")

    observed = get(PROTECTED_RESULT)["results"]["economic"]
    retained = observed["roles"]["economic"]["observation"]
    prior_review = get(REVIEW)
    if (
        not observed["passed_exact_contract"]
        or retained != expected_outcomes()
        or file_digest(REVIEW) != observed["review_sha256"]
        or any(file_digest(MOUNT / name) != pin for name, pin in prior_review["files"].items())
        or observed["runtime_image_id"] != IMAGE
    ):
        raise ValueError("verified economic input or result changed")
    fixtures = get(MOUNT / "fixtures.json")
    verifier = (MOUNT / "upstream_test.py").read_bytes()
    preserved_observer = (MOUNT / "economic_protected_grader.py").read_text()
    pause, separator, _ = preserved_observer.rpartition('if __name__ == "__main__":')
    if not separator:
        raise ValueError("reviewed observer entry point changed")

    ref = fixtures["artifacts"]["reference"].encode("ascii")
    binding = {
        "task_id": TASK_ID,
        "output_field": "answer_b64",
        "max_output_bytes": 128,
        "archive_sha256": value["task_archive_sha256"],
        "input_digest": content_digest(value),
        "verifier_sha256": fixtures["verifier_sha256"],
        "expected": fixtures["expected"],
    }
    guest = (HERE / "economic_recipe_guest.py").read_text()
    program = pause + "\n" + guest + f"\ndispatch({binding!r}, {verifier!r}, observe)\n"
    compile(program, "protected economic recipe", "exec")
    builder = runpy.run_path(str(BUILDER))
    recipe = builder["recipe_for"](
        "economic-detrending", binding, value, ref, fixtures["artifacts"]["excluded_2024"].encode("ascii")
    ).model_dump(mode="json")
    recipe["dependencies"].update(
        protected_reference=file_digest(PROTECTED_RESULT),
        verifier=binding["verifier_sha256"],
    )
    extension = recipe["extension"]
    extension["grader"]["config"].update(
        argv=["python3", "-I", "-B", "-c", program],
        timeout_seconds=20,
        max_output_bytes=4096,
    )
    extension["failure_codes"].append("precision_rejected")
    fault_roles = ("excluded_2024", "excess_precision", "quarterly_smoothing")
    extension["fault_outputs"] = [
        {"answer_b64": base64.b64encode(fixtures["artifacts"][role].encode("ascii")).decode("ascii")}
        for role in fault_roles
    ]
    recipe = RecipeDefinition.model_validate(recipe)
    environment = AssessmentEnvironment(
        environment_id="economic-ordinary-grader",
        kind="container",
        identity={"protected_reference": observed["review_sha256"]},
        container_image=IMAGE,
        container_runtime=DOCKER,
        container_socket=SOCKET,
        memory_mb=512,
        process_limit=96,
    )
    require_environment(recipe, environment)
    truth = {"task_archive_sha256": value["task_archive_sha256"]}
    case = BenchmarkCase(
        case_id="economic-ordinary-integration",
        split="qualification",
        variation=TASK_ID,
        template_family=extension["template_families"][0],
        action=ActionRequest(
            action_id="act_3e5017591520427e99196d188ead1a8b",
            capability=recipe.capability,
            input=value,
        ),
        validators=[ValidationSpec(kind="callback", config={
            "name": grader_name(value, truth), "expected": truth,
            "failure_codes": extension["failure_codes"],
        })],
    )
    cases = IntegrationCaseSet(
        request_id="economic-ordinary-preparation",
        purpose="stack_integration_only",
        recipe_digest=content_digest(recipe),
        environment_digest=content_digest(environment),
        benchmark_pack_digest=value["benchmark_pack_sha256"],
        seed=0,
        cases=[case],
    )
    reference = {"answer_b64": base64.b64encode(ref).decode("ascii")}
    validate_json(value, recipe.input_schema, label="ordinary economic task")
    validate_json(reference, recipe.output_schema, label="protected economic reference")
    assert recipe.extension is not None
    validate_json(truth, recipe.extension.truth_schema, label="protected economic binding")
    examples = [
        {"input": value, "output": output, "expected": truth}
        for output in [reference, *faulty_outputs(reference), *recipe.extension.fault_outputs]
    ]
    codes = [None, *["output_contract"] * len(faulty_outputs(reference)),
             "precision_rejected", "precision_rejected", "upstream_rejected"]
    assert len(bounded_batches(examples, separate=True)) == len(codes) == len(examples)
    return recipe, environment, cases, examples, codes


def prepare():
    recipe, environment, cases, _examples, codes = definitions()
    OUT.mkdir(mode=0o700)
    for name, model in (("recipe", recipe), ("environment", environment), ("case-set", cases)):
        target = OUT / f"{name}.json"
        put(target, model.model_dump(mode="json"))
        target.chmod(0o400)
    report = {
        "task_id": TASK_ID,
        "recipe_digest": content_digest(recipe),
        "environment_digest": content_digest(environment),
        "integration_case_set_digest": content_digest(cases),
        "pack_digest": cases.benchmark_pack_digest,
        "prepared_root": str(OUT.relative_to(WORK.parents[1])),
        "definition_files": {path.name: file_digest(path) for path in OUT.glob("*.json")},
        "protected_reference_source_sha256": file_digest(PROTECTED_RESULT),
        "prospective_grader_codes": codes,
        "runtime_verified": False,
        "formal_cases_adopted": 0,
        "models": 0,
    }
    put(HERE / "economic-ordinary-recipe-preparation.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    prepare()

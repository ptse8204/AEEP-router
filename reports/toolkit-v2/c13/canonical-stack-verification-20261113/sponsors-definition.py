"""Build two inert, finite stack definitions from the retained Sponsors evidence."""

import json
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import file_digest
from aeep.assessment.models import AssessmentEnvironment, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import IntegrationDefinition
from aeep_toolkit.stack_verification import VerificationDefinitions

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
COMPONENT = "github-sponsors"
RUNTIME = "/Applications/Docker.app/Contents/Resources/bin/docker"
IMAGE = "sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04"
RETAINED = C13 / "workflow-sponsors-20261104"
REVIEW = C13 / "skillsbench-software-substitute-20261109/managed-preparation/managed-engineering/operation-review.json"


def load(path):
    return json.loads(path.read_bytes())


def build():
    source = verification_source_digest(ROOT)
    public = {
        "no-observations.json": ROOT / "reports/toolkit-v2/c12/developer-source/no-observations.json",
        "sponsors-review.json": RETAINED / "sponsors-review.json",
        "FUNDING.yml": RETAINED / "FUNDING.yml",
    }
    payload = {name: path.read_bytes().hex() for name, path in public.items()}
    expected = {
        "source_attribution": {"funding_drift_rejected": True,
                              "funding_source_revision": load(public["sponsors-review.json"])["source"]["revision"]},
        "authorized_link": {"explicit_source_disclosure_required": True,
                            "support_url": load(RETAINED / "preview.json")["document"]["developer"]["assertion"]["support_url"]},
    }
    program = HERE / "sponsors-check.py"
    scope = load(REVIEW)
    with ReceiptStore(scope["database"], read_only=True) as store:
        repository = AssessmentRepository(store)
        plan = repository.get("plan", load(REVIEW.with_name("dispatch-ready.json"))["plan_id"])
        grant = repository.current_grant(plan["authorization_id"])
        assert plan["subject_digest"] in grant.subject_digests and plan["recipe_digest"] in grant.recipe_digests
    env = AssessmentEnvironment(
        environment_id="local-offline-sponsors-verification",
        kind="container", identity={"purpose": "canonical-functional-probe"},
        container_image=IMAGE, container_runtime=RUNTIME,
        container_socket=str(Path.home() / ".docker/run/docker.sock"),
    )
    checks = {}
    for name, facts in expected.items():
        checks[name] = BoundaryProbeDefinition(
            name=f"{COMPONENT}.{name}",
            executor=ExecutorSpec(
                id="toolkit.sponsors-check", capability="toolkit.sponsors-check@1", kind="command",
                description="Check the actual source-attribution CLI on an exact public funding declaration",
                config={"argv": ["/usr/local/bin/python", "-B", "-c", program.read_text(),
                                 json.dumps([name, source, source, payload], separators=(",", ":")),
                                 str(ROOT / "src")],
                        "argv_literal": True, "timeout_seconds": 20, "output": {"type": "json"}},
            ),
            expected={"component": COMPONENT, "check": name, "source_revision": source,
                      "implementation_source": source, "mode": "upstream_functional", **facts},
        )
    definition = IntegrationDefinition(
        component=COMPONENT, implementation_source=source, source_revision=source,
        runtime_digest=content_digest(env),
        executable_dependencies={str(p): file_digest(p) for p in [program, *public.values(), Path(RUNTIME)]},
        probe_definitions={name: content_digest(check) for name, check in checks.items()},
    )
    ref = content_digest(definition)
    requests = {
        name: RecipeMaterializationRequest(
            plan_id=f"canonical-sponsors-{ref[:16]}-{name}", subject_digest=plan["subject_digest"],
            recipe_digest=plan["recipe_digest"], mapping_digest=check, environment_digest=content_digest(env),
            authorization_id=plan["authorization_id"], definition_digests=[ref, check], seed=0,
        ) for name, check in definition.probe_definitions.items()
    }
    return VerificationDefinitions(integration=definition, checks=checks, requests=requests, environment=env)


if __name__ == "__main__":
    print(build().model_dump_json(indent=2))

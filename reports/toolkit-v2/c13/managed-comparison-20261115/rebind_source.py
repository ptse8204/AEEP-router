"""Bind the retained stack to a private source snapshot free of Finder metadata."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from freeze_study import DATABASE
from prepare_runtime import DESIGN, ROOT, WORK, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import StackCompletion, require_stack_complete, source_revisions
from aeep_toolkit.stack_receipts import KIND as COMPONENT_KIND
from aeep_toolkit.stack_receipts import StackReceiptEvidence, verify_receipt_evidence
from aeep_toolkit.workflow_evidence import KIND as WORKFLOW_KIND
from aeep_toolkit.workflow_evidence import WorkflowEvidence, inspect_workflow, verify_workflow

SOURCE_ROOT = WORK / "frozen-source"
STACK_REBINDING = WORK / "source-stack-rebinding.json"
ROOTS = (
    "src",
    "tests",
    "scripts",
    "integrations/aeep",
    "integrations/assessment-runtime",
    "integrations/managed-worker",
)
BASIS = (
    "Dispatch reuses the verified product bytes at 70943060 and the same local dev "
    "configuration and CI fixture. The copied execution source excludes Finder metadata "
    "and ignored Python caches. Original runtime proofs, observations and historical sources remain bound."
)


def prepare_source():
    assert not SOURCE_ROOT.exists()
    command = ["git", "diff", "70943060", "--quiet", "--", *ROOTS]
    subprocess.run(command, cwd=ROOT, check=True)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *ROOTS],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert untracked == ["tests/test_ci_checkout.py"]
    SOURCE_ROOT.mkdir(mode=0o700)
    shutil.copy2(ROOT / "pyproject.toml", SOURCE_ROOT / "pyproject.toml")
    for name in ROOTS:
        shutil.copytree(
            ROOT / name,
            SOURCE_ROOT / name,
            ignore=shutil.ignore_patterns(
                ".DS_Store",
                "__pycache__",
                "*.egg-info",
            ),
        )
    return verification_source_digest(SOURCE_ROOT)


def derive(repo, source):
    design = read(DESIGN)
    old_ref = design["stack_completion_ref"]
    original = StackCompletion.model_validate(repo.get("toolkit_stack_completion", old_ref))
    assert content_digest(original) == old_ref
    assert original.implementation_source == design["implementation_source"]
    reviewed = dict(
        repo.store._connection.execute("SELECT digest, revoked FROM assessment_reviews")
    )
    assert all(reviewed.get(ref) == 0 for ref in [old_ref, *original.components.values()])
    records = {}
    for component, ref in original.components.items():
        if component.startswith("workflow-"):
            kind = WORKFLOW_KIND
            old = WorkflowEvidence.model_validate(repo.get(kind, ref))
            request = old.request.model_copy(
                update={
                    "compatibility_basis": old.request.compatibility_basis + " " + BASIS,
                }
            )
            new = inspect_workflow(repo, request, source)
            assert old.original_source == new.original_source
            assert {k: v for k, v in old.observations.items() if k != "prepared_workflow_ref"} == {
                k: v for k, v in new.observations.items() if k != "prepared_workflow_ref"
            }
            verify_workflow(repo, new, component=component, source=source)
        else:
            kind = COMPONENT_KIND
            old = StackReceiptEvidence.model_validate(repo.get(kind, ref))
            new = old.model_copy(
                update={
                    "implementation_source": source,
                    "source_revision": source_revisions(source)[component],
                    "compatibility_basis": old.compatibility_basis + " " + BASIS,
                }
            )
            assert verify_receipt_evidence(repo, new, component=component, source=source) == (
                verify_receipt_evidence(
                    repo, old, component=component, source=original.implementation_source
                )
            )
        records[component] = {"kind": kind, "value": new.model_dump(mode="json")}
    completion = StackCompletion(
        schema_version=original.schema_version,
        implementation_source=source,
        components={name: content_digest(record["value"]) for name, record in records.items()},
    )
    return {
        "implementation_source": source,
        "original_source": original.implementation_source,
        "original_completion_ref": design["stack_completion_ref"],
        "stack_completion_ref": content_digest(completion),
        "completion": completion.model_dump(mode="json"),
        "records": records,
        "verified_required_checks": 37,
        "reused_observations": True,
        "waza_selected": False,
    }


def register(repo, bundle):
    source = verification_source_digest(SOURCE_ROOT)
    assert bundle == derive(repo, source)
    for record in bundle["records"].values():
        digest = content_digest(record["value"])
        model = WorkflowEvidence if record["kind"] == WORKFLOW_KIND else StackReceiptEvidence
        repo.put(record["kind"], digest, model.model_validate(record["value"]))
        repo.review(digest)
    completion = StackCompletion.model_validate(bundle["completion"])
    ref = bundle["stack_completion_ref"]
    repo.put("toolkit_stack_completion", ref, completion)
    repo.review(ref)
    require_stack_complete(repo, ref, source_digest=source)


def check_copy():
    source = verification_source_digest(SOURCE_ROOT)
    with (
        tempfile.TemporaryDirectory(prefix="stable-source-ledger-", dir=WORK) as temporary,
        ReceiptStore(DATABASE, read_only=True) as original,
        ReceiptStore(Path(temporary) / "ledger.sqlite3") as copy,
    ):
        original._connection.backup(copy._connection)
        repo = AssessmentRepository(copy)
        bundle = derive(repo, source)
        register(repo, bundle)
    write(STACK_REBINDING, bundle)
    print(source, bundle["stack_completion_ref"], bundle["verified_required_checks"])


if __name__ == "__main__":
    if not SOURCE_ROOT.is_dir():
        prepare_source()
    check_copy()

"""Generic package inspection fixtures do not establish real worker conformance."""

import copy

import pytest
from test_v08_pair_inspection import definition as original

from aeep.hosts.codex_pair_inspection import (
    ReviewedSkillProfile,
    WorkerPairInspection,
    expected_probes,
)

pytestmark = pytest.mark.assessment_contract


def reviewed_definition():
    value = original(task_profile=True).model_dump(mode="json")
    root = "/opt/dependencies/reviewed-document-bundle"
    skill, alias = root + "/SKILL.md", "/etc/codex/skills/document-bundle/SKILL.md"
    files = {
        skill: "a" * 64,
        root + "/scripts/transform.py": "e" * 64,
        root + "/references/pdf.md": "f" * 64,
    }
    value.update(
        schema_version="assessment.worker-pair-inspection.v4",
        profile="reviewed-skill:1",
        reviewed_skill=dict(
            primary_path=skill,
            alias_path=alias,
            package_root=root,
            aliases=["document-bundle"],
            files=files,
        ),
    )
    value["differential"].update(
        candidate_paths=[skill, alias, root],
        candidate_aliases=["document-bundle"],
        control_inventory={"python": "d" * 64},
        candidate_inventory={"skill:document-bundle": "a" * 64},
        treatment_inventory={"python": "d" * 64, "skill:document-bundle": "a" * 64},
    )
    value["treatment"]["config"]["managed_worker"]["reviewed_files"] = files
    value["treatment"]["config"]["invocation"].update(
        skill_name="document-bundle", skill_path=skill
    )
    return WorkerPairInspection.model_validate(value)


def test_new_package_profile_preserves_control_absence_and_exact_package_files():
    value = reviewed_definition()
    assert len(value.reviewed_skill.files) == 3
    assert value.skill_profile()[0].endswith("reviewed-document-bundle/SKILL.md")
    assert expected_probes(value, "control")["candidate_access"]["candidate_available"] is False
    assert expected_probes(value, "treatment")["candidate_access"]["candidate_available"] is True
    # Historical bytes do not acquire the new optional profile field.
    old = original(task_profile=True)
    assert "reviewed_skill" not in old.model_dump(mode="json")
    assert WorkerPairInspection.model_validate_json(old.model_dump_json()) == old


@pytest.mark.parametrize(
    "change",
    [
        "old_schema",
        "missing_profile",
        "missing_file",
        "control_copy",
        "primary_hash",
        "wrong_target",
        "wrong_alias",
    ],
)
def test_generic_profile_does_not_relabel_legacy_or_allow_partial_inventory(change):
    value = reviewed_definition().model_dump(mode="json")
    if change == "old_schema":
        value["schema_version"] = "assessment.worker-pair-inspection.v3"
    elif change == "missing_profile":
        value["reviewed_skill"] = None
    elif change == "missing_file":
        value["treatment"]["config"]["managed_worker"]["reviewed_files"].pop(
            next(p for p in value["reviewed_skill"]["files"] if p.endswith(".py"))
        )
    elif change == "control_copy":
        value["control"]["config"]["managed_worker"]["reviewed_files"] = copy.deepcopy(
            value["reviewed_skill"]["files"]
        )
    elif change == "primary_hash":
        value["reviewed_skill"]["files"][value["reviewed_skill"]["primary_path"]] = "e" * 64
    elif change == "wrong_target":
        value["treatment"]["config"]["invocation"]["skill_path"] = (
            "/opt/dependencies/other/SKILL.md"
        )
    else:
        value["differential"]["candidate_aliases"] = ["unreviewed"]
    with pytest.raises(ValueError):
        WorkerPairInspection.model_validate(value)


@pytest.mark.parametrize(
    "path",
    [
        "/worker/auth/auth.json",
        "/opt/dependencies/../secret",
        "/opt/dependencies/.codex/secret",
        "/opt/dependencies/.env",
        "/opt/dependencies/credentials.json",
    ],
)
def test_generic_profile_cannot_target_auth_or_unbounded_paths(path):
    value = reviewed_definition().reviewed_skill.model_dump(mode="json")
    value["files"][path] = "a" * 64
    with pytest.raises(ValueError):
        ReviewedSkillProfile.model_validate(value)

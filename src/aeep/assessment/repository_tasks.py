"""Repository patch grading: protected answers, fresh contained behavioral probes.

No candidate code is imported here. The existing recipe executor runs each probe
in a fresh offline container; only its observed JSON result returns for grading.
"""
from __future__ import annotations

import base64
import json
import zlib
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from ..errors import ConfigurationError
from ..models import StrictModel, TrustLevel, ValidationKind, ValidationResult
from .models import Digest, content_digest

if TYPE_CHECKING:
    from .models import RecipeDefinition


def checked_files(files: dict[str, str]) -> dict[str, str]:
    if not 1 <= len(files) <= 64 or len(json.dumps(files).encode()) > 500_000:
        raise ValueError('repository snapshot exceeds its reviewed transport bound')
    for name, value in files.items():
        path = PurePosixPath(name)
        if (not name or str(path) != name or path.is_absolute() or '\\' in name
                or any(part.startswith('.') or ':' in part for part in path.parts)
                or not name.isprintable() or len(name) > 240 or '\x00' in value):
            raise ValueError('repository files require canonical relative text paths')
    names = sorted(files)
    if any(other.startswith(name + '/') for name in names for other in names):
        raise ValueError('repository file and directory paths conflict')
    return files


class RepositoryInput(StrictModel):
    task_id: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1, max_length=4000)
    family: str = Field(min_length=1, max_length=128)
    files: dict[str, str]
    editable_paths: list[str] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def snapshot(self) -> RepositoryInput:
        checked_files(self.files)
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False)) > 100_000:
            raise ValueError('repository input exceeds the existing structural extractor bound')
        if (len(set(self.editable_paths)) != len(self.editable_paths)
                or not set(self.editable_paths) <= self.files.keys()):
            raise ValueError('editable paths must identify existing snapshot files')
        return self


class RepositoryCheck(StrictModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    probe: dict[str, Any]
    expected: Any


class RepositoryTruth(StrictModel):
    input_sha256: Digest
    checks: list[RepositoryCheck] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def unique_checks(self) -> RepositoryTruth:
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError('repository checks must have unique names')
        if len(self.model_dump_json().encode()) > 100_000:
            raise ValueError('repository oracle exceeds its transport bound')
        return self


class RepositoryPatch(StrictModel):
    base_sha256: Digest
    files: dict[str, str] = Field(max_length=32)


Probe = Callable[[dict[str, Any]], Awaitable[Any]]


async def grade_repository_output(value: dict[str, Any], truth: dict[str, Any],
                                  output: Any, probe: Probe) -> ValidationResult:
    """A probe observes code; only this protected coordinator decides correctness."""
    task = RepositoryInput.model_validate(value)
    oracle = RepositoryTruth.model_validate(truth)
    if oracle.input_sha256 != content_digest(value):
        raise ConfigurationError('repository grader input binding changed')
    for check in oracle.checks:
        validate_probe(task, check)
    failure = None
    try:
        patch = RepositoryPatch.model_validate(output)
        if patch.base_sha256 != oracle.input_sha256:
            failure = 'input_binding'
        elif not set(patch.files) <= set(task.editable_paths):
            failure = 'patch_contract'
        else:
            files = checked_files({**task.files, **patch.files})
    except ValueError:
        failure = 'patch_contract'
    if failure is None:
        for check in oracle.checks:
            # Never pass expected answers, later checks or the reference patch.
            reply = await probe({'files': files, 'probe': check.probe})
            if not isinstance(reply, dict) or set(reply) != {'status', 'result'}:
                raise ConfigurationError('repository probe protocol failed; assessment blocked')
            if reply['status'] not in ('ok', 'candidate_error'):
                raise ConfigurationError('repository probe status is unknown')
            try:
                matched = (json.dumps(reply['result'], sort_keys=True, allow_nan=False)
                           == json.dumps(check.expected, sort_keys=True, allow_nan=False))
            except (ValueError, TypeError) as exc:
                raise ConfigurationError('repository probe returned invalid JSON') from exc
            if reply['status'] != 'ok' or not matched:
                failure = 'behavior_mismatch'
                break
    return ValidationResult(kind=ValidationKind.CALLBACK, valid=failure is None,
        quality_score=1.0 if failure is None else 0.0, detail=failure or '', trust=TrustLevel.VERIFIED)


# This program has no answers or verdict logic. It executes only in the existing
# offline ContainerExecutor, separately for every check, never in the coordinator.
REPOSITORY_PROBE = '''import json, pathlib, runpy, sys, tempfile
request = json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix="repository-probe-") as directory:
    root = pathlib.Path(directory)
    for name, text in request["files"].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    probe = request["probe"]
    sys.path.insert(0, str(root))
    try:
        namespace = runpy.run_path(str(root / probe["module"]))
        result = namespace[probe["call"]](*probe.get("args", []), **probe.get("kwargs", {}))
        wire = json.dumps({"status": "ok", "result": result}, allow_nan=False)
    except Exception:
        wire = json.dumps({"status": "candidate_error", "result": None})
    sys.stdout.write(wire)
'''


class RepositoryCase(StrictModel):
    """Curated task and oracle; never send this whole record to a trial worker."""
    schema_version: Literal['assessment.repository-case.v1'] = 'assessment.repository-case.v1'
    input: RepositoryInput
    truth: RepositoryTruth
    reference_patch: RepositoryPatch
    fault_patches: list[RepositoryPatch] = Field(min_length=1, max_length=4)
    source_repository: str
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    source_path: str
    source_sha256: Digest
    license: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    split: Literal['development', 'qualification', 'training', 'holdout'] = 'development'
    independent_case_id: str = Field(min_length=1)
    template_family: str = Field(min_length=1)
    used_for_development: bool = True

    @model_validator(mode='after')
    def bindings(self) -> RepositoryCase:
        digest = content_digest(self.input)
        if self.truth.input_sha256 != digest or self.reference_patch.base_sha256 != digest:
            raise ValueError('repository case snapshot, oracle and reference must agree')
        if not set(self.reference_patch.files) <= set(self.input.editable_paths):
            raise ValueError('reference patch changes files outside task scope')
        checked_files({**self.input.files, **self.reference_patch.files})
        for fault in self.fault_patches:
            if (fault.base_sha256 != digest or not fault.files
                    or not set(fault.files) <= set(self.input.editable_paths)):
                raise ValueError('semantic fault patches must have valid input and editable-file bindings')
            checked_files({**self.input.files, **fault.files})
        for check in self.truth.checks:
            validate_probe(self.input, check)
        return self


def validate_probe(task: RepositoryInput, check: RepositoryCheck) -> None:
    if (set(check.probe) - {'module', 'call', 'args', 'kwargs'}
            or check.probe.get('module') not in task.files
            or not isinstance(check.probe.get('call'), str)
            or not check.probe['call'].isidentifier()
            or not isinstance(check.probe.get('args', []), list)
            or not isinstance(check.probe.get('kwargs', {}), dict)):
        raise ValueError('repository check requires a frozen module, callable and JSON arguments')
    json.dumps(check.model_dump(mode='json'), allow_nan=False)


def repository_recipe(cases: list[RepositoryCase], *, assessment: bool = False) -> RecipeDefinition:
    """Export the existing recipe contract; development examples cannot seed holdout."""
    from collections import Counter

    from ..models import ExecutorKind, ExecutorSpec
    from .models import (
        ExecutableRecipeExtension,
        RecipeDefinition,
        RecipeFeatureRule,
        RecipeLiteralFixture,
    )

    literals = [case for case in cases if case.split == 'development']
    if len(literals) < 3:
        raise ValueError('repository grader needs at least three reviewed development examples')
    identifiers = [case.input.task_id for case in cases]
    if len(set(identifiers)) != len(cases):
        raise ValueError('repository task identifiers must be unique')
    stages = {'qualification': 8, 'training': 28, 'holdout': 105}
    campaign = [case for case in cases if case.split != 'development']
    if assessment:
        if Counter(case.split for case in campaign) != Counter(stages):
            raise ValueError('assessment requires 8/28/105 curated cases, separate from development')
        if any(case.used_for_development for case in campaign if case.split == 'holdout'):
            raise ValueError('development-exposed cases cannot become independent holdouts')
        identities = [case.independent_case_id for case in cases]
        origins = [(case.source_revision, case.source_path, case.source_sha256) for case in cases]
        snapshots = [content_digest({'files': case.input.files}) for case in cases]
        if any(len(set(keys)) != len(cases) for keys in (identities, origins, snapshots)):
            raise ValueError('relabelled or repeated repository cases cannot supply independent holdouts')
    elif campaign:
        raise ValueError('development export cannot contain assessment splits')
    variations = sorted({case.input.family for case in cases})
    if assessment:
        counts = Counter(case.input.family for case in campaign if case.split == 'holdout')
        if set(counts) != set(variations) or max(counts.values()) - min(counts.values()) > 1:
            raise ValueError('repository holdout families must be balanced')
    raw = [case.model_dump(mode='json') for case in cases]
    packed = base64.b64encode(zlib.compress(json.dumps(raw).encode())).decode()
    if len(packed) > 100_000:
        raise ValueError('curated repository programs exceed the portable argv bound')
    common = ('import base64, json, sys, zlib\nCASES = json.loads(zlib.decompress(base64.b64decode('
        + repr(packed) + ')))\nrequest=json.load(sys.stdin)\n')
    generator = common + ('raise ValueError("development cases are not campaign holdouts")\n' if not assessment else
        'assert request["stages"] == [{"split": s, "count": n} for s,n in '
        + repr(list(stages.items())) + ']\n'
        + 'assert request["variations"] == ' + repr(variations) + '\n'
        + 'print(json.dumps({"cases": [{"input": c["input"], "output": c["truth"], '
        + '"variation": c["input"]["family"], "template_family": c["template_family"]} '
        + 'for s in ' + repr(list(stages)) + ' for c in CASES if c["split"] == s]}))\n')
    reference = common + '''outputs=[]
for value in request["inputs"]:
    matches=[c for c in CASES if c["input"] == value]
    assert len(matches) == 1
    outputs.append(matches[0]["reference_patch"])
print(json.dumps({"outputs": outputs}))
'''

    def executor(name: str, source: str) -> ExecutorSpec:
        return ExecutorSpec(id='repository.patch.' + name, capability='assessment.repository_patch@1',
            kind=ExecutorKind.COMMAND, description='Reviewed repository task ' + name,
            config={'argv': ['python3', '-I', '-c', source], 'argv_literal': True,
                'stdin_json': True, 'timeout_seconds': 30, 'max_output_bytes': 1_000_000,
                'output': {'type': 'json'}})

    fixtures = [RecipeLiteralFixture(input=case.input.model_dump(mode='json'),
        output=case.truth.model_dump(mode='json'), grader_output=case.reference_patch.model_dump(mode='json'))
        for case in literals]
    fault_outputs = [fault.model_dump(mode='json') for case in literals for fault in case.fault_patches]
    if len(fault_outputs) > 99:
        raise ValueError('repository grader supports at most 99 reviewed semantic faults')
    return RecipeDefinition(schema_version='assessment.recipe.v2',
        recipe_id='repository-patch-v1-' + content_digest({'cases': raw})[:16],
        capability='assessment.repository_patch@1', description='Curated bounded repository behavior repairs; no arbitrary repository correctness claim.',
        input_schema=RepositoryInput.model_json_schema(), output_schema=RepositoryPatch.model_json_schema(),
        generator='contained_json:1', grader='contained_json:1', extractor='structural_json:1',
        generator_config={'purpose': 'assessment' if assessment else 'development',
            'case_set_sha256': content_digest({'cases': raw}), 'provenance': [
                {key: value for key, value in case.items() if key not in ('input', 'truth', 'reference_patch', 'fault_patches')}
                for case in raw], 'maximum_behavior_probes_per_output': 32,
            'independence': 'Curator assertions require source/rights review; distinct hashes alone do not establish independence.'},
        variations=variations, exclusions=['arbitrary builds or dependency installation',
            'new/deleted/binary files or symlinks', 'general repository preservation',
            'development cases as independent holdout evidence', 'in-process candidate execution'],
        extension=ExecutableRecipeExtension(schema_version='assessment.recipe-extension.v4',
            generator=executor('generate', generator), reference=executor('reference', reference),
            grader=executor('observe', REPOSITORY_PROBE), truth_schema=RepositoryTruth.model_json_schema(),
            independent_fixtures=fixtures[:2], transformed_fixtures=fixtures[2:],
            fault_outputs=[{'base_sha256': '0' * 64, 'files': {}}, *fault_outputs],
            failure_codes=['input_binding', 'patch_contract', 'behavior_mismatch'],
            feature_rules={'family': RecipeFeatureRule(path='/family', operation='enum', values=[*variations])},
            variation_features={family: {'family': family} for family in variations},
            template_families=sorted({case.template_family for case in cases})))

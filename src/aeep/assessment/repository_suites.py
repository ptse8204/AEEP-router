"""Curated repository suites on the existing assessment and artifact transports.

Assets remain in the coordinator. Only the current public archive reaches an
agent; candidate patches execute with protected tests in fresh grader containers.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import re
import sysconfig
import tarfile
import zlib
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import ConfigDict, Field, TypeAdapter, model_validator

from ..artifact_store import _read_stable_file
from ..errors import ConfigurationError
from ..models import (
    ExecutorKind,
    ExecutorSpec,
    StrictModel,
    TrustLevel,
    ValidationKind,
    ValidationResult,
)
from .identity import protected_directory
from .models import Digest, RecipeDefinition, content_digest
from .repository_tasks import Probe, RepositoryPatch, checked_files

MAX_ARCHIVE = 650_000
MAX_EXPANDED = 4_000_000
MAX_PAYLOAD = 1_800_000
FAILURES = ['input_binding', 'patch_contract', 'test_failure', 'missing_test']


class SuiteAsset(StrictModel):
    path: str
    sha256: Digest
    size_bytes: int = Field(gt=0, le=MAX_ARCHIVE)

    @model_validator(mode='after')
    def safe_path(self) -> SuiteAsset:
        path = Path(self.path)
        if (not path.is_absolute() or path.absolute() != path.resolve()
                or protected_directory(path) or path.name in {'auth.json', '.env', 'credentials.json'}):
            raise ValueError('suite assets require explicit canonical non-secret paths')
        return self

    def read(self) -> bytes:
        data = _read_stable_file(Path(self.path), self.size_bytes)
        if len(data) != self.size_bytes or hashlib.sha256(data).hexdigest() != self.sha256:
            raise ConfigurationError('repository suite asset changed; renewed review required')
        return data


def archive_files(data: bytes) -> dict[str, bytes]:
    """Bound decompression before tar parsing; accept regular canonical files only."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            raw = compressed.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError('archive expanded size')
        result: dict[str, bytes] = {}
        total = 0
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if (not member.isfile() or not name.parts or name.is_absolute() or '..' in name.parts
                        or str(name) != member.name or '\\' in member.name or not member.name.isprintable()
                        or len(member.name) > 240 or member.name in result
                        or any(part in {'.git', '.codex', '.agents'} for part in name.parts)
                        or name.name in {'AGENTS.md', 'auth.json', '.env', 'credentials.json'}):
                    raise ValueError('archive member')
                total += member.size
                if total > MAX_EXPANDED or len(result) >= 1000:
                    raise ValueError('archive bound')
                stream = archive.extractfile(member)
                assert stream is not None
                result[member.name] = stream.read()
        names = sorted(result)
        if not result or any(other.startswith(name + '/') for name in names for other in names):
            raise ValueError('archive file/directory conflict')
        return result
    except (OSError, EOFError, tarfile.TarError, ValueError) as exc:
        raise ConfigurationError('repository suite archive is invalid or exceeds its bound') from exc


def pack_files(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o444
            archive.addfile(member, io.BytesIO(data))
    data = gzip.compress(stream.getvalue(), mtime=0)
    if len(data) > MAX_ARCHIVE:
        raise ConfigurationError('patched repository archive exceeds transport bound')
    archive_files(data)
    return data


class SuiteInput(StrictModel):
    task_id: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1, max_length=4000)
    family: str = Field(min_length=1, max_length=128)
    source_sha256: Digest
    editable_paths: list[str] = Field(min_length=1, max_length=256)

    @model_validator(mode='after')
    def edits(self) -> SuiteInput:
        if len(set(self.editable_paths)) != len(self.editable_paths):
            raise ValueError('duplicate editable path')
        for name in self.editable_paths:
            checked_files({name: ''})
            if (not name.endswith('.py') or PurePosixPath(name).name == 'conftest.py'
                    or any(part in {'test', 'tests', 'testing'} for part in PurePosixPath(name).parts)):
                raise ValueError('suite edits cannot replace tests or configuration')
        return self


class SuiteTruth(StrictModel):
    input_sha256: Digest
    source: SuiteAsset
    tests: SuiteAsset
    wheels: list[SuiteAsset] = Field(min_length=1, max_length=32)
    python: str = Field(pattern=r'^3\.(?:1[1-9]|[2-9][0-9])$')
    pytest: str = Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')
    test_paths: list[str] = Field(min_length=1, max_length=64)
    fail_to_pass: list[str] = Field(max_length=5000)
    pass_to_pass: list[str] = Field(min_length=1, max_length=5000)

    @model_validator(mode='after')
    def oracle(self) -> SuiteTruth:
        names = self.fail_to_pass + self.pass_to_pass
        if (len(set(names)) != len(names) or len(json.dumps(names)) > 300_000
                or any(not name or any(char.isspace() for char in name) for name in names)):
            raise ValueError('suite oracle needs distinct bounded upstream test identities')
        if len(set(self.test_paths)) != len(self.test_paths):
            raise ValueError('duplicate test module')
        for path in self.test_paths:
            checked_files({path: ''})
            if not path.endswith('.py') or not path.startswith('tests/'):
                raise ValueError('suite test modules must be reviewed Python tests')
        if any(name.split('::')[0] not in self.test_paths or '::' not in name for name in names):
            raise ValueError('oracle identity lies outside selected test modules')
        filenames = [Path(asset.path).name for asset in self.wheels]
        if len(set(filenames)) != len(filenames) or any(not name.endswith('-none-any.whl') for name in filenames):
            raise ValueError('suite runtime requires distinct reviewed pure-Python wheels')
        return self


class SuiteTruthV2(SuiteTruth):
    """Operator-reviewed plugins; loading stays explicit with autoload disabled."""

    pytest_plugins: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def plugins(self) -> SuiteTruthV2:
        if (len(set(self.pytest_plugins)) != len(self.pytest_plugins)
                or any(len(name) > 128 or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', name, flags=re.ASCII)
                       for name in self.pytest_plugins)):
            raise ValueError('pytest plugins must be distinct bounded module names')
        return self


class SuiteTruthV3(SuiteTruthV2):
    """Bounded compressed patch transport; source and test limits stay unchanged."""

    patch_encoding: Literal['gzip-json']
    pytest_plugins: list[str] = Field(default_factory=list, max_length=8)


class SuiteArtifact(StrictModel):
    patch_b64: str = Field(max_length=700_000)


class SuiteCompressedArtifact(StrictModel):
    patch_gzip_b64: str = Field(max_length=700_000)


def patch_artifact(patch: RepositoryPatch) -> dict[str, str]:
    return {'patch_b64': base64.b64encode(patch.model_dump_json().encode()).decode()}


def compressed_patch_artifact(patch: RepositoryPatch) -> dict[str, str]:
    data = gzip.compress(patch.model_dump_json().encode(), mtime=0)
    return {'patch_gzip_b64': base64.b64encode(data).decode()}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate JSON key')
        result[name] = value
    return result


def decode_patch(value: Any) -> RepositoryPatch:
    artifact = SuiteArtifact.model_validate(value)
    raw = base64.b64decode(artifact.patch_b64, validate=True)
    if len(raw) > 500_000:
        raise ValueError('patch byte bound')
    patch = RepositoryPatch.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
    if patch.files:
        checked_files(patch.files)
    return patch


def _decode_suite_patch(oracle: SuiteTruth, value: Any) -> RepositoryPatch:
    if not isinstance(oracle, SuiteTruthV3):
        return decode_patch(value)
    artifact = SuiteCompressedArtifact.model_validate(value)
    data = base64.b64decode(artifact.patch_gzip_b64, validate=True)
    if len(data) > 500_000:
        raise ValueError('compressed patch byte bound')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(MAX_EXPANDED + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError('compressed patch stream') from exc
    if len(raw) > MAX_EXPANDED:
        raise ValueError('expanded patch byte bound')
    patch = RepositoryPatch.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
    if patch.files:
        checked_files(patch.files, max_bytes=MAX_EXPANDED)
    return patch


def _suite_version_schema(schema: dict[str, Any]) -> None:
    # Reuse Pydantic's references so definition renaming remains valid.
    compact_truth, plugin_truth, legacy_truth = schema['properties']['truth']['anyOf']
    schema['allOf'] = [
        {'if': {'properties': {'schema_version': {'const': 'assessment.repository-suite-case.v1'}}},
         'then': {'properties': {'truth': legacy_truth}}},
        {'if': {'properties': {'schema_version': {'const': 'assessment.repository-suite-case.v2'}}, 'required': ['schema_version']},
         'then': {'properties': {'truth': plugin_truth}}},
        {'if': {'properties': {'schema_version': {'const': 'assessment.repository-suite-case.v3'}}, 'required': ['schema_version']},
         'then': {'properties': {'truth': compact_truth}}},
    ]


class RepositorySuiteCase(StrictModel):
    model_config = ConfigDict(json_schema_extra=_suite_version_schema)
    schema_version: Literal['assessment.repository-suite-case.v1', 'assessment.repository-suite-case.v2', 'assessment.repository-suite-case.v3'] = 'assessment.repository-suite-case.v1'
    input: SuiteInput
    truth: SuiteTruthV3 | SuiteTruthV2 | SuiteTruth
    reference: SuiteAsset
    fault_outputs: list[dict[str, Any]] = Field(min_length=1, max_length=4)
    source_repository: str
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    independent_case_id: str = Field(min_length=1)
    license: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    origin_kind: Literal['upstream_issue', 'authored_control', 'synthetic_fixture'] = 'synthetic_fixture'
    split: Literal['development', 'qualification', 'training', 'holdout'] = 'development'
    used_for_development: bool = True

    @model_validator(mode='after')
    def bindings(self) -> RepositorySuiteCase:
        version = 'v3' if isinstance(self.truth, SuiteTruthV3) else 'v2' if isinstance(self.truth, SuiteTruthV2) else 'v1'
        if self.schema_version != 'assessment.repository-suite-case.' + version:
            raise ValueError('explicit pytest plugins require repository suite case v2; compact patches require v3')
        if (self.truth.input_sha256 != content_digest(self.input)
                or self.truth.source.sha256 != self.input.source_sha256
                or Path(self.truth.source.path).name != self.input.source_sha256 + '.tar.gz'):
            raise ValueError('suite task/source/oracle binding mismatch')
        for output in self.fault_outputs:
            patch = _decode_suite_patch(self.truth, output)
            if (patch.base_sha256 != self.truth.input_sha256 or not patch.files
                    or not set(patch.files) <= set(self.input.editable_paths)):
                raise ValueError('suite faults require correctly bound, scoped nonempty patches')
        return self


def public_archive(arguments: dict[str, Any], roots: list[str]) -> dict[str, Any]:
    """Existing declarative adapter projects one hash-named public asset only."""
    task = SuiteInput.model_validate(arguments)
    if len(roots) != 1:
        raise ConfigurationError('repository archive mapping requires one reviewed public asset root')
    root = Path(roots[0])
    if root.is_symlink() or root.resolve() != root or protected_directory(root):
        raise ConfigurationError('repository archive root is invalid')
    data = _read_stable_file(root / (task.source_sha256 + '.tar.gz'), MAX_ARCHIVE)
    if hashlib.sha256(data).hexdigest() != task.source_sha256:
        raise ConfigurationError('public repository source changed')
    archive_files(data)
    return {**arguments, 'base_sha256': content_digest(arguments), 'source_b64': base64.b64encode(data).decode()}


async def grade_suite_output(value: dict[str, Any], truth: dict[str, Any], output: Any,
                             probe: Probe) -> ValidationResult:
    task = SuiteInput.model_validate(value)
    oracle = (SuiteTruthV3 if 'patch_encoding' in truth else SuiteTruthV2 if 'pytest_plugins' in truth else SuiteTruth).model_validate(truth)
    if oracle.input_sha256 != content_digest(value) or oracle.source.sha256 != task.source_sha256:
        raise ConfigurationError('repository suite input binding changed')
    failure = None
    try:
        patch = _decode_suite_patch(oracle, output)
        if patch.base_sha256 != oracle.input_sha256:
            failure = 'input_binding'
        elif not set(patch.files) <= set(task.editable_paths):
            failure = 'patch_contract'
    except ValueError:
        failure = 'patch_contract'
    if failure is None:
        files = archive_files(oracle.source.read())
        if not set(task.editable_paths) <= files.keys():
            raise ConfigurationError('editable source absent from reviewed archive')
        tests = archive_files(oracle.tests.read())
        if (any(not name.startswith('tests/') for name in tests)
                or set(tests) & set(task.editable_paths) or not set(oracle.test_paths) <= files.keys() | tests.keys()):
            raise ConfigurationError('protected test overlay conflicts with source scope')
        files.update({name: text.encode('utf-8') for name, text in patch.files.items()})
        files.update(tests)
        archive = pack_files(files)
        payload = {'archive': base64.b64encode(archive).decode(), 'archive_sha256': hashlib.sha256(archive).hexdigest(),
            'python': oracle.python, 'pytest': oracle.pytest, 'test_paths': oracle.test_paths,
            'wheels': [{'filename': Path(asset.path).name, 'sha256': asset.sha256,
                        'data': base64.b64encode(asset.read()).decode()} for asset in oracle.wheels]}
        if isinstance(oracle, SuiteTruthV2):
            payload['pytest_plugins'] = oracle.pytest_plugins
            modules = [PurePosixPath(name).parts[1:] if name.startswith('src/') else PurePosixPath(name).parts
                       for name in task.editable_paths]
            payload['source_modules'] = sorted({parts[0].removesuffix('.py') for parts in modules
                                                if parts[0].removesuffix('.py').isidentifier()})
        if len(json.dumps(payload).encode()) > MAX_PAYLOAD - 30_000:
            raise ConfigurationError('repository test payload exceeds reviewed transport bound')
        reply = await probe(payload)
        if (not isinstance(reply, dict) or set(reply) != {'exit_code', 'statuses', 'archive_sha256', 'python', 'pytest'}
                or reply['archive_sha256'] != payload['archive_sha256'] or reply['python'] != oracle.python
                or reply['pytest'] != oracle.pytest or type(reply['exit_code']) is not int
                or reply['exit_code'] not in {0, 1, 2, 3, 4, 5} or not isinstance(reply['statuses'], dict)
                or len(reply['statuses']) > 10000 or any(not isinstance(name, str) or not isinstance(status, str) or status not in
                    {'PASSED', 'FAILED', 'ERROR', 'SKIPPED', 'XFAIL'} for name, status in reply['statuses'].items())):
            raise ConfigurationError('repository suite probe protocol failed')
        required = oracle.fail_to_pass + oracle.pass_to_pass
        if any(name not in reply['statuses'] for name in required):
            failure = 'missing_test'
        elif reply['exit_code'] != 0 or any(reply['statuses'][name] != 'PASSED' for name in required):
            failure = 'test_failure'
    return ValidationResult(kind=ValidationKind.CALLBACK, valid=failure is None,
        quality_score=1.0 if failure is None else 0.0, detail=failure or '', trust=TrustLevel.VERIFIED)


def curated_cases(recipe: RecipeDefinition, *, assessment: bool = False) -> list[RepositorySuiteCase]:
    cases = [RepositorySuiteCase.model_validate(value) for value in recipe.generator_config['cases']]
    if not cases or len(cases) > 241:
        raise ConfigurationError('repository suite case count is invalid')
    ids = [case.independent_case_id for case in cases]
    origins = [(case.source_repository.casefold(), case.source_revision) for case in cases]
    inputs = [content_digest(case.input) for case in cases]
    snapshots = [case.input.source_sha256 for case in cases]
    if any(len(set(items)) != len(cases) for items in (ids, origins, inputs, snapshots)):
        raise ConfigurationError('repository suite has repeated origins or inputs')
    campaign = [case for case in cases if case.split != 'development']
    if assessment and (Counter(case.split for case in campaign) != Counter(qualification=8, training=28, holdout=105)
            or any(case.used_for_development for case in campaign)):
        raise ConfigurationError('repository suite needs unexposed source-disjoint 8/28/105 cases')
    if not assessment and campaign:
        raise ConfigurationError('development recipe cannot contain campaign cases')
    return cases


def curated_payload(recipe: RecipeDefinition) -> dict[str, Any]:
    cases = curated_cases(recipe, assessment=True)
    return {'cases': [{'input': case.input.model_dump(mode='json'), 'output': case.truth.model_dump(mode='json'),
        'variation': case.input.family, 'template_family': case.source_repository.casefold()}
        for split in ('qualification', 'training', 'holdout') for case in cases if case.split == split]}


def reference_outputs(recipe: RecipeDefinition, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_input = {content_digest(case.input): case for case in curated_cases(recipe, assessment=bool(
        any(value['split'] != 'development' for value in recipe.generator_config['cases'])))}
    outputs = []
    for value in inputs:
        case = by_input.get(content_digest(value))
        if case is None:
            raise ConfigurationError('repository reference input absent from reviewed cohort')
        output = json.loads(case.reference.read(), object_pairs_hook=_unique_object)
        patch = _decode_suite_patch(case.truth, output)
        if patch.base_sha256 != content_digest(value) or not set(patch.files) <= set(case.input.editable_paths):
            raise ConfigurationError('published reference patch has changed binding or scope')
        outputs.append(output)
    return outputs


def repository_suite_recipe(cases: list[RepositorySuiteCase], *, assessment: bool = False) -> RecipeDefinition:
    from .models import ExecutableRecipeExtension, RecipeFeatureRule, RecipeLiteralFixture

    root = Path(__file__).resolve().parents[3] / 'integrations/assessment-runtime'
    if not root.is_dir():
        root = Path(sysconfig.get_path('data')) / 'share/aeep/integrations/assessment-runtime'
    parser = (root / 'swe_rebench_pytest_parser.py').read_text()
    plugins = any(isinstance(case.truth, SuiteTruthV2) for case in cases)
    program = parser + '\n' + (root / ('repository_suite_plugins_program.py' if plugins else 'repository_suite_program.py')).read_text()
    observer = ExecutorSpec(id='repository.suite.observe', capability='assessment.repository_suite@1', kind=ExecutorKind.COMMAND,
        description='Pinned upstream pytest observations; protected coordinator decides task correctness.',
        config={'argv': ['python3', '-B', '-c', program], 'argv_literal': True, 'stdin_json': True,
            'timeout_seconds': 30, 'max_stdin_bytes': MAX_PAYLOAD, 'max_output_bytes': 500_000, 'output': {'type': 'json'}})
    literals = [case for case in cases if case.split == 'development']
    if len(literals) < 3:
        raise ConfigurationError('repository suite needs three reviewed development cases')
    fixtures = [RecipeLiteralFixture(input=case.input.model_dump(mode='json'), output=case.truth.model_dump(mode='json'),
        grader_output=json.loads(case.reference.read(), object_pairs_hook=_unique_object)) for case in literals]
    variations = sorted({case.input.family for case in cases})
    # V5 retains the legacy executor slots, but materializes curated data and
    # reads pinned published reference patches instead of dispatching those slots.
    identity: dict[str, Any] = {'cases': [case.model_dump(mode='json') for case in cases]}
    if plugins:
        identity['runtime_program_sha256'] = hashlib.sha256(program.encode()).hexdigest()
    recipe = RecipeDefinition(schema_version='assessment.recipe.v2', recipe_id='repository-suite-' + content_digest(identity)[:16], capability=observer.capability,
        description='Curated source-bound Python repository suites; no official benchmark score or arbitrary preservation claim.',
        input_schema=SuiteInput.model_json_schema(), output_schema=(TypeAdapter(SuiteArtifact | SuiteCompressedArtifact).json_schema()
            if any(isinstance(case.truth, SuiteTruthV3) for case in cases) else SuiteArtifact.model_json_schema()),
        generator='curated_repository:1', grader='contained_json:1', extractor='structural_json:1',
        generator_config={'cases': [case.model_dump(mode='json') for case in cases], 'assessment': assessment,
            'declared_origin_counts': dict(Counter(case.origin_kind for case in cases)),
            'real_repository_workload': all(case.origin_kind != 'synthetic_fixture' for case in cases)},
        dependencies={'program': hashlib.sha256(program.encode()).hexdigest()}, variations=variations,
        exclusions=['unreviewed source/runtime', 'new/deleted files', 'tests/configuration edits', 'official upstream image equivalence',
                    'adversarial test/log forgery guarantees', 'population-wide workload generalization'],
        extension=ExecutableRecipeExtension(schema_version='assessment.recipe-extension.v5', generator=observer, reference=observer,
            grader=observer, truth_schema=(TypeAdapter(SuiteTruthV3 | SuiteTruthV2 | SuiteTruth).json_schema()
                if any(isinstance(case.truth, SuiteTruthV3) for case in cases) else TypeAdapter(SuiteTruthV2 | SuiteTruth).json_schema()
                if plugins else SuiteTruth.model_json_schema()),
            independent_fixtures=fixtures[:2], transformed_fixtures=fixtures[2:],
            fault_outputs=[fault for case in literals for fault in case.fault_outputs], failure_codes=FAILURES,
            feature_rules={'family': RecipeFeatureRule(path='/family', operation='enum', values=[*variations])},
            variation_features={name: {'family': name} for name in variations},
            template_families=sorted({case.source_repository.casefold() for case in cases})))
    curated_cases(recipe, assessment=assessment)
    return recipe

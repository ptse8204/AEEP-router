"""Create inert exact setup authority; no downloads, builds or model calls."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject, ConformanceProbeRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.skillsbench_recipe import skillsbench_offer_letter_recipe
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = '060fbefd55ff1c73256520a0c1e3d0de0e029755b75437cf7a93d7b68335e293'

class Definition(StrictModel):
    source_digest: str
    stage_hashes: dict[str, str]
    plan: dict
if not not (OUT / 'setup-review.json').exists():
    raise RuntimeError('preserve existing request')
if not verification_source_digest(ROOT) == SOURCE:
    raise RuntimeError('reviewed setup guard failed')
files = {name: OUT / name for name in ('prepare-setup.py', 'run-setup.py', 'image-build-plan.json', 'LICENSE', 'NOTICE', 'provenance.json', 'storage_probe.py')}
files.update({name: OUT / 'image-context' / name for name in ('Dockerfile.docx', 'requirements-docx.lock', 'docx/SKILL.md')})
hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
plan = json.loads((OUT / 'image-build-plan.json').read_text())
if not hashes['docx/SKILL.md'] == plan['candidate']['skill_sha256']:
    raise RuntimeError('reviewed setup guard failed')
if not (len(plan['packages']) == 3 and sum((p['size'] for p in plan['packages'])) == 5049844):
    raise RuntimeError('reviewed setup guard failed')
capacities = dict((line.split('=', 1) for line in subprocess.check_output(['python3', str(OUT / 'storage_probe.py')], text=True).splitlines()))
if not int(capacities['NSURLVolumeAvailableCapacityForImportantUsageKey_bytes']) >= 50 * 1024 ** 3 + 3000000000:
    raise RuntimeError('reviewed setup guard failed')
base = json.loads(subprocess.check_output(['docker', 'image', 'inspect', '--format', '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"Os":{{json .Os}},"Architecture":{{json .Architecture}}}', plan['common_base']['tag']], text=True, timeout=15))
if not (base['Id'] == plan['common_base']['image_id'] and plan['common_base']['repo_digest'] in base['RepoDigests']):
    raise RuntimeError('reviewed setup guard failed')
if not (base['Os'] == 'linux' and base['Architecture'] == 'arm64'):
    raise RuntimeError('reviewed setup guard failed')
if not not list((OUT / 'image-context/wheels').iterdir()):
    raise RuntimeError('preserve prior download files')
for tag in plan['context']['output_tags'].values():
    result = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True, text=True, timeout=10)
    if not (result.returncode != 0 and 'no such image' in result.stderr.lower()):
        raise RuntimeError('preserve existing or uncertain tag')
router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
repo = AssessmentRepository(router.store)
try:
    definitions = {}

    def put(kind, value, identity=None):
        digest = content_digest(value)
        repo.put(kind, identity or digest, value)
        definitions[digest] = value.model_dump(mode='json')
        return digest
    subject = AssessmentSubject(kind='skill', location=str(files['docx/SKILL.md']), dependency_digests={'SKILL.md': hashes['docx/SKILL.md']}, description='Pinned SkillsBench docx skill; image setup only, no assessment result.')
    sd = put('subject', subject, subject.subject_id)
    recipe = skillsbench_offer_letter_recipe()
    rd = put('recipe', recipe, recipe.recipe_id)
    environment = AssessmentEnvironment(environment_id='skillsbench-docx-image-setup-20261002', kind='trusted_local', network=True, identity={'purpose': 'Pinned public wheel downloads and offline local Docker builds only'})
    ed = put('environment', environment)
    definition = Definition(source_digest=SOURCE, stage_hashes=hashes, plan=plan)
    md = put('docx_setup_definition', definition)
    dependencies = {**runtime_dependencies(), **{str(path): hashes[name] for name, path in files.items()}}
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = put('probe_runtime', runtime)
    old = repo.get('worker_pair_definition', 'a62371cc67388021616af291ec55e8c4c6e4952ec5003d558e84c0f1fe04b729')
    worker = binding_from_config(ExecutorSpec.model_validate(old['control']).managed_host_config().managed_worker)
    if not (worker and worker.image == base['Id']):
        raise RuntimeError('reviewed setup guard failed')
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2', operation='worker_inspection', subject_digest=sd, recipe_digest=rd, mapping_digest=md, environment_digest=ed, authorization_id='onboarding', definition_digests=[sd, rd, md, ed, runtime_digest], worker_digest=worker.digest(), executable_dependencies=dependencies)
    put('conformance_request', request, request.plan_id)
    original = AssessmentAuthorization.model_validate(repo.get('authorization', 'onboarding'))
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=content_digest(original), subject_digests=[sd], recipe_digests=[rd], environment_digests=[ed], reviewed_digests=list(definitions))
    review = {'authority': 'September25/27 finite definition/setup delegation; user resumed after macOS capacity correction', 'purpose': 'Image setup only; request cannot establish worker conformance or admission', 'source_digest': SOURCE, 'request': request.model_dump(mode='json'), 'request_digest': content_digest(request), 'definitions': definitions, 'amendment': amendment.model_dump(mode='json'), 'stage_hashes': hashes, 'base_image': {'image_id': base['Id'], 'repo_digests': base['RepoDigests']}, 'output_tags': plan['context']['output_tags'], 'resource_and_grant_bounds': plan['resource_and_grant_bounds'], 'preflight': {'host_free_bytes': shutil.disk_usage(ROOT).free, 'capacities': capacities, 'docker_system_df': subprocess.check_output(['docker', 'system', 'df'], text=True, timeout=15)}, 'approval_committed': False, 'no_model_or_authentication': True}
    (OUT / 'setup-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'request_id': request.plan_id, 'review_sha256': hashlib.sha256((OUT / 'setup-review.json').read_bytes()).hexdigest()}))
finally:
    router.store.close()

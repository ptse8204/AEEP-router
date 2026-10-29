"""Bind one concrete model/disclosure review; start no workers or services."""
import ast
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from aeep.assessment.budget import campaign_allowances
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import ActionRequest, ValidationSpec
from aeep.router import Router
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
GRADER = 'sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'operation-review.json').exists()
    proposal = json.loads((HERE / 'collector-definitions.json').read_text())
    source = verification_source_digest(ROOT)
    assert source == proposal['source_digest']
    stability = HERE.parent / 'repository-shared-native-20261028/validation/source-stability.json'
    validation = json.loads(stability.read_text())
    assert validation['source_digest'] == source and validation['all_passed'] and validation['source_unchanged']
    cohort = json.loads((HERE / 'cohort.json').read_text())
    pair = WorkerPairInspection.model_validate(proposal['definitions'][proposal['pair_definition_digest']])
    recipe = RecipeDefinition.model_validate(json.loads((HERE / 'recipe.json').read_text()))
    assert content_digest(recipe) == proposal['requests'][0]['recipe_digest']
    previous = json.loads((HERE.parent.parent / 'c07/capture-explicit-profile-20261021/positive-operation-review.json').read_text())
    proxy = {key: previous[key] for key in ('proxy_name', 'proxy_id', 'proxy_image', 'proxy_memory_bytes', 'network_id', 'proxy_inspect_format')}
    observed = json.loads(subprocess.check_output([*DOCKER, 'inspect', '--format', proxy['proxy_inspect_format'], proxy['proxy_name']], timeout=20))
    assert observed['Id'] == proxy['proxy_id'] and observed['Image'] == proxy['proxy_image'] and not observed['Running']
    assert observed['Memory'] == observed['MemorySwap'] == proxy['proxy_memory_bytes']
    assert proxy['network_id'] in [value['NetworkID'] for value in observed['Networks'].values()]
    images = {role: getattr(pair, role).config['managed_worker']['image'] for role in ('control', 'treatment')}
    images['grader'] = GRADER
    for image in images.values():
        assert subprocess.check_output([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', image], timeout=20).decode().strip() == image
    free = shutil.disk_usage(ROOT).free
    assert free > 51 * 1024**3
    for name in ('task-delivery-check.json', 'grade-binding-check.json', 'evidence-gate-check.json', 'analysis-check.json', 'controller-check.json'):
        assert json.loads((HERE / name).read_text())['passed']
    assets = dict(cohort['assets'])
    files = [*HERE.glob('*.py'), HERE / 'PLAN.md', HERE / 'cohort.json', HERE / 'cases.json', HERE / 'recipe.json', HERE / 'collector-definitions.json',
             *(HERE / name for name in ('task-delivery-check.json', 'grade-binding-check.json', 'evidence-gate-check.json', 'analysis-check.json', 'controller-check.json')), stability,
             HERE.parent / 'repository-model-fault-correction-20261023/run-corrected.py']
    from aeep.assessment.identity import runtime_dependencies
    assets.update(runtime_dependencies())
    for path in files:
        if path.suffix == '.py':
            ast.parse(path.read_text())
        assets[str(path.resolve())] = sha(path)
    assert all(sha(Path(path)) == digest for path, digest in assets.items())
    collector = {**proxy, 'source_digest': source, 'definitions_sha256': sha(HERE / 'collector-definitions.json'),
        'runner_sha256': sha(HERE / 'run-collector.py'), 'images': {role: images[role] for role in ('control', 'treatment')},
        'purpose': 'Fresh exact public-root/instruction worker fingerprints:11 isolation groups per role and collector denial;zero models.',
        'maximum_model_turns': 0, 'limits': {'maximum_inspection_operations': 2, 'maximum_inspection_seconds': 480,
            'maximum_proxy_lifecycle_operations': 1, 'maximum_proxy_lifecycle_seconds': 600},
        'authority': 'Only actual approval of the parent review authorizes this component.'}
    (HERE / 'collector-operation-review.json').write_text(json.dumps(collector, indent=2) + '\n')
    assets[str((HERE / 'collector-operation-review.json').resolve())] = sha(HERE / 'collector-operation-review.json')
    # Use the existing allowance calculator on a non-executable schedule. No conformance is invented.
    cases = [BenchmarkCase(case_id='development-' + value['input']['task_id'], split='training',
        variation=value['input']['family'], template_family=value['source_repository'].casefold(),
        action=ActionRequest(capability=recipe.capability, input=value['input']),
        validators=[ValidationSpec(kind='callback', config={'expected': value['truth']})])
        for value in recipe.generator_config['cases']]
    suite = BenchmarkSuite(suite_id='budget-only-repository-usefulness-20261029', domain='development', seed=71,
        repetitions=1, routes=[{'route_id': value.id, 'executor_id': value.id} for value in (pair.control, pair.treatment)],
        conditions=['fresh-worker'], warmup_cases=[], max_total_cash_usd='0', baseline_route_id=pair.control.id, paired_order=True, cases=cases)
    router = Router.from_manifest(BASE / 'aeep.json')
    try:
        counters = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    finally:
        router.store.close()
    def get_recipe(kind, digest):
        assert kind == 'recipe' and digest == content_digest(recipe)
        return recipe.model_dump(mode='json')
    repository = SimpleNamespace(get=get_recipe, operation_ledger=lambda *args: SimpleNamespace(operations=[]))
    service = SimpleNamespace(repository=repository, router=SimpleNamespace(store=SimpleNamespace(_lock=nullcontext())),
        _cost_sources=lambda *args, **kwargs: ([], []))
    schedule = SimpleNamespace(suite=suite, recipe_digest=content_digest(recipe), setup_cost_ids=[], plan_id='budget-only-no-conformance')
    budget = campaign_allowances(service, schedule, operations_per_case=2, turns_per_case=2, seconds_per_case=610,
        cash_per_case=Decimal(0), remaining={'operations': 50000-counters[0], 'model_turns': 6000-counters[1],
            'elapsed_seconds': 604800-counters[2], 'cash_usd': '0'})
    assert budget['fits_remaining'] and budget['upper_allowance']['model_turns'] == 42
    total_ops = budget['upper_allowance']['operations'] + 4
    total_seconds = budget['upper_allowance']['elapsed_seconds'] + 1080 + 18000
    (HERE / 'reservation-preview.json').write_text(json.dumps({'inert_schedule_only': True, 'actual_current_conformance_claim': False,
        'existing_engine_projection': budget, 'extra_inspection_proxy_operations': 4,
        'extra_inspection_proxy_reserved_seconds': 19080, 'total_upper_operations': total_ops,
        'total_upper_reserved_seconds': total_seconds, 'grant_counters': counters}, indent=2) + '\n')
    assets[str((HERE / 'reservation-preview.json').resolve())] = sha(HERE / 'reservation-preview.json')
    review = {**proxy, 'purpose': '21 paired real-repository development usefulness observations,then actual admission-restraint check.',
        'source_digest': source, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'assets': assets, 'images': images, 'model_worker_images': [images['control'], images['treatment']],
        'pair_definition_digest': proposal['pair_definition_digest'], 'candidate_skill_sha256': pair.candidate_skill_digest,
        'candidate': 'Ponytail4.10.0 optional;authoring skill versions are not the treatment',
        'public_tasks': [{key: case[key] for key in ('task_id', 'family', 'repository', 'revision', 'origin_kind', 'public_archive')}
                         for case in cohort['cases']],
        'maximum_model_turns': 42, 'maximum_operations': total_ops, 'maximum_reserved_seconds': total_seconds,
        'maximum_task_seconds': 300, 'maximum_task_phase_wall_seconds': 17500,
        'cash_usd': 0, 'minimum_free_bytes': 51*1024**3, 'automatic_retry': False,
        'routine_control_amendments': 'Standing first-party definition/budget delegation may correct bookkeeping or controller bindings for UNSTARTED phases,with an exact recorded amendment and the original cumulative anchor/ceilings. It may not change third-party software,source/test/reference bytes,model,destination,permissions,metrics or cohort;restart or retry any started or uncertain source/model invocation;refund charges;or enlarge this envelope. Such a routine correction does not need another human approval. Any changed untrusted software or disclosure still does.',
        'phases': ['Recheck source/assets/images,grant/expiry,public-only roots and exact finite counters. Start no model on stale authority.',
            'Fresh existing worker/collector isolation for the changed public-root/instruction profiles:11 groups per role. Reuse retained images and restore existing proxy stopped.',
            'Existing AssessmentService independent grader validation checks all21 reference outputs and frozen faults on retained35dc before any task turn. Stop on any failed validation;do not repair optional dependencies mid-run.',
            'One fresh paired-order BenchmarkRunner schedule:21 tasks/seven per family/21 repositories,two arms,one repetition. At most42 model turns. Candidate is optional. Read canonical trial/receipt/journal and verify task prompt,independent grade,token capture and cleanup after EVERY trial before the next dispatch.',
            'Retain candidate failures as results. Missing or uncertain execution/grading/capture/cleanup stops dispatch without retry or inferred zero. Preserve all charges. Restore proxy stopped;remove only newly owned transient workers/graders.',
            'Reopen canonical completion evidence;reuse existing grouped descriptive analysis. Call only the synchronous admission gate after confirming this actual report has failed formal qualification. Assert rejection and unchanged admissions/counters. No identity refresh,qualification forgery,activation or positive live selector claim.'],
        'public_data_disclosure_scope': 'Only the21 exact public repository source snapshots/task instructions listed here and already pinned public Ponytail instructions may reach the same existing Codex destination/model. No private tests,answers,other repository/user files,new destinations or credential access. Codex owns authentication.',
        'decision_enabled': 'Determine observed task success/resource differences and optional skill engagement;decide whether a larger formal usefulness campaign is justified. Verify that actual development evidence cannot be admitted.',
        'formal_exclusion_count_after_model_exposure': 24, 'provisional_cases_left_after_exposure': 41,
        'not_authorized': ['No downloads,pulls,builds,installations,new software/dependencies,credentials,paid services,new services/destinations,release,publication or image/volume/backup deletion.',
            'No formal qualification/admission/activation,8/28/105 changes,threshold relaxation,automatic retry,historical replay or backfill.',
            'No further corpus expansion,Param/Ruff work,package/docs/full-source-suite reruns or production resource-acceptance test.'],
        'limits': ['Development tasks never supply formal campaign stages. Public tasks may be contaminated. Seven cases per family do not resolve five-percentage-point effects.',
            'Loading instructions does not prove semantic contribution. Provider usage is not independently metered billing. No monetary savings claim.',
            'The reservation projection is a conservative upper bound,not expected or measured time. Actual validation often rejects malformed faults before launching a container.'],
        'approval_reason': 'New untrusted repository code/model workers and new public-source disclosure are reserved by the user continuation and CONTINUATION.md;the prior ca735 approval allowed zero models and different sources. Routine inert definition/budget preparation is delegated. No architecture choice is needed.'}
    (HERE / 'operation-review.json').write_text(json.dumps(review, indent=2) + '\n')
    audit = {'passed': True, 'review_sha256': sha(HERE / 'operation-review.json'), 'assets_verified': len(assets),
        'models_workers_services_started': False, 'source_unchanged': True, 'free_bytes': free,
        'maximum_operations': total_ops, 'maximum_reserved_seconds': total_seconds, 'maximum_model_turns': 42,
        'formal_qualification_or_new_comparison_evidence': False}
    (HERE / 'preparation-checks.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit))


if __name__ == '__main__':
    main()

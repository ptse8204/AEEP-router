"""Freeze one exact fresh-boundary and six-turn development review,without execution."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import RecipeDefinition
from aeep.assessment.repository_suites import RepositorySuiteCase
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent.parent/'c07/capture-explicit-profile-20261021'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'operation-review.json').exists()
    proposal=json.loads((HERE/'collector-definitions.json').read_text());assert verification_source_digest(ROOT)==proposal['source_digest']
    stability=HERE.parent/'repository-task-delivery-20261023/validation-final/source-stability.json';checks=json.loads(stability.read_text());assert checks['all_passed'] and checks['source_unchanged'] and checks['source_digest']==proposal['source_digest']
    previous=json.loads((PRIOR/'positive-operation-review.json').read_text());proxy={k:previous[k] for k in ('proxy_name','proxy_id','proxy_image','proxy_memory_bytes','network_id','proxy_inspect_format')}
    docker=['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock']
    observed=json.loads(subprocess.check_output([*docker,'inspect','--format',proxy['proxy_inspect_format'],proxy['proxy_name']],timeout=20))
    assert observed['Id']==proxy['proxy_id'] and observed['Image']==proxy['proxy_image'] and not observed['Running'];assert observed['Memory']==observed['MemorySwap']==proxy['proxy_memory_bytes']
    assert proxy['network_id'] in [n['NetworkID'] for n in observed['Networks'].values()]
    pair=proposal['definitions'][proposal['pair_definition_digest']];images={role:pair[role]['config']['managed_worker']['image'] for role in ('control','treatment')}
    images['grader']='sha256:324a1fee6ee58475ecfdc659c98be5b5a8480fae4389b26b13b5b0b43bc32d2b'
    for image in images.values():assert subprocess.check_output([*docker,'image','inspect','--format','{{.Id}}',image],timeout=20).decode().strip()==image
    free=shutil.disk_usage(ROOT).free;assert free>51*1024**3
    recipe=RecipeDefinition.model_validate(proposal['definitions'][proposal['requests'][0]['recipe_digest']]);cases=[RepositorySuiteCase.model_validate(c) for c in recipe.generator_config['cases']]
    assert len(cases)==3 and all(c.split=='development' and c.used_for_development for c in cases)
    assets={str(p.resolve()):sha(p) for p in [stability,HERE/'collector-definitions.json',HERE/'task-delivery-check.json',*(HERE/n for n in ('run-review.py','run-collector.py','assemble-collector-boundary.py','run-model-journey.py','review-budget.py','run-grader-probes.py','grader-probe-definitions.json','grader-probes.json','grade-binding-check.json'))]}
    assets[str((HERE.parent/'repository-model-fault-correction-20261023/run-corrected.py').resolve())]=sha(HERE.parent/'repository-model-fault-correction-20261023/run-corrected.py')
    for case in cases:
        for item in (case.truth.source,case.truth.tests,case.reference,*case.truth.wheels):item.read();assets[item.path]=item.sha256
    for path,digest in runtime_dependencies().items():assets[path]=digest
    source=proposal['source_digest'];collector={**proxy,'purpose':'Fresh exact repository-artifact optional-skill profile inspection,all11 probes per worker and actual collector denied access; no model before pass.',
        'source_digest':source,'definitions_sha256':sha(HERE/'collector-definitions.json'),'runner_sha256':sha(HERE/'run-collector.py'),'images':{r:images[r] for r in ('control','treatment')},
        'collector_sha256':sha(ROOT/'src/aeep/hosts/codex_metrics.py'),'candidate_skill_sha256':pair['candidate_skill_digest'],'maximum_model_turns':0,
        'limits':{'maximum_inspection_operations':2,'maximum_inspection_seconds':480,'maximum_proxy_lifecycle_operations':1,'maximum_proxy_lifecycle_seconds':600},
        'authority':'Only actual parent operation-review approval authorizes this component; no old conformance transfers.'}
    (HERE/'collector-operation-review.json').write_text(json.dumps(collector,indent=2)+'\n');assets[str((HERE/'collector-operation-review.json').resolve())]=sha(HERE/'collector-operation-review.json')
    for name in ('run-review.py','run-collector.py','assemble-collector-boundary.py','run-model-journey.py','review-budget.py'):ast.parse((HERE/name).read_text())
    review={**proxy,'purpose':'Complete the real repository artifact journey with a small prospective optional-skill development comparison. Reuse existing engine,worker images,collector,proxy and offline grader. No full study/qualification/admission claim.',
        'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),'assets':assets,'images':images,'pair_definition_digest':proposal['pair_definition_digest'],'candidate_skill_sha256':pair['candidate_skill_digest'],
        'public_tasks':[{'task_id':c.input.task_id,'repository':c.source_repository,'revision':c.source_revision,'public_archive':c.truth.source.model_dump(mode='json'),'input_digest':c.truth.input_sha256,'development_only':True} for c in cases],
        'maximum_model_turns':6,'maximum_operations':128,'maximum_reserved_seconds':10000,'cash_usd':0,'minimum_free_bytes':51*1024**3,'maximum_task_seconds':300,
        'maximum_grader_calls_including_validation_and_task_grading':96,'maximum_fresh_model_workers_including_inspection':24,'maximum_concurrent_model_workers':4,'automatic_retry':False,
        'phases':['Run the existing11 conformance groups in each of two fresh exact artifact-profile workers,plus actual collector-port denial. Reuse and restore the existing stopped512MiB proxy. No model turns in this phase.',
            'Only after observed current-source conformance passes,assemble exact BoundaryConformance and DifferentialConformance records through existing contracts. Bind those actual identities into the reviewed deterministic development-plan compiler.',
            'Run exactly three fresh offline grader boundary/state probes on the existing pinned image,with one new nonsecret owned canary. Five operations and at most165 reserved seconds include the three35-second wrapper margins;retain receipts and remove the unchanged canary. No image or dependency change.',
            'Compile one legacy development plan with three preexisting development cases,two exact routes and one fresh-worker repetition:at most six task turns. Candidate Ponytail4.10 remains optional. Use the pinned offline grader and original protected assertions; normal service grader validation must pass before tasks.',
            'Run once through AssessmentService and BenchmarkRunner on the existing grant. Stop on environment,authority,accounting,identity,cleanup or evidence uncertainty. Preserve charged preflight skips and all failure receipts. Do not automatically retry.',
            'Require six canonical receipts with bound canonical-trial independent callback grades,bound token capture chains,exact prechecked task-instruction hashes and confirmed worker cleanup for a completed engineering journey. Optional skill loading may be absent or unknown and is never forced. Retain canonical receipts,verification results,numeric/hash-only token and candidate-loading evidence,and explicit unknowns. Restore the proxy stopped and remove only newly owned transient workers/graders. Preserve all images,volumes and historical records.'],
        'public_data_disclosure_scope':'The actual user approval must cover sending only these three pinned public repository task snapshots/instructions and the already pinned public Ponytail instructions to the same existing Codex model destination. No private repository/user files,new destination or credential access. Codex retains authentication ownership.',
        'fresh_reservation_bound_components':{'collector_inspection_and_proxy':1080,'grader_boundary_setup_and_analysis_and_three_calls':165,'task_proxy':3000,'campaign_including_wrapper_margins':5355,'total_upper_seconds':9600,'review_upper_seconds':10000},'task_delivery_check_sha256':sha(HERE/'task-delivery-check.json'),'grade_binding_check_sha256':sha(HERE/'grade-binding-check.json'),'budget_enforcement':'Every reservation in the inspection and task phases is checked against the initial persisted grant counters and exact128-operation,6-turn,10000-second,zero-cash review ceiling. Include actual reserved balances,trial timeout+5 and grader timeout+5 wrapper margins. Other concurrent usage can cause a conservative stop; never reset/subtract counters.',
        'not_included':['No downloads,installation,image build/pull,OS package,new service/destination or credential reading/sign-in capture.','No full8/28/105 cohort,holdout generation,threshold relaxation,formal candidate qualification,powered efficacy inference,selection validation,admission,activation,release or publication.','No package/docs operation is authorized by this model-component review alone;any combined bundle binds those independent reviews separately. No historical replay. These already used development repositories remain excluded from future holdouts.'],
        'limitations':['Three task pairs cannot establish a material benefit. Outputs are descriptive development evidence; candidate loading does not establish semantic contribution.','Trust labels and missing token/use fields are preserved. No provider-internal meter,billed-cash savings or production resource acceptance is inferred.','If fresh conformance or grader validation fails,no subsequent model turn is authorized by a passing placeholder or old boundary.','The current35-case provisional pool and its original runtime/source bindings remain independent.'],
        'approval_reason':'The prior exact model reviewd775e93e ended terminal with five ungraded turns and29 operations charged. This new source fixes stopping,metadata retention,and case delivery;its worker fingerprints/inventories require fresh applicable conformance. The pasted continuation withholds untrusted execution/expanded disclosure,CONTINUATION.md requires applicable provisioning/service authority,and ACCEPTANCE.md requires explicit live-call authority. This exact finite bundle covers the new public task disclosure,worker profile and six turns. Routine definition compilation is already delegated; no architecture decision is needed.'}
    (HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
    audit={'passed':True,'source_unchanged':True,'public_development_cases':3,'planned_model_turns':6,'assets_verified':len(assets),'old_worker_images_present':True,'old_proxy_present_stopped':True,'grader_image_present':True,'free_bytes':free,'no_workers_started':True,'no_models':True,'review_sha256':sha(HERE/'operation-review.json')}
    (HERE/'preparation-checks.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':main()

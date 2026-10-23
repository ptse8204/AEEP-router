"""Freeze existing prepared component reviews, without executing any component."""
import hashlib
import json
from pathlib import Path
import sys

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (HERE/'approval-bundle.json').exists()
paths={'model':HERE,'package':ROOT/'reports/toolkit-v2/integration-completion/package-review-task-delivery-20261023','docs':ROOT/'reports/toolkit-v2/integration-completion/lychee-task-delivery-review-20261023'}
reviews={name:json.loads((directory/'operation-review.json').read_text()) for name,directory in paths.items()}
source=verification_source_digest(ROOT);assert all(r['source_digest']==source for r in reviews.values())
assert json.loads((HERE/'validation-final/source-stability.json').read_text())['all_passed']
assets=dict(reviews['model']['assets'])
for name,directory in paths.items():
    assets[str((directory/'operation-review.json').resolve())]=sha(directory/'operation-review.json')
for name in ['run-integration-bundle.py','task-delivery-check.json','grade-binding-check.json']:
    assets[str((HERE/name).resolve())]=sha(HERE/name)
for name in ['installation.json','registry.json','policy.json','review.json','capture-fixture.json','run_review.py']:
    assets[str((paths['package']/name).resolve())]=sha(paths['package']/name)
for name,digest in reviews['package']['inputs'].items():assets[str((ROOT/name).resolve())]=digest
installation=json.loads((paths['package']/'installation.json').read_text())
for wheel in installation['wheels']:assets[str(Path(installation['wheelhouse'])/wheel['filename'])]=wheel['sha256']
for name in ['run-review.py','sandbox-preflight.py','sandbox-preflight.json','sandbox-template.sb']:
    assets[str((paths['docs']/name).resolve())]=sha(paths['docs']/name)
assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
for path,digest in assets.items():assert sha(Path(path))==digest
components={name:{'directory':str(directory.resolve()),'review_sha256':sha(directory/'operation-review.json')} for name,directory in paths.items()}
components['model'].update(argv=[str(HERE/'run-review.py')],maximum_driver_seconds=5400,result_file='execution-result.json',passed_field='development_journey_completed')
components['package'].update(argv=[str(paths['package']/'run_review.py')],maximum_driver_seconds=1800,result_file='execution/summary.json',passed_field='runtime_removed')
components['docs'].update(argv=[str(paths['docs']/'run-review.py')],maximum_driver_seconds=600,result_file='execution-result.json',passed_field='passed')
review={'purpose':'One corrected task-delivery development attempt and independent installed current-wheel/offline docs checks.','source_digest':source,'assets':assets,'components':components,'model_worker_images':[reviews['model']['images'][role] for role in ['control','treatment']],
 'model_component_limits':{'maximum_turns':6,'maximum_operations':128,'maximum_reserved_seconds':10000,'maximum_grader_calls':96,'cash_usd':0},
 'installation_component_limits':{'first_party_wheels':1,'unchanged_cached_dependency_wheels':32,'offline_installed_checks':19,'downloads':0,'models':0},
 'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'network':False,'models':0},
 'changes':['Deliver task text,base hash,editable paths and artifact paths through the existing input template;verify six actual managed-executor recording checks and compare actual receipt hashes.','Stop after the first indeterminate invocation,retain safe bounded artifact/cleanup evidence and error codes,and bind independent grades to canonical trials.','Run fresh applicable worker/collector and three offline grader probes on source4cb0bf74 before normal grader validation and up to six task turns. Same images,collector,model/public tasks and destination;no build/pull/new dependency.','Install only the current first-party wheel and32 unchanged cached dependency wheels privately for19 offline checks;retain evidence and remove only unchanged owned runtime/scratch.','Run the cached pinned offline docs checker in its reviewed sandbox,then remove only its unchanged private runtime.'],
 'no_authority_for':['Downloads,new images/builds/pulls,other software,credentials,new services/destinations,cash,host activation,release/publication,old-image/volume/backup deletion or historical replay.','Formal qualification,usefulness/selection claims,admission or production resource acceptance.'],
 'failure_policy':'No automatic retries. Failed model components stop dependent phases. Independent package/docs components may proceed only after reviewed worker images have no containers and the model proxy is stopped;otherwise stop external dispatch. Preserve all charges,receipts,unknowns and resources with uncertain ownership.',
 'approval_reason':'Terminald775e93e binds previous source and task instructions and forbids retries. The new source,worker fingerprints and wheel require this exact execution approval under the pasted untrusted-software boundary and CONTINUATION.md. Routine source/definition work remains delegated;no architecture decision is needed.'}
(HERE/'approval-bundle.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'execution_started':False}))

"""Bind the exact prepared components after all current-source gates pass."""
import json,shutil
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import file_digest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
assert not (HERE/'operation-review.json').exists()
checks=json.loads((HERE/'verification-final/checks.json').read_bytes())
assert len(checks['checks'])==13 and all(c['exit_code']==0 for c in checks['checks'])
assert checks['source_before']==checks['source_after']==verification_source_digest(ROOT)
for name in ('first-party-driver.json','first-party-package-driver.json','native-boundary-preparation.json','package-preparation.json','fixture-cleanup-check.json','docs-tool-identity-check.json','cli-preview-entrypoint-check.json'):
 assert json.loads((HERE/name).read_bytes())['passed'],name
assert file_digest(HERE/'package.sb')==json.loads((HERE/'native-boundary-preparation.json').read_bytes())['profile_sha256']
package=json.loads((HERE/'package-preparation.json').read_bytes())
plan=json.loads((HERE/'package-installation.json').read_bytes())
preview=json.loads((HERE/'cli-preview.json').read_bytes())
docs=json.loads((HERE/'docs-preparation.json').read_bytes())
state=json.loads(Path(docs['runtime_record']).read_bytes())
for name,value in state['files'].items():assert file_digest(Path(state['runtime'])/name)==value,name
review={'purpose':'Connect actual Cisco scanning to the ordinary CLI and canonical records; verify the installed current wheel and current offline documentation. Engineering only; comparisons remain paused.',
 'source':checks['source_before'],'source_checks':'verification-final/checks.json',
 'cli_review_sha256':preview['review_sha256'],'candidate_sha256':preview['candidate']['candidate_sha256'],
 'scanner_image':preview['environment']['container_image'],
 'scanner':{'boundary_calls':1,'actual_scanner_calls':1,'wrapper_operations':1,'maximum_canonical_operations':3,'maximum_reserved_seconds':240,'maximum_cli_process_seconds':180,
  'runtime':'Existing exact image only; fixed offline nonroot launch through the existing container executor.',
  'candidate':'Existing public format-json payload only; bundled eval answers and credential-state files excluded.',
  'authority':'Apply only the two finite zero-model engineering grants and exact definitions in cli-authority.json after this parent approval. Existing grants/counters are untouched.',
  'scope':'Actual scan and source-bound applicability to both configurations. No SkillsBench task or agent evaluation; no full-stack pass.',
  'attempts':1},
 'package':{'installation_digest':package['installation_digest'],'installed_source':package['installed_source'],'runtime':plan['destination'],
  'wheels':33,'changed_first_party_wheels':1,'unchanged_cached_dependencies':32,'maximum_install_processes':3,'maximum_install_seconds_each':300,
  'boundary_calls':1,'installed_source_cli_calls':1,'maximum_boundary_seconds':20,'maximum_installed_check_seconds':60,
  'attempts':1,'retain_unchanged_runtime':True,'preparation_space_blocked':package['space_blocked']},
 'docs':docs,
 'maximum_model_turns':0,'cash_usd':0,'downloads':False,'image_builds':False,'image_pulls':False,'image_deletion':False,
 'services':False,'credentials':False,'new_destinations':False,'activation':False,'publication':False,'release':False,
 'minimum_host_reserve_bytes':50*1024**3,'minimum_headroom_bytes':package['reserve_bytes']+16*1024**2,
 'space_policy':'Check free host space and read-only Docker usage before execution. Refuse any effects below the50GiB reserve plus16MiB. The package additionally requires its full reviewed installation headroom; if short it stays unstarted without consuming an attempt. Scanner/docs remain independently eligible. No older fixture, runtime, image, volume, backup or unknown resource cleanup.',
 'cleanup':'Only new disposable scanner containers with verified ownership/image/immutable ID; keep all images/volumes. Keep private package runtime and cached docs tools. Preserve uncertain resources, attempts, partial costs and evidence.',
 'failure_policy':'One attempt for scanner and package. A settled component failure leaves independent package/docs work eligible; source drift, accounting or ownership uncertainty blocks the affected dispatch. No automatic model/task retry or broader source/profile repair. Docs permit two attempts total with Markdown-only fixes in the same72-input list and unchanged tools/configs/sandbox.',
 'accounting':'Scanner and wrapper use canonical existing operation ledger and journals with nested time excluded. Installer retains owned journals; package process receipts and docs wall/input logs are separate engineering costs. Final persistence and whole-system CPU/RSS remain outside complete measurement. Never infer missing usage or savings.',
 'acceptance':'Only bounded scanner CLI/current-package/docs engineering. All-integration and both workload journeys, candidate usefulness, selection usefulness, resource qualification and release remain open.',
 'prepared_free_bytes':shutil.disk_usage(ROOT).free}
bound={}
for path in HERE.iterdir():
 if path.is_file() and path.suffix in {'.py','.json','.sb'} and path.name not in {'operation-review.json','operator-approval.json','summary.json'}:
  bound[str(path.relative_to(ROOT))]=file_digest(path)
for directory in ('verification','verification-recovery','verification-final'):
 for path in (HERE/directory).iterdir():
  if path.is_file() and path.suffix in {'.json','.log'}:bound[str(path.relative_to(ROOT))]=file_digest(path)
# Bind the immutable tool-state record; actual document hashes are captured at each attempt.
bound[str(Path(docs['runtime_record']).relative_to(ROOT))]=file_digest(Path(docs['runtime_record']))
bound['Makefile']=file_digest(ROOT/'Makefile');bound['.markdownlint-cli2.jsonc']=file_digest(ROOT/'.markdownlint-cli2.jsonc')
review['bound_files']=bound
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'review_sha256':file_digest(HERE/'operation-review.json'),'bound_files':len(bound),'executed':False,'source_checks':13}))

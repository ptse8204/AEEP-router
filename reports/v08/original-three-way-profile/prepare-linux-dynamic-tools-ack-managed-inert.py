"""Build exact inert review from existing records; no store writes or worker launch."""
import copy
import hashlib
import json
import tomllib
from pathlib import Path
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = 'bcbef9aa86a9376511560bd855bd70695057cbd120d260dca633de007610633b'
assert verification_source_digest(ROOT) == SOURCE
old = json.loads((OUT / 'linux-noauth-status-review.json').read_text())
prep = json.loads((ROOT / 'reports/v08/native-dynamic-tools-ack-preparation.json').read_text())
profile = copy.deepcopy(old['definition']['profiles']['outside_mcp'])
config = profile['config']
filesystem = tomllib.loads((OUT / 'immutable-diagnostic/requirements.toml').read_text())['permissions']['aeep']['filesystem']
inline = '{' + ', '.join(json.dumps(k) + ' = ' + json.dumps(v) for k, v in filesystem.items()) + '}'
# Reuse the complete exact already accepted managed argv, with no policy overrides.
assert config['argv'] == ['/opt/codex/codex', 'app-server', '-c', 'mcp_servers.linux_boundary_diagnostic.command="/usr/local/bin/python3"', '-c', 'mcp_servers.linux_boundary_diagnostic.args=["/opt/aeep/linux-mcp-server.py"]', '-c', 'mcp_servers.linux_boundary_diagnostic.enabled=true']
worker = binding_from_config(config['managed_worker'])
assert worker and worker.credential_volume is None and worker.network_id is None and worker.model_proxy_url is None
params = {'ephemeral': True, 'cwd': '/workspace', 'model': 'gpt-6.1-sol', 'permissions': 'aeep', 'approvalPolicy': 'never', 'approvalsReviewer': 'user', 'dynamicTools': prep['declarations']}
expected_permissions = {'aeep': {'filesystem': filesystem}}
definition = {'source_digest': SOURCE, 'profiles': {'outside_mcp': profile}, 'thread_start_params': params, 'expected_permissions': expected_permissions, 'maximum_operations': 1, 'maximum_reserved_seconds': 60, 'maximum_model_turns': 0}
digest = content_digest(definition)
original = old['requests'][0]
definitions = {digest: definition}
for key in ('subject_digest', 'recipe_digest', 'environment_digest'):
    definitions[original[key]] = old['definitions'][original[key]]
driver = OUT / 'run-linux-dynamic-tools-ack-managed-inert.py'
dependencies = runtime_dependencies()
dependencies[str(driver)] = hashlib.sha256(driver.read_bytes()).hexdigest()
request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2', operation='worker_inspection', subject_digest=original['subject_digest'], recipe_digest=original['recipe_digest'], mapping_digest=digest, environment_digest=original['environment_digest'], authorization_id='onboarding', definition_digests=[digest, original['recipe_digest'], original['environment_digest']], worker_digest=worker.digest(), executable_dependencies=dependencies)
definitions[content_digest(request)] = request.model_dump(mode='json')
amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=old['amendment']['authorization_digest'], subject_digests=[original['subject_digest']], recipe_digests=[original['recipe_digest']], environment_digests=[original['environment_digest']], reviewed_digests=list(definitions))
review = {'execution_authorized': False, 'authority': 'Standing finite setup/testing delegation; exact root review pending; original onboarding grant unchanged.', 'source_digest': SOURCE, 'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(), 'validation_record': 'reports/v08/delivery-boundary-validation-' + SOURCE[:12] + '.json', 'definition': definition, 'definition_digest': digest, 'definitions': definitions, 'requests': [request.model_dump(mode='json')], 'amendment': amendment.model_dump(mode='json'), 'effective_requirements_expected': {'allowedPermissionProfiles': {'aeep': True}, 'allowedApprovalPolicies': ['never']}, 'expected_permissions': expected_permissions, 'thread_start_params': params, 'declaration_sha256': prep['declaration_sha256'], 'setup_canonical_record_digest': old['setup_canonical_record_digest'], 'protected_file_sha256': old['protected_file_sha256'], 'maximum_operations': 1, 'maximum_reserved_seconds': 60, 'maximum_model_turns': 0, 'cash_usd': 0, 'applicability': 'Exact no-auth Linux declaration ACK with original permitted fixed MCP startup; no tool calls or model turn. Prior failed ACK exact first error remains unknown; fresh changed definition/request, no image/policy changes or full conformance claim.', 'managed_requirements_file_binding': {'image': 'sha256:e7e465b7ba53cb72817860cfe53a1db5d7039bfdf0201727de892944187e107b', 'path': '/etc/codex/requirements.toml', 'sha256': '5804803cff64274400cbfb3595cd79cb316ee4181dc1055160efb66862c9621a', 'source': 'existing reviewed image observation; no /etc expansion of worker reviewed_files'}, 'extra_startup_behavior': 'Original fixed MCP may initialize/list; writes owned synthetic canary; no tools/call/nested sandbox probe; counted within60s.'}
(OUT / 'linux-dynamic-tools-ack-managed-review.json').write_text(json.dumps(review, indent=2) + '\n')
prep.update(source_digest=SOURCE, driver_sha256=review['driver_sha256'], binary=worker.binary, binary_sha256=worker.binary_sha256, argv_template=config['argv'], permission_profile_id='aeep', review='reports/v08/original-three-way-profile/linux-dynamic-tools-ack-managed-review.json', review_sha256=hashlib.sha256((OUT / 'linux-dynamic-tools-ack-managed-review.json').read_bytes()).hexdigest(), pending_bindings=['completed validation and root exact review; execution_authorized remains false'])
(ROOT / 'reports/v08/native-dynamic-tools-ack-preparation.json').write_text(json.dumps(prep, indent=2) + '\n')
print(json.dumps({'review_sha256': prep['review_sha256'], 'worker_digest': worker.digest(), 'request': request.plan_id, 'execution_authorized': False}))

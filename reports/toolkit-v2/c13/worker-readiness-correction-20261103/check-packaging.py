"""First-party filesystem/configuration checks; no Docker or model starts."""
import json
import tempfile
from pathlib import Path

import integration

from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_invocation import isolated_config, resolve_skill_name

pair, shared = integration.pair('sha256:' + 'e' * 64, verification_source_digest(integration.ROOT))
controls = []
for role in ('control', 'treatment'):
    spec = getattr(pair, role)
    config = spec.managed_host_config()
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=b'inert-first-party-construction')
    assert adapter.transport._process is None
    if adapter._worker_security:
        adapter._worker_security.cleanup()
    controls.append(role + ' constructor creates no transport process')
    target = config.invocation
    catalog = {'apps': [], 'servers': [], 'skills': [] if role == 'control' else [{
        'name': 'stack-check', 'path': target.skill_path, 'enabled': True, 'dependencies': None}]}
    selected = resolve_skill_name(catalog, target)
    values = isolated_config(catalog, selected, verified_worker_skill=role == 'treatment',
        reviewed_worker_files=config.managed_worker['reviewed_files'])
    assert values['features.shell_tool'] is values['features.unified_exec'] is True
    assert sum(item['enabled'] for item in values['skills.config']) == int(role == 'treatment')
controls.append('ordinary tool profile and exact primary skill mapping compile')
bad_target = pair.treatment.managed_host_config().invocation.model_copy(update={'skill_name': 'aeep-stack-check'})
try:
    isolated_config({'apps': [], 'servers': [], 'skills': [{
        'name': bad_target.skill_name, 'path': bad_target.skill_path, 'enabled': True}]},
        bad_target, verified_worker_skill=True, reviewed_worker_files=pair.treatment.config['managed_worker']['reviewed_files'])
except ConfigurationError:
    controls.append('existing recursive AEEP skill guard remains enforced')
else:
    raise AssertionError('recursive name accepted')
with tempfile.TemporaryDirectory(prefix='aeep-stack-packaging-fixture-') as temporary:
    root = Path(temporary)
    package = root / 'package'
    package.mkdir()
    (package / 'SKILL.md').write_bytes((integration.HERE / 'candidate/SKILL.md').read_bytes())
    alias = root / 'native-skill'
    alias.symlink_to(package, target_is_directory=True)
    assert (alias / 'SKILL.md').resolve() == (package / 'SKILL.md').resolve()
    assert (alias / 'SKILL.md').read_bytes() == (package / 'SKILL.md').read_bytes()
controls.append('native directory alias resolves to the reviewed primary bytes')
integration.write(integration.HERE / 'packaging-controls.json', {'passed': True,
    'controls': controls, 'fixture_only': True, 'actual_Codex_inventory': 'NOT_OBSERVED',
    'actual_images_built': 0, 'models': 0, 'grants_touched': 0,
    'native_alias_strategy': 'Same directory symlink as existing managed-worker Dockerfile.incremental'})
print(json.dumps({'passed': True, 'controls': len(controls), 'models': 0, 'images_built': 0}))

"""Bind the frozen four-arm campaign to its bounded one-shot execution driver."""
import asyncio
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

from aeep.assessment.models import AssessmentPlan, ReviewedMapping
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


async def main():
    assert not (OUT / 'value-execution-review.json').exists()
    proposed = json.loads((OUT / 'value-review.json').read_text())
    source = verification_source_digest(ROOT)
    assert source == proposed['source_digest']
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    try:
        plan = AssessmentPlan.model_validate(service.repository.get('plan', proposed['plan_id']))
        mapping = ReviewedMapping.model_validate(service.repository.get('mapping', plan.mapping_digest))
        for spec in mapping.subjects:
            router.register(spec)
        router.managed_hosts.configure(mapping.subjects, principal_salt=router.store.host_principal_key,
                                       manifest_directory=router.manifest_path.parent)
        service._verify_dependencies(plan)
        budget = service.budget_preview(plan.plan_id)
        allowance = budget['campaign_allowance']
        assert allowance['upper_allowance'] == proposed['budget_preview']['campaign_allowance']['upper_allowance']
        assert allowance['fits_remaining'] and not allowance['gaps']
        assert all(item['eligible'] for item in budget['adapter_eligibility'])
        assert allowance['upper_allowance']['model_turns'] == 564
        assert allowance['upper_allowance']['elapsed_seconds'] <= 200000
        stages = {stage['stage']: stage for stage in allowance['stages']}
        copies = stages['trial']['calls_upper'] + stages['router_setup']['calls_upper'] + 2
        worker = mapping.baseline.config['managed_worker']
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        review = {
            'authority': 'Standing exact finite definition delegation and explicit source/image approvals; no new cash or disclosure',
            'source_digest': source, 'plan_id': plan.plan_id, 'plan_digest': proposed['plan_digest'],
            'proposal_sha256': sha(OUT / 'value-review.json'),
            'runner_sha256': sha(OUT / 'run-value.py'),
            'pair_result_sha256': sha(OUT / 'pair-result.json'),
            'boundary_result_sha256': sha(OUT / 'boundary-result.json'),
            'proxy_name': 'aeep-reviewed-model-proxy', 'proxy_id_prefix': '5f9a44f86633',
            'proxy_image': 'sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de',
            'proxy_memory_bytes': 536870912, 'network_id': worker['network_id'],
            'minimum_free_bytes': 51 * 1024**3, 'campaign_copies_upper': copies,
            'maximum_campaign_seconds': math.ceil(allowance['upper_allowance']['elapsed_seconds']) + 1,
            'additional_operations': 3, 'additional_reserved_seconds': 150,
            'grant_counters': list(router.store._connection.execute(
                "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()),
            'host_free_bytes': shutil.disk_usage(ROOT).free,
            'docker_usage': subprocess.check_output([
                '/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock',
                'system', 'df'], text=True, timeout=30),
            'source_execution_approval_sha256': 'dbc2dda63cff7586a0a0d9a699021085e1b9b4c9f619c54a54d90da7047d6d4b',
            'image_permission_approval_sha256': '1484c3ba6b748d740c28107fe88b179b3fe4b0a0d5022991079fcd71ced3bd15',
            'stop_rules': 'Existing frozen correctness, execution, accounting, conformance and grant gates; stop new dispatch below51GiB. No automatic retry, source repair, threshold change, admission or publication.',
        }
        (OUT / 'value-execution-review.json').write_text(json.dumps(review, indent=2) + '\n')
        print(json.dumps({'review_sha256': sha(OUT / 'value-execution-review.json'),
                          'plan_id': plan.plan_id, 'copy_allowance': copies,
                          'maximum_campaign_seconds': review['maximum_campaign_seconds']}))
    finally:
        await router.close()


asyncio.run(main())

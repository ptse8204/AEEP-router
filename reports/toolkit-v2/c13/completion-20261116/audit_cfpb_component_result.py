"""Replay the two approved local CFPB scopes without any upstream execution."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from aeep.assessment.extensions import grader_results
from aeep.assessment.models import AssessmentOperationLedger, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import RawExecution
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_evidence import _settled

ROOT = Path(__file__).resolve().parents[4]
PRIVATE = ROOT/'.aeep/completion-20261116/cfpb-canonical-first-20261117'
CONTINUATION = PRIVATE/'unstarted-five'
FIRST = '58dce0716e4f1b2f848c76b5b7b09ba376c072501a4e63c7b70d399c21670fa1'
NEXT = '9d2627d26def81f6596daa94e371d50be765b372f4adc8bea8a16fae5b5d7511'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def audit():
    require(sha(PRIVATE/'operation-review.json') == FIRST and sha(CONTINUATION/'operation-review.json') == NEXT,
            'exact reviews changed')
    parent = read(PRIVATE/'operation-review.json')
    continuation = read(CONTINUATION/'operation-review.json')
    for directory, exact in ((PRIVATE, FIRST), (CONTINUATION, NEXT)):
        require(read(directory/'approval.json') == {'approved': True, 'review_sha256': exact}, 'exact authority differs')
        require(read(directory/'root-delegated-review.json')['review_sha256'] == exact, 'delegation binds another review')
        require(sha(directory/'driver.py') == read(directory/'operation-review.json')['driver_sha256'], 'driver changed')
    require(all(sha(PRIVATE/name) == pin for name, pin in continuation['parent_files'].items()),
            'the original attempt or partial charges changed')
    spec = importlib.util.spec_from_file_location('cfpb_original', PRIVATE/'driver.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    require(driver.source() == parent['source'], 'current coordinator source differs')
    image_id = driver.bind_output(parent)
    image = driver.image(image_id)
    recipe, environment, calls = driver.definitions(image_id)
    require(not environment.read_only_roots and not environment.network, 'extra runtime roots or network appeared')
    require(content_digest(recipe) == parent['recipe_sha256'], 'protected recipe changed')
    expected_calls = [{key: value for key, value in call.items() if key != 'payload'} for call in calls]
    require(expected_calls == parent['calls'] and expected_calls[1:] == continuation['calls'], 'task/control bytes changed')
    exported = read(CONTINUATION/'execution/result.json')
    require(exported['review_sha256'] == NEXT and exported['parent_review_sha256'] == FIRST
            and exported['image'] == image_id and exported['all_controls_match'] is False,
            'original driver assertions were changed or exports differ')
    exported_ledger = AssessmentOperationLedger.model_validate_json((CONTINUATION/'execution/ledger.json').read_bytes())
    prior_ledger = AssessmentOperationLedger.model_validate_json((PRIVATE/'execution/ledger.json').read_bytes())
    observations = []
    with ReceiptStore(CONTINUATION/'execution/receipts.sqlite3', read_only=True) as store:
        repo = AssessmentRepository(store)
        ledger = repo.operation_ledger(driver.NAME)
        require(ledger == exported_ledger and len(ledger.operations) == 7, 'ledger export or cumulative count differs')
        indexed = {operation.operation_id: operation for operation in ledger.operations}
        require(all(indexed[op.operation_id] == op for op in prior_ledger.operations), 'inherited measurements changed')
        require(len(prior_ledger.operations) == 2, 'wrong original attempt prefix')
        require(set(indexed) == {driver.NAME+':build', *(call['operation'] for call in calls)}, 'unreviewed operation exists')
        for operation in ledger.operations:
            require(_settled(repo, operation.operation_id) == operation, 'operation is unresolved')
            require(operation.reserved.max_model_turns == operation.reserved.max_cash_usd == 0, 'model/cash authority expanded')
        grant = repo.current_grant(driver.NAME)
        require(grant.limits.max_operations == 7 and grant.limits.max_elapsed_seconds == 425
                and not grant.remote_disclosure and grant.allowed_destinations == ['local'], 'grant limits changed')
        for index, (call, row) in enumerate(zip(calls, exported['results'], strict=True)):
            directory = PRIVATE/'execution' if index == 0 else CONTINUATION/'execution'
            exact = FIRST if index == 0 else NEXT
            require((row['task'], row['role'], row['operation']) == (call['task'], call['role'], call['operation']), 'task/arm binding differs')
            raw_file = directory/(call['operation']+'.raw.json')
            raw = RawExecution.model_validate_json(raw_file.read_bytes())
            receipt = store.get_receipt(row['receipt_id'])
            operation = _settled(repo, call['operation'])
            require(receipt is not None and content_digest(receipt) == row['receipt_ref'], 'receipt hash differs')
            require(receipt.action_id == receipt.decision_id == call['operation'], 'receipt came from another operation')
            require(content_digest(raw) == row['raw_sha256'] == receipt.metadata['raw_sha256'], 'raw observation differs')
            require(receipt.metadata['review_sha256'] == exact and receipt.metadata['payload_sha256'] == call['payload_sha256'],
                    'receipt review or task payload differs')
            require(raw.status.value == row['program_status'] == 'success' and row['normalization_error'] is None,
                    'protected grader did not execute correctly')
            require(raw.resources == receipt.actual_resources == operation.resources, 'resource measurement differs')
            grade, = grader_results(raw.output, recipe.extension, 1)
            require(grade.model_dump(mode='json') == row['grade'], 'ordinary score normalization differs')
            require(raw.output['valid'] == [grade.valid] and raw.output['quality_scores'] == [grade.quality_score],
                    'native v7 score certificate differs')
            original_expected = grade.valid is call['expected_valid'] and grade.quality_score == (1.0 if call['expected_valid'] else 0.0)
            require(row['matches_expected'] is original_expected and receipt.execution_success is original_expected
                    and receipt.status.value == ('success' if original_expected else 'failed'), 'historical strict-driver result changed')
            _, owned = driver.ContainerExecutor(environment).command(driver.context(recipe.extension.grader, call['operation'], call['payload']))
            require(owned == row['container_name'] and row['container_absent'] and receipt.metadata['container_absent'],
                    'owned cleanup evidence differs')
            require(not driver.docker('ps', '-aq', '--filter', 'name=^/'+owned+'$'), 'owned grader container still exists')
            observations.append({'task': call['task'], 'role': call['role'], 'operation_id': call['operation'],
                'review_sha256': exact, 'payload_sha256': call['payload_sha256'], 'raw_observation': bound(raw_file),
                'receipt_id': receipt.receipt_id, 'receipt_ref': content_digest(receipt),
                'settled_measurement_ref': content_digest(operation), 'settled_seconds': operation.elapsed_seconds,
                'native_v7_certificate': raw.output, 'upstream_value_f1_normalized': grade.quality_score,
                'upstream_perfect_normalized': int(grade.valid), 'protected_valid': grade.valid,
                'original_zero_score_assertion_matched': original_expected,
                'preexisting_binary_contract_met': grade.valid is call['expected_valid'],
                'container_name': owned, 'container_absent': True,
                'observed_resource_dimensions': ['latency_ms'], 'other_resource_defaults_are_not_observations': True})
        build_operation = indexed[driver.NAME+':build']
        build_raw = RawExecution.model_validate_json((PRIVATE/'execution/build-raw.json').read_bytes())
        build_receipts = [r for r in store.list_receipts(limit=20) if r.action_id == build_operation.operation_id]
        build_receipt, = build_receipts
        require(build_receipt.execution_success and build_receipt.metadata['raw_sha256'] == content_digest(build_raw),
                'build receipt differs')
        require(build_raw.resources == build_operation.resources == build_receipt.actual_resources, 'build resources differ')
    scorer = driver.PROTECTED/'cases'/calls[0]['task']/'verifier/harbor_original.py'
    definition = driver.PROTECTED/'cases'/calls[0]['task']/'extract_bench/analysis/metric_definitions.py'
    guest = driver.PROTECTED/'extractbench_recipe_guest.py'
    observer = driver.PROTECTED/'extractbench_harbor_observer.py'
    require('report["perfect"] = int(report["value_f1"] == 1.0)' in scorer.read_text(), 'upstream perfect rule changed')
    require('omitted key scores as an explicit null' in definition.read_text(), 'null-field scoring evidence differs')
    return {'schema_version': 'aeep.c13.cfpb-local-component-result.v1',
        'review_records': [bound(PRIVATE/'operation-review.json'), bound(CONTINUATION/'operation-review.json')],
        'approval_records': [bound(PRIVATE/'approval.json'), bound(CONTINUATION/'approval.json')],
        'delegation_records': [bound(PRIVATE/'root-delegated-review.json'), bound(CONTINUATION/'root-delegated-review.json')],
        'source': parent['source'], 'image_id': image_id, 'image_tag': driver.TAG,
        'image_layers': image['RootFS']['Layers'], 'image_config_ref': content_digest(image['Config']),
        'sealed_environment_ref': content_digest(environment), 'recipe_ref': content_digest(recipe),
        'pack_digest': parent['pack_sha256'], 'calibrated_dependency_source_review': parent['calibrated_runtime_review'],
        'protected_context_manifest': bound(driver.PACK/'protected-context-manifest.json'),
        'scoring_source_records': [bound(scorer), bound(definition), bound(guest), bound(observer)],
        'observations': observations,
        'build': {'operation_id': build_operation.operation_id, 'settled_seconds': build_operation.elapsed_seconds,
            'receipt_id': build_receipt.receipt_id, 'receipt_ref': content_digest(build_receipt),
            'raw_observation': bound(PRIVATE/'execution/build-raw.json'),
            'resource_scope': 'Docker client process measurements. Whole Docker daemon/host resources remain unmeasured.'},
        'charges': {'unique_operations': 7, 'inherited_operations_counted_once': 2, 'outstanding_reservations': 0,
            'reserved_seconds': math.fsum(op.reserved.max_elapsed_seconds for op in ledger.operations),
            'settled_seconds': math.fsum(op.elapsed_seconds for op in ledger.operations)},
        'original_driver_all_controls_match': exported['all_controls_match'],
        'preexisting_binary_reference_control_contract_met': all(row['preexisting_binary_contract_met'] for row in observations),
        'reconciliation': 'Every reference is perfect and every empty object is rejected by the preexisting upstream exact-match rule. The driver incorrectly expected every empty object to have F1 zero. Original mismatch flags, scores and thresholds remain unchanged.',
        'fractional_empty_score_explanation': 'The pinned upstream metric definition treats omitted scalar keys as explicit null. Faithful nulls receive value-F1 credit. Therefore an empty object may earn fractional F1 while remaining imperfect and rejected.',
        'native_raw_marker_retention': 'The unmodified recipe adapter emits quality_scores from upstream value_f1 and valid from upstream perfect. Those exact v7 replies are retained. Upstream marker files and per-cell feedback remain transient.',
        'task_count': 3, 'source_family_count': 1, 'formal_cases_adopted': 0,
        'new_model_turns': 0, 'cash_usd': 0, 'provider_disclosure_allowed': False,
        'managed_cli_journey_complete': False, 'comparisons_paused': True, 'waza_excluded': True,
        'result_export': bound(CONTINUATION/'execution/result.json'),
        'ledger_export': bound(CONTINUATION/'execution/ledger.json'),
        'original_parent_ledger_unchanged': True}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))

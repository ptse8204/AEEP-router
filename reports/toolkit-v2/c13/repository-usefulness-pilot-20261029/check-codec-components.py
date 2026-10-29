"""Check real case transport contracts as data; execute no repository code."""
import asyncio
import base64
from contextlib import nullcontext
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.budget import campaign_allowances
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, _decode_suite_patch, grade_suite_output
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.models import ActionRequest, ValidationSpec
from aeep.registry import validate_json

HERE = Path(__file__).resolve().parent


class Reached(BaseException):
    def __init__(self, payload):
        self.payload = payload


async def main():
    amendment = json.loads((HERE / 'codec-definition-amendment.json').read_text())
    originals = {value['input']['task_id']: value for value in json.loads((HERE / 'cases.json').read_text())}
    checked = []
    upper_ops = 0
    upper_seconds = 0
    for part in amendment['components']:
        target = Path(part['directory'])
        review = json.loads((target / 'operation-review.json').read_text())
        assert hashlib.sha256((target / 'operation-review.json').read_bytes()).hexdigest() == part['review_sha256']
        for path, digest in review['assets'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        recipe = RecipeDefinition.model_validate_json((target / 'recipe.json').read_text())
        cases = [RepositorySuiteCase.model_validate(value) for value in json.loads((target / 'cases.json').read_text())]
        proposal = json.loads((target / 'collector-definitions.json').read_text())
        pair = proposal['definitions'][proposal['pair_definition_digest']]
        for case in cases:
            assert case.model_dump(mode='json') == originals[case.input.task_id]
            reference = json.loads(case.reference.read())
            patch = _decode_suite_patch(case.truth, reference)
            raw = patch.model_dump_json().encode()
            output = {'patch_b64': base64.b64encode(raw).decode()} if part['mode'] == 'plain' else {'patch_gzip_b64': base64.b64encode(gzip.compress(raw)).decode()}
            validate_json(output, recipe.output_schema, label='actual worker-codec fixture')
            assert _decode_suite_patch(case.truth, output) == patch
            if part['mode'] == 'plain':
                try:
                    _decode_suite_patch(case.truth, {'patch_gzip_b64': base64.b64encode(gzip.compress(raw)).decode()})
                except ValueError:
                    pass
                else:
                    raise AssertionError('The original mismatched gzip transport was accepted')
            async def probe(payload):
                raise Reached(payload)
            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), output, probe)
            except Reached as marker:
                size = len(json.dumps(marker.payload).encode())
                assert size < recipe.extension.grader.config['max_stdin_bytes']
            else:
                raise AssertionError('The corrected artifact did not reach the existing grader')
            for role in ('control', 'treatment'):
                artifact = pair[role]['config']['artifact']
                assert artifact['output_field'] == next(iter(output))
                assert artifact['output_name'] == ('patch.json' if part['mode'] == 'plain' else 'patch.json.gz')
            checked.append({'case': case.input.task_id, 'mode': part['mode'], 'grader_payload_bytes': size,
                            'strict_original_decoder_roundtrip': True, 'all_original_case_fields_unchanged': True})
        suite = BenchmarkSuite(suite_id='budget-only', domain='development', repetitions=1, seed=71,
            routes=[{'route_id': pair[role]['id'], 'executor_id': pair[role]['id']} for role in ('control', 'treatment')],
            conditions=['fresh-worker'], warmup_cases=[], max_total_cash_usd='0', baseline_route_id=pair['control']['id'], paired_order=True,
            cases=[BenchmarkCase(case_id=case.input.task_id, split='training', action=ActionRequest(capability=recipe.capability, input=case.input.model_dump(mode='json')),
                validators=[ValidationSpec(kind='callback', config={'expected': case.truth.model_dump(mode='json')})]) for case in cases])
        repository = SimpleNamespace(get=lambda kind, digest: recipe.model_dump(mode='json'), operation_ledger=lambda *args: SimpleNamespace(operations=[]))
        service = SimpleNamespace(repository=repository, router=SimpleNamespace(store=SimpleNamespace(_lock=nullcontext())), _cost_sources=lambda *args, **kwargs: ([], []))
        budget = campaign_allowances(service, SimpleNamespace(suite=suite, recipe_digest=content_digest(recipe), setup_cost_ids=[], plan_id='inert-budget'),
            operations_per_case=2, turns_per_case=2, seconds_per_case=610, cash_per_case=Decimal(0), remaining=None)
        total = budget['upper_allowance']
        proxy = 11500 if part['mode'] == 'plain' else 5000
        assert total['operations'] + 4 <= part['maximum_operations']
        assert total['elapsed_seconds'] + 1080 + proxy <= part['maximum_reserved_seconds']
        upper_ops += part['maximum_operations']
        upper_seconds += part['maximum_reserved_seconds']
    assert len(checked) == 19
    result = {'passed': True, 'strict_case_codec_roundtrips': checked, 'existing_grader_payloads_prepared_without_execution': 19,
              'new_source_or_model_invocations': 0, 'combined_component_caps_operations': upper_ops,
              'combined_component_caps_seconds': upper_seconds, 'old_costs_not_reset': True,
              'existing_engine_bounds_fit_each_component': True, 'old_mismatch_rejected_for_all_plain_cases': True}
    with (HERE / 'codec-component-check.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'strict_case_codec_roundtrips'}))


if __name__ == '__main__':
    asyncio.run(main())

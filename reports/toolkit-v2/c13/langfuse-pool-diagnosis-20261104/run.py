"""One read-only diagnosis via the existing Langfuse command/receipt bridge."""
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'langfuse-threadpool-correction-20261104'
sys.path.insert(0, str(PRIOR))
spec = importlib.util.spec_from_file_location('reviewed_langfuse_service', PRIOR / 'run-service.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.HERE = HERE

from aeep.assessment.models import AssessmentLimits, RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ResourceVector
from aeep.store import ReceiptStore

review_file = HERE / 'operation-review.json'
identity = hashlib.sha256(review_file.read_bytes()).hexdigest()
review = base.load(review_file)
authority = base.load(HERE / 'delegated-authority.json')
assert sys.argv[1:] == ['--execute-delegated', identity]
assert authority['review_sha256'] == identity and authority['first_attempt'] is True
base.validate(review)
request = RecipeMaterializationRequest.model_validate(
    base.load(PRIOR / 'prepared.json')['request']
).model_copy(update={'plan_id': 'langfuse-pool-diagnosis-20261104'})
result = {'passed': False, 'models': 0, 'service_started': False, 'raw_logs_retained': False}
with ReceiptStore(review['ledger']) as store:
    repository = AssessmentRepository(store)
    journey = base.Journey(review, repository, request, identity)
    assert journey.counters() == review['counters_before']
    with (HERE / 'execution-started.json').open('x') as f:
        json.dump({'review_sha256': identity}, f)
    (HERE / 'service-execution').mkdir(mode=0o700)
    outer = request.plan_id + ':overhead'
    repository.reserve(request, outer, AssessmentLimits(
        max_operations=1, max_model_turns=0, max_elapsed_seconds=30
    ), stage='langfuse_pool_diagnosis_overhead')
    started = time.perf_counter()
    try:
        observation = json.loads(journey.command(
            'inspect-stopped-pool-namespace',
            [review['diagnostic_python'], '-I', '-B', str(HERE / 'observe.py'), str(review_file)],
            30,
        ))
        result.update(passed=True, observation=observation)
    except Exception as error:
        result['error_type'] = type(error).__name__
    finally:
        elapsed = max(0.0, time.perf_counter() - started - journey.child_seconds)
        repository.finish_operation(outer, elapsed_seconds=elapsed,
                                    resources=ResourceVector(latency_ms=elapsed * 1000))
        result['accounting_uncertain'] = bool(store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
            (request.authorization_id,)
        ).fetchone())
        result['grant_counters'] = journey.counters()
        base.write(HERE / 'operation-ledger.json',
                   repository.operation_ledger(request.plan_id + ':driver-commands').model_dump(mode='json'))
        base.write(HERE / 'summary.json', result)
print(json.dumps(result))
raise SystemExit(not result['passed'] or result['accounting_uncertain'])

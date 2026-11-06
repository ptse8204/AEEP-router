"""Build one offline macOS SkillRank carrier for the ordinary CLI scheduler."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import struct
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
PREVIOUS = HERE.parent / 'skillrank-callback-proof-20261105'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
VENDOR = ROOT / '.aeep/skillrank-license-correction-20261103/runtime/vendor'
BRIDGE = ROOT / 'integrations/toolkit/skillrank/bridge.rs'
RUST = Path.home() / '.rustup/toolchains/stable-aarch64-apple-darwin'
XCODE = Path('/Applications/Xcode.app/Contents/Developer')
TOOLS = XCODE / 'Toolchains/XcodeDefault.xctoolchain/usr/bin'
SDK = XCODE / 'Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
SANDBOX = Path('/usr/bin/sandbox-exec')
BINARY = WORK / 'target/aarch64-apple-darwin/release/aeep-skillrank-bridge'
RESERVE = 50 * 1024**3
PROFILE = HERE / 'build.sb'


class BuildScope(StrictModel):
    schema_version: str = 'aeep.toolkit.skillrank-native-carrier.v1'
    review_sha256: str


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def tree(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            files[path.relative_to(root).as_posix()] = {'link': os.readlink(path)}
        elif path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path)
    return content_digest(files)


def inputs():
    return {
        'source_tree': tree(WORK / 'source'), 'vendor_tree': tree(VENDOR),
        'rust_library_tree': tree(RUST / 'lib'), 'apple_sdk_tree': tree(SDK),
        'artifacts': {str(path): sha(path) for path in (
            Path(__file__), BRIDGE, AUTHORITY, PROFILE, SANDBOX, RUST / 'bin/cargo',
            RUST / 'bin/rustc', TOOLS / 'clang', TOOLS / 'ld', TOOLS / 'ar',
            PREVIOUS / 'operation-review.json', PREVIOUS / 'result.json',
        )},
    }



async def execute(review, identity):
    assert inputs() == review['input_bindings']
    assert sha(WORK / 'source/Cargo.lock') == review['cargo_lock_sha256']
    assert verification_source_digest(ROOT) == review['implementation_source']
    assert shutil.disk_usage(ROOT).free >= RESERVE + 2 * 1024**3
    assert not BINARY.exists() and not any((WORK / 'target').iterdir())
    write(HERE / 'dispatch-intent.json', {'review_sha256': identity})
    scope = BuildScope(review_sha256=identity)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=HERE.name, subject_digest=ref, recipe_digest=ref, mapping_digest=ref,
        environment_digest=ref, authorization_id=HERE.name, definition_digests=[ref], seed=0,
    )
    limits = AssessmentLimits(max_operations=1, max_elapsed_seconds=610)
    grant = AssessmentAuthorization(
        authorization_id=HERE.name, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], limits=limits, expires_at=utc_now() + timedelta(minutes=30),
        allowed_destinations=['local'], remote_disclosure=False,
    )
    spec = ExecutorSpec(
        id='skillrank.native-carrier', capability='toolkit.upstream-engineering@1',
        kind='command', side_effect='write', description='Build the reviewed native bridge offline',
        config={'argv': review['argv'], 'cwd': review['cwd'], 'env': review['env'],
                'argv_literal': True, 'inherit_env': False, 'timeout_seconds': 600,
                'max_output_bytes': 65536, 'output': {'type': 'text'}},
    )
    operation = HERE.name + ':compile'
    started, clock = utc_now(), time.perf_counter()
    raw = evidence_ref = None
    executor = CommandExecutor()
    result = {'passed': False, 'review_sha256': identity, 'model_turns': 0}
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('skillrank_native_carrier_scope', ref, scope) == ref
        repo.approve_bundle(grant, {ref: scope.model_dump(mode='json')})
        repo.reserve(request, operation, limits, stage='skillrank_native_carrier_build')
        def authorize():
            repo.authorize(request)
            return identity

        try:
            with persist_execution_events(lambda key, event: repo.put('execution_event', key + ':' + str(event.sequence), event)):
                handle = await executor.start(ExecutionContext(
                    request=ActionRequest(action_id=operation, capability=spec.capability),
                    spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                    approved_side_effect=spec.side_effect, invocation_check=authorize,
                ))
                while not handle.task.done():
                    await asyncio.wait({handle.task}, timeout=1)
                    if shutil.disk_usage(ROOT).free < RESERVE:
                        await executor.cancel(handle)
                        raise RuntimeError('HostReserveCrossed')
                raw = await handle.task
            evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            assert evidence.complete
            evidence_ref = repo.put('execution_evidence', evidence.digest(), evidence)
            assert raw.exit_code == 0 and raw.status.value == 'success'
            with BINARY.open('rb') as stream:
                assert struct.unpack('<II', stream.read(8)) == (0xFEEDFACF, 0x0100000C)
            assert inputs() == review['input_bindings']
            result.update(passed=True, binary_sha256=sha(BINARY), binary=str(BINARY), architecture='macOS ARM64')
        except Exception as failure:
            result['error_type'] = type(failure).__name__
            if raw is not None:
                (HERE / 'public-compiler-diagnostic.log').write_text((raw.stderr or '')[-8000:])
        finally:
            await executor.close()
            elapsed = time.perf_counter() - clock
            receipt = ExecutionReceipt(
                decision_id=operation, action_id=operation, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, status=raw.status if raw else 'failed',
                started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                execution_success=result['passed'], error_type=result.get('error_type'),
                metadata={'review_sha256': identity, 'execution_evidence_ref': evidence_ref,
                          'observed_resource_dimensions': ['latency_ms']},
            )
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
            write(HERE / 'build-receipt.json', receipt.model_dump(mode='json'))
            write(HERE / 'operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(HERE / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated', required=True)
    args = parser.parse_args()
    path = HERE / 'execution-review.json'
    authority = read(HERE / 'execution-authority.json')
    identity = sha(path)
    assert args.execute_delegated == identity == authority['review_sha256']
    assert authority['standing_authority_sha256'] == sha(AUTHORITY)
    assert authority['first_native_build'] is True
    result = asyncio.run(execute(read(path), identity))
    print(json.dumps(result))
    raise SystemExit(not result['passed'])

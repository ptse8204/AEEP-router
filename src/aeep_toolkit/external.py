"""Read pinned upstream reports without executing their software or trusting claims."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import Count, Digest, Measure

PINS = {
    'waza': 'e534d149d89ae77ea158469fb4d2003804b2ee76',
    'cisco-skill-scanner': 'c3d7fd9fee50cf2ea45f0b381eb61f857360f825',
}
Status = Literal['passed', 'failed', 'error', 'skipped', 'n/a']


class UpstreamFields(BaseModel):
    # Only selected fields leave this boundary; prompts, paths and diagnostics do not.
    model_config = ConfigDict(extra='ignore', strict=True, allow_inf_nan=False)


class WazaUsage(UpstreamFields):
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    cache_read_tokens: Count | None = None
    cache_write_tokens: Count | None = None
    premium_requests: Measure | None = None
    ai_credits: Measure | None = None


class WazaRun(UpstreamFields):
    run_number: Annotated[int, Field(strict=True, ge=1)]
    attempts: Count | None = None
    status: Status
    duration_ms: Count | None = None
    usage: WazaUsage | None = None


class WazaTask(UpstreamFields):
    test_id: str = Field(min_length=1, max_length=1000)
    status: Status
    cached: bool = False
    runs: list[WazaRun] = Field(max_length=1000)


class WazaResult(UpstreamFields):
    schemaVersion: Literal['1.0', '1.1', '1.2', '1.3', '1.4']
    eval_id: str = Field(min_length=1, max_length=1000)
    tasks: list[WazaTask] = Field(max_length=1000)
    is_baseline: bool = False


class Finding(UpstreamFields):
    id: str = Field(min_length=1, max_length=1000)
    severity: Literal['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', 'SAFE']


class ScannerResult(UpstreamFields):
    skill_name: str = Field(min_length=1, max_length=1000)
    findings_count: Count
    findings: list[Finding] = Field(max_length=1000)
    suppressed_findings: list[Finding] = Field(default_factory=list, max_length=1000)
    analyzers_used: list[str] = Field(max_length=100)
    analyzers_failed: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    scan_duration_seconds: Measure | None = None


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _waza(data: dict[str, Any], role: str = 'candidate') -> dict[str, Any]:
    source = WazaResult.model_validate(data)
    if len({task.test_id for task in source.tasks}) != len(source.tasks):
        raise ValueError('duplicate Waza tasks')
    runs = []
    for task in source.tasks:
        if len({run.run_number for run in task.runs}) != len(task.runs):
            raise ValueError('duplicate Waza trials')
        for run in task.runs:
            runs.append({
                'task_ref': _hash(task.test_id), 'run_number': run.run_number,
                'reported_status': run.status, 'attempts': run.attempts,
                'cached': task.cached, 'reported_duration_seconds': run.duration_ms / 1000 if run.duration_ms is not None else None,
                'reported_usage': run.usage.model_dump() if run.usage else None,
                'verified_outcome': 'unknown', 'candidate_exposed': None, 'candidate_invoked': None,
            })
    return {'role_claim': role,
            'evaluation_ref': _hash(source.eval_id), 'tasks': len(source.tasks), 'runs': runs,
            'reported_task_statuses': dict(Counter(task.status for task in source.tasks)),
            'billing_scope': 'unresolved_evaluation_sessions', 'actual_cash': None,
            'token_total': None, 'cache_semantics': 'unverified', 'paired_worker_conformance': None}


def import_result(raw: bytes, backend: str, *, revision: str, candidate_sha256: str) -> dict[str, Any]:
    """A local supplied-source assertion; hashes prove identity, not execution or safety."""
    if backend not in PINS or len(raw) > 1024 * 1024 or revision != PINS[backend]:
        raise ValueError('unsupported report size or upstream revision')
    from pydantic import TypeAdapter
    TypeAdapter(Digest).validate_python(candidate_sha256)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON keys')
            result[key] = value
        return result

    data = json.loads(raw, object_pairs_hook=unique)
    # Also reject nonfinite values in ignored fields rather than hashing ambiguous JSON.
    _hash(data)
    if not isinstance(data, dict):
        raise ValueError('upstream report must be an object')
    if backend == 'waza':
        observations = _waza(data)
        if data.get('baseline_outcome') is not None:
            baseline = data['baseline_outcome']
            # Upstream is_baseline flags the outer comparison, not the control arm.
            if (data.get('is_baseline') is not True or not isinstance(baseline, dict)
                    or baseline.get('is_baseline', False) is not False or baseline.get('baseline_outcome') is not None):
                raise ValueError('unsupported nested Waza baseline')
            observations['baseline'] = _waza(baseline, 'baseline')
        elif data.get('is_baseline'):
            raise ValueError('Waza comparison is missing its baseline')
        limitations = [
            'Imported status is an upstream claim, not an independent AEEP grade.',
            'Runs, cached diagnostics and evaluation session usage are not added together.',
            'Premium requests and AI credits are not cash; token overlap and complete billing remain unresolved.',
            'Arm labels do not establish matching tasks, optional exposure or worker isolation.',
        ]
    else:
        scan = ScannerResult.model_validate(data)
        if scan.findings_count != len(scan.findings):
            raise ValueError('scanner count disagrees with findings')
        observations = {
            'findings_by_severity': dict(Counter(finding.severity for finding in scan.findings)),
            'finding_refs': [_hash(finding.model_dump()) for finding in scan.findings],
            'suppressed_by_severity': dict(Counter(finding.severity for finding in scan.suppressed_findings)),
            'analyzer_refs': [_hash(name) for name in scan.analyzers_used],
            'failed_analyzers': len(scan.analyzers_failed),
            'reported_duration_seconds': scan.scan_duration_seconds,
            'coverage': 'incomplete' if scan.analyzers_failed or not scan.analyzers_used else 'unverified',
            'safety_verdict': 'NOT_ESTABLISHED',
        }
        limitations = ['Scanner findings are risk advice; absence of findings is not proof of safety.',
                       'Analyzer execution, candidate binding, policy and suppressions require independent review.']
    result = {
        'schema_version': 'aeep.toolkit.upstream-observations.v1', 'backend': backend,
        'source_revision_asserted': revision, 'candidate_sha256_asserted': candidate_sha256,
        'artifact_sha256': hashlib.sha256(raw).hexdigest(), 'trust': 'supplied_unverified',
        'outcome': 'NOT_ASSESSED', 'execution_performed': False, 'observations': observations,
        'limitations': [*limitations, 'Paths, names, prompts, outputs and diagnostic text are omitted; digests can still identify a study.'],
    }
    return {**result, 'content_sha256': _hash(result)}


def render_import(result: dict[str, Any], format: str) -> str:
    """Render minimized data only; all claims retain the unverified trust tier."""
    text = json.dumps(result, indent=2, allow_nan=False)
    if format == 'json':
        return text
    heading = f"{result['backend']} — imported observations (NOT_ASSESSED)"
    notice = 'No software executed. No verified safety, benefit, billing or worker-isolation conclusion.'
    if format == 'markdown':
        return f'# {heading}\n\n{notice}\n\n```json\n{text}\n```\n'
    if format == 'html':
        import html
        return ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{html.escape(heading)}</title><main><h1>{html.escape(heading)}</h1>'
                f'<p>{notice}</p><pre>{html.escape(text)}</pre></main></html>')
    raise ValueError('unsupported format')

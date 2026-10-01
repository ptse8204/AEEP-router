from __future__ import annotations

import json
from decimal import Decimal

import pytest
from conftest import manifest_with, python_spec

from aeep.benchmarking import (
    AssessmentBenchmarkCondition,
    BenchmarkCase,
    BenchmarkCondition,
    BenchmarkPhase,
    BenchmarkRoute,
    BenchmarkRunner,
    BenchmarkSplit,
    BenchmarkSuite,
    BenchmarkTrial,
)
from aeep.errors import ConfigurationError
from aeep.models import ActionConstraints, ActionRequest, ValidationKind, ValidationSpec
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep.workflow import WorkflowRequest

pytestmark = pytest.mark.assessment_lifecycle


def suite_for(*routes):
    return BenchmarkSuite(
        suite_id="controlled",
        repetitions=1,
        routes=list(routes),
        conditions=[AssessmentBenchmarkCondition.ROUTER_FRESH],
        max_total_cash_usd=Decimal(0),
        cases=[
            BenchmarkCase(
                case_id="case",
                split=BenchmarkSplit.HOLDOUT,
                action=ActionRequest(
                    capability="text.stats", input={"text": "private synthetic fixture"}
                ),
                validators=[
                    ValidationSpec(
                        kind=ValidationKind.EXACT_MATCH, config={"path": "words", "expected": 3}
                    )
                ],
            )
        ],
    )


def test_scoped_campaign_snapshot_retains_bound_definitions_and_runtime_guard_records(tmp_path):
    source = ReceiptStore(tmp_path / 'source.sqlite3')
    selected, unrelated = 'a' * 64, 'b' * 64
    with source._immediate_transaction() as connection:
        for kind, identity, digest in (
            ('campaign', 'selected', selected), ('campaign', 'historical', unrelated),
            ('recipe_case_set', 'historical', 'c' * 64),
            ('plan', 'historical', '1' * 64),
            ('mapping', 'historical', '2' * 64),
            ('boundary_probe_definition', 'historical', '3' * 64),
            ('worker_pair_definition', 'reviewed', '4' * 64),
            ('admission', 'runtime', 'd' * 64), ('environment', 'runtime', 'e' * 64),
            ('recipe', 'runtime', 'f' * 64),
        ):
            connection.execute('INSERT INTO assessment_records VALUES (?, ?, ?, ?)',
                (kind, identity, digest, '{"fixture":true}'))
        connection.execute("INSERT INTO assessment_reviews VALUES (?, ?, 0)",
            ('4' * 64, '2026-09-29T00:00:00Z'))
        connection.execute("INSERT INTO assessment_admissions VALUES ('fallback', 'runtime', 1, NULL)")
    broad = source.campaign_snapshot()
    scoped = source.campaign_snapshot(bound_digests={selected})
    try:
        def rows(store):
            return {tuple(row) for row in store._connection.execute('SELECT kind, id FROM assessment_records')}
        assert ('campaign', 'historical') in rows(broad)
        assert rows(scoped) == {('campaign', 'selected'), ('admission', 'runtime')}
        assert scoped._connection.execute("SELECT revoked FROM assessment_admissions WHERE executor_id='fallback'").fetchone()[0] == 1
        assert len(rows(source)) == 10
    finally:
        broad.close()
        scoped.close()
        source.close()


def test_scoped_snapshot_reference_closure_and_external_hashes(tmp_path):
    source = ReceiptStore(tmp_path / "source.sqlite3")
    documents = [
        ("plan", "scope", "a" * 64, {"recipe_digest": "recipe-name", "definition_digests": ["b" * 64], "planning_request_ids": ["planning-name"]}),
        ("boundary_conformance", "boundary", "b" * 64, {"configuration_digest": "0" * 64, "identity_digest": "0" * 64, "binary_digest": "0" * 64, "effective_inventory": {"python": "3" * 64}, "reviewed_inventory_digest": "inventory-name", "effective_policy_digest": "policy-name"}),
        ("reviewed_inventory", "inventory-name", "c" * 64, {}),
        ("effective_policy_definition", "policy-name", "d" * 64, {}),
        ("recipe", "recipe-name", "e" * 64, {}),
        ("planning_request", "planning-name", "3" * 64, {}),
        ("admission", "fallback", "f" * 64, {"recipe_digest": "fallback-recipe", "environment_digest": "fallback-environment", "report_id": "fallback-report"}),
        ("recipe", "fallback-recipe", "4" * 64, {}),
        ("environment", "fallback-environment", "5" * 64, {"conformance_digests": ["b" * 64]}),
        ("report", "fallback-report", "6" * 64, {"plan_digest": "a" * 64}),
        ("environment", "historical", "7" * 64, {"conformance_digests": ["8" * 64]}),
        ("boundary_conformance", "historical", "8" * 64, {}),
        ("task_activation", "activation-name", "9" * 64, {"scope_digest": "a" * 64, "manifest_digest": "0" * 64}),
        ("task_codex_binding", "activation-name", "1" * 64, {"activation_id": "activation-name"}),
        ("task_lifecycle", "pause", "2" * 64, {"activation_digest": "9" * 64}),
    ]
    with source._immediate_transaction() as connection:
        for kind, identity, digest, document in documents:
            connection.execute("INSERT INTO assessment_records VALUES (?, ?, ?, ?)", (kind, identity, digest, json.dumps(document)))
        connection.execute("INSERT INTO assessment_admissions VALUES ('fallback', 'fallback', 1, NULL)")
        connection.execute("INSERT INTO assessment_reviews VALUES (?, ?, 1)", ('8' * 64, '2026-09-29T00:00:00Z'))
    before = list(source._connection.iterdump())
    scoped = source.campaign_snapshot(bound_digests={"a" * 64, "0" * 64})
    try:
        identities = {(row[0], row[1]) for row in scoped._connection.execute("SELECT kind,id FROM assessment_records")}
        assert identities == {(kind, identity) for kind, identity, _, _ in documents if identity != "historical"}
        assert scoped._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
        assert scoped._connection.execute("SELECT revoked FROM assessment_reviews").fetchone()[0] == 1
        assert not scoped._connection.execute("SELECT * FROM execution_attempts").fetchall()
        assert list(source._connection.iterdump()) == before
    finally:
        scoped.close()
        source.close()


@pytest.mark.parametrize("documents", [
    [("a" * 64, {"recipe_digest": "missing-recipe"})],
    [("a" * 64, {"recipe_digest": "b" * 64}), ("b" * 64, {"recipe_digest": "a" * 64})],
])
def test_scoped_snapshot_missing_and_cyclic_dependencies_fail_closed(tmp_path, documents):
    source = ReceiptStore(tmp_path / "source.sqlite3")
    with source._immediate_transaction() as connection:
        for digest, document in documents:
            connection.execute("INSERT INTO assessment_records VALUES ('recipe', ?, ?, ?)", (digest, digest, json.dumps(document)))
    before = list(source._connection.iterdump())
    try:
        with pytest.raises(ConfigurationError, match=r"missing|cyclic"):
            source.campaign_snapshot(bound_digests={"a" * 64})
        assert list(source._connection.iterdump()) == before
    finally:
        source.close()


async def test_inactive_candidate_trial_preserves_production_and_receipts(tmp_path):
    spec = python_spec("inactive", "aeep.examples.tools:text_stats")
    spec.enabled = False
    source = Router(manifest_with(spec))
    suite = suite_for(BenchmarkRoute(route_id="inactive", executor_id="inactive"))
    runner = BenchmarkRunner(
        lambda: source._campaign_router([spec], plan_digest="a" * 64), tmp_path / "campaign.db"
    )
    try:
        report = await runner.run(suite)
        assert report.trials[0].valid
        assert not source.registry.get("inactive").enabled
        assert source.route(suite.cases[0].action).selected_executor_id is None
        assert not source.store.list_receipts()
        receipts = runner.connection.execute("SELECT payload_json FROM trial_receipts").fetchall()
        assert len(receipts) == 1
        assert "private synthetic fixture" not in receipts[0][0]
        assert report.trials[0].case_validation[0].valid
        assert (await runner.run(suite)).trials == report.trials
        spec.config["timeout_seconds"] = 19
        with pytest.raises(ConfigurationError, match="environment changed"):
            await runner.run(suite)
    finally:
        runner.connection.close()
        await source.close()


async def test_pinning_cannot_weaken_allowed_ids_and_workflow_binding_is_shared(tmp_path):
    spec = python_spec("local", "aeep.examples.tools:text_stats")
    manifest = manifest_with(spec)
    direct = suite_for(BenchmarkRoute(route_id="local", executor_id="local"))
    direct.cases[0].action.constraints.allowed_executor_ids = ["other"]
    runner = BenchmarkRunner(lambda: Router(manifest), tmp_path / "direct.db")
    report = await runner.run(direct)
    assert not report.trials[0].ok
    assert not runner.connection.execute("SELECT * FROM trial_receipts").fetchall()
    runner.connection.close()
    workflow = WorkflowRequest.model_validate(
        {
            "workflow_id": "flow",
            "input": {"source": "unbound"},
            "steps": [
                {
                    "step_id": "stats",
                    "action": {"capability": "text.stats", "input": {"text": "placeholder"}},
                    "bindings": [{"source_path": "/source", "target_path": "/text"}],
                }
            ],
            "outputs": [{"name": "stats", "step_id": "stats", "path": ""}],
        }
    )
    route = BenchmarkRoute(
        route_id="workflow",
        workflow=workflow,
        case_input_bindings={"/source": "/text"},
        validation_output_path="stats",
    )
    bound = suite_for(route)
    runner = BenchmarkRunner(lambda: Router(manifest), tmp_path / "workflow.db")
    try:
        assert (await runner.run(bound)).trials[0].valid
        assert workflow.input == {"source": "unbound"}
        forbidden = bound.model_copy(deep=True)
        forbidden.suite_id = "forbidden"
        forbidden.cases[0].action.constraints = ActionConstraints(denied_executor_ids=["local"])
        with pytest.raises(ConfigurationError):
            await runner.run(forbidden)
    finally:
        runner.connection.close()


async def test_usage_survives_case_grader_failure(tmp_path, monkeypatch):
    import aeep.benchmarking as module

    async def broken(*args):
        raise RuntimeError("grader fault containing synthetic fixture")

    spec = python_spec("local", "aeep.examples.tools:text_stats")
    runner = BenchmarkRunner(lambda: Router(manifest_with(spec)), tmp_path / "grading.db")
    monkeypatch.setattr(module, "run_validators", broken)
    try:
        trial = (
            await runner.run(suite_for(BenchmarkRoute(route_id="local", executor_id="local")))
        ).trials[0]
        assert trial.state == "failed"
        assert trial.receipt_ids and trial.actual_resources.latency_ms > 0
        assert trial.error_message is None
        assert runner.connection.execute("SELECT count(*) FROM trial_receipts").fetchone()[0] == 1
    finally:
        runner.connection.close()


def test_trial_claims_are_atomic_and_legacy_conditions_unchanged(tmp_path):
    assert list(BenchmarkCondition) == [
        BenchmarkCondition.PROCESS_COLD,
        BenchmarkCondition.ROUTER_WARM,
    ]
    one = BenchmarkRunner(lambda: Router(manifest_with()), tmp_path / "claim.db")
    two = BenchmarkRunner(lambda: Router(manifest_with()), tmp_path / "claim.db")
    trial = BenchmarkTrial(
        trial_id="same",
        run_id="run",
        suite_id="suite",
        case_id="case",
        route_id="route",
        condition=BenchmarkCondition.PROCESS_COLD,
        repetition=0,
        phase=BenchmarkPhase.HOLDOUT,
        state="running",
    )
    try:
        one._claim_trial(trial)
        with pytest.raises(ConfigurationError, match="claimed"):
            two._claim_trial(trial)
        with pytest.raises(ValueError, match="warm-up"):
            BenchmarkSuite(
                suite_id="staged",
                routes=[BenchmarkRoute(route_id="x", executor_id="x")],
                cases=suite_for(BenchmarkRoute(route_id="x", executor_id="x")).cases,
                sequential_stages=True,
            )
    finally:
        one.connection.close()
        two.connection.close()


def test_schema_seven_migration_and_private_host_key_survive_reopen(tmp_path):
    import sqlite3

    from aeep.store import _V08_ASSESSMENT_SCHEMA

    database = tmp_path / "legacy.sqlite3"
    with ReceiptStore(database) as store:
        store._connection.execute("PRAGMA foreign_keys=OFF")
        for statement in reversed(_V08_ASSESSMENT_SCHEMA):
            table = statement.split("EXISTS ")[1].split(" ")[0]
            store._connection.execute(f"DROP TABLE {table}")
        store._connection.execute("PRAGMA user_version=7")
    with ReceiptStore(database) as store:
        key = store.host_principal_key()
        assert len(key) == 32
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 8
        snapshot = store.campaign_snapshot()
        assert snapshot.host_principal_key() == key
        assert not snapshot.list_receipts()
        snapshot.close()
    with ReceiptStore(database) as store:
        assert store.host_principal_key() == key
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM assessment_grants").fetchone()[0] == 0


async def test_partial_codex_usage_is_retained_without_claiming_complete_measurements():
    import sys
    import time

    from aeep.hosts.codex_app_server import CodexAppServerAdapter, _TurnCollector
    from aeep.models import EvidenceStatus, ExecutionStatus

    adapter = CodexAppServerAdapter(
        argv=(sys.executable,), resource_id="fixture", principal_salt=b"fixture-aeep-key"
    )
    collector = _TurnCollector(max_output_bytes=1024)
    collector.actual_model = "fixture-model"
    collector.turn_id = "turn"
    collector.token_usage = {"inputTokens": 12, "outputTokens": 4}
    raw = adapter._partial_execution(collector, ExecutionStatus.TIMEOUT, time.monotonic())
    assert raw.resources.input_tokens == 12
    assert raw.resources.output_tokens == 4
    assert raw.accounting.model_usage[0].evidence.status == EvidenceStatus.PARTIAL
    assert raw.metadata["model_turn_count"] == 1
    collector.token_usage = None
    assert not adapter._partial_execution(
        collector, ExecutionStatus.FAILED, time.monotonic()
    ).accounting.model_usage
    await adapter.close()


async def test_worker_conditions_require_actual_adapter_support(tmp_path):
    import sys

    from aeep.benchmarking import AssessmentBenchmarkCondition
    from aeep.models import ExecutorSpec

    spec = ExecutorSpec(id='worker',capability='text.stats',kind='command',description='Fresh command-process fixture',
        config={'argv':[sys.executable,'-c',"print('{\"characters\":5,\"words\":1,\"lines\":1}')"],'output':{'type':'json'}})
    spec.estimate = python_spec('estimate','aeep.examples.tools:text_stats').estimate
    suite = suite_for(BenchmarkRoute(route_id='worker',executor_id='worker'))
    suite.conditions = [AssessmentBenchmarkCondition.FRESH_WORKER]
    runner = BenchmarkRunner(lambda: Router(manifest_with(spec)),tmp_path/'fresh.db')
    try:
        report = await runner.run(suite)
        assert report.trials[0].ok
        assert report.trials[0].condition.value == 'fresh-worker'
        reused = suite.model_copy(update={'suite_id':'reused','conditions':[AssessmentBenchmarkCondition.REUSED_WORKER]})
        with pytest.raises(ConfigurationError,match='reused_worker'):
            await runner.run(reused)
        assert not runner.connection.execute("SELECT 1 FROM trials WHERE suite_id='reused'").fetchall()
    finally:
        runner.connection.close()


async def test_campaign_retains_only_reviewed_failure_codes(tmp_path):
    from aeep.models import ValidationResult

    spec = python_spec('local', 'aeep.examples.tools:text_stats')
    suite = suite_for(BenchmarkRoute(route_id='local', executor_id='local'))
    suite.cases[0].validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
        config={'name': name, 'failure_codes': ['cell_value']})
        for name in ('reviewed', 'private', 'unreviewed', 'successful')]
    def router():
        value = Router(manifest_with(spec))
        for name, detail, valid in [('reviewed', 'cell_value', False),
                                   ('private', 'private workbook contents', False),
                                   ('unreviewed', 'undeclared_code', False),
                                   ('successful', 'cell_value', True)]:
            value.validator_callbacks[name] = lambda _ctx, detail=detail, valid=valid: ValidationResult(
                kind=ValidationKind.CALLBACK, valid=valid, detail=detail)
        return value
    runner = BenchmarkRunner(router, tmp_path / 'codes.db')
    try:
        report = await runner.run(suite)
        trial = report.trials[0]
        assert trial.correctness_failed and trial.failure_stage == 'grading'
        assert [value.detail for value in trial.case_validation] == ['cell_value', '', '', '']
        stored = runner.connection.execute('SELECT payload_json FROM trials').fetchone()[0]
        assert 'cell_value' in stored and 'private workbook contents' not in stored and 'undeclared_code' not in stored
        assert (await runner.run(suite)).trials == report.trials
    finally:
        runner.connection.close()

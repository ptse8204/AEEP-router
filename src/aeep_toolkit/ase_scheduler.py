"""ASE owns scheduling/assertions; AEEP owns every actual controlled trial."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from aeep.assessment.models import (
    AssessmentLimits,
    AssessmentPlan,
    AssessmentSubject,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import require_scheduler
from aeep.benchmarking import BenchmarkTrial
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ResourceVector,
    SideEffect,
    StrictModel,
    utc_now,
)

from .ase_contract import ASE_ARTIFACT, ASE_REVISION, ASE_SOURCE_FILES
from .candidate import inspect
from .install_runtime import canonical, snapshot


class SchedulerObservation(StrictModel):
    definition_ref: str
    process_receipt_ref: str
    trial_refs: dict[str, str]
    grade_summaries: dict[str, dict[str, int | float]]
    grading_semantics: str = "ASE assertion over the existing protected task-grade certificate"
    upstream_timing_is_compatibility_only: bool = True


class ControlledScheduler:
    grading_semantics = SchedulerObservation.model_fields["grading_semantics"].default

    def validate_definition(self) -> None:
        raise NotImplementedError

    def prepare_payload(
        self, workspace: Path, trial_ids: tuple[str, ...], token: str
    ) -> dict[str, object]:
        raise NotImplementedError

    def requested_slot(self, message: dict[str, Any], token: str) -> str:
        raise NotImplementedError

    def certificate(self, slot: str, trial: BenchmarkTrial, token: str) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError

    def validate_completion(
        self, output: object, trials: dict[str, BenchmarkTrial], token: str
    ) -> dict[str, dict[str, int | float]]:
        raise NotImplementedError

    def __init__(self, repository: AssessmentRepository, plan: AssessmentPlan):
        self.repository, self.plan = repository, plan
        if plan.scheduler_digest is None:
            raise ConfigurationError("external evaluator is absent from the frozen plan")
        self.definition_digest = plan.scheduler_digest
        self.definition = require_scheduler(repository, self.definition_digest)
        self.validate_definition()
        self.require_runtime()

    def authorize(self) -> None:
        self.repository.authorize(self.plan)
        if require_scheduler(self.repository, self.definition_digest) != self.definition:
            raise ConfigurationError("scheduler changed after preparation")
        self.require_runtime()

    def require_runtime(self) -> None:
        if snapshot(Path(self.definition.runtime_root)) != self.definition.runtime_tree_digest:
            raise ConfigurationError("scheduler runtime tree changed after installation")

    async def coordinate(
        self, trial_ids: tuple[str, ...], execute: Callable[[str], Awaitable[BenchmarkTrial | None]]
    ) -> None:
        self.authorize()
        definition, repository, plan = self.definition, self.repository, self.plan
        if not 1 <= len(trial_ids) <= definition.maximum_requests:
            raise ConfigurationError("scheduler trial ceiling exceeded")
        workspace = canonical(definition.workspace)
        if workspace.exists() or not workspace.parent.is_dir():
            raise ConfigurationError("scheduler workspace exists; inspect prior work, never replay")
        operation = plan.plan_id + ":external-scheduler"
        repository.reserve(
            plan,
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=definition.overhead_seconds),
            stage="external_scheduler",
        )
        began, started_at = time.perf_counter(), utc_now()
        nested = 0.0
        raw = None
        receipt_ref = None
        error = None
        executor = None
        handle = None
        server = None
        trials: dict[str, BenchmarkTrial] = {}
        grade_summaries = {}
        try:
            workspace.mkdir(mode=0o700)
            for directory in ("responses", "home", "tmp"):
                (workspace / directory).mkdir(mode=0o700)
            token = content_digest(
                {"plan": content_digest(plan), "scheduler": self.definition_digest}
            )
            payload = self.prepare_payload(workspace, trial_ids, token)
            queue: asyncio.Queue[str] = asyncio.Queue(maxsize=6)
            buffer = bytearray()

            def observe(chunk: bytes) -> None:
                buffer.extend(chunk)
                if len(buffer) > 65536:
                    raise ConfigurationError("scheduler protocol frame exceeds its bound")
                while b"\n" in buffer:
                    line, _, rest = buffer.partition(b"\n")
                    buffer[:] = rest
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ConfigurationError("scheduler protocol requires an object")
                    if message.get("kind") == "done":
                        continue
                    queue.put_nowait(self.requested_slot(message, token))

            async def dispatch() -> None:
                nonlocal nested
                for slot in trial_ids:
                    if await queue.get() != slot:
                        raise ConfigurationError(
                            "scheduler reordered, repeated or invented a trial"
                        )
                    self.authorize()
                    clock = time.perf_counter()
                    try:
                        trial = await execute(slot)
                    finally:
                        nested += time.perf_counter() - clock
                    # Missing/uncertain execution remains unknown, never an ASE failure score.
                    if trial is None or trial.state != "complete" or type(trial.valid) is not bool:
                        raise ConfigurationError("canonical trial is skipped or unresolved")
                    trials[slot] = trial
                    name, response = self.certificate(slot, trial, token)
                    target = workspace / "responses" / (name + ".json")
                    # Publish the complete record without replacing a child-created path.
                    temporary = target.with_suffix(".tmp")
                    fd = os.open(
                        temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(fd, "w") as stream:
                        json.dump(response, stream)
                    os.link(temporary, target, follow_symlinks=False)
                    temporary.unlink()

            action = ActionRequest(
                action_id=operation,
                capability=definition.executor.capability,
                input=payload,
            )
            context = ExecutionContext(
                request=action,
                spec=definition.executor,
                estimate=definition.executor.estimate,
                attempt=1,
                attempt_id=operation,
                approved_side_effect=SideEffect.WRITE,
                invocation_check=self.authorize,
            )
            executor = CommandExecutor(stdout_observer=observe)
            server = asyncio.create_task(dispatch())
            handle = await executor.start(context)
            completed, _ = await asyncio.wait(
                {server, handle.task}, return_when=asyncio.FIRST_COMPLETED
            )
            if server in completed:
                await server
                raw = await handle.task
            else:
                raw = await handle.task
                if not server.done():
                    raise ConfigurationError("scheduler ended before canonical trials completed")
                await server
            if (
                raw.status.value != "success"
                or len(trials) != len(trial_ids)
                or not queue.empty()
                or buffer
            ):
                raise ConfigurationError("upstream scheduler failed; receipts and charges retained")
            grade_summaries = self.validate_completion(raw.output, trials, token)
        except BaseException as caught:
            error = caught
        finally:
            if server is not None and not server.done():
                server.cancel()
                with suppress(asyncio.CancelledError):
                    await server
            if executor is not None and handle is not None and not handle.task.done():
                await executor.cancel(handle)
            if handle is not None:
                with suppress(asyncio.CancelledError):
                    raw = await handle.task
            if executor is not None:
                await executor.close()
            elapsed = max(0.0, time.perf_counter() - began - nested)
            if raw is not None:
                receipt = ExecutionReceipt(
                    decision_id=operation,
                    action_id=operation,
                    capability=definition.executor.capability,
                    executor_id=definition.executor.id,
                    executor_kind=definition.executor.kind,
                    status=raw.status,
                    started_at=started_at,
                    ended_at=utc_now(),
                    estimated=definition.executor.estimate,
                    actual_resources=raw.resources,
                    accounting=raw.accounting,
                    execution_success=error is None and raw.status.value == "success",
                    error_type=type(error).__name__ if error else raw.error_type,
                    metadata={
                        **raw.metadata,
                        "scheduler_definition": self.definition_digest,
                        "upstream_timing_excluded": True,
                        "stderr_sha256": hashlib.sha256((raw.stderr or "").encode()).hexdigest(),
                        "nested_intervals_excluded_seconds": nested,
                    },
                )
                repository.store.save_receipt(receipt)
                receipt_ref = repository.put("scheduler_receipt", operation, receipt)
            # Child SDK intervals exclude all awaited canonical trial intervals.
            repository.finish_operation(
                operation,
                elapsed_seconds=elapsed,
                accounting=raw.accounting if raw else None,
                resources=raw.resources.model_copy(update={"latency_ms": elapsed * 1000})
                if raw
                else ResourceVector(latency_ms=elapsed * 1000),
            )
        if error is not None:
            raise ConfigurationError(
                "controlled scheduling stopped; inspect canonical evidence"
            ) from error
        assert receipt_ref is not None
        observation = SchedulerObservation(
            definition_ref=self.definition_digest,
            process_receipt_ref=receipt_ref,
            trial_refs={slot: content_digest(trial) for slot, trial in trials.items()},
            grade_summaries=grade_summaries,
            grading_semantics=self.grading_semantics,
        )
        repository.put("scheduler_observation", plan.plan_id, observation)


class AgentSkillEvalCoordinator(ControlledScheduler):
    def validate_definition(self) -> None:
        if (
            self.definition.adapter_id != "agent-skill-eval.controlled.v1"
            or self.definition.source_revision != ASE_REVISION
            or self.definition.artifact_sha256 != ASE_ARTIFACT
        ):
            raise ConfigurationError("scheduler differs from the reviewed ASE contract")
        expected_argv = [
            "/usr/bin/sandbox-exec",
            "-f",
            self.definition.boundary_profile,
            str(Path(self.definition.runtime_root) / "bin/python"),
            "-I",
            "-B",
            "-m",
            "aeep_toolkit.ase_child",
        ]
        if self.definition.executor.config["argv"] != expected_argv:
            raise ConfigurationError("scheduler entrypoint differs from the reviewed child")
        for name, expected in ASE_SOURCE_FILES.items():
            matches = [
                value
                for path, value in self.definition.executable_dependencies.items()
                if path.endswith("/" + name)
            ]
            if matches != [expected]:
                raise ConfigurationError("scheduler must bind every pinned ASE source file")

    def prepare_payload(
        self, workspace: Path, trial_ids: tuple[str, ...], token: str
    ) -> dict[str, object]:
        subject = AssessmentSubject.model_validate(
            self.repository.get("subject", self.plan.subject_digest)
        )
        payload = inspect(Path(subject.location))
        if payload.describe()["files"] != subject.dependency_digests:
            raise ConfigurationError(
                "scheduler candidate snapshot differs from the canonical subject"
            )
        (workspace / "candidate").mkdir(mode=0o700)
        # The candidate copy is coordinator metadata only. Actual exposure
        # continues to be verified in the existing isolated worker profiles.
        mapping = ReviewedMapping.model_validate(self.repository.get("mapping", self.plan.mapping_digest))
        invocation = mapping.candidate.managed_host_config().invocation
        if invocation is None or invocation.mode != "skill" or not invocation.skill_name:
            raise ConfigurationError("ASE bridge requires the reviewed primary skill mapping")
        skill_name = invocation.skill_name
        payload.stage(workspace / "candidate" / skill_name)
        evaluations = workspace / "candidate" / skill_name / "evals"
        evaluations.mkdir()
        (evaluations / "evals.json").write_text(
            json.dumps(
                {
                    "skill_name": skill_name,
                    "evals": [
                        {
                            "id": slot,
                            "prompt": slot,
                            "expected_output": "Canonical protected task grade",
                            "assertions": [
                                {
                                    "type": "json_path",
                                    "json_path": "canonical_valid",
                                    "equals": True,
                                }
                            ],
                        }
                        for slot in trial_ids
                    ],
                }
            )
        )
        return {
            "slots": list(trial_ids),
            "run_token": token,
            "skill_name": skill_name,
            "response_timeout": float(self.definition.executor.config["timeout_seconds"]),
        }

    def requested_slot(self, message: dict[str, Any], token: str) -> str:
        if (
            set(message) != {"kind", "slot", "run_token"}
            or message["kind"] != "trial"
            or message["run_token"] != token
            or not isinstance(message["slot"], str)
        ):
            raise ConfigurationError("scheduler requested an unreviewed operation")
        return message["slot"]

    def certificate(self, slot: str, trial: BenchmarkTrial, token: str) -> tuple[str, dict[str, Any]]:
        return slot, {
            "run_token": token,
            "slot": slot,
            "trial_ref": content_digest(trial),
            "canonical_valid": trial.valid,
        }

    def validate_completion(
        self, output: object, trials: dict[str, BenchmarkTrial], token: str
    ) -> dict[str, dict[str, int | float]]:
        grade_summaries = {}
        if (
            not isinstance(output, dict)
            or set(output) != {"kind", "grades", "upstream_timing_is_compatibility_only"}
            or output["kind"] != "done"
            or output["upstream_timing_is_compatibility_only"] is not True
            or len(output["grades"]) != len(trials)
        ):
            raise ConfigurationError("upstream grader completion differs from its contract")
        for slot, grade in zip(trials, output["grades"], strict=True):
            expected = int(trials[slot].valid is True)
            summary = {
                "passed": expected,
                "failed": 1 - expected,
                "total": 1,
                "pass_rate": float(expected),
                "skipped": 0,
            }
            if grade != {"slot": slot, "summary": summary} or any(
                type(grade["summary"][key]) is not type(value) for key, value in summary.items()
            ):
                raise ConfigurationError(
                    "upstream grade differs from the canonical protected grade"
                )
            grade_summaries[slot] = summary
        return grade_summaries

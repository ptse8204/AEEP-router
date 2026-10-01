"""Recover local worker resources without replaying an uncertain candidate invocation."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from ..errors import ConfigurationError
from ..models import StrictModel, new_id, utc_now
from .containment import ContainerExecutor
from .models import AssessmentEnvironment, content_digest
from .repository import AssessmentRepository

if TYPE_CHECKING:
    from .service import AssessmentService


class AssessmentWorker(StrictModel):
    assessment_id: str
    pid: int
    process_started_at: float


class RecoveryRecord(StrictModel):
    recovery_id: str
    assessment_id: str
    retained_attempt_ids: list[str]
    containers_removed: int
    elapsed_seconds: float


def worker_record(assessment_id: str) -> AssessmentWorker:
    return AssessmentWorker(assessment_id=assessment_id, pid=os.getpid(), process_started_at=psutil.Process().create_time())


def worker_alive(repository: AssessmentRepository, assessment_id: str) -> bool | None:
    try:
        worker = AssessmentWorker.model_validate(repository.get("worker", assessment_id))
    except ConfigurationError:
        return None
    try:
        process = psutil.Process(worker.pid)
        return process.create_time() == worker.process_started_at and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return None


async def recover(service: AssessmentService, assessment_id: str) -> RecoveryRecord:
    job = service.status(assessment_id)
    if job["state"] == "running" or worker_alive(service.repository, assessment_id) is True:
        raise ConfigurationError("cannot recover a live assessment worker")
    started = time.perf_counter()
    plan = service.repository.get("plan", job["plan_id"])
    environment = AssessmentEnvironment.model_validate(service.repository.get("environment", plan["environment_digest"]))
    root = (service.directory / plan["plan_id"]).resolve()
    campaign = root / "campaign.sqlite3"
    attempts: list[str] = []
    removed = 0
    if campaign.is_file():
        connection = sqlite3.connect(campaign.as_uri() + "?mode=ro", uri=True)
        try:
            stores = connection.execute("SELECT DISTINCT database_path FROM trial_stores").fetchall()
        finally:
            connection.close()
        for (name,) in stores:
            path = Path(name)
            resolved = await asyncio.to_thread(path.resolve)
            if resolved != path or not resolved.is_relative_to(root / "attempts"):
                raise ConfigurationError("trial store lies outside this assessment")
            store = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                rows = store.execute("SELECT attempt_id FROM execution_attempts WHERE state IN ('CLAIMED','RESERVED','INVOKING','VALIDATING','SETTLING','INDETERMINATE')").fetchall()
            finally:
                store.close()
            for (attempt_id,) in rows:
                attempts.append(attempt_id)
                if environment.kind == "container":
                    removed += int(await ContainerExecutor(environment).cleanup(attempt_id))
    record = RecoveryRecord(recovery_id=new_id("recovery"), assessment_id=assessment_id, retained_attempt_ids=attempts, containers_removed=removed, elapsed_seconds=time.perf_counter() - started)
    service.repository.put("recovery", record.recovery_id, record)
    return record


def record_worker_locked(repository: AssessmentRepository, assessment_id: str) -> None:
    record = worker_record(assessment_id)
    repository.store._connection.execute("INSERT INTO assessment_records VALUES ('worker', ?, ?, ?)", (assessment_id, content_digest(record), record.model_dump_json()))


def mark_dead_worker(repository: AssessmentRepository, assessment_id: str) -> None:
    if worker_alive(repository, assessment_id) is False:
        with repository.store._immediate_transaction() as connection:
            changed = connection.execute("UPDATE assessment_jobs SET state='indeterminate', error_code='worker_disappeared' WHERE id=? AND state='running'", (assessment_id,)).rowcount
            if changed:
                connection.execute("UPDATE assessment_admissions SET revoked=1, revoked_at=? WHERE admission_id IN (SELECT id FROM assessment_records WHERE kind='admission' AND json_extract(payload_json, '$.report_id') IN (SELECT report_id FROM assessment_jobs WHERE id=?))", (utc_now().isoformat(), assessment_id))

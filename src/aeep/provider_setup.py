"""Operator-registered, non-charging provider readiness and setup handoffs.

Login stays with the host/provider. These checks never read Codex authentication
or interpret successful authentication as qualification or permission to spend.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

import httpx
from pydantic import Field, model_validator

from .assessment.models import content_digest
from .assessment.repository import AssessmentRepository
from .errors import ConfigurationError
from .executors.network import validate_http_url
from .models import StrictModel, new_id, utc_now
from .store import ReceiptStore


def implementation_digest() -> str:
    return 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ProviderSetupDefinition(StrictModel):
    schema_version: Literal['aeep.provider-setup.v1'] = 'aeep.provider-setup.v1'
    setup_id: str = Field(pattern=r'^[A-Za-z0-9_.:-]+$', max_length=100)
    adapter: Literal['https-readiness', 'local-runtime', 'host-managed']
    adapter_revision: str | None = Field(default=None, pattern=r'^sha256:[a-f0-9]{64}$')
    endpoint: str | None = None
    secret_env: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    executable: str | None = None
    executable_digest: str | None = Field(default=None, pattern=r'^sha256:[a-f0-9]{64}$')
    version_args: list[str] = Field(default_factory=list, max_length=8)
    auth_url: str | None = None
    billing_url: str | None = None
    documentation_url: str | None = None
    billing_credit_pointer: str | None = Field(default=None, pattern=r'^/[^\s]{1,200}$')
    required_checks: list[Literal['connectivity', 'authentication', 'billing', 'runtime']] = Field(default=['connectivity'])
    non_charging: bool = False
    timeout_seconds: float = Field(default=10, gt=0, le=30)
    valid_seconds: int = Field(default=300, ge=1, le=3600)

    @model_validator(mode='after')
    def boundary(self) -> ProviderSetupDefinition:
        for value in (self.endpoint, self.auth_url, self.billing_url, self.documentation_url):
            if value:
                url = httpx.URL(value)
                if url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment:
                    raise ValueError('setup URLs must be credential-free HTTPS without query or fragment')
        if self.secret_env and any(word in self.secret_env.upper() for word in ('CODEX', 'COOKIE', 'PASSWORD')):
            raise ValueError('host authentication cannot be a provider secret binding')
        if self.adapter == 'https-readiness' and not self.endpoint:
            raise ValueError('HTTPS readiness requires an exact reviewed non-charging endpoint')
        if self.adapter == 'local-runtime' and (not self.executable or not self.executable_digest or not self.version_args):
            raise ValueError('local runtime requires a pinned executable and reviewed version arguments')
        if self.executable and not Path(self.executable).is_absolute():
            raise ValueError('runtime executable must be absolute')
        return self


class ProviderSetupCheck(StrictModel):
    check_id: str = Field(default_factory=lambda: new_id('setup_check'))
    definition_digest: str
    started_at: datetime = Field(default_factory=utc_now)


class ProviderSetupObservation(StrictModel):
    schema_version: Literal['aeep.provider-setup-observation.v1'] = 'aeep.provider-setup-observation.v1'
    check_id: str
    observation_id: str = Field(default_factory=lambda: new_id('setup'))
    setup_id: str
    definition_digest: str
    observed_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    checks: dict[Literal['connectivity', 'authentication', 'billing', 'runtime'], Literal['ready', 'blocked', 'unknown']]
    elapsed_ms: float = Field(ge=0)
    status: Literal['complete', 'cancelled', 'failed']
    cash_usd: Literal[0] = 0
    limitations: list[str] = Field(default_factory=lambda: ['Connectivity is not qualification, admission or payment authority.'])


class SetupAdapter(Protocol):
    async def check(self, definition: ProviderSetupDefinition) -> dict[str, str]: ...


class HTTPSReadinessAdapter:
    async def check(self, definition: ProviderSetupDefinition) -> dict[str, str]:
        assert definition.endpoint is not None
        checks = {'connectivity': 'unknown', 'authentication': 'unknown', 'billing': 'unknown'}
        headers = {'accept': 'application/json'}
        if definition.secret_env:
            secret = os.environ.get(definition.secret_env)
            if not secret:
                return {**checks, 'authentication': 'blocked'}
            headers['authorization'] = 'Bearer ' + secret
        url = httpx.URL(definition.endpoint)
        await validate_http_url(definition.endpoint, {'allowed_hosts': [url.host]}, label='provider readiness')
        async with (
            httpx.AsyncClient(timeout=definition.timeout_seconds, follow_redirects=False, trust_env=False) as client,
            client.stream('GET', definition.endpoint, headers=headers) as response,
        ):
            # No raw provider body or account/billing data enters the result.
            checks['connectivity'] = 'ready'
            if response.status_code in {401, 403}:
                checks['authentication'] = 'blocked'
            elif 200 <= response.status_code < 300:
                checks['authentication'] = 'ready' if definition.secret_env else 'unknown'
                if definition.billing_credit_pointer:
                    import json
                    import math

                    from .workflow import pointer_get
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ConfigurationError('provider readiness response exceeds limit')
                    credit = pointer_get(json.loads(body), definition.billing_credit_pointer)
                    if type(credit) not in {int, float} or not math.isfinite(credit) or credit < 0:
                        raise ConfigurationError('provider credit observation is invalid')
                    checks['billing'] = 'ready' if credit > 0 else 'blocked'

            else:
                checks['connectivity'] = 'blocked'
        return checks


class LocalRuntimeAdapter:
    async def check(self, definition: ProviderSetupDefinition) -> dict[str, str]:
        assert definition.executable is not None
        executable = Path(definition.executable)
        def matches() -> bool:
            if not executable.is_file() or executable.is_symlink():
                return False
            with executable.open('rb') as stream:
                return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == definition.executable_digest
        if not await asyncio.to_thread(matches):
            return {'runtime': 'blocked', 'connectivity': 'blocked'}
        process = await asyncio.create_subprocess_exec(str(executable), *definition.version_args,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, env={'PATH': os.defpath})
        try:
            await asyncio.wait_for(process.wait(), definition.timeout_seconds)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        state = 'ready' if process.returncode == 0 else 'blocked'
        return {'runtime': state, 'connectivity': state}


class HostManagedSetupAdapter:
    """Injected by the host integration, never dynamically imported from metadata."""
    def __init__(self, check: Callable[[ProviderSetupDefinition], Awaitable[dict[str, str]]], *, revision: str) -> None:
        self._check = check
        self.revision = revision

    async def check(self, definition: ProviderSetupDefinition) -> dict[str, str]:
        return await self._check(definition)


class ProviderSetupService:
    def __init__(self, store: ReceiptStore, *, host_adapter: SetupAdapter | None = None) -> None:
        self.store = store
        self.repository = AssessmentRepository(store)
        self.adapters: dict[str, SetupAdapter] = {'https-readiness': HTTPSReadinessAdapter(), 'local-runtime': LocalRuntimeAdapter()}
        if host_adapter:
            self.adapters['host-managed'] = host_adapter

    def _revision(self, adapter: str) -> str | None:
        registered = self.adapters.get(adapter)
        if isinstance(registered, HostManagedSetupAdapter):
            return registered.revision
        return implementation_digest() if registered is not None else None

    def define(self, definition: ProviderSetupDefinition) -> str:
        if definition.adapter_revision is None:
            definition.adapter_revision = self._revision(definition.adapter)
        definition = ProviderSetupDefinition.model_validate(definition.model_dump())
        return self.repository.put('provider_setup', definition.setup_id, definition)

    def inspect(self, identity: str) -> dict[str, object]:
        definition = ProviderSetupDefinition.model_validate(self.repository.get('provider_setup', identity))
        return {'setup_id': definition.setup_id, 'definition_digest': content_digest(definition),
                'auth_url': definition.auth_url, 'billing_url': definition.billing_url,
                'documentation_url': definition.documentation_url, 'required_checks': definition.required_checks,
                'adapter_supported': definition.adapter in self.adapters,
                'ready': self.ready(identity), 'handoff': 'Complete sign-in or billing setup in the provider/host interface, then recheck. Do not paste credentials.'}

    def ready(self, identity: str) -> bool:
        try:
            definition = ProviderSetupDefinition.model_validate(self.repository.get('provider_setup', identity))
        except ConfigurationError:
            return False
        if definition.adapter_revision is None or definition.adapter_revision != self._revision(definition.adapter):
            return False
        digest = content_digest(definition)
        with self.store._lock:
            review = self.store._connection.execute('SELECT 1 FROM assessment_reviews WHERE digest=? AND revoked=0', (digest,)).fetchone()
            rows = self.store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='provider_setup_observation'").fetchall()
        if not review:
            return False
        matching = [ProviderSetupObservation.model_validate_json(row[0]) for row in rows]
        matching = [item for item in matching if item.setup_id == definition.setup_id and item.definition_digest == digest]
        if not matching:
            return False
        latest = max(matching, key=lambda item: item.observed_at)
        return (latest.status == 'complete' and utc_now() < latest.expires_at and
                all(latest.checks.get(check) == 'ready' for check in definition.required_checks))

    async def check(self, identity: str) -> ProviderSetupObservation:
        import time
        definition = ProviderSetupDefinition.model_validate(self.repository.get('provider_setup', identity))
        digest = content_digest(definition)
        with self.store._lock:
            reviewed = self.store._connection.execute('SELECT 1 FROM assessment_reviews WHERE digest=? AND revoked=0', (digest,)).fetchone()
        if not reviewed or not definition.non_charging:
            raise ConfigurationError('setup check requires exact operator review and a non-charging contract')
        adapter = self.adapters.get(definition.adapter)
        if definition.adapter_revision is None or definition.adapter_revision != self._revision(definition.adapter):
            raise ConfigurationError('setup adapter changed or unavailable; a new exact definition review is required')
        if adapter is None:
            raise ConfigurationError('setup adapter unavailable; host integration required')
        check = ProviderSetupCheck(definition_digest=digest)
        self.repository.put('provider_setup_check', check.check_id, check)
        started = time.monotonic()
        status = 'complete'
        checks: dict[str, str] = {}
        try:
            async with asyncio.timeout(definition.timeout_seconds):
                raw = await adapter.check(definition)
                for key in ('connectivity', 'authentication', 'billing', 'runtime'):
                    if key in raw:
                        if raw[key] not in {'ready', 'blocked', 'unknown'}:
                            raise ConfigurationError('invalid readiness observation')
                        checks[key] = raw[key]
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception:
            # Provider exceptions may contain credentials or account data.
            status = 'failed'
        finally:
            observation = ProviderSetupObservation.model_validate(dict(check_id=check.check_id, setup_id=definition.setup_id,
                definition_digest=digest, expires_at=utc_now() + timedelta(seconds=definition.valid_seconds),
                checks=checks, elapsed_ms=(time.monotonic() - started) * 1000, status=status))
            self.repository.put('provider_setup_observation', observation.observation_id, observation)
        return observation

    @staticmethod
    def storage_preflight(target: Path, additional_bytes: int = 0) -> None:
        if additional_bytes < 0 or shutil.disk_usage(target).free - additional_bytes < 50 * 1024**3:
            raise ConfigurationError('operation would cross the 50 GiB host storage reserve')

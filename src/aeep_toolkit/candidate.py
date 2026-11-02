"""Capture exactly the local skill bytes that may later reach a reviewed worker."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXCLUDED = frozenset({'evals', '.git', '__pycache__'})
PROTECTED = frozenset({'.codex', '.ssh', '.aws', '.azure', '.gnupg', '.docker', '.config', '.npm'})


def identity(files: dict[str, bytes]) -> str:
    if 'SKILL.md' not in files or not 1 <= len(files) <= 512 or sum(map(len, files.values())) > 8 * 1024**2:
        raise ValueError('skill payload requires SKILL.md, at most 512 files and at most 8 MiB')
    folded = set()
    for name, raw in files.items():
        path = Path(name)
        if (not name or len(name) > 512 or path.is_absolute() or '..' in path.parts or '\\' in name
                or str(path) != name or any(part.casefold() in EXCLUDED | PROTECTED for part in path.parts)
                or name.casefold() in folded or not isinstance(raw, bytes)
                or path.name.casefold() in {'auth.json', 'credentials.json'} or path.name.casefold().startswith('.env')):
            raise ValueError('unsafe or ambiguous candidate payload path')
        folded.add(name.casefold())
    manifest = {name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class CandidatePayload:
    files: dict[str, bytes]
    sha256: str

    def describe(self) -> dict[str, Any]:
        if identity(self.files) != self.sha256:
            raise ValueError('captured candidate payload changed')
        return {'candidate_sha256':self.sha256, 'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(self.files.items())},
                'payload_bytes':sum(map(len,self.files.values())), 'excluded_directories':sorted(EXCLUDED),
                'executed':False, 'notice':'Local byte identity only; no developer verification, installation, safety or value qualification.'}

    def stage(self, destination: Path) -> None:
        from .install_runtime import canonical

        self.describe()
        canonical(str(destination))
        if any(part.casefold() in PROTECTED for part in destination.parts):
            raise ValueError('candidate staging excludes credential-state directories')
        if destination.exists():
            raise ValueError('staging requires a new directory')
        destination.mkdir(mode=0o700)
        for name, raw in sorted(self.files.items()):
            target = destination/name
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with target.open('xb') as handle:
                handle.write(raw)


def inspect(path: Path) -> CandidatePayload:
    from .cli import read_bytes
    from .install_runtime import canonical

    root = path.parent if path.name == 'SKILL.md' else path
    canonical(str(root))
    if any(part.casefold() in PROTECTED for part in root.parts):
        raise ValueError('credential-state directories are excluded')
    if not root.is_dir():
        raise ValueError('candidate must be a canonical local directory or SKILL.md')
    files: dict[str, bytes] = {}
    entries = 0
    for directory, directories, names in os.walk(root,followlinks=False):
        directories[:] = sorted(name for name in directories if name.casefold() not in EXCLUDED)
        for name in [*directories, *names]:
            entries += 1
            if entries > 1024:
                raise ValueError('candidate tree exceeds the bounded inventory')
            selected = Path(directory)/name
            info = selected.lstat()
            if stat.S_ISDIR(info.st_mode):
                if name.casefold() in PROTECTED:
                    raise ValueError('credential-state directories are excluded')
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('candidate links and special files are excluded')
            if name.casefold() in {'auth.json', 'credentials.json'} or name.casefold().startswith('.env'):
                raise ValueError('credential-state files are excluded')
            files[str(selected.relative_to(root))] = read_bytes(selected)
            if len(files) > 512 or sum(map(len,files.values())) > 8 * 1024**2:
                raise ValueError('candidate payload exceeds bounds')
    return CandidatePayload(files,identity(files))



def stage_subject(source: Path, destination: Path, manifest: Path | None = None) -> dict[str, Any]:
    """Copy the captured public skill payload; optionally reuse canonical inspection."""
    import time

    from aeep.component_setup import require_space

    began, cpu = time.perf_counter(), time.process_time()
    payload = inspect(source)
    require_space(destination, sum(len(raw) for raw in payload.files.values()) + 1024**2)
    payload.stage(destination)
    result = {**payload.describe(), 'staged_path': str(destination), 'subject_ref': None,
              'subject_id': None, 'setup_cost_ref': None, 'execution_authorized': False}
    if manifest is None:
        result['preparation_wall_seconds'] = time.perf_counter() - began
        result['preparation_process_cpu_ms'] = (time.process_time() - cpu) * 1000
        result['canonical_cost_coverage'] = 'NOT_RECORDED'
        return result
    import asyncio

    from aeep.assessment.models import AssessmentSetupCost, content_digest
    from aeep.assessment.service import AssessmentService
    from aeep.router import Router

    router = Router.from_manifest(manifest)
    elapsed, used = time.perf_counter() - began, (time.process_time() - cpu) * 1000
    try:
        service = AssessmentService(router, manifest.parent / '.aeep' / 'assessments')
        subject = service.inspect_local(destination, kind='skill')
        if subject.dependency_digests != payload.describe()['files']:
            raise ValueError('staged candidate changed during canonical inspection; preserve the copy')
        cost = AssessmentSetupCost(subject_digest=content_digest(subject), stage='candidate_payload_preparation',
                                   elapsed_seconds=elapsed, cpu_ms=used)
        ref = service.repository.put('setup_cost', cost.cost_id, cost)
        return {**result, 'subject_ref': content_digest(subject), 'subject_id': subject.subject_id,
                'setup_cost_ref': ref, 'canonical_cost_coverage':
                'Captured preparation and canonical static inspection; final persistence/Router close excluded. No grant created.'}
    finally:
        asyncio.run(router.close())

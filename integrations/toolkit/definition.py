"""Capture the reviewed inputs of a synthetic upstream evaluation, without effects."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from aeep_toolkit.candidate import CandidatePayload, inspect
from aeep_toolkit.cli import read_json
from aeep_toolkit.models import ContractModel, SourcePin


class Case(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,39}$')
    prompt: str = Field(min_length=1, max_length=8192)
    expected_output: str = Field(max_length=512)
    force_skill_invocation: Literal[False] = False
    side_effect_level: Literal['static'] = 'static'
    assertions: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def literal_assertions(self):
        for assertion in self.assertions:
            if (not assertion.startswith('The output contains `') or not assertion.endswith('`')
                    or not 1 <= len(assertion) <= 512 or assertion.count('`') != 2
                    or not assertion[len('The output contains `'):-1]):
                raise ValueError('offline suite supports only nonempty literal contains assertions')
        return self


class Suite(ContractModel):
    skill_name: str = Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    retain_outputs: bool = Field(default=False, strict=True)
    evals: tuple[Case, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def unique_positions(self):
        if len({case.id for case in self.evals}) != len(self.evals) or len({case.prompt for case in self.evals}) != len(self.evals):
            raise ValueError('case IDs and prompts must each be unique')
        return self

    def upstream(self):
        return {'skill_name': self.skill_name,
                'evals': [case.model_dump(mode='json') | {'force_skill_invocation': False, 'side_effect_level': 'static'} for case in self.evals]}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Inputs:
    candidate: CandidatePayload
    suite: Suite
    source: SourcePin
    sha256: str

    def binding(self):
        candidate = self.candidate.describe()
        return {'candidate': candidate, 'suite_sha256': digest(self.suite.model_dump(mode='json')),
                'source': self.source.model_dump(mode='json'), 'cases':len(self.suite.evals),
                'trials':2*len(self.suite.evals), 'retain_outputs':self.suite.retain_outputs, 'model_turns':0, 'evidence_kind':'synthetic',
                'notice':'Scripted harness checks only; candidate instructions are not interpreted by a model.'}

    def verify(self):
        if self.source.artifact_sha256 != self.candidate.sha256 or digest(self.binding()) != self.sha256:
            raise ValueError('captured candidate or suite changed after review')

    def worker_payload(self):
        self.verify()
        return {'name':self.suite.skill_name,'sha256':self.candidate.sha256,
                'files':{name:base64.b64encode(raw).decode('ascii') for name,raw in self.candidate.files.items()}}


def prepare(candidate: Path, suite: Path, source: SourcePin) -> Inputs:
    captured = inspect(candidate)
    selected = Suite.model_validate(read_json(suite))
    root = candidate.parent if candidate.name == 'SKILL.md' else candidate
    if root.name != selected.skill_name or source.artifact_sha256 != captured.sha256:
        raise ValueError('selected skill name or source identity differs from captured candidate')
    result = Inputs(captured,selected,source,'')
    result = Inputs(captured,selected,source,digest(result.binding()))
    payload = result.worker_payload()
    if any(len(json.dumps({'prompt':case.prompt,'skill':payload}).encode()) > 60000 for case in selected.evals):
        raise ValueError('candidate and task exceed the bounded synthetic worker input')
    return result

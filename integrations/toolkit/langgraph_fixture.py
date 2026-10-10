"""Finite operator-owned LangGraph worker; launch only through a reviewed executor."""
from __future__ import annotations

import json
import sys
from importlib.metadata import version
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(max_length=2000)
    case: Literal['upper', 'lower']
    suffixes: int = Field(ge=0, le=3)


class State(TypedDict):
    text: str
    case: str
    remaining: int
    steps: int


def normalize(state: State) -> dict:
    return {'text': state['text'].upper() if state['case'] == 'upper' else state['text'].lower(), 'steps': state['steps']+1}


def suffix(state: State) -> dict:
    return {'text': state['text']+'!', 'remaining': state['remaining']-1, 'steps': state['steps']+1}


def successor(state: State) -> str:
    return 'suffix' if state['remaining'] else 'end'


def execute(payload: Input) -> dict:
    if version('langgraph') != '1.2.14':
        raise ValueError('unsupported LangGraph runtime; artifact pin is checked by the outer executor review')
    from langgraph.graph import END, START, StateGraph
    builder = StateGraph(State)
    builder.add_node('normalize', normalize)
    builder.add_node('suffix', suffix)
    builder.add_edge(START, 'normalize')
    for node in ('normalize', 'suffix'):
        builder.add_conditional_edges(node, successor, {'suffix': 'suffix', 'end': END})
    graph = builder.compile()
    result = graph.invoke({'text': payload.text, 'case': payload.case, 'remaining': payload.suffixes, 'steps': 0},
                          {'recursion_limit': 8})
    return {'text': result['text'], 'steps': result['steps']}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('oversized workflow input')
        result = execute(Input.model_validate_json(raw))
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception:
        # Do not copy input text or dependency diagnostics to durable output.
        print('{"error":"workflow_unavailable_or_failed"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

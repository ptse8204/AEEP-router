"""Validate the owned worker contract; never stand in for actual LangGraph execution."""
import pytest
from langgraph_fixture import Input, execute, normalize, successor, suffix


def test_bounded_input_and_pure_nodes():
    value = Input(text='Example', case='upper', suffixes=2)
    state = {'text': value.text, 'case': value.case, 'remaining': value.suffixes, 'steps': 0}
    state.update(normalize(state))
    assert state['text'] == 'EXAMPLE'
    state.update(suffix(state))
    assert successor(state) == 'suffix'
    state.update(suffix(state))
    assert successor(state) == 'end'
    assert state['text'] == 'EXAMPLE!!' and state['steps'] == 3
    assert normalize({**state, 'case': 'lower'})['text'] == 'example!!'
    for changed in ({'suffixes': 4}, {'suffixes': True}, {'text': 'x'*2001}, {'case': 'shell'}, {'code': 'bad'}):
        with pytest.raises(ValueError):
            Input(**(value.model_dump() | changed))


def test_missing_or_other_version_does_not_import_engine(monkeypatch):
    monkeypatch.setattr('langgraph_fixture.version', lambda name: '0.0')
    with pytest.raises(ValueError, match='unsupported'):
        execute(Input(text='test', case='lower', suffixes=0))

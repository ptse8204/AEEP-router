"""One operator CLI delegates to the existing explicit backends."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aeep_toolkit import cli, managed


def test_managed_cli_delegates_without_process_or_fallback(monkeypatch):
    calls=[]
    monkeypatch.setattr(managed,'main',lambda argv:calls.append(argv))
    monkeypatch.setattr(cli.subprocess,'run',lambda *args,**kwargs:pytest.fail('managed facade must not spawn a helper'))
    assert cli.main(['eval','managed','plan','--plan','input.json','--source','source.json'])==0
    assert calls==[['plan','--plan','input.json','--source','source.json']]


def test_scripted_cli_uses_fixed_owned_script_and_keeps_failure(monkeypatch):
    calls=[]
    monkeypatch.setattr(cli,'__file__',str(Path.cwd()/'src/aeep_toolkit/cli.py'))
    def run(argv,*,check):
        calls.append((argv,check))
        return SimpleNamespace(returncode=7)
    monkeypatch.setattr(cli.subprocess,'run',run)
    assert cli.main(['eval','scripted','report','--output','spaces and $(literal)'])==7
    assert calls==[([sys.executable,'-B',str(Path.cwd()/'integrations/toolkit/evaluate.py'),'report','--output','spaces and $(literal)'],False)]


def test_uninstalled_scripted_backend_is_explicit_and_never_substituted(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(cli,'__file__',str(tmp_path/'src/aeep_toolkit/cli.py'))
    monkeypatch.setattr(cli.subprocess,'run',lambda *args,**kwargs:pytest.fail('unavailable backend executed'))
    monkeypatch.setattr(managed,'main',lambda *args:pytest.fail('backend silently switched'))
    with pytest.raises(SystemExit) as error:
        cli.main(['eval','scripted','plan'])
    assert error.value.code==2 and 'unavailable in this installation' in capsys.readouterr().err


def test_backend_choice_is_required(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(['eval','plan'])
    assert error.value.code==2 and 'invalid choice' in capsys.readouterr().err

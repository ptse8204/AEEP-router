from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest


def test_marketplace_launcher_requires_setup_and_executes_fixed_runtime(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / '.agents/plugins/marketplace.json').read_text())
    plugin = root / catalog['plugins'][0]['source']['path']
    mcp = json.loads((plugin / '.mcp.json').read_text())['mcpServers']['aeep']
    assert mcp == {'command': 'python3', 'args': ['${PLUGIN_ROOT}/serve.py']}
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    launch = runpy.run_path(str(plugin / 'serve.py'))['main']
    with pytest.raises(SystemExit, match='setup is incomplete'):
        launch()
    runtime = tmp_path / '.local/share/aeep/venv/bin/python'
    manifest = tmp_path / '.config/aeep/config.yaml'
    for path in (runtime, manifest):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    calls = []
    monkeypatch.setattr('os.execv', lambda executable, argv: calls.append((executable, argv)))
    launch()
    assert calls == [(str(runtime), [str(runtime), '-m', 'aeep', 'serve',
                                    '--transport', 'stdio', '--profile', 'legacy',
                                    '--manifest', str(manifest)])]

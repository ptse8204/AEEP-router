"""Offline scoped environment/argv construction check; no native/model launch."""
import ast,hashlib,json,os,tempfile
from contextlib import contextmanager
from pathlib import Path
from aeep.hosts.codex_sandbox import NativeSandboxConfig
ROOT=Path(__file__).resolve().parents[2];p=ROOT/'reports/v08/native-model-resource-baseline-tmpdir-ade3.py'
tree=ast.parse(p.read_text());nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in {'scoped_process_environment','tempfile_preflight_program'}];ns={'os':os,'contextmanager':contextmanager};exec(compile(ast.Module(body=nodes,type_ignores=[]),'scoped-baseline-helper','exec'),ns)
python=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve();binary=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='aeep-owned-env-check-',dir=ROOT) as td:
 root=Path(td).resolve();scratch=root/'scratch';scratch.mkdir();boundary=NativeSandboxConfig(binary=str(binary),binary_sha256='sha256:'+sha(binary),project_root=str(root),read_roots=[str(python.parents[1])],write_roots=[str(scratch)],single_process=True,python_binary=str(python),python_sha256='sha256:'+sha(python));configured=boundary.validate_environment({'TMPDIR':str(scratch),'TMP':str(scratch),'TEMP':str(scratch)})
 before={key:os.environ.get(key) for key in configured}
 with ns['scoped_process_environment'](configured):assert all(os.environ[key]==value for key,value in configured.items())
 assert {key:os.environ.get(key) for key in configured}==before
 try:
  with ns['scoped_process_environment'](configured):raise RuntimeError('owned restoration check')
 except RuntimeError:pass
 assert {key:os.environ.get(key) for key in configured}==before
 compile(ns['tempfile_preflight_program'](scratch),'native-tempfile-check','exec')
print('Offline exact scratch validation + normal/error environment restoration + native preflight program compilation PASS; no native propagation result inferred.')

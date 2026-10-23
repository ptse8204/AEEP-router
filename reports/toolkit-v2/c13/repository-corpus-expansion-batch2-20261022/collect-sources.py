"""Reuse the pinned Git-blob collector for two additional inert source scopes."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[4]
here = Path(__file__).resolve().parent
prior = here.parent / 'repository-corpus-expansion-20261022/collect-tree-scopes.py'
spec = importlib.util.spec_from_file_location('aeep_pinned_git_blob_collector', prior)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = here
module.CACHE = root / '.aeep/repository-corpus-tree-scopes-batch2-20261022'
module.IDENTITIES = ['tobymao__sqlglot-6374', 'tobymao__sqlglot-7479']
module.main()

"""Reuse existing exact cached-wheel preparation; do not install."""
import importlib.util,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
old=HERE.parent/'workflow-skillrank-20261103/prepare-package.py'
spec=importlib.util.spec_from_file_location('existing_exact_package_preparation',old)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

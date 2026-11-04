"""Isolated Python entrypoint with only the reviewed helper directory on sys.path."""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
runpy.run_path(str(HERE / 'vendor-cli.py'), run_name='__main__')

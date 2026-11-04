"""Reuse reviewed task, skill and scheduler bytes; no new upstream implementation."""
import importlib.util
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
LAST=HERE.parent/'worker-readiness-correction-20261103'
sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('reviewed_worker_helpers',LAST/'integration.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
for name in ('OLD','sha','load','write','inspect','recipe','scheduler','snapshot','RUNTIME','PARENT_TAG',
             'PARENT_ID','GRADER','TAG','TOOLS','SCHEDULER_WORK','ASE_REVISION','ASE_ARTIFACT'):
 globals()[name]=getattr(previous,name)
CANDIDATE=LAST/'candidate'
WORK=ROOT/'.aeep/integration-snapshot-correction-20261103'

def pair(image,source=None):
 return previous.pair(image,source or load(HERE/'context.json')['source'])

"""Private package-preparation context only; no installation or execution."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
WORK=ROOT/'.aeep/workflow-telemetry-20261104/package'
sys.path.insert(0,str(ROOT/'src'))
def load(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

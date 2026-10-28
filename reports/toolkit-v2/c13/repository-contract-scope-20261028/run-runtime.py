"""Run a fresh approved worker profile on the retained image; never build or retry."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    assert len(sys.argv)==2 and sha(HERE/'operation-review.json')==sys.argv[1]
    review=json.loads((HERE/'operation-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert verification_source_digest(ROOT)==review['source_digest']
    for path,expected in review['assets'].items():assert sha(Path(path))==expected and not Path(path).is_symlink()
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro',uri=True) as connection:
        before=list(connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    save(HERE/'review-budget-anchor.json',{'grant_before':before,'scope':'One cumulative initial phase and any explicit recorded same-software control continuation;not a fresh allowance per plan.'})
    canary=ROOT/review['host_canary'];assert not canary.exists()
    canary.parent.mkdir(exist_ok=True);marker=b'AEEP reviewed contract-scope host-only canary; no secret.\n'
    with canary.open('xb') as stream:stream.write(marker)
    try:
        with (HERE/'runtime-execution.log').open('x') as log:
            result=subprocess.run([sys.executable,str(HERE/'run.py'),sys.argv[1]],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=review['maximum_reserved_seconds']+60)
        assert result.returncode==0,'Preserve terminal result;no automatic retry'
        with (HERE/'runtime-audit.log').open('x') as log:
            result=subprocess.run([sys.executable,str(HERE/'audit-execution.py')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        assert result.returncode==0,'Canonical reconciliation failed;stop dispatch'
    finally:
        assert canary.is_file() and not canary.is_symlink() and canary.read_bytes()==marker
        canary.unlink();save(HERE/'canary-cleanup.json',{'unchanged_owned_canary_removed':True})

if __name__=='__main__':main()

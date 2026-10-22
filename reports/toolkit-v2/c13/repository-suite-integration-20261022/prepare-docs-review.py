"""Prepare cached checker metadata and run only the first-party OS sandbox probe."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
OLD = ROOT / 'reports/toolkit-v2/integration-completion/lychee-repository-audit-review-20261021'
OUT = OLD.parent / 'lychee-repository-suites-review-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 100 * 1024**2
    review = json.loads((OLD / 'operation-review.json').read_text())
    archive = Path(review['archive_path'])
    assert sha(archive) == review['archive_sha256'] and archive.stat().st_size == review['archive_bytes']
    with tarfile.open(archive) as bundle:
        member = bundle.getmember(review['binary_member'])
        assert member.isfile() and member.size == review['binary_bytes']
        assert hashlib.sha256(bundle.extractfile(member).read()).hexdigest() == review['binary_sha256']
    for name in ('run-review.py', 'sandbox-template.sb', 'sandbox-preflight.py'):
        shutil.copyfile(OLD / name, OUT / name)
    with tempfile.TemporaryDirectory(prefix='aeep-docs-preflight-', dir='/private/tmp') as temporary:
        scratch = Path(temporary).resolve()
        (scratch / 'home').mkdir()
        (scratch / 'tmp').mkdir()
        profile = (OUT / 'sandbox-template.sb').read_text()
        for key, value in {'HOME':scratch/'home','TMP':scratch/'tmp','ROOT':ROOT,
            'AEEP':ROOT/'.aeep','GIT':ROOT/'.git','CODEX':ROOT/'.codex'}.items():
            profile = profile.replace('@'+key+'@', json.dumps(str(value)))
        path = scratch / 'profile.sb'
        path.write_text(profile)
        result = subprocess.run(['/usr/bin/sandbox-exec','-f',str(path),sys.executable,'-I','-B',
            str(OUT/'sandbox-preflight.py'),str(ROOT),str(scratch)], capture_output=True, text=True, timeout=20,
            env={'PATH':'/usr/bin:/bin','HOME':str(scratch/'home'),'TMPDIR':str(scratch/'tmp')})
        checks = json.loads(result.stdout) if result.stdout else {}
        record = {'passed':result.returncode==0 and bool(checks) and all(checks.values()),
            'checks':checks,'returncode':result.returncode,'stderr':result.stderr,'external_binary_executed':False,
            'probe_sha256':sha(OUT/'sandbox-preflight.py'),'temporary_scratch_removed':False}
    record['temporary_scratch_removed'] = not scratch.exists()
    (OUT/'sandbox-preflight.json').write_text(json.dumps(record,indent=2)+'\n')
    assert record['passed'] and record['temporary_scratch_removed']
    review.update(authority='Pending exact repository-suite execution bundle; no earlier terminal approval reused.',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        source_digest=verification_source_digest(ROOT),runner_sha256=sha(OUT/'run-review.py'),
        sandbox_template_sha256=sha(OUT/'sandbox-template.sb'),sandbox_preflight_sha256=sha(OUT/'sandbox-preflight.py'),
        makefile_sha256=sha(ROOT/'Makefile'),config_sha256=sha(ROOT/'.lychee.toml'),
        previous_terminal_review_sha256=sha(OLD/'operation-review.json'),
        preflight_reused_from=None,execution_started=False)
    # Expand the exact Makefile list as data; no checker execution.
    lines = subprocess.check_output(['make','--no-print-directory','-n','docs-links','LYCHEE=/aeep-not-executed'],cwd=ROOT,text=True).splitlines()
    review['documents'] = lines[-1].split()[3:]
    assert 'README.md' in review['documents'] and 'docs/aeep-toolkit/REPOSITORY_EVALUATION.md' in review['documents']
    assert all((ROOT/name).is_file() for name in review['documents'])
    with (OUT/'operation-review.json').open('x') as stream:
        json.dump(review,stream,indent=2);stream.write('\n')
    print(json.dumps({'review_sha256':sha(OUT/'operation-review.json'),'documents':len(review['documents']),
        'first_party_probe_passed':True,'external_binary_executed':False}))


if __name__ == '__main__':
    main()

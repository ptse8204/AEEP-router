"""Bind the cached offline documentation checker; never execute it in preparation."""
import hashlib,json,subprocess
from pathlib import Path
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'lychee-test-roots-review-20261027'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'operation-review.json').exists()
    review=json.loads((OLD/'operation-review.json').read_text())
    assert sha(Path(review['archive_path']))==review['archive_sha256']
    assert json.loads((HERE/'sandbox-preflight.json').read_text())['passed']
    assert json.loads((ROOT/'reports/toolkit-v2/c13/repository-large-archives-20261027/validation/source-stability.json').read_text())['all_passed']
    review.update(authority='Pending exact larger-repository runtime/package/docs bundle; no earlier terminal approval reused.',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),source_digest=verification_source_digest(ROOT),
        runner_sha256=sha(HERE/'run-review.py'),sandbox_template_sha256=sha(HERE/'sandbox-template.sb'),sandbox_preflight_sha256=sha(HERE/'sandbox-preflight.py'),
        makefile_sha256=sha(ROOT/'Makefile'),config_sha256=sha(ROOT/'.lychee.toml'),previous_terminal_review_sha256=sha(OLD/'operation-review.json'),preflight_reused_from=None,execution_started=False)
    review['document_sha256']={name:sha(ROOT/name) for name in review['documents']}
    (HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'documents':len(review['documents']),'cached_archive_bytes':review['archive_bytes'],'execution_started':False}))


if __name__=='__main__':main()

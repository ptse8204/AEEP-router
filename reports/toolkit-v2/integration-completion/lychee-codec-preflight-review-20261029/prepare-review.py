"""Bind cached checker and current documentation; never execute external software."""
import hashlib
import json
import subprocess
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / 'lychee-shared-native-review-20261028'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (HERE / 'operation-review.json').exists()
review = json.loads((OLD / 'operation-review.json').read_text())
assert sha(Path(review['archive_path'])) == review['archive_sha256']
assert json.loads((HERE / 'sandbox-preflight.json').read_text())['passed']
for name in ('sandbox-template.sb', 'sandbox-preflight.py', 'sandbox-preflight.json'):
    assert sha(HERE / name) == sha(OLD / name)
assert sha(ROOT / 'Makefile') == review['makefile_sha256']
assert sha(ROOT / '.lychee.toml') == review['config_sha256']
# No standalone checker version replay: the same binary's retained version record
# and the Makefile's own mandatory version check cover this invocation.
review.update(
    authority='Pending exact codec-preflight wheel/docs bundle; no preceding approval transferred.',
    source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
    source_digest=verification_source_digest(ROOT),
    runner_sha256=sha(HERE / 'run-review.py'),
    previous_terminal_review_sha256=sha(OLD / 'operation-review.json'),
    preflight_reused_from=str(OLD / 'sandbox-preflight.json'),
    actions=[
        'Extract only the exact cached executable into one new owned private runtime.',
        'Run Makefile version check and offline link scan through the unchanged sandbox; use cached markdownlint0.23.3.',
        'Retain logs and hashes; remove only the unchanged private runtime; retain archive and other resources.',
    ],
    scope_limits=[
        'No online URL validation, installation, download, models, credentials, services or release.',
        'Release hash and source license records do not prove binary build provenance.',
        'The exact listed documentation hashes are checked before execution; changed inputs require a recorded applicable review.',
    ],
    execution_started=False,
)
review['limits']['maximum_binary_invocations'] = 2
review['document_sha256'] = {name: sha(ROOT / name) for name in review['documents']}
(HERE / 'operation-review.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps({'review_file_sha256': sha(HERE / 'operation-review.json'),
    'documents': len(review['documents']), 'execution_started': False}))

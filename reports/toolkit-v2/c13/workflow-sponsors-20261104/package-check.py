"""Use the installed CLI and shipped schema with the pinned funding declaration."""
import contextlib
import hashlib
import io
import json
import sys
import sysconfig
from pathlib import Path

from aeep.assessment import verification
from aeep_toolkit.cli import main
from aeep_toolkit.sponsors import SponsorReview

expected = json.load(sys.stdin)['installed_source']
package = Path(sysconfig.get_path('data'))
assert verification.verification_source_digest(Path(verification.__file__).resolve().parents[3]) == expected
schema = json.loads((package / 'share/aeep/schemas/toolkit-sponsor-review.schema.json').read_bytes())
assert schema == SponsorReview.model_json_schema()
reviewed = hashlib.sha256(Path('sponsors-review.json').read_bytes()).hexdigest()
arguments = [
    'export-preview', '--evidence', 'no-observations.json', '--disclose-source',
    '--sponsors-review', 'sponsors-review.json', '--reviewed-digest', reviewed,
]
printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    assert main(arguments) == 0
data = json.loads(printed.getvalue())['document']
assert data['developer']['status'] == 'reviewed_source_declaration'
assert data['developer']['assertion']['assertion_ref'] == reviewed
assert data['developer']['assertion']['support_url'] == 'https://github.com/sponsors/DietrichGebert'
assert data['outcome'] == 'NOT_ASSESSED' and data['cohorts'] == []
assert not data['publication_performed']
with contextlib.redirect_stderr(io.StringIO()):
    try:
        main([*arguments[:-1], '0' * 64])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError('installed CLI accepted a mismatched review')
print(json.dumps({'passed': True, 'installed_source': expected,
                  'checks': ['installed source', 'shipped schema', 'actual pinned funding',
                             'no evaluation outcome inferred', 'mismatched review denied'],
                  'models': 0}))

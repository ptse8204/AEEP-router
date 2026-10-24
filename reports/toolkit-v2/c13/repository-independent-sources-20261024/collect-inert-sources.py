"""Reuse bounded source triage; never install or execute the reviewed subjects."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
REPOSITORIES = {
    'agronholm/sqlacodegen', 'azuread/microsoft-authentication-library-for-python',
    'brianpugh/cyclopts', 'jonathonreinhart/scuba', 'lmstudio-ai/lmstudio-python',
    'model-bakers/model_bakery', 'octodns/octodns', 'openlawlibrary/pygls',
    'pypa/twine', 'python-babel/babel', 'sloria/sphinx-issues',
    'ucfopen/canvasapi', 'valohai/valohai-cli',
}


def main():
    manifest = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json').read_text())
    inventory = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json').read_text())
    eligible = {x['instance_id'] for x in inventory['rows'] if not x['metadata_blockers']}
    prior = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-workload-batch-20261022/combined-source-review.json').read_text())
    previous = {r['instance_id'] for r in prior['sources']}
    identities = set()
    for source in manifest['sources']:
        import hashlib
        data = (ROOT / source['private_cache']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source['sha256']
        for item in json.loads(data)['rows']:
            row = item['row']
            if (row['repo'].casefold() in REPOSITORIES and row['instance_id'] in eligible
                    and row['instance_id'] not in previous
                    and all(n.startswith('tests/') for n in row['FAIL_TO_PASS'] + row['PASS_TO_PASS'])):
                identities.add(row['instance_id'])
    assert 0 < len(identities) <= 50
    specification = importlib.util.spec_from_file_location('bounded_inert_source_triage', HERE.parent / 'repository-workload-batch-20261022/collect-sources.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.HERE = HERE
    module.CACHE = ROOT / '.aeep/repository-independent-sources-20261024'
    module.EXPLICIT_SQLGLOT = identities
    module.REPOSITORIES = ()
    module.main()


if __name__ == '__main__':
    main()

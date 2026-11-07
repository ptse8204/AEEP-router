"""Bind private protected grades to the two allowed workflow changes."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.models import ValidationSpec
from aeep.validators import ValidationContext, run_validators

import variants

HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent / 'optimizer-directory-correction'
ROOT = HERE.parents[5]
WORK = ROOT / '.aeep' / 'proposal-optimizer-preparation-20261105' / 'calibration-finite-cycle'
VARIANTS = ('reject_duplicate', 'keep_first')


def encode(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def certify():
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    preparation = json.loads((HERE.parent / 'calibration-preparation.json').read_bytes())
    public_path = HERE.parent / 'public-cases.json'
    assert sha(public_path) == preparation['public_cases_sha256']
    reference_path = WORK.parent / 'protected-calibration/reference.json'
    assert sha(reference_path) == preparation['protected_reference_sha256']
    capture = json.loads((CAPTURE / 'result.json').read_bytes())
    assert capture['passed'] and not capture['models'] and not capture['generated_code_executed']
    protected = json.loads(reference_path.read_bytes())
    public = json.loads(public_path.read_bytes())['cases']
    assert len(public) == len(protected['definitions']) == 3
    certificates = {}
    for policy in VARIANTS:
        variants.POLICY = policy
        outputs, observed = [], []
        for case, expected in zip(public, protected['definitions'], strict=True):
            assert case['id'] == expected['case_id'] and content_digest(case['input']) == expected['input_sha256']
            output = await variants.Workflow()(**case['input'])
            results = await run_validators([ValidationSpec.model_validate(expected['validator'])],
                                           ValidationContext(case['input'], output), {}, raise_errors=True)
            outputs.append(output)
            observed.append(results[0].valid)
        certificates[policy] = {'passed': sum(observed), 'cases': len(observed),
                                'outputs_sha256': hashlib.sha256(encode(outputs)).hexdigest()}
    assert certificates['reject_duplicate']['passed'] == 3 and certificates['keep_first']['passed'] == 2
    assert len({cert['outputs_sha256'] for cert in certificates.values()}) == 2
    return certificates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-private', action='store_true')
    args = parser.parse_args()
    certificates = asyncio.run(certify())
    if args.write_private:
        WORK.mkdir(mode=0o700)
        path = WORK / 'certificates.json'
        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o444), 'wb') as stream:
            stream.write(encode(certificates))
        print(json.dumps({'contract': 'first_party_protected_calibration', 'policies': len(certificates),
                          'cases_per_policy': 3, 'certificates_sha256': sha(path), 'models': 0}))
    else:
        print(json.dumps({'policies': len(certificates), 'cases_per_policy': 3, 'models': 0}))


if __name__ == '__main__':
    main()

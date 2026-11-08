"""Measure nonroot scratch use around the unchanged protected React assertions."""

import json
import os
import runpy
import threading
from pathlib import Path

DRIVER = Path('/opt/aeep-react-reference.py')


def used(path):
    stat = os.statvfs(path)
    return (stat.f_blocks - stat.f_bfree) * stat.f_frsize


def main():
    result = {'passed': False, 'models': 0, 'network': 'loopback only',
              'official_reproduction': False, 'uid': os.geteuid(), 'gid': os.getegid()}
    assert (result['uid'], result['gid']) == (65534, 65534)
    scratch = ('/tmp', '/dev/shm')
    baseline = {path: used(path) for path in scratch}
    peaks = dict(baseline)
    stop = threading.Event()

    def sample():
        for path in scratch:
            peaks[path] = max(peaks[path], used(path))

    def monitor():
        while not stop.wait(0.05):
            sample()

    sampler = threading.Thread(target=monitor, daemon=True)
    sampler.start()
    try:
        runpy.run_path(str(DRIVER), run_name='react_reference_probe')['run'](result)
    except Exception as error:
        result.update(passed=False, error_type=type(error).__name__)
    finally:
        stop.set()
        sampler.join()
        sample()
    result['sample_interval_ms'] = 50
    result['peak_used_bytes_above_start'] = {path: peaks[path] - baseline[path] for path in scratch}
    result['original_verifier_assertions'] = 11
    print(json.dumps(result, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

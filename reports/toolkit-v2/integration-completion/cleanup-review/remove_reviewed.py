"""Delete only the exact inactive pytest roots after separate operator approval."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def inspect(path):
    entries = []
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            item = Path(parent) / name
            stat = item.lstat()
            entries.append([str(item.relative_to(path)), stat.st_mode, stat.st_size,
                            stat.st_mtime_ns, stat.st_ino])
    entries.sort()
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approve-review-sha256', required=True)
    args = parser.parse_args()
    raw = (HERE / 'review.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.approve_review_sha256
    review = json.loads(raw)
    allowed = {'pytest-908', 'pytest-911', 'pytest-1003'}
    assert {Path(item['path']).name for item in review['entries']} == allowed
    assert len(review['entries']) == 3
    assert not (HERE / 'cleanup-result.json').exists()
    for item in review['entries']:
        path = Path(item['path'])
        assert path.is_dir() and not path.is_symlink()
        stat = path.stat()
        assert (stat.st_dev, stat.st_ino, stat.st_uid) == (item['device'], item['inode'], item['uid'])
        assert (path / '.lock').read_text().strip() == item['lock_pid']
        check = subprocess.run(['ps', '-p', item['lock_pid'], '-o', 'pid='], capture_output=True, text=True)
        assert check.returncode == 1 and not check.stdout.strip()
        assert inspect(path) == item['metadata_sha256']
    result = {'review_sha256': args.approve_review_sha256,
              'free_bytes_before': shutil.disk_usage(HERE).free, 'removed': []}
    with (HERE / 'cleanup-started.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    for item in review['entries']:
        path = Path(item['path'])
        assert inspect(path) == item['metadata_sha256']
        shutil.rmtree(path)
        assert not path.exists()
        result['removed'].append(str(path))
        result['free_bytes_after'] = shutil.disk_usage(HERE).free
        (HERE / 'cleanup-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

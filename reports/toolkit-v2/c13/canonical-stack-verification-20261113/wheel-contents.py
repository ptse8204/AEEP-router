"""Verify the previously built wheel offline without installing dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(wheel, dependency_root, work, proof):
    expected = json.loads(proof.read_bytes())
    assert expected["passed"] and expected["built_artifacts"][wheel.name] == sha(wheel)
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    work.mkdir(mode=0o700)
    prefix = work / "wheel"
    prefix.mkdir(mode=0o700)
    with zipfile.ZipFile(wheel) as package:
        names = set()
        for item in package.infolist():
            p = PurePosixPath(item.filename)
            assert p.parts and not p.is_absolute() and ".." not in p.parts and str(p) not in names
            names.add(str(p))
            assert item.file_size <= 32 * 1024**2
        package.extractall(prefix)
    py = Path(sys.executable).resolve()
    script = work / "check.py"
    script.write_text(
        "from pathlib import Path\nimport sys, json, sqlite3, contextlib, io\n"
        f"sys.path[:0] = [{str(prefix)!r}, {str(dependency_root)!r}]\n"
        "from aeep_toolkit.cli import main\nfrom aeep.store import ReceiptStore\n"
        "from aeep_toolkit.stack_readiness import REQUIRED_CHECKS\n"
        f"assert Path(sys.modules['aeep_toolkit'].__file__).is_relative_to(Path({str(prefix)!r}))\n"
        f"path=Path({str(work/'receipt.sqlite3')!r})\n"
        "with ReceiptStore(path): pass\n"
        "with ReceiptStore(path, read_only=True) as store:\n"
        "    assert store._connection.execute('SELECT count(*) FROM assessment_records').fetchone()[0]==0\n"
        "out=io.StringIO()\nwith contextlib.redirect_stdout(out): assert main(['stack-status'])==0\n"
        "assert len(json.loads(out.getvalue())['components'])==19\n"
        "assert sum(map(len, REQUIRED_CHECKS.values()))==39\n"
        "print(json.dumps({'contents_imported':True,'existing_database_read_only':True,'requirements':39,'models':0}))\n"
    )
    profile=work/"offline.sb"
    policy=["(version 1)","(allow default)","(deny network*)","(deny file-write*)",
        f'(allow file-write* (subpath {json.dumps(str(work))}) (literal "/dev/null"))',
        '(deny file-read* (subpath "/Users"))',
        f'(allow file-read* (subpath {json.dumps(str(work))}) (subpath {json.dumps(str(dependency_root))}))',
    ]
    metadata={p for name in (work,dependency_root) for p in name.parents if str(p).startswith("/Users")}
    policy.append("(allow file-read-metadata " + " ".join(f"(literal {json.dumps(str(p))})" for p in sorted(metadata)) + ")")
    profile.write_text("\n".join(policy)+"\n")
    env={"PATH":"/usr/bin:/bin","HOME":str(work),"TMPDIR":str(work),"LC_ALL":"C"}
    inputs={str(p):sha(p) for p in (wheel,script,profile,py,Path('/usr/bin/sandbox-exec'))}
    review={"purpose":"First exact built-wheel contents smoke test in retained dependency runtime",
            "wheel_sha256":expected["built_artifacts"][wheel.name],"inputs":inputs,"network":False,"model_turns":0,
            "max_attempts":1,"runtime_installs":0}
    review_file=work/"operation-review.json"
    review_file.write_text(json.dumps(review,indent=2)+"\n")
    finished=subprocess.run(["/usr/bin/sandbox-exec","-f",str(profile),str(py),"-I","-B",str(script)],
        env=env,cwd=work,capture_output=True,timeout=30)
    result={"review_sha256":sha(review_file),"wheel_sha256":sha(wheel),"exit_code":finished.returncode,
            "runtime_installs":0,"model_turns":0,"network":False}
    if finished.returncode:
        result.update(passed=False,stdout_sha256=hashlib.sha256(finished.stdout).hexdigest(),
                      stderr_sha256=hashlib.sha256(finished.stderr).hexdigest())
        (work/"stderr.log").write_bytes(finished.stderr)
    else:
        result.update(passed=True,observations=json.loads(finished.stdout))
    (work/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    return int(not result["passed"])


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("wheel",type=Path)
    parser.add_argument("dependency_root",type=Path)
    parser.add_argument("work",type=Path)
    parser.add_argument("proof",type=Path)
    args=parser.parse_args()
    raise SystemExit(check(args.wheel.resolve(),args.dependency_root.resolve(),args.work.resolve(),args.proof.resolve()))

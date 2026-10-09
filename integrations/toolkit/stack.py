"""Reproducible development stack; only the checked-in synthetic suite can run."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from aeep_toolkit.cli import read_json

BASE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return read_json(path)


def manifest() -> dict:
    data = read(BASE / "stack.json")
    for name, expected in {data["lock_file"]: data["lock_sha256"], "packages.json": data["packages_sha256"], **data["fixtures"]}.items():
        if digest(BASE / name) != expected:
            raise ValueError("Stack inputs changed; review and regenerate the lock before execution")
    if data["fixture_source"]["artifact_sha256"] != data["fixtures"]["fixtures/format-json/SKILL.md"]:
        raise ValueError("Fixture provenance does not match the reviewed candidate")
    packages = read(BASE / "packages.json")
    expected_lock = {f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}" for item in packages}
    lines = (BASE / data["lock_file"]).read_text().splitlines()
    if set(lines) != expected_lock or len(lines) != len(packages):
        raise ValueError("Package inventory does not match the complete wheel lock")
    return data


def require_host() -> None:
    if (sys.platform, platform.machine(), sys.version_info[:2]) != ("darwin", "arm64", (3, 13)):
        raise ValueError("This development lock is qualified only for macOS arm64 / Python 3.13")
    if shutil.disk_usage(BASE).free < 50 * 1024**3 + 500 * 1024**2:
        raise ValueError("The stack needs 500 MiB above the host's 50 GiB reserve")


def command(argv: list[str], *, cwd: Path, env: dict | None = None, timeout: int = 120) -> str:
    with subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, start_new_session=True) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ValueError("Stack command timed out; its process group was stopped") from None
    if process.returncode:
        raise ValueError(f"Stack command failed ({process.returncode}): {output[-4000:]}")
    return output


def verify_runtime(runtime: Path, stack: dict) -> dict:
    from runtime import inspect_runtime

    facts = inspect_runtime(runtime, stack, read(BASE / "packages.json"))
    if facts["blockers"]:
        raise ValueError("Installed runtime differs from reviewed metadata/source; inspect inventory before execution")
    return facts


def setup(runtime: Path, stack: dict) -> None:
    if runtime.exists():
        raise ValueError("Choose a new runtime directory; existing environments are preserved")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(runtime.parent).free < 50 * 1024**3 + 500 * 1024**2:
        raise ValueError("Insufficient space on the runtime filesystem")
    venv.EnvBuilder(with_pip=True).create(runtime)
    log = command([str(runtime / "bin/python"), "-m", "pip", "--isolated", "install",
                   "--only-binary=:all:", "--no-deps", "--require-hashes", "-r",
                   str(BASE / stack["lock_file"])], cwd=BASE, timeout=300)
    (runtime / "installation.log").write_text(log)
    facts = verify_runtime(runtime, stack)
    (runtime / "aeep-stack.json").write_text(json.dumps(facts, indent=2) + "\n")
    print(f"Installed and verified {len(facts['versions'])} pinned packages in {runtime}")


def sandbox(root: Path, runtime: Path) -> tuple[list[str], dict]:
    for name in ("home", "tmp"):
        (root / name).mkdir()
    profile = root / "fixture.sb"
    # Allow the selected runtime if the operator installed it beneath their home.
    quote = json.dumps
    profile.write_text(f"""(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath {quote(str(root))}))
(allow file-write* (literal "/dev/null"))
(deny file-read* (subpath {quote(str(Path.home().resolve()))}))
(allow file-read* (subpath {quote(str(runtime))}))
""")
    env = {"PATH": "/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin",
           "DEVELOPER_DIR": "/Library/Developer/CommandLineTools", "HOME": str(root / "home"),
           "TMPDIR": str(root / "tmp"), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHON_DOTENV_DISABLED": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "en_US.UTF-8"}
    return ["/usr/bin/sandbox-exec", "-f", str(profile), str(runtime / "bin/python"), "-B"], env


def probe(prefix: list[str], env: dict, root: Path) -> dict:
    # Read a harmless known source file, never real credentials, to check home denial.
    code = """import pathlib,socket,json,sys
checks={}
try:pathlib.Path(sys.argv[1]).read_text()
except PermissionError:checks['home_read_denied']=True
with socket.socket() as sock:
 try:sock.connect(('127.0.0.1',9))
 except PermissionError:checks['network_connect_denied']=True
p=pathlib.Path('probe.txt');p.write_text('fixture');checks['scratch_write']=p.read_text()=='fixture'
try:pathlib.Path(sys.argv[2]).write_text('unexpected')
except PermissionError:checks['outside_write_denied']=True
print(json.dumps(checks))
"""
    outside = root.parent / (root.name + "-outside-probe")
    facts = json.loads(command([*prefix, "-c", code, str(BASE / "stack.json"), str(outside)], cwd=root, env=env))
    if outside.exists():
        outside.unlink()  # Only this probe's unique path, never an existing user file.
    if len(facts) != 4 or not all(facts.values()):
        raise ValueError("Fixture sandbox preflight failed; upstream execution refused")
    return facts


def collect(iteration: Path) -> list[dict]:
    suite = read(BASE / "fixtures/format-json/evals/evals.json")
    rows = []
    subjects = set()
    expected_paths = set()
    for case in suite["evals"]:
        for arm in ("without_skill", "with_skill"):
            directory = iteration / f"eval-{case['id']}" / "fake" / arm
            expected_paths.add(directory / "run_meta.json")
            meta, timing, grading = [read(directory / name) for name in
                                     ("run_meta.json", "timing.json", "grading.json")]
            if (meta["eval_id"] != case["id"] or meta["agent"] != "fake"
                    or meta["harness_version"] != "0.7.0" or meta["model"] is not None
                    or meta["with_skill"] is not (arm == "with_skill")
                    or timing["exit_code"] != 0 or timing["timed_out"] or timing["retries"] != 0):
                raise ValueError("Incomplete or mismatched upstream trial")
            subjects.add(meta["skill_hash"])
            output = (directory / "outputs/output.txt").read_text()
            needle = case["assertions"][0].split("`")[1]
            passed = needle in output
            assertions = grading["assertion_results"]
            if (len(assertions) != 1 or assertions[0]["skipped"]
                    or assertions[0]["method"] != "deterministic"
                    or assertions[0]["passed"] is not passed):
                raise ValueError("Independent fixture check disagrees with upstream grading")
            trajectory = json.loads((directory / "trajectory.json").read_text())
            exposed = any(event["event"] == "skill_installed" for event in trajectory)
            if exposed != (arm == "with_skill"):
                raise ValueError("Candidate exposure does not match the selected arm")
            rows.append({"case": case["id"], "arm": arm, "verified": passed,
                         "exposed": exposed, "candidate_invoked": None,
                         "model_tokens": None, "model_wall_seconds": None, "actual_cash": None,
                         "evidence_kind": "synthetic", "artifact": str(directory.relative_to(iteration))})
    skill = (BASE / "fixtures/format-json/SKILL.md").read_bytes()
    expected_subject = hashlib.sha256(b"SKILL.md\0" + skill + b"\0").hexdigest()
    if subjects != {expected_subject} or set(iteration.rglob("run_meta.json")) != expected_paths:
        raise ValueError("Missing, extra or differently pinned trials")
    return rows


def report(output: Path, stack: dict, facts: dict, rows: list[dict], checks: dict) -> None:
    evidence = {"schema": "aeep.development-demo.v1", "evidence_kind": "synthetic",
                "outcome": "NOT_ASSESSED", "model_benefit": "Not assessed by fake-harness runs",
                "evaluator": stack["evaluator"], "environment": facts, "sandbox_checks": checks,
                "container_conformance": False, "canonical_receipts_connected": (output / "coordinator-receipt.json").exists(),
                "receipt_scope": "coordinator process only; no per-trial model accounting", "runs": rows,
                "implementation_sha256": {name: digest(BASE / name) for name in
                                          ("stack.py", "receipts.py", "runtime.py", "stack.json", "report.html", "packages.json", stack["lock_file"])}}
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    markdown = ["# AEEP development stack", "", "**Synthetic fixtures. Real model benefit: NOT ASSESSED.**", "",
                "The pinned external evaluator ran both arms. AEEP independently checked each fixture output.", "",
                "| Case | Arm | Verified fixture output | Candidate exposed |", "|---|---|---|---|"]
    table = []
    for row in rows:
        result = "Pass" if row["verified"] else "Fail"
        arm = "Control" if row["arm"] == "without_skill" else "Treatment"
        markdown.append(f"| {row['case']} | {arm} | {result} | {row['exposed']} |")
        table.append(f"<tr><td>{html.escape(row['case'])}</td><td>{arm}</td>"
                     f"<td><span class='{result.lower()}'>{result}</span></td>"
                     f"<td>{'Available' if row['exposed'] else 'Absent'}</td></tr>")
    markdown += ["", "The formatting difference is engineered into upstream's fake harness; it is not a measured skill benefit.",
                 "Model tokens, model time and actual billing are unavailable. Upstream fixture constants remain only in raw artifacts.",
                 "The batch has a canonical coordinator receipt; per-trial model accounting, Docker worker conformance and live trials remain unestablished."]
    (output / "report.md").write_text("\n".join(markdown) + "\n")
    template = (BASE / "report.html").read_text()
    page = template.replace("{{ROWS}}", "".join(table)).replace("{{PACKAGES}}", str(len(facts["versions"])))
    components = "".join("<tr>" + "".join(f"<td>{html.escape(item[key])}</td>" for key in
                                         ("function", "preferred_solution", "responsibility", "status")) + "</tr>"
                         for item in stack["recommended_components"])
    page = page.replace("{{COMPONENTS}}", components)
    page = page.replace("{{REVISION}}", html.escape(stack["evaluator"]["source_revision"]))
    (output / "index.html").write_text(page)
    artifacts = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "artifact-hashes.json").write_text(json.dumps(artifacts, indent=2) + "\n")


def demo(runtime: Path, output: Path, stack: dict) -> None:
    facts = verify_runtime(runtime, stack)
    output.mkdir(parents=True, exist_ok=False)
    (output / "runtime-inventory.json").write_text(json.dumps(facts, indent=2) + "\n")
    root = Path(tempfile.mkdtemp(prefix="aeep-stack-fixture-", dir="/tmp")).resolve()
    (output / "execution.json").write_text(json.dumps({"scratch": str(root), "status": "started"}) + "\n")
    try:
        shutil.copytree(BASE / "fixtures", root / "input")
        prefix, env = sandbox(root, runtime)
        checks = probe(prefix, env, root)
        args = ["-m", "agent_skill_eval", "run", "--skill", str(root / "input/format-json"),
                "--evals", str(root / "input/format-json/evals/evals.json"), "--agent", "fake",
                "--workspace", str(root / "output"), "--grader-model", "", "--baseline", "--runs", "1",
                "--concurrency", "1", "--retries", "0", "--timeout", "30"]
        import receipts

        log, receipt_id = asyncio.run(receipts.execute([*prefix, *args], root, env, output / "receipts.sqlite3"))
        (output / "upstream.log").write_text(log)
        iteration = root / "output/format-json-workspace/iteration-1"
        rows = collect(iteration)  # The upstream CLI may exit zero even if every trial errored.
        shutil.copytree(iteration, output / "upstream")
        upstream_report = command([*prefix, "-m", "agent_skill_eval", "report", "--workspace",
                                   str(root / "output/format-json-workspace"), "--format", "markdown"], cwd=root, env=env)
        (output / "upstream-report.md").write_text(upstream_report)
        receipts.normalize(
            output, stack, facts, rows, read(BASE / "fixtures/format-json/evals/evals.json"),
            receipt_id, digest(root / "fixture.sb"),
            hashlib.sha256(b"".join((BASE / name).read_bytes() for name in ("stack.py", "receipts.py", "runtime.py"))).hexdigest(),
            {str(p.relative_to(output)): digest(p) for p in sorted((output / "upstream").rglob("*")) if p.is_file()},
        )
        receipts.verify(output)
        shutil.rmtree(root)
        (output / "execution.json").write_text(json.dumps({"scratch": str(root), "status": "complete",
                                                           "argv": args, "scratch_removed": True}, indent=2) + "\n")
        report(output, stack, facts, rows, checks)
    except (OSError, ValueError, KeyError) as error:
        (output / "failure.json").write_text(json.dumps({"error": str(error), "scratch": str(root)}) + "\n")
        raise
    print(f"Verified synthetic stack demonstration: {output / 'index.html'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="Print the complete development stack without effects")
    plan.add_argument("--runtime", type=Path, help="Include a read-only installed-runtime observation")
    inventory = sub.add_parser("inventory", help="Read runtime package metadata and evaluator hashes without starting it")
    inventory.add_argument("--runtime", type=Path, required=True)
    install = sub.add_parser("setup", help="Install the reviewed lock into a new private runtime")
    install.add_argument("--runtime", type=Path, required=True)
    run = sub.add_parser("demo", help="Run only the pinned synthetic suite and write a local report")
    run.add_argument("--runtime", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify", help="Resolve saved synthetic evidence without executing upstream")
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            import receipts
            bundle = receipts.verify(args.output.expanduser().resolve())
            print(f"Verified {len(bundle.runs)} synthetic records and coordinator receipt; model benefit NOT_ASSESSED")
            return
        stack = manifest()
        if args.action == "plan":
            result = {**stack, "package_inventory": read(BASE / "packages.json")}
            if args.runtime is not None:
                from runtime import inspect_runtime
                result["runtime_inventory"] = inspect_runtime(args.runtime.expanduser().resolve(), stack, result["package_inventory"])
            print(json.dumps(result, indent=2))
            if result.get("runtime_inventory", {}).get("blockers"):
                raise SystemExit(2)
            return
        if args.action == "inventory":
            from runtime import inspect_runtime
            facts = inspect_runtime(args.runtime.expanduser().resolve(), stack, read(BASE / "packages.json"))
            print(json.dumps(facts, indent=2))
            if facts["blockers"]:
                raise SystemExit(2)
            return
        require_host()
        runtime = args.runtime.expanduser().resolve()
        if args.action == "setup":
            setup(runtime, stack)
        else:
            demo(runtime, args.output.expanduser().resolve(), stack)
    except (OSError, ValueError, KeyError) as error:
        if args.action in {"verify", "inventory", "plan"}:
            parser.exit(2, "Cannot validate toolkit evidence or runtime metadata; check the selected files and source pins.\n")
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()

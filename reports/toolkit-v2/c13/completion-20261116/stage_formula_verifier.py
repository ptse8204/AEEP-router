"""Stage the Formula Extraction reference and controls without executing upstream code."""

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PRIVATE = ROOT / ".aeep/completion-20261116"
SOURCE = PRIVATE / "skillsbench-independent-workbook-assets/latex-formula-extraction"
ASSETS = PRIVATE / "formula-offline-assets"
OUTPUT = ASSETS / "protected-fixtures"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError("reviewed formula asset changed")
    return data


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("reviewed formula source does not match the expected adaptation")
    return text.replace(before, after, 1)


def selectors(source):
    tree = ast.parse(source)
    return {
        f"test_outputs.py::{group.name}::{test.name}": ast.dump(test, include_attributes=False)
        for group in tree.body if isinstance(group, ast.ClassDef)
        for test in group.body if isinstance(test, ast.FunctionDef) and test.name.startswith("test_")
    }


def main():
    intake = json.loads((HERE / "formula-extraction-intake.json").read_bytes())
    pixel = json.loads((HERE / "formula-verifier-assessment.json").read_bytes())
    runtime = json.loads((ASSETS / "runtime-publications.json").read_bytes())
    if runtime["execution"] or runtime["installation"]:
        raise ValueError("offline artifacts are no longer in their reviewed intake state")
    pins = {entry["path"].split("latex-formula-extraction/", 1)[1]: entry["sha256"]
            for entry in intake["assets"]}
    original = pinned(SOURCE / "protected/verifier/test_outputs.py", pins["verifier/test_outputs.py"])
    corrected = pinned(SOURCE / "proposed-verifier-correction/test_outputs.py",
                       pixel["proposed_protected_correction"]["patched_verifier_sha256"])
    if corrected != replace_once(original.decode(), "return diff.getbbox() is None",
                                 "return diff.getbbox(alpha_only=False) is None").encode():
        raise ValueError("unexpected pixel correction")
    for name in ("latex_formula_extraction.md", "latex_paper.pdf"):
        corrected = replace_once(corrected.decode(), f'Path("/root/{name}")', f'Path.cwd() / "{name}"').encode()
    mathjax = runtime["mathjax"]
    corrected = replace_once(corrected.decode(),
        "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js", mathjax["bundle_url"])
    corrected = replace_once(corrected,
        "        self._tex_page = self._browser.new_page()\n",
        "        self._tex_page = self._browser.new_page()\n"
        '        def serve_mathjax(route):\n'
        '            script = Path.cwd() / "tex-svg.js"\n'
        '            if script.is_file():\n'
        '                route.fulfill(path=script, content_type="application/javascript")\n'
        '            else:\n'
        '                route.abort()\n'
        '        self._tex_page.route(MATHJAX_TEX_SVG_CDN, serve_mathjax)\n')
    tests = selectors(original)
    if len(tests) != 7 or tests != selectors(corrected):
        raise ValueError("offline adaptations must preserve all seven test bodies")
    compile(corrected, "protected-formula-verifier", "exec")
    pdf = pinned(SOURCE / "agent/environment/latex_paper.pdf", pins["environment/latex_paper.pdf"])
    solver = pinned(SOURCE / "protected/oracle/solve.sh", pins["oracle/solve.sh"]).decode()
    # Read the fixed oracle data without starting the upstream shell or verifier.
    formula = re.search(r"(?m)^cat > /root/latex_formula_extraction\.md <<'EOF'\n([\s\S]+?)\nEOF$", solver)
    if not formula:
        raise ValueError("oracle output envelope changed")
    lines = formula[1].splitlines()
    if not lines or len(set(lines)) != len(lines) or any(not line.startswith("$$") or not line.endswith("$$")
                                                       for line in lines):
        raise ValueError("published formula reference output drift")
    reference = "\n".join(lines) + "\n"
    wrong = replace_once(reference, r"\rho_1", r"\rho_9")
    incomplete = "\n".join(lines[:-1]) + "\n"
    if len(set(wrong.splitlines())) != len(lines):
        raise ValueError("wrong-value control must keep the original count and distinct formulas")
    script = pinned(ASSETS / "tex-svg.js", mathjax["bundle_sha256"])
    if not pdf.startswith(b"%PDF-") or not script:
        raise ValueError("protected input or renderer bundle invalid")
    OUTPUT.mkdir(mode=0o700)
    inputs = {"latex_paper.pdf": pdf, "tex-svg.js": script, "test_outputs.py": corrected.encode(),
              "reference.md": reference.encode(), "wrong-value.md": wrong.encode(),
              "incomplete.md": incomplete.encode()}
    for name, data in inputs.items():
        with (OUTPUT / name).open("xb") as output:
            output.write(data)
    rendered = next(test for test in tests if test.endswith("::test_formulas_render_match_expected"))
    count = next(test for test in tests if test.endswith("::test_formula_count_matches"))
    result = {"source_sha256": sha(original), "test_bodies_preserved": True,
        "identities": list(tests), "reference_lines": len(lines),
        "roles": {"reference": {"must_fail": [], "infrastructure_failure": False},
            "wrong-value": {"must_fail": [rendered], "infrastructure_failure": False},
            "incomplete": {"must_fail": sorted([count, rendered]), "infrastructure_failure": False},
            "renderer-unavailable": {"must_fail": [], "infrastructure_failure": True,
                "affected_test": rendered, "omit_local_mathjax": True}},
        "files": {name: sha(data) for name, data in inputs.items()}, "executed_upstream_code": False,
        "models": 0}
    with (OUTPUT / "protected-fixture-lock.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"protected_roles": len(result["roles"]), "published_test_bodies": len(tests),
        "oracle_output_lines": result["reference_lines"], "executed_upstream_code": False}))


if __name__ == "__main__":
    main()

"""Check retained evidence and changed prose locally; never dispatch or retry."""
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from aeep.assessment.verification import verification_source_digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
MD = MarkdownIt("commonmark").enable("table")
BASE = '34072c8e17d59c4ccb579a6b9639ad7600fb8964'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = Counter()
        self.row_cells = []
        self.cells = 0

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        assert tag not in {"script", "iframe", "object", "embed", "base"}
        for key, value in attrs:
            assert not key.startswith("on")
            if key in {"src", "href"}:
                assert not urlsplit(value).scheme and not value.startswith("//")
        if tag == "tr":
            self.cells = 0
        elif tag in {"td", "th"}:
            self.cells += 1

    def handle_endtag(self, tag):
        if tag == "tr":
            self.row_cells.append(self.cells)


def heading_ids(path):
    tokens = MD.parse(path.read_text())
    counts = Counter()
    result = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', path.read_text()))
    for pos, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        text = "".join(
            child.content for child in tokens[pos + 1].children or []
            if child.type in {"text", "code_inline"}
        )
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        suffix = "" if not counts[slug] else f"-{counts[slug]}"
        result.add(slug + suffix)
        counts[slug] += 1
    return result


def changed_paths():
    names = set()
    for args in (["diff", BASE, "--name-only", "-z"], ["ls-files", "--others", "--exclude-standard", "-z"]):
        names.update(p.decode() for p in subprocess.check_output(["git", *args], cwd=ROOT).split(b"\0") if p)
    return [ROOT / name for name in sorted(names) if (ROOT / name).is_file()]


def main():
    review_path = OUT / "positive-operation-review.json"
    expected = "ba27e521798f450581d66ba963bd9a764799474af1c64c137a83e00eb36fd91e"
    assert sha(review_path) == expected
    review = json.loads(review_path.read_text())
    assert len(review["exact_driver_inputs"]) == 8
    for rel, digest in review["exact_driver_inputs"].items():
        assert sha(ROOT / rel) == digest, rel
    assert verification_source_digest(ROOT) == review["source_digest"]
    approval = json.loads((OUT / "positive-operator-approval.json").read_text())
    assert approval["approved"] and approval["review_sha256"] == expected
    exercise = json.loads((ROOT / "reports/toolkit-v2/c13/human-comprehension/editing-comparison-exercise.json").read_text())
    for rel, digest in exercise["presented_files"].items():
        assert sha(ROOT / rel) == digest, rel
    status = json.loads((OUT / "capture-status.json").read_text())
    assert status["actual_model_receipts"] == status["token_captures_verified"] == 4
    assert status["charged_diagnostic_turn_reservations"] == 5
    assert status["preflight_skipped_reservations_retained"] == 1
    assert status["positive_loading_observed"] and status["pending_additional_task_turns"] == 0
    assert status["task_correctness"] == {"passed": 3, "ungraded": 1}
    assert not status["new_qualification_or_admission"]
    for rel, digest in status["source_records"].items():
        assert sha(ROOT / rel) == digest, rel
    audit = json.loads((OUT / "completion-audit.json").read_text())
    assert audit["passed"] and audit["candidate_loading"]["instructions_loaded"] is True
    assert audit["capture"]["provider_usage_independently_verified"] is False
    assert audit["proxy"]["running"] is False
    assert all(not image["referencing_containers"] for image in audit["images"].values())
    resource = json.loads((ROOT / "reports/toolkit-v2/c13/cli-resource-profile-20261021/summary.json").read_text())
    assert resource["characterization_complete"] and not resource["resource_acceptance"]
    assert sum(row["samples"] for row in resource["commands"]) == 24
    assert resource["model_calls"] == 0
    response = json.loads((ROOT / "reports/toolkit-v2/c13/human-comprehension/editing-comparison-response-20261021.json").read_text())
    assert response["categories"] == {"unaided": 0, "helped": 3, "incorrect": 2, "unanswered": 0}
    assert response["presented_files"] == exercise["presented_files"]
    assert not response["journey_comprehension_established"]
    follow_path = ROOT / "reports/toolkit-v2/c13/human-comprehension/editing-comparison-follow-up-response-20261021.json"
    follow = json.loads(follow_path.read_text())
    assert follow["category"] == "helped" and all(row["supported"] for row in follow["scores"])
    assert sha(ROOT / follow["presented_report"]) == follow["presented_report_sha256"]
    assert follow["release_or_production_approval"] is False

    html = {}
    for path, tables, rows in [
        (OUT / "capture-status.html", 1, [8] * 5),
        (ROOT / "reports/toolkit-v2/c13/cli-resource-profile-20261021/summary.html", 2, [5] * 4 + [5] * 4),
    ]:
        parser = Document()
        parser.feed(path.read_text())
        parser.close()
        assert parser.tags["main"] == parser.tags["h1"] == 1
        assert parser.tags["table"] == tables and parser.row_cells == rows
        html[str(path.relative_to(ROOT))] = {"tables": tables, "rows": len(rows), "sha256": sha(path)}

    paths = changed_paths()
    links = []
    missing = []
    markdown = [path for path in paths if path.suffix == ".md"]
    for path in markdown:
        for block in MD.parse(path.read_text()):
            for token in block.children or []:
                value = token.attrGet("href") if token.type == "link_open" else token.attrGet("src") if token.type == "image" else None
                if value is None:
                    continue
                target = urlsplit(value)
                if target.scheme or target.netloc:
                    continue
                dest = (path.parent / unquote(target.path)).resolve() if target.path else path
                links.append({"source": str(path.relative_to(ROOT)), "target": value})
                if not dest.exists():
                    missing.append(links[-1])
                elif target.fragment and dest.suffix == ".md" and unquote(target.fragment) not in heading_ids(dest):
                    missing.append(links[-1])
    assert not missing, missing
    python = [path for path in paths if path.suffix == ".py"]
    for path in python:
        ast.parse(path.read_text(), filename=str(path))
    json_files = [path for path in paths if path.suffix == ".json"]
    for path in json_files:
        json.loads(path.read_text())
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "source_digest_unchanged": review["source_digest"],
        "approved_review_sha256": expected,
        "exact_approved_input_pins_unchanged": 8,
        "human_presented_file_hashes_unchanged": 5,
        "helped_human_report_comprehension_supported": True,
        "html_structure": html,
        "visual_review": "unverified; browser file-URL security rejection retained, no workaround",
        "changed_markdown_files": len(markdown),
        "local_markdown_links_checked": len(links),
        "missing_local_targets_or_markdown_anchors": missing,
        "python_files_ast_checked": len(python),
        "json_files_parsed": len(json_files),
        "method_limit": "First-party local Markdown-token paths/heading check, not a full Lychee or browser rendering result. No external requests, runtime inspection or model calls.",
        "checked_markdown_sha256": {str(path.relative_to(ROOT)): sha(path) for path in markdown},
    }
    (OUT / "final-record-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"html_structure", "checked_markdown_sha256"}}))


if __name__ == "__main__":
    main()

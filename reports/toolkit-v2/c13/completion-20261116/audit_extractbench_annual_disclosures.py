"""Bind the annual disclosure family while keeping returned documents untouched."""

import argparse
import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from audit_extractbench_transport_capacity import RECOVERY, RECOVERY_PIN, eligible_groups
from audit_extractbench_year_groups import linked_groups
from recover_extractbench_schemas import bound_inputs
from stage_repository_transport import HERE, WORK, digest, encode, read, write

OFFICIAL_INDEX = (
    "https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/"
    "primary-election-june-2-2026/candidate-tax-return"
)
CONSENT = (
    "https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/"
    "qualifications-requirements/income-tax-disclosure-governor.pdf"
)
BODY_LIMIT = 512 * 1024
PUBLIC_PDF = "environment/document.pdf"
OUTPUT = WORK / "extractbench-annual-disclosure-review-20261119"
REPORT = HERE / "recovery-67a93f4c-result-20261119.json"
MANIFEST_REVISION = "f9b910906cd7e73cc9eb5379a8d5d935c67b92c4"


class OfficialLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.filenames = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        url = urlsplit(href)
        if (
            url.scheme == "https"
            and url.netloc == "elections.cdn.sos.ca.gov"
            and url.path.startswith("/statewide-elections/2026-primary/")
            and not url.query
            and not url.fragment
            and url.path.endswith(".pdf")
        ):
            self.filenames.add(Path(url.path).name)


def inspect_index(raw):
    html = raw.decode()
    if "Candidate Tax Return Disclosures" not in html:
        raise ValueError("expected the California candidate tax-return index")
    parser = OfficialLinks()
    parser.feed(html)
    return parser.filenames


def audit(raw):
    frozen = json.loads(read(RECOVERY, RECOVERY_PIN))
    rows, _, _ = bound_inputs(frozen, RECOVERY.parent)
    groups = eligible_groups(rows)
    _, annual, _, stems = linked_groups(
        rows, groups, {item["schema_sha256"] for item in frozen["requests"]}
    )
    names = {Path(rows[case]["pdf"]).name for case in annual}
    matches = names & inspect_index(raw)
    if len(names) != 18 or len(matches) != 4:
        raise ValueError("annual filenames or their official overlaps require review")
    # The benchmark did not retain a comparison proving equivalence to agency bytes.
    summary = json.loads(REPORT.read_bytes())["extractbench"]
    scopes = summary["updated_feasibility"]
    held = {scope: case["holding_annual_family"] for scope, case in scopes.items()}
    if any(row["balanced_metadata_witness"] != "insufficient_population" for row in held.values()):
        raise ValueError("existing conservative capacity result changed")
    withheld = {
        "state": "held_for_exact_asset_use_review",
        "revision": MANIFEST_REVISION,
        "inputs": {case: rows[case]["files"][PUBLIC_PDF] for case in sorted(annual)},
    }
    return {
        "source_family": "california_governor_candidate_tax_disclosure",
        "publisher_revision": MANIFEST_REVISION,
        "publisher_manifest_sha256": frozen["manifest_sha256"],
        "previous_capacity_record_sha256": digest(REPORT.read_bytes()),
        "official_page": OFFICIAL_INDEX,
        "official_index_sha256": digest(raw),
        "official_consent_and_elections_code_excerpt": CONSENT,
        "candidate_pdf_slots": len(annual),
        "candidate_families_by_year_count": dict(stems),
        "current_index_filename_matches": len(matches),
        "current_index_matches_by_year": dict(Counter(name[-8:-4] for name in matches)),
        "official_pdf_bytes_equivalence_verified": False,
        "held_input_set": {
            "path": str((OUTPUT / "held-inputs.json").relative_to(HERE.parents[3])),
            "sha256": digest(encode(withheld)),
        },
        "asset_use_approved": False,
        "provider_disclosure_authorized": False,
        "candidate_pdf_requests": 0,
        "formal_case_assignments": 0,
        "models": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
        "held_family_capacity": held,
        "additional_multiple_collection_slots_at_best": {
            scope: max(0, 122 - case["multiple_collections"]) for scope, case in held.items()
        },
    }, withheld


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-index", action="store_true")
    args = parser.parse_args()
    evidence = OUTPUT / "official-index.html"
    if args.fetch_index:
        with urlopen(OFFICIAL_INDEX, timeout=15) as response:
            if response.geturl() != OFFICIAL_INDEX or response.headers.get_content_type() != "text/html":
                raise ValueError("unexpected agency index response")
            raw = response.read(BODY_LIMIT + 1)
        if not 0 < len(raw) <= BODY_LIMIT:
            raise ValueError("agency index exceeds the HTML budget")
        OUTPUT.mkdir(mode=0o700)
        write(evidence, raw)
    else:
        raw = evidence.read_bytes()
    if not 0 < len(raw) <= BODY_LIMIT:
        raise ValueError("retained agency index exceeds the HTML budget")
    report, withheld = audit(raw)
    held_inputs = OUTPUT / "held-inputs.json"
    data = encode(withheld)
    if held_inputs.exists():
        read(held_inputs, digest(data))
    else:
        write(held_inputs, data)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

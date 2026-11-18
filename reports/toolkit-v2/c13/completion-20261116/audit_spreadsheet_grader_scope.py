"""Measure SpreadsheetBench's declared grading scope from pinned manifests."""

import json
import re
from collections import Counter
from itertools import combinations
from statistics import median

from audit_spreadsheet_archive_index import CATEGORIES, HERE, SOURCE, TARGET, WORK, digest

ARCHIVE_AUDIT = HERE / "spreadsheet-archive-index-20261117.json"
UPSTREAM_SCORER = WORK / "document-corpus-metadata/spreadsheet-eval"
COLUMN, ROW = r"[A-Z]{1,3}", r"[1-9][0-9]{0,6}"
CELL = re.compile(rf"({COLUMN})({ROW})")
ADDRESS = COLUMN + ROW
RANGE = re.compile(
    rf"'(?P<sheet>(?:[^']|'')+)'!(?P<first>{ADDRESS})(?::(?P<last>{ADDRESS}))?"
)


def coordinate(address):
    match = CELL.fullmatch(address)
    if match is None:
        raise ValueError("unsupported workbook address")
    letters, digits = match.groups()
    column = 0
    for letter in letters:
        column = 26 * column + ord(letter) - ord("A") + 1
    row = int(digits)
    if column > 16_384 or row > 1_048_576:
        raise ValueError("address outside the worksheet")
    return column, row


def declared_ranges(value):
    if not isinstance(value, str) or not 0 < len(value) <= 16_384:
        raise ValueError("unsupported workbook range list")
    ranges = []
    cursor = 0
    while cursor < len(value):
        match = RANGE.match(value, cursor)
        if match is None:
            raise ValueError("unsupported workbook range list")
        first, last = match["first"], match["last"]
        left, top = coordinate(first)
        right, bottom = coordinate(last or first)
        if left > right or top > bottom:
            raise ValueError("reversed workbook range")
        ranges.append((match["sheet"], left, top, right, bottom))
        cursor = match.end()
        if cursor == len(value):
            return ranges
        if value[cursor] != "," or cursor + 1 == len(value):
            raise ValueError("unsupported workbook range separator")
        cursor += 1
    raise ValueError("empty workbook range list")


def overlaps(ranges):
    return any(
        name == other and max(left, x) <= min(right, end_x) and max(top, y) <= min(bottom, end_y)
        for (name, left, top, right, bottom), (other, x, y, end_x, end_y) in combinations(ranges, 2)
    )


def extent(values):
    return {"minimum": min(values), "median": median(values), "maximum": max(values)}


def one_mismatch_cutoff(target):
    return next(count for count in range(1, 25_001) if round((count - 1) / count, 4) >= target)


def category_scope(rows, category, limits):
    ranges_per_case = []
    visits_per_case = []
    sheet_counts = []
    overlap_count = 0
    modes = Counter()
    for row in rows:
        ranges = declared_ranges(row["answer_position"])
        ranges_per_case.append(len(ranges))
        visits_per_case.append(sum(
            (right - left + 1) * (bottom - top + 1)
            for _, left, top, right, bottom in ranges
        ))
        sheet_counts.append(len({shape[0] for shape in ranges}))
        overlap_count += overlaps(ranges)
        path = row["spreadsheet_path"]
        color = category == "Debugging" and "Color" in path
        formula = category == "Debugging" and "Embedded" in path
        modes[{(False, False): "values", (True, False): "values_and_font_color",
               (False, True): "formulas", (True, True): "both_flags"}[color, formula]] += 1
    return {
        "tasks": len(rows),
        "published_comparison_modes": dict(modes),
        "ranges_per_task": extent(ranges_per_case),
        "distinct_sheet_names_per_task": extent(sheet_counts),
        "declared_cell_visits_per_task": extent(visits_per_case),
        "tasks_with_overlapping_ranges": overlap_count,
        "tasks_whose_declared_visits_reach_cutoff": {
            name: sum(visits >= cutoff for visits in visits_per_case) for name, cutoff in limits.items()
        },
    }


def audit():
    pinned = json.loads(ARCHIVE_AUDIT.read_bytes())
    scorer = UPSTREAM_SCORER.read_bytes()
    scorer_ref = json.loads(SOURCE.read_bytes())["documents"]["spreadsheet-eval"]
    if (len(scorer), digest(scorer)) != (scorer_ref["bytes"], scorer_ref["sha256"]):
        raise ValueError("SpreadsheetBench scorer source drifted")
    cutoffs = {
        "one_regression_mismatch_can_round_to_full_credit": one_mismatch_cutoff(0.998),
        "one_modification_mismatch_can_round_to_full_credit": one_mismatch_cutoff(1),
    }
    sections = {}
    for category in CATEGORIES[:-1]:
        raw = (TARGET / (category + ".manifest.json")).read_bytes()
        ref = pinned["dataset_manifests"][category]
        if (len(raw), digest(raw)) != (ref["manifest_bytes"], ref["manifest_sha256"]):
            raise ValueError("publisher manifest drifted")
        rows = json.loads(raw)
        if len(rows) != ref["records"]:
            raise ValueError("publisher manifest record count drifted")
        sections[category] = category_scope(rows, category, cutoffs)
    return {
        "schema_version": "aeep.c13.spreadsheetbench-grader-scope.v1",
        "publisher_revision": pinned["publisher_revision"],
        "publisher_archive": pinned["recommended_archive_for_source_and_rights_review"],
        "archive_audit_sha256": digest(ARCHIVE_AUDIT.read_bytes()),
        "scorer": scorer_ref,
        "minimum_cells_in_one_scoring_bucket": cutoffs,
        "categories": sections,
        "interpretation": (
            "Declared visits bound each regression or modification bucket from above. Reaching a cutoff "
            "does not establish the actual bucket size, workbook preservation, or an observed grade."
        ),
        "native_score_or_thresholds_changed": False,
        "workbook_bodies_read": 0,
        "graders_executed": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))

"""Recompute the public-data reference privately without executing its verifier."""

import ast
import hashlib
import json
import math
import re
import statistics
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
CUSTODY = ROOT / ".aeep/completion-20261116/skillsbench-economic-and-data-custody"
TASK = CUSTODY / "tasks/econ-detrending-correlation"
YEARS = tuple(range(1973, 2025))


def bound_bytes(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"retained source drift: {path.name}")
    return data


def published_series(text):
    annual, quarters = {}, {}
    current_year = None
    for line in text.decode().splitlines():
        annual_row = re.match(r"^(\d{4})\s+[^\d]+([\d,]+\.\d)", line)
        if annual_row:
            year = int(annual_row[1])
            assert year not in annual
            annual[year] = float(annual_row[2].replace(",", ""))
            continue
        quarter_row = re.match(r"^\s*(?:(\d{4}):\s*)?(IV|III|II|I)\b[^\d]+([\d,]+\.\d)", line)
        if quarter_row:
            if quarter_row[1]:
                current_year = int(quarter_row[1])
            if current_year == 2024:
                quarter = quarter_row[2]
                assert quarter not in quarters
                quarters[quarter] = float(quarter_row[3].replace(",", ""))
    assert set(annual) == set(YEARS[:-1]) and set(quarters) == {"I", "II", "III"}
    annual[2024] = statistics.mean(quarters.values())
    return [annual[year] for year in YEARS]


def workbook_deflator(path):
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as book:
        xml = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    annual = {}
    for row in xml.findall(".//x:row", namespace)[1:]:
        year, ratio = (cell.text for cell in row.findall("x:c/x:v", namespace))
        assert int(year) not in annual
        annual[int(year)] = float(ratio)
    assert set(annual) == set(YEARS) and annual[2024] == 1
    assert all(math.isfinite(value) and value > 0 for value in annual.values())
    return [annual[year] for year in YEARS]


def cycle(series, smoothing):
    # Solve (I + smoothing * D^T D) trend = series, with D the second difference.
    n = len(series)
    rows = [[float(i == j) for j in range(n)] + [series[i]] for i in range(n)]
    for start in range(n - 2):
        for i, a in enumerate((1, -2, 1), start):
            for j, b in enumerate((1, -2, 1), start):
                rows[i][j] += smoothing * a * b
    for i, row in enumerate(rows):
        assert row[i] > 0
        for later in rows[i + 1 :]:
            scale = later[i] / row[i]
            for j in range(i + 1, n + 1):
                later[j] -= scale * row[j]
    trend = [0.0] * n
    for i in reversed(range(n)):
        row = rows[i]
        residual = row[-1] - math.fsum(row[j] * trend[j] for j in range(i + 1, n))
        trend[i] = residual / row[i]
    return [base - fitted for base, fitted in zip(series, trend, strict=True)]


def audit():
    names = ("EXPECTED_CORRELATION", "TOLERANCE")
    records = json.loads((CUSTODY / "custody.json").read_bytes())["files"]
    verifier = next(
        row
        for row in records
        if row["path"] == "tasks/econ-detrending-correlation/verifier/test_outputs.py"
    )
    code = ast.parse(bound_bytes(TASK / "verifier/test_outputs.py", verifier["sha256"]))
    settings = {
        item.targets[0].id: ast.literal_eval(item.value)
        for item in ast.walk(code)
        if isinstance(item, ast.Assign)
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id in names
    }
    assert settings.keys() == set(names)
    inputs = json.loads((CUSTODY / "economic-input-custody.json").read_bytes())
    book = TASK / "environment/CPI.xlsx"
    bound_bytes(book, next(row["sha256"] for row in inputs if row["name"] == book.name))
    deflator = workbook_deflator(book)
    pdfs = json.loads((CUSTODY / "economic-pdf-custody.json").read_bytes())
    nominal = [
        published_series(bound_bytes(CUSTODY / f"table{table}.txt", pin["text_sha256"]))
        for table, pin in zip((10, 12), pdfs, strict=True)
    ]

    def calculate(*, smoothing=100, deflate=True, log=True, exclude_last=False):
        before = [list(row) for row in nominal]
        if deflate:
            before = [
                [value / factor for value, factor in zip(row, deflator, strict=True)]
                for row in before
            ]
        if log:
            before = [[math.log(value) for value in row] for row in before]
        after = [cycle(row[:-1] if exclude_last else row, smoothing) for row in before]
        return statistics.correlation(*after)

    expected, tolerance = (settings[name] for name in names)
    independent = calculate()
    controls = {
        "quarterly_smoothing": calculate(smoothing=1600),
        "nominal_series": calculate(deflate=False),
        "unlogged_series": calculate(log=False),
        "excluded_2024": calculate(exclude_last=True),
    }
    assert round(independent, 5) == expected
    rejected = {name: abs(value - expected) > tolerance for name, value in controls.items()}
    assert all(round(value, 5) != expected for value in controls.values())
    assert rejected == dict(
        quarterly_smoothing=True, nominal_series=True, unlogged_series=True, excluded_2024=False
    )
    return {
        "included_years": len(YEARS),
        "first_year": min(YEARS),
        "last_year": max(YEARS),
        "third_quarter_last_in_published_2024_tables": True,
        "matches_upstream_reference_at_five_decimals": True,
        "rejected_by_numeric_tolerance": rejected,
        "all_four_controls_change_the_five_decimal_result": True,
        "upstream_verifier_execution": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))

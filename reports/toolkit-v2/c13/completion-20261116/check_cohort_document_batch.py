"""Cross-check publisher references and grade supplemental document packs."""

import argparse
import asyncio
import copy
import json
import os
import re
import subprocess
import sys
from calendar import monthrange
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import check_wasde_document_pack as verifier
from prepare_wasde_recipe import artifact, recipe_for
from stage_repository_transport import HERE, ROOT, digest, read, write

from aeep.assessment.models import DocumentTaskInput, RecipeDefinition, content_digest
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, BenchmarkTask
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_verification import ROOT as SOURCE_ROOT

BATCH = ROOT / ".aeep/c13-cohort-batch-20261124"
WORK = BATCH / "documents-verified"
TREASURY = BATCH / "treasury-october"
ENERGY = ROOT / ".aeep/c13-cohort-continuation-20261124/publisher-inputs"
POPPLER = Path("/usr/local/Cellar/poppler/25.01.0/bin/pdftotext")
POPPLER_SHA = "7d507ea2df5ce2b8eac1f09ee085c88b2c3cce7a7c5687eef60acfeeb22184a2"
PDF_PINS = {
    "census": "d5d6c33ab8a39915bebd82a9e2761d4e916cefde543339db8562595d320de938",
    "bea": "8e62214df875053d3a167b11affdcac2edd2113ce585dea136c1fdd524889574",
    "treasury": "956fca41af770139de490eff3f6d524367d28e7904761053cd8759ba075cb725",
    "energy": "53b7e6f85694576a11d031e46f108c5bdcd6e47d90828b4542bbeedf1f1acec6",
}
CENSUS_CODES = ("441", "442", "443", "445", "446", "447")
CENSUS_XLSX = "56629b17222b0b1f20c34efccda92bc5679091b2bf5048f8e05b7e79e38ca306"
CENSUS_LISTING = "https://www.census.gov/retail/marts/historic_releases.html"
BEA_LISTING = "https://www.bea.gov/news/2026/gdp-advance-estimate-3rd-quarter-2026"
TREASURY_LISTING = "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"
ENERGY_LISTING = "https://www.eia.gov/outlooks/steo/data.php"
ENERGY_WORKBOOK = "7d28012ff726ebeafd584905d842ded42bb3c9922550cb26e005af9cd4e27fb5"
SOURCE_LISTINGS = {
    "census": CENSUS_LISTING,
    "bea": BEA_LISTING,
    "treasury": TREASURY_LISTING,
    "energy": ENERGY_LISTING,
}
TASK_IDS = {
    "census": "census-advance-retail-202609",
    "bea": "bea-gdp-2026q3-advance",
    "treasury": "treasury-mts-202610",
    "energy": "eia-steo-balances-202611",
}
BEA_VALUES = {
    "activity": (
        ("real_gdp", "3.4", "2.2"),
        ("real_final_sales_to_private_domestic_purchasers", "4.9", "4.6"),
    ),
    "prices": (
        ("gross_domestic_purchases_price_index", "3.0", "5.6"),
        ("pce_price_index", "2.1", "5.0"),
        ("pce_price_index_excluding_food_energy", "2.5", "3.3"),
    ),
}
GUIDES = {
    "census": (
        "Use Tables 1 and 2 of the Census September 2026 advance retail release. "
        "For NAICS 441, 442, 443, 445, 446 and 447 in that order, extract September and August "
        "seasonally adjusted sales in millions into sales. Extract September-over-August "
        "and September-over-September changes from Table 2 into changes. Use the exact printed "
        "one-decimal percent values as strings, without a percent sign. Sales are integers."
    ),
    "bea": (
        "Read the opening narrative of the BEA Q3 2026 advance estimate. Extract real GDP "
        "and real final sales to private domestic purchasers in activity. Extract the gross domestic "
        "purchases, PCE and PCE excluding food and energy price indexes in prices. Keep this order. "
        "For each measure give the third- and second-quarter annualized percent changes as "
        "one-decimal strings without the percent sign, including trailing zeroes."
    ),
    "treasury": (
        "Use the October 2026 Monthly Treasury Statement. For Table 4, collect the "
        "current-month gross receipts, refunds and net receipts for Total -- Individual Income "
        "Taxes, Corporation Income Taxes, Customs Duties and Total -- Receipts. For Table 5, "
        "collect the current-month gross outlays, applicable receipts and net outlays for House "
        "of Representatives, Library of Congress, Total--Legislative Branch and "
        "Total--Judicial Branch. Preserve the stated row order, exact row names and the printed "
        "integer amounts in millions of dollars. Use receipts and outlays as the collection names."
    ),
    "energy": (
        "Use the EIA November 2026 Short-Term Energy Outlook tables. Extract the 2025, "
        "2026 and 2027 annual columns from Table 4a and Table 5a. In petroleum, include "
        "Alaska, Total Supply, Commercial inventory net withdrawals and Petroleum product "
        "net imports (d), in million barrels per day. In natural_gas, include U.S. total "
        "marketed natural gas production, Total supply, Net imports and Total consumption, "
        "in billion cubic feet per day. Keep this row order, exact labels, signs and printed "
        "decimal places. Store the numeric values as strings."
    ),
}


def pdf_text(label, directory=BATCH):
    path = directory / f"{label}.pdf"
    read(path, PDF_PINS[label])
    if file_digest(POPPLER) != POPPLER_SHA:
        raise ValueError("pinned PDF decoder changed")
    return subprocess.check_output([str(POPPLER), "-layout", str(path), "-"], timeout=15).decode()


def worksheet_rows(archive, sheet):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = archive.read("xl/sharedStrings.xml")
    data = archive.read(f"xl/worksheets/sheet{sheet}.xml")
    if any(len(body) > 500_000 or b"<!" in body for body in (strings, data)):
        raise ValueError("workbook XML exceeds the reviewed format")
    texts = ["".join(elem.itertext()) for elem in ElementTree.fromstring(strings)]
    by_code = {}
    for row in ElementTree.fromstring(data).findall(".//s:row", ns):
        cells = {}
        for cell in row.findall("s:c", ns):
            value = cell.findtext("s:v", None, ns)
            if value is not None:
                column = cell.get("r").rstrip("0123456789")
                cells[column] = texts[int(value)] if cell.get("t") == "s" else value
        if cells.get("A") in CENSUS_CODES:
            if cells["A"] in by_code:
                raise ValueError("duplicate Census row")
            by_code[cells["A"]] = cells
    return by_code


def census_reference(text):
    read(BATCH / "census.xlsx", CENSUS_XLSX)
    with ZipFile(BATCH / "census.xlsx") as data:
        sales, changes = worksheet_rows(data, 1), worksheet_rows(data, 2)
    table1 = text.split("Table 1. Estimated Monthly Sales", 1)[1].split("Table 2.", 1)[0]
    table2 = text.split("Table 2. Estimated Change", 1)[1].split("Table 3.", 1)[0]
    result = {"sales": [], "changes": []}
    for code in CENSUS_CODES:
        values = [int(sales[code][column]) for column in ("J", "K")]
        rates = [
            format(Decimal(changes[code][column]).quantize(Decimal("0.1")), "f")
            for column in ("C", "D")
        ]
        row = rf"^[ \t]*{code}[ \t]+([^\n]+)"
        (line1,) = re.findall(row, table1, flags=re.MULTILINE)
        (line2,) = re.findall(row, table2, flags=re.MULTILINE)
        number = r"-?\d[\d,]*(?:\.\d+)?"
        pdf_sales = re.findall(number, line1)
        pdf_change = re.findall(number, line2)
        if (
            len(pdf_sales) != 12
            or len(pdf_change) != 6
            or [int(item.replace(",", "")) for item in pdf_sales[-5:-3]] != values
            or pdf_change[:2] != rates
        ):
            raise ValueError(f"Census PDF/workbook discrepancy for NAICS {code}")
        result["sales"].append(
            {"naics": code, "september_millions": values[0], "august_millions": values[1]}
        )
        result["changes"].append(
            {
                "naics": code,
                "month_over_month_percent": rates[0],
                "year_over_year_percent": rates[1],
            }
        )
    return result


def bea_reference(text):
    # The values were independently read from the publisher's archived HTML
    # release narrative. Guard both the metric order and the quarter pairing.
    patterns = {
        "real_gdp": r"Real gross domestic product \(GDP\) increased at an annual rate of ([\d.]+) percent.*?In the second quarter, real GDP increased ([\d.]+) percent",
        "real_final_sales_to_private_domestic_purchasers": r"Real final sales to private domestic purchasers,.*?increased ([\d.]+) percent in the third quarter, compared with an increase of ([\d.]+) percent",
        "gross_domestic_purchases_price_index": r"The price index for gross domestic purchases increased ([\d.]+) percent in the third quarter, compared with an increase of ([\d.]+) percent",
        "pce_price_index": r"The personal consumption expenditures \(PCE\) price index increased ([\d.]+) percent, compared with an increase of ([\d.]+) percent",
        "pce_price_index_excluding_food_energy": r"excluding food and energy increased ([\d.]+) percent, compared with an increase of ([\d.]+) percent",
    }
    front = " ".join(text.split("Technical Notes\n")[0].split())
    result = {}
    for group, measures in BEA_VALUES.items():
        result[group] = []
        for field, third, second in measures:
            if re.findall(patterns[field], front) != [(third, second)]:
                raise ValueError("BEA PDF differs from its HTML release narrative")
            result[group].append(
                {"measure": field, "q3_2026_percent": third, "q2_2026_percent": second}
            )
    return result


def schema_for(result):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(result),
        "properties": {
            name: {
                "type": "array",
                "minItems": len(rows),
                "maxItems": len(rows),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(rows[0]),
                    "properties": {
                        key: {"type": "integer" if type(value) is int else "string"}
                        for key, value in rows[0].items()
                    },
                },
            }
            for name, rows in result.items()
        },
    }


def treasury_reference(text):
    receipt_table = text.split("Table 4. Receipts of the U.S. Government, October 2026", 1)[1]
    receipt_table, outlay_table = receipt_table.split(
        "Table 5. Outlays of the U.S. Government, October 2026", 1
    )
    outlay_table = outlay_table.split("Department of Agriculture:", 1)[0]
    specs = {
        "receipts": (
            receipt_table,
            "receipts.json",
            "78b2fa366ede3d8c0eb7905e5059a9dc367dd9eb301c51ce01a10e167d4901f4",
            (
                "Total -- Individual Income Taxes",
                "Corporation Income Taxes",
                "Customs Duties",
                "Total -- Receipts",
            ),
            {
                "gross_receipts_millions": "current_month_gross_rcpt_amt",
                "refunds_millions": "current_month_refund_amt",
                "net_receipts_millions": "current_month_net_rcpt_amt",
            },
        ),
        "outlays": (
            outlay_table,
            "outlays-sample.json",
            "118c6175932daded8a69961723b3205bad1c4e92e90fb59227835fca661b3c5c",
            (
                "House of Representatives",
                "Library of Congress",
                "Total--Legislative Branch",
                "Total--Judicial Branch",
            ),
            {
                "gross_outlays_millions": "current_month_gross_outly_amt",
                "applicable_receipts_millions": "current_month_app_rcpt_amt",
                "net_outlays_millions": "current_month_net_outly_amt",
            },
        ),
    }

    def normalized(value):
        return re.sub(r"\s*--\s*", "--", value)

    groups = {}
    for group, (table, name, pin, labels, fields) in specs.items():
        rows = json.loads(read(TREASURY / name, pin))["data"]
        groups[group] = []
        for label in labels:
            (published,) = [
                row for row in rows if normalized(row["classification_desc"]) == normalized(label)
            ]
            if published["record_date"] != "2026-10-31":
                raise ValueError("Treasury release dates differ")
            (printed,) = re.findall(
                r"(?m)^ *" + re.escape(label) + r" {2,}(-?[\d,]+) +(-?[\d,]+) +(-?[\d,]+) ",
                table,
            )
            values = tuple(int(value.replace(",", "")) for value in printed)
            independent = tuple(
                int(
                    (Decimal(published[key]) / 10**6).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )
                for key in fields.values()
            )
            if values != independent:
                raise ValueError("Treasury API and PDF disagree")
            groups[group].append(
                {"classification": label, **dict(zip(fields, values, strict=True))}
            )
    return groups


def energy_reference(text):
    specs = (
        (
            "petroleum",
            "4a",
            10,
            "0.01",
            (
                "Alaska",
                "Total Supply",
                "Commercial inventory net withdrawals",
                "Petroleum product net imports (d)",
            ),
        ),
        (
            "natural_gas",
            "5a",
            14,
            "0.1",
            (
                "U.S. total marketed natural gas production",
                "Total supply",
                "Net imports",
                "Total consumption",
            ),
        ),
    )
    if "Short-Term Energy Outlook - November 2026" not in text:
        raise ValueError("EIA report vintage differs")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    workbook = ENERGY / "energy.xlsx"
    read(workbook, ENERGY_WORKBOOK)
    groups = {}
    columns = [f"A{c}" for c in "MNOPQRSTUVWXYZ"] + [f"B{c}" for c in "ABCDEFGHIJKLMNOPQRSTUV"]

    def xml(archive, name):
        if archive.getinfo(name).file_size > 500_000:
            raise ValueError("EIA workbook XML exceeds its scope")
        raw = archive.read(name)
        if b"<!" in raw:
            raise ValueError("unexpected EIA workbook XML declaration")
        return ElementTree.fromstring(raw)

    with ZipFile(workbook) as archive:
        strings = ["".join(item.itertext()) for item in xml(archive, "xl/sharedStrings.xml")]
        for group, table, sheet, precision, labels in specs:
            pdf = text.split(f"Table {table}.", 1)[1].split(f"Table {table[0]}b.", 1)[0]
            tree = xml(archive, f"xl/worksheets/sheet{sheet}.xml")
            rows = {}
            for row in tree.findall(".//s:row", ns):
                cells = {}
                for item in row.findall("s:c", ns):
                    value = item.findtext("s:v", None, ns)
                    if value is not None:
                        col = item.attrib["r"].rstrip("0123456789")
                        cells[col] = strings[int(value)] if item.attrib.get("t") == "s" else value
                label = cells.get("B")
                if row.attrib["r"] == "2" and "November 2026" not in (label or ""):
                    raise ValueError("EIA workbook vintage differs")
                if row.attrib["r"] == "3" and tuple(cells[key] for key in ("AM", "AY", "BK")) != (
                    "2025",
                    "2026",
                    "2027",
                ):
                    raise ValueError("EIA workbook years differ")
                if label in labels:
                    if label in rows:
                        raise ValueError("duplicate EIA row")
                    # AM through BV are the consecutive months for 2025 through 2027.
                    rows[label] = [Decimal(cells[col]) for col in columns]
            groups[group] = []
            for label in labels:
                (match,) = re.findall(r"(?m)^ *" + re.escape(label) + r" +\.+ +(.+)$", pdf)
                figures = match.split()
                if len(figures) != 15:
                    raise ValueError("EIA quarter and annual columns differ")
                output = {"measure": label}
                for i, year in enumerate((2025, 2026, 2027)):
                    months = rows[label][12 * i : 12 * (i + 1)]
                    weights = [monthrange(year, month)[1] for month in range(1, 13)]
                    annual = sum(
                        number * days for number, days in zip(months, weights, strict=True)
                    ) / sum(weights)
                    printed = format(
                        annual.quantize(Decimal(precision), rounding=ROUND_HALF_UP), "f"
                    )
                    if printed != figures[12 + i]:
                        raise ValueError("EIA workbook and PDF annual values differ")
                    output[f"year_{year}"] = printed
                groups[group].append(output)
    return groups


def prepare_pack(directory, acquisition, source):
    acquisition = verifier.get(directory / acquisition)
    tasks, pins, protected = [], {}, {}
    guest = (HERE / "wasde_recipe_guest.py").read_bytes()
    bridge = (HERE / "extractbench_recipe_guest.py").read_bytes()
    for label, result in source.items():
        task_id = TASK_IDS[label]
        pdf = read(directory / f"{label}.pdf", PDF_PINS[label])
        schema = schema_for(result)
        validate_json(result, schema, label="supplemental exact reference")
        expected = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        instruction = (GUIDES[label] + "\nUse the provided schema and save output.json.\n").encode()
        files = {
            "instruction.md": instruction,
            "environment/document.pdf": pdf,
            "environment/schema.json": json.dumps(schema, indent=2).encode(),
            "solution/expected.json": expected,
            "tests/verifier.py": guest,
        }
        assets = []
        for name, body in files.items():
            relative = f"tasks/{task_id}/{name}"
            write(WORK / "pack" / relative, body)
            assets.append(
                {
                    "path": relative,
                    "sha256": digest(body),
                    "bytes": len(body),
                    "role": verifier.ROLES[name],
                }
            )
        tasks.append(
            BenchmarkTask.model_validate(
                {
                    "task_id": task_id,
                    "domain": "document-data",
                    "difficulty": "unknown",
                    "output_paths": ["output.json"],
                    "upstream_score": "binary",
                    "assets": assets,
                    "adaptations": [
                        "Locally authored exact extraction rubric; whole publisher PDF retained."
                    ],
                }
            )
        )
        pins[task_id] = SourcePin(
            repository=acquisition[f"{label}.pdf"]["url"],
            revision=PDF_PINS[label],
            artifact_sha256=PDF_PINS[label],
            license_expression="LicenseRef-Publisher-asset-use-review-pending",
            data_rights="Public federal statistical release. Local verification scope; provider use requires its own reviewed record.",
        )
        protected[task_id] = (label, result, expected, guest, bridge)
    inventory = content_digest(
        {
            "tasks": [row.model_dump(mode="json") for row in tasks],
            "task_sources": {name: pin.model_dump(mode="json") for name, pin in pins.items()},
        }
    )
    pack = BenchmarkPack(
        schema_version="aeep.toolkit.benchmark-pack.v2",
        pack_id="reviewed-documents",
        tasks=tuple(tasks),
        task_sources=pins,
        source=SourcePin(
            repository=SOURCE_LISTINGS[next(iter(source))],
            revision=inventory,
            artifact_sha256=inventory,
            license_expression="LicenseRef-Per-task-review",
            data_rights="Per-task publisher source bindings; no provider transfer.",
        ),
    )
    verifier.put(WORK / "pack.json", pack.model_dump(mode="json"))
    return pack, protected


def controls(descriptor, expected):
    action = descriptor.model_dump(mode="json")
    truth = {"input_sha256": content_digest(descriptor)}
    good = artifact(expected)
    missing = copy.deepcopy(json.loads(expected))
    missing[next(iter(missing))].pop()

    def request(output):
        return {"examples": [{"input": action, "expected": truth, "output": output}]}

    return [
        ("reference", {"inputs": [action]}, good),
        ("reference-grade", request(good), (True, 1.0, "")),
        (
            "missing-row",
            request(artifact(json.dumps(missing).encode())),
            (False, 0.0, "inexact_extraction"),
        ),
        ("bad-json", request(artifact(b"{")), (False, 0.0, "invalid_submission")),
    ]


async def run_case(pack, task, protected):
    label, result, expected, guest, bridge = protected
    root = WORK / task.task_id
    public = root / "public"
    public.mkdir(mode=0o700, parents=True)
    spec = await asyncio.to_thread(
        subprocess.check_output,
        [
            sys.executable,
            "-B",
            "-m",
            "aeep_toolkit",
            "benchmark",
            "stage-document",
            "--pack",
            str(WORK / "pack.json"),
            "--root",
            str(WORK / "pack"),
            "--task",
            task.task_id,
            "--family",
            "multiple-collections",
            "--destination",
            str(public),
            "--archive-instructions",
        ],
        env={"PYTHONPATH": str(SOURCE_ROOT / "src"), "PATH": os.defpath, "HOME": str(root)},
        cwd=SOURCE_ROOT,
        timeout=20,
    )
    descriptor = DocumentTaskInput.model_validate_json(spec)
    path = public / f"{descriptor.task_archive_sha256}.zip"
    with ZipFile(path) as archive:
        members = archive.namelist()
        expected_hashes = {
            item.path.removeprefix(f"tasks/{task.task_id}/"): item.sha256
            for item in task.assets
            if item.role in {"input", "instruction"}
        }
        if (
            len(members) != 3
            or {name: digest(archive.read(name)) for name in members} != expected_hashes
        ):
            raise ValueError("public archive contains unreviewed bytes")
    verifier.NAME = "c13-doc-batch-" + label + "-20261124"
    verifier.WORK = root
    support = verifier.PROTECTED = root / "grader"
    verifier.observations = controls
    recipe = recipe_for(descriptor, digest(guest), digest(bridge)).model_dump(mode="json")
    recipe.update(
        recipe_id=f"c13-{task.task_id}-local-exact", description="Local exact publisher extraction"
    )
    recipe["dependencies"]["protected_reference"] = digest(expected)
    recipe["dependencies"]["schema"] = expected_hashes["environment/schema.json"]
    recipe["extension"]["template_families"] = [task.task_id]
    for role, mode in (("reference", "reference"), ("grader", "grade")):
        recipe["extension"][role]["config"]["argv"] = [
            "python3",
            "-I",
            "-B",
            str(support / "wasde_recipe_guest.py"),
            mode,
            "--support",
            str(support),
        ]
    recipe = RecipeDefinition.model_validate(recipe)
    verifier.put(root / "document.json", descriptor.model_dump(mode="json"))
    verifier.put(root / "recipe.json", recipe.model_dump(mode="json"))
    write(support / "wasde_recipe_guest.py", guest)
    write(support / "extractbench_recipe_guest.py", bridge)
    verifier.put(
        support / "bindings.json",
        {
            content_digest(descriptor): {
                "case": task.task_id,
                "reference_sha256": digest(expected),
                "oracle_sha256": digest(expected),
            }
        },
    )
    for location in ("verifier/reference.test.json", "controls/oracle.json"):
        write(support / "cases" / task.task_id / location, expected)
    support.chmod(0o555)
    for item in support.rglob("*"):
        item.chmod(0o555 if item.is_dir() else 0o444)
    exact, checks = await verifier.grade(pack, descriptor, recipe, expected)
    return {
        "source_family": {
            "census": "census-marts",
            "bea": "bea-nipa-gdp",
            "treasury": "treasury-monthly-statement",
            "energy": "eia-short-term-energy-outlook",
        }[label],
        "publisher_crosscheck": SOURCE_LISTINGS[label],
        "public_zip_sha256": file_digest(path),
        "public_zip_bytes": path.stat().st_size,
        "crosschecked_row_count": sum(len(rows) for rows in result.values()),
        "protected_review": exact,
        "checks": checks,
    }


async def main():
    global WORK
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--treasury", action="store_true")
    mode.add_argument("--energy", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.treasury:
        WORK = TREASURY / "document-verified"
        directory, acquisition = TREASURY, "result.json"
        source = {"treasury": treasury_reference(pdf_text("treasury", TREASURY))}
    elif args.energy:
        WORK = ENERGY.parent / "energy-verified"
        directory, acquisition = ENERGY, "acquisition-result.json"
        source = {"energy": energy_reference(pdf_text("energy", ENERGY))}
    else:
        directory, acquisition = BATCH, "local-acquisition-result.json"
        source = {
            "census": census_reference(pdf_text("census")),
            "bea": bea_reference(pdf_text("bea")),
        }
    WORK.mkdir(mode=0o700)
    pack, protected = prepare_pack(directory, acquisition, source)
    done = {}
    for task in pack.tasks:
        done[task.task_id] = await run_case(pack, task, protected[task.task_id])
    verifier.put(
        WORK / "result.json",
        {
            "pack_sha256": content_digest(pack.model_dump(mode="json")),
            "cases": done,
            "asset_use_reviewed_for_provider": False,
            "formal_assignments": 0,
            "model_turns": 0,
            "cash_usd": 0,
            "compared": False,
            "waza_excluded": True,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())

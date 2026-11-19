"""Cross-check a real USDA document and machine-readable reference in memory."""

import argparse
import base64
import io
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from stage_repository_transport import WORK, digest, encode, write

from aeep.assessment.adapters import project_document_archive
from aeep.assessment.models import DocumentTaskInput
from aeep.registry import validate_json

ORIGIN = "https://esmis.nal.usda.gov/sites/default/release-files/796142/"
SOURCES = {
    "wasde1126.pdf": (1015158, "c9d63b4b07dd48626ebf4bb5ab57bd52046f11cd5d6c968043fefd5e3283bcc2"),
    "wasde1126.xml": (2052149, "c285bbba0e9228dfa91f255cdbdacc7612718162d264fe09fe53050ce016780a"),
}
POPPLER = Path("/usr/local/bin/pdftotext")
OUTPUT = WORK / "wasde-reference-calibration-20261119"
GROUPS = ("world", "united_states")
HEADINGS = ("Output", "Total Supply", "Trade 2/", "Total Use 3/", "Ending Stocks")
FIELDS = ("output", "total_supply", "trade", "total_use", "ending_stocks")
COMMODITIES = ("Total Grains 4/", "Wheat", "Coarse Grains 5/", "Rice, milled")
PERIODS = ("2024/25", "2025/26 (Est.)", "2026/27 (Proj.) Oct", "2026/27 (Proj.) Nov")
DECIMAL = r"[0-9]+\.[0-9]{2}"
ROW = re.compile(
    r"(?P<commodity>.*?)\s*(?P<period>\d{4}/\d{2}(?: \(Est\.\)| \(Proj\.\) (?:Oct|Nov))?)"
    + "".join(rf"\s+(?P<{field}>{DECIMAL})" for field in FIELDS)
)
INSTRUCTION = """Use only page 8 (WASDE - 677 - 8) of environment/document.pdf.
Extract the World and United States grain supply and use tables into output.json
using environment/schema.json. Preserve the printed commodity labels, including
footnote markers. Use the printed marketing period labels and carry forward the
commodity and projection period where the next printed row omits them. Keep
the October and November rows distinct. Give every amount in million metric tons
as a string with exactly two decimal places. Keep the original row order.
Ignore notes and invisible layout placeholders. Read all 16 data rows per table.
"""


def source(name):
    size, checksum = SOURCES[name]
    address = ORIGIN + name
    with urlopen(address, timeout=15) as response:
        if response.geturl() != address:
            raise ValueError("publisher source redirected")
        data = response.read(size + 1)
    if len(data) != size or digest(data) != checksum:
        raise ValueError("publisher artifact changed")
    return data


def xml_reference(raw):
    if any(x in raw.lower() for x in (b"<!doctype", b"<!entity")):
        raise ValueError("external or expanded XML is unsupported")
    output = {}
    root = ElementTree.fromstring(raw).find("./sr08/Report")
    if root is None or root.get("Report_Month") != "November 2026":
        raise ValueError("wrong release or report page")
    for number, group in enumerate(GROUPS, 1):
        prefix = f"m{number}_"
        rows = root.findall(f"./matrix{number}/{prefix}commodity_group_Collection/{prefix}commodity_group")
        output[group] = []
        for item in rows:
            year = item.find(f"./{prefix}year_group_Collection/{prefix}year_group")
            month = year.find(f"./{prefix}month_group_Collection/{prefix}month_group")
            columns = month.find(f"./{prefix}attribute_group_Collection")
            cells = {}
            for column in columns:
                named = column[0] if number == 1 else column
                title = " ".join(named.attrib[f"attribute{number}"].split())
                (cell,) = named.iter("Cell")
                if title in cells:
                    raise ValueError("duplicate reference column")
                cells[title] = cell.attrib[f"cell_value{number}"]
            if tuple(cells) != HEADINGS:
                raise ValueError("publisher reference columns changed")
            output[group].append({
                "commodity": item.attrib[f"commodity{number}"].strip(),
                "period": " ".join(part for part in (
                    year.attrib[f"market_year{number}"].strip(),
                    month.attrib[f"forecast_month{number}"].strip(),
                ) if part),
                **dict(zip(FIELDS, cells.values(), strict=True)),
            })
    return output


def pdf_reference(raw):
    captured = subprocess.run(
        [str(POPPLER), "-layout", "-f", "8", "-l", "8", "-", "-"],
        input=raw, capture_output=True, check=True, timeout=20,
    ).stdout.decode()
    if "WASDE - 677 - 8" not in captured or "Million Metric Tons" not in captured:
        raise ValueError("document page or units changed")
    groups = {}
    group = commodity = None
    for line in map(str.strip, captured.splitlines()):
        if line.startswith("World ") and "Trade 2/" in line:
            group = "world"
            groups[group] = []
            commodity = None
        elif line == "United States":
            group = "united_states"
            groups[group] = []
            commodity = None
        elif match := ROW.fullmatch(line):
            row = match.groupdict()
            commodity = row.pop("commodity").strip() or commodity
            if group is None or commodity not in COMMODITIES:
                raise ValueError("unmapped PDF row")
            groups[group].append({"commodity": commodity, **row})
    return groups


def output_schema():
    properties = {"commodity": {"enum": list(COMMODITIES)}, "period": {"enum": list(PERIODS)}}
    properties.update({name: {"type": "string", "pattern": "^" + DECIMAL + "$"} for name in FIELDS})
    row = {"type": "object", "properties": properties,
           "additionalProperties": False, "required": list(properties)}
    return {
        "type": "object", "additionalProperties": False, "required": list(GROUPS),
        "properties": {group: {"type": "array", "minItems": 16, "maxItems": 16, "items": row}
                       for group in GROUPS},
    }


def check_reference(reference, prediction, schema):
    validate_json(prediction, schema, label="USDA output")
    if prediction != reference:
        raise ValueError("output differs from the frozen USDA rows")


def transport(pdf, schema):
    instruction = INSTRUCTION.encode()
    files = {"instruction.md": instruction, "environment/document.pdf": pdf,
             "environment/schema.json": encode(schema)}
    packed = io.BytesIO()
    with ZipFile(packed, "w") as archive:
        for name, body in sorted(files.items()):
            archive.writestr(ZipInfo(name), body, compress_type=ZIP_DEFLATED)
    payload = packed.getvalue()
    identity = DocumentTaskInput(
        task_id="usda-wasde-677-local-calibration",
        family="multiple-collections",
        instruction_sha256=digest(instruction),
        benchmark_pack_sha256=digest(encode({name: digest(body) for name, body in files.items()})),
        task_archive_sha256=digest(payload),
        document_sha256=digest(pdf),
        output_paths=["output.json"],
    )
    with tempfile.TemporaryDirectory(prefix="aeep-wasde-calibration-", dir="/private/tmp") as temp:
        directory = Path(temp).resolve()
        write(directory / f"{identity.task_archive_sha256}.zip", payload)
        projected = project_document_archive(identity.model_dump(mode="json"), [str(directory)])
        if projected["task"] != INSTRUCTION or base64.b64decode(projected["task_archive_b64"]) != payload:
            raise ValueError("existing document transport changed the planned input")
    return {"bytes": len(payload), "sha256": digest(payload), "public_files": sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-pinned-publisher", action="store_true", required=True)
    parser.parse_args()
    pdf, xml = (source(name) for name in SOURCES)
    reference = xml_reference(xml)
    schema = output_schema()
    counterpart = pdf_reference(pdf)
    check_reference(reference, counterpart, schema)
    required = [(commodity, period) for commodity in COMMODITIES for period in PERIODS]
    for rows in reference.values():
        if [(row["commodity"], row["period"]) for row in rows] != required:
            raise ValueError("reference identities or order differ")
    public_transport = transport(pdf, schema)
    OUTPUT.mkdir(mode=0o700)
    write(OUTPUT / "protected-reference.json", encode(reference))
    write(OUTPUT / "schema.json", encode(schema))
    write(OUTPUT / "instruction.md", INSTRUCTION.encode())
    write(OUTPUT / "result.json", encode({
        "publisher_release": "USDA WASDE-677 November 2026",
        "sources": {ORIGIN + name: {"bytes": size, "sha256": pin} for name, (size, pin) in SOURCES.items()},
        "row_counts": {group: len(rows) for group, rows in reference.items()},
        "numeric_cells_matched": sum(len(rows) for rows in reference.values()) * len(FIELDS),
        "protected_reference_sha256": digest(encode(reference)),
        "public_transport": public_transport,
        "scope": "local calibration of public source and reference; no protected executor dispatch",
        "archive_used_pinned_ordinary_extractbench_pack": False,
        "formal_cases_adopted": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }))


if __name__ == "__main__":
    main()

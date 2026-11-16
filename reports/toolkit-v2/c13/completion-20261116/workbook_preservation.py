"""Supplemental value-preservation rule for the reviewed workbook recovery task."""

import math


def values(sheet):
    # The candidate workbook is opened only inside the protected grader.
    if sheet.max_row * sheet.max_column > 8192:
        raise ValueError("worksheet exceeds the reviewed recovery bound")
    return {
        cell.coordinate: (cell.data_type, cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    }


def preserves_unaffected_values(original, recovered):
    """Require the same populated cells and numeric replacements for the 15 gaps."""
    if original.sheetnames != recovered.sheetnames:
        return False
    placeholder_count = 0
    for before, after in zip(original.worksheets, recovered.worksheets, strict=True):
        before_cells = values(before)
        try:
            after_cells = values(after)
        except ValueError:
            return False
        if before_cells.keys() != after_cells.keys():
            return False
        for address, previous in before_cells.items():
            current = after_cells[address]
            if previous[1] == "???":
                placeholder_count += 1
                kind, value = current
                if (kind != "n" or type(value) not in (int, float)
                        or (type(value) is float and not math.isfinite(value))):
                    return False
            elif current != previous:
                return False
    if placeholder_count != 15:
        raise ValueError("pinned workbook placeholder inventory changed")
    return True

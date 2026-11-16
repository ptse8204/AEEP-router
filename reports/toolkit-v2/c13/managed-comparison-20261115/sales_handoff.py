"""Restore the previously verified Sales Pivot file-delivery instructions."""

HANDOFF = (
    "Use the bound input_path /workspace/skillsbench-task.zip. Read the original task and "
    "unpack its public inputs under /workspace/task-input. In the original task, "
    "/root/population.pdf and /root/income.xlsx refer to the copies in the archive under "
    "its environment directory. The original /root/demographic_analysis.xlsx output "
    "maps to the exact bound file /workspace/demographic_analysis.xlsx. Do not write "
    "under /root or deliver a similarly named file elsewhere. Before returning completion, "
    "verify that the exact bound output is a readable regular file with one hard link, "
    "is not a symlink, and has a size from 1 to 300000 bytes. Keep the requested workbook "
    "content and native pivot structures. "
)


def corrected_sales_instructions(original: str) -> str:
    return HANDOFF + original

"""Initial reviewed AFlow workflow for the synthetic text calibration."""


class Workflow:
    async def __call__(self, text, fields):
        extracted = {}
        for line in text.splitlines():
            label, separator, value = line.partition(":")
            if separator and label in fields:
                extracted[label] = value.lstrip(" ")
        return {"fields": extracted}

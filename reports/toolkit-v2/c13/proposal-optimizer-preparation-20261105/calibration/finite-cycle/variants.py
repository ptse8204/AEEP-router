"""Two reviewed workflow changes for one AFlow integration cycle."""

POLICY = "initial"


class Workflow:
    async def __call__(self, text, fields):
        extracted = {}
        for line in text.splitlines():
            label, separator, value = line.partition(":")
            if separator and label in fields:
                if label in extracted:
                    if POLICY == "reject_duplicate":
                        return {"error": "invalid_input"}
                    if POLICY == "keep_first":
                        continue
                extracted[label] = value.lstrip(" ")
        return {"fields": extracted}

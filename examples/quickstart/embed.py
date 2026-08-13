from __future__ import annotations

import asyncio
from pathlib import Path

from aeep import ActionRequest, Router


async def main() -> None:
    manifest = Path(__file__).with_name("aeep.yaml")
    async with Router.from_manifest(manifest) as router:
        request = ActionRequest(
            capability="text.stats",
            input={"text": "AEEP chooses an execution path."},
            policy="balanced",
        )
        decision = router.route(request)
        print("selected:", decision.selected_executor_id)
        outcome = await router.execute(decision)
        print("output:", outcome.output)
        print("actual:", outcome.receipts[-1].actual_resources.model_dump())


if __name__ == "__main__":
    asyncio.run(main())

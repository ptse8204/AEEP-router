"""One durable assessment per local worker process."""

from __future__ import annotations

import argparse
import asyncio
import signal
from contextlib import suppress
from pathlib import Path

from ..errors import ConfigurationError
from ..router import Router
from .models import AssessmentPlan
from .service import AssessmentService


async def run(manifest: Path, directory: Path, assessment_id: str) -> None:
    router = Router.from_manifest(manifest)
    service = AssessmentService(router, directory)
    plan = AssessmentPlan.model_validate(service.repository.get("plan", service.status(assessment_id)["plan_id"]))
    work = asyncio.create_task(service.run(assessment_id))

    async def watch_authorization() -> None:
        while not work.done():
            await asyncio.sleep(0.2)
            try:
                service.repository.authorize(plan)
                if service.status(assessment_id)["state"] == "cancelled":
                    work.cancel()
                    return
            except ConfigurationError:
                work.cancel()
                return

    watcher = asyncio.create_task(watch_authorization())
    loop = asyncio.get_running_loop()
    with suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGTERM, work.cancel)
    try:
        await work
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await router.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--assessment", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.manifest, args.directory, args.assessment))


if __name__ == "__main__":
    main()

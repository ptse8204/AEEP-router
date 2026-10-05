"""Run synthetic stack journeys. No paid APIs, installation or real media generation."""
from __future__ import annotations

import asyncio
import json

from aeep.assessment.models import content_digest
from aeep.examples.stack_fixtures import fixture
from aeep.router import Router
from aeep.stack_planning import StackService
from aeep.stack_runtime import StackRuntime


async def main() -> None:
    for family in ('media', 'data', 'research'):
        manifest, goal, inputs = fixture(family)
        router = Router(manifest)
        try:
            service = StackService(router)
            proposal = service.propose(goal)
            # Explicit operator review in an isolated in-memory demonstration.
            # Production callers use the existing assess review command.
            service.repository.review(content_digest(proposal))
            result = await StackRuntime(service).run(proposal.proposal_id, inputs)
            print(json.dumps({'family': family, 'status': result['status'],
                              'nodes': len(proposal.components), 'receipts': len(result['receipt_ids']),
                              'synthetic': True}))
        finally:
            await router.close()


if __name__ == '__main__':
    asyncio.run(main())

"""Validate planner graph references through the existing inert AEEP stack planner."""

import argparse
import asyncio
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.examples.stack_fixtures import fixture
from aeep.router import Router
from aeep.stack_planning import StackService


async def inspect_graph(graph, request_sha256):
    if not isinstance(graph, dict) or set(graph) != {
        'status', 'nodes', 'edges', 'request_sha256', 'generated_code_executed', 'boundary',
    }:
        raise ValueError('unexpected graph envelope')
    if graph['status'] != 'graph_ready' or graph['request_sha256'] != request_sha256:
        raise ValueError('graph is not tied to the captured request')
    if graph['generated_code_executed'] is not False or graph['boundary']['inherited_sockets'] != 0:
        raise ValueError('invalid proposal boundary')
    manifest, contract, _ = fixture('data')
    names = sorted(node.node_id for node in contract.nodes)
    expected_edges = sorted([binding.source_node, node.node_id]
                            for node in contract.nodes for binding in node.bindings)
    if graph['nodes'] != names or graph['edges'] != expected_edges:
        raise ValueError('graph differs from operator inventory or port bindings')
    goal = contract.model_copy(update={'goal_id': 'evoagentx.planner-handoff', 'propose_only': True})
    router = Router(manifest)
    try:
        proposal = StackService(router).propose(goal)
        if (not proposal.goal.propose_only
                or sorted(component.node_id for component in proposal.components) != names):
            raise ValueError('ordinary stack planner did not resolve the reviewed components')
        return {'goal_sha256': content_digest(goal), 'proposal_id': proposal.proposal_id,
                'request_sha256': request_sha256, 'nodes': names, 'bindings': expected_edges,
                'execution_authorized': False, 'executors_started': 0}
    finally:
        await router.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('graph', type=Path)
    parser.add_argument('--request-sha256', required=True)
    args = parser.parse_args()
    data = args.graph.read_bytes()
    if len(data) > 4096:
        raise ValueError('graph exceeds local handoff size')
    result = asyncio.run(inspect_graph(json.loads(data), args.request_sha256))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

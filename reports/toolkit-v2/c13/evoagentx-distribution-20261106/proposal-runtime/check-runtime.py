"""Verify the real EvoAgentX graph builder in the offline runtime, with no model."""

import contextlib
import json
import os
import sys
from pathlib import Path

sys.path[:0] = ['/opt', '/opt/evoagentx-dependencies', '/opt/evoagentx-source']
from check_socket_boundary import socket_boundary


def main():
    assert os.geteuid() == os.getegid() == 65534
    assert sys.version_info[:3] == (3, 12, 16)
    assert not Path('/var/run/docker.sock').exists() and not os.access('/opt', os.W_OK)
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    assert status['Seccomp'].strip() == '2' and status['NoNewPrivs'].strip() == '1'
    assert int(status['CapEff'], 16) == 0
    boundary = socket_boundary()
    with contextlib.redirect_stdout(sys.stderr):
        from evoagentx.workflow.workflow_generator import WorkFlowGenerator
        from evoagentx.actions.task_planning import TaskPlanningOutput
        from evoagentx.core.base_config import Parameter
        from evoagentx.workflow.workflow_graph import WorkFlowNode

        assert Path(sys.modules[WorkFlowGenerator.__module__].__file__).is_relative_to(
            '/opt/evoagentx-source/evoagentx'
        )
        from typing import Literal
        from evoagentx.agents.agent import Agent
        from evoagentx import tools
        assert Agent.model_fields['use_long_term_memory'].annotation == Literal[False]
        assert tools.__all__ == ['Tool', 'Toolkit']
        port = Parameter(name='document', type='string', description='Local document text')
        start = WorkFlowNode(name='source', description='Supply the document', outputs=[port])
        finish = WorkFlowNode(name='validate', description='Validate the document', inputs=[port])
        plan = TaskPlanningOutput(sub_tasks=[start, finish])
        generator = WorkFlowGenerator.model_construct()
        graph = generator.build_workflow_from_plan('Validate a public document', plan)
        assert [node.name for node in graph.nodes] == ['source', 'validate']
        assert [(edge.source, edge.target) for edge in graph.edges] == [('source', 'validate')]
    print(json.dumps({'actual_graph_builder_passed': True, 'boundary': boundary,
                      'fixture_kind': 'typed_local_graph', 'actual_proposal_generation': False,
                      'models': 0, 'generated_code_executed': False}))


if __name__ == '__main__':
    main()

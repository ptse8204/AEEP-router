"""Check the actual pinned optimizer and graph parser without model calls."""

import json
import os
import socket
import sys
from pathlib import Path

sys.path[:0] = ['/opt/aflow-dependencies', '/opt/aflow-source']
assert os.geteuid() == 65534
interfaces = sorted(name for _, name in socket.if_nameindex())
assert interfaces == ['lo']
route_rows = Path('/proc/net/route').read_text().splitlines()
assert len(route_rows) == 1 and route_rows[0].split()[0] == 'Iface'
assert not Path('/var/run/docker.sock').exists()
assert sys.version_info[:3] == (3, 12, 16)

import numpy
import pandas
from scripts.optimizer import GraphOptimize, Optimizer
from scripts.optimizer_utils.graph_utils import GraphUtils

assert numpy.__version__ == '2.0.2' and pandas.__version__ == '2.2.3'
assert Path(sys.modules[Optimizer.__module__].__file__).parent == Path('/opt/aflow-source/scripts')
fixture = 'class Workflow:\n    async def __call__(self):\n        return 1\n'
assert GraphUtils('/tmp/reviewed-graph').extract_solve_graph(fixture) == [fixture]
assert set(GraphOptimize.model_fields) == {'modification', 'graph', 'prompt'}
print(json.dumps({'optimizer_imported': True, 'actual_graph_parser_passed': True, 'models': 0,
                  'network_interfaces': interfaces, 'python': '3.12.16', 'generated_code_executed': False,
                  'optimizer_calibration': 'UNSTARTED'}))

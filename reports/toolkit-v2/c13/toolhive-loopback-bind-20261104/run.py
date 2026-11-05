"""Continue the retained ToolHive lifecycle behind an observed loopback listener."""
import argparse
import asyncio
import importlib.util
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'toolhive-mcp-launch-continuation-20261104'
sys.path.insert(0, str(PRIOR))
spec = importlib.util.spec_from_file_location('reviewed_toolhive_lifecycle', PRIOR / 'run.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class LoopbackJourney(base.Journey):
    async def start_server(self):
        args = self.review['run_arguments']
        port = self.review['port']
        assert args.count('--host') == args.count('--proxy-port') == 1
        assert args[args.index('--host') + 1] == '127.0.0.1'
        assert args[args.index('--proxy-port') + 1] == str(port)
        assert self.review['endpoint'] == f'http://127.0.0.1:{port}/mcp'
        # Check both protocols on the declared address. Nothing is left listening.
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as check:
                check.bind(('127.0.0.1', port))
        await super().start_server()
        listeners = await self.command(
            'verify-loopback-listener',
            [self.review['lsof'], '-a', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-Fpcn'],
            8,
        )
        assert [row for row in listeners.splitlines() if row.startswith('c')] == ['cthv']
        assert [row for row in listeners.splitlines() if row.startswith('n')] == [f'n127.0.0.1:{port}']
        assert not self.server.task.done()
        base.write(HERE / 'listener-verdict.json', {
            'observed_address': '127.0.0.1', 'port': port, 'process_command': 'thv',
            'matched_listeners': 1, 'raw_output_retained': False,
        })


parser = argparse.ArgumentParser()
parser.add_argument('--execute-approved', required=True)
args = parser.parse_args()
path = HERE / 'operation-review.json'
review = base.load(path)
identity = base.sha(path)
approval = base.load(HERE / 'operator-approval.json')
assert args.execute_approved == identity == approval['review_sha256'] and approval['approved'] is True
base.validate(review)
base.HERE = HERE
base.Journey = LoopbackJourney
result = asyncio.run(base.execute(review, identity))
print(base.json.dumps(result))
raise SystemExit(not result['passed'] or result['accounting_uncertain'])

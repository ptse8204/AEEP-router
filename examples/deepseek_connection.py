"""List schemas offline, or explicitly run a bounded DeepSeek application loop."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx

from aeep.integrations.connected_tools import ConnectedTools


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--connection', type=Path, required=True)
    parser.add_argument('--prompt')
    parser.add_argument('--model')
    args = parser.parse_args()
    bridge = ConnectedTools(args.connection)
    try:
        if not args.prompt:
            print(json.dumps(bridge.declarations(), indent=2))
            return
        if not args.model or not os.environ.get('DEEPSEEK_API_KEY'):
            parser.error('--prompt requires an explicit --model and DEEPSEEK_API_KEY in the application environment')
        messages = [{'role': 'user', 'content': args.prompt}]
        async with httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False) as client:
            for _ in range(8):
                response = await client.post('https://api.deepseek.com/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY']},
                    json={'model': args.model, 'messages': messages, 'tools': bridge.declarations()})
                if response.status_code != 200:
                    raise RuntimeError(f'DeepSeek request failed with HTTP {response.status_code}; response omitted')
                message = response.json()['choices'][0]['message']
                messages.append(message)
                calls = message.get('tool_calls', [])
                if not calls:
                    print(message.get('content', ''))
                    return
                for call in calls:
                    result = await bridge.call(call['function']['name'], json.loads(call['function']['arguments']))
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
            raise RuntimeError('Application turn ceiling reached; no further model calls made')
    finally:
        await bridge.close()


if __name__ == '__main__':
    asyncio.run(main())

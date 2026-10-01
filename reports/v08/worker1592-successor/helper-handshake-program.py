"""Fixed zero-model helper protocol check, executed only inside the reviewed worker."""
import asyncio
import json
import os


async def main():
    process = await asyncio.create_subprocess_exec(
        '/opt/codex/codex-code-mode-host', '--listen', 'stdio',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env={'PATH': os.environ.get('PATH', '')},
    )
    try:
        async with asyncio.timeout(10):
            hello = json.dumps({'type': 'connection/hello', 'supportedVersions': [1],
                'requiredCapabilities': [], 'optionalCapabilities': []}, separators=(',', ':')).encode()
            process.stdin.write(len(hello).to_bytes(4, 'little') + hello)
            await process.stdin.drain()
            length = int.from_bytes(await process.stdout.readexactly(4), 'little')
            if not 0 < length <= 4096:
                raise ValueError('bounded helper frame length rejected')
            ready = json.loads(await process.stdout.readexactly(length))
            if ready.get('type') != 'connection/ready' or ready.get('selectedVersion') != 1:
                raise ValueError('helper protocol readiness rejected')
            process.stdin.close()
            await process.stdin.wait_closed()
            await process.wait()
            stderr = await process.stderr.read(4097)
            if process.returncode != 0 or len(stderr) > 4096:
                raise ValueError('helper terminal bounds rejected')
            print(json.dumps({'helper_ready': True, 'selected_version': 1,
                'normal_exit': True, 'stderr_bytes': len(stderr)}))
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                process.kill()
                await asyncio.wait_for(process.wait(), 2)


asyncio.run(main())

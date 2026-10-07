"""Actual terminal interaction through packaged setup/menu; not a human usability score."""
import errno
import json
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

report = Path(__file__).parent
root = Path('/tmp/aeep-onboarding-continuation/menu').resolve()
root.mkdir(exist_ok=False)
home, project = root / 'home', root / 'project'
home.mkdir(); project.mkdir()
env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'AEEP_CONFIG_HOME': str(home / 'config'), 'TERM': 'dumb'}
command = [sys.executable, '-I', '-m', 'aeep']
setup = subprocess.run([*command, 'setup'], input='deepseek-api\n\ny\n', text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=env, cwd=project, timeout=120)
(report / 'menu-setup.log').write_text(setup.stdout)
setup.check_returncode()
market = root / 'marketplace/.claude-plugin/marketplace.json'
market.parent.mkdir(parents=True)
market.write_text(json.dumps({'name':'local-demo','plugins':[{'name':'storyboard','source':'./storyboard','description':'Video storyboard instruction metadata'}]}))


def menu(name, answers):
    master, slave = pty.openpty()
    process = subprocess.Popen(command, env=env, cwd=project, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    data = bytearray()
    try:
        os.write(master, answers.encode())
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO: raise
                    break
                if not chunk: break
                data.extend(chunk)
        process.wait(timeout=2)
        assert process.returncode == 0
        assert b'Cannot complete:' not in data and b'Aborted!' not in data, data.decode()
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=5)
        os.close(master)
        (report / (name + '.log')).write_bytes(data)


def explain():
    return json.loads(subprocess.check_output([*command,'access','explain','deepseek-api','--json'],env=env,cwd=project,text=True))


menu('menu-add-catalog',f'5\nadd\nlocal-demo\n{market.parent.parent}\ny\n8\n')
listed=json.loads(subprocess.check_output([*command,'catalogs','list','--json'],env=env,cwd=project,text=True))
assert len(listed['sources']) == 3
menu('menu-deny','4\ndeepseek-api\ndeny\naeep_stack_recommend\n8\n')
denied=explain()
assert not next(t for t in denied['tools'] if t['name']=='aeep_stack_recommend')['call_allowed_by_connection']
menu('menu-restore','4\ndeepseek-api\nallow\naeep_stack_recommend\ny\n6\n8\n')
restored=explain()
assert next(t for t in restored['tools'] if t['name']=='aeep_stack_recommend')['call_allowed_by_connection']
(report/'menu-result.json').write_text(json.dumps({'status':'passed','workspace':str(root), 'checks':['interactive setup','add local marketplace from menu','deny from menu','explain denied access','restore from menu','check setup from menu'], 'human_usability':'unverified; scripted terminal interaction','denied':denied,'restored':restored},indent=2)+'\n')

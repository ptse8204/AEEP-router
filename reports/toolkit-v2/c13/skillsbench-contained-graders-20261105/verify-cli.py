"""Exercise inert recipe registration and the ordinary CLI's dispatch guards."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name / 'recipes'
SOURCE = HERE.parent / 'skillsbench-ordinary-cli-preparation-20261105/workflow.json'


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    if path.exists():
        assert not path.is_symlink() and read(path) == value
        return
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o400)


def bind(path):
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    manifest = PRIVATE/'preview-manifest.json'
    save(manifest, {'version':'0.2','database':str(PRIVATE/'preview.sqlite3'),'executors':[]})
    workflow = read(SOURCE)
    records = read(HERE/'recipe-bindings.json')['records']
    workflows = zip(('document-data','software-engineering'),records,strict=True)
    matrix = [(name,row,PRIVATE/(row['role']+'-recipe.json')) for name,row in workflows]
    for name, _, path in matrix:
        workflow['configurations'][name]['benchmark_recipe'] = bind(path)
    definition = PRIVATE/'workflow-preview.json'
    save(definition,workflow)
    env = {'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONPATH':str(ROOT/'src'),
           'PYTHONDONTWRITEBYTECODE':'1','HOME':str(PRIVATE),'LC_ALL':'C'}

    def cli(*args):
        return subprocess.run([sys.executable,'-B',*args], env=env, cwd=ROOT,
                              text=True,capture_output=True,timeout=35)

    evidence = []
    for name, record, path in matrix:
        defined = cli('-m','aeep','assess','--manifest',str(manifest),'define',str(path))
        assert defined.returncode==0, defined.stderr[-400:]
        inert = json.loads(defined.stdout)
        assert inert == {'recipe_id':record['recipe_id'],'digest':record['recipe_digest'],'reviewed':False}
        selectors = ['--workflow',str(definition),'--configuration',name]
        planned = cli('-m','aeep_toolkit','workflow','plan',*selectors)
        assert planned.returncode==0, planned.stderr[-400:]
        preview = json.loads(planned.stdout)
        selected = preview['workflow']['configurations'][name]
        assert selected['benchmark_recipe']==bind(path)
        assert 'selected task asset rights have no exact review reference' in preview['blockers']
        blocked = PRIVATE/(record['role']+'-blocked-plan')
        prepared = cli('-m','aeep_toolkit','workflow','prepare',*selectors,
                       '--reviewed-digest',preview['review_sha256'],'--write-plan',str(blocked))
        assert prepared.returncode==2 and not blocked.exists()
        evidence.append({'configuration':name,'recipe':inert,
                         'selected_task':preview['benchmark']['tasks'][0]['task_id'],
                         'workflow_review_sha256':preview['review_sha256'],
                         'blockers':preview['blockers'],'prepare_exit_code':2,'plan_written':False})
    save(HERE/'cli-preparation.json', {'operation':'Ordinary CLI recipe definition, workflow preview and blocked preparation',
        'workflows':evidence,'workflow_sha256':bind(definition)['sha256'],
        'provider_disclosure_authorized':False,'model_turns':0,'comparison':'PAUSED'})
    print(json.dumps([row['configuration'] for row in evidence]))


if __name__ == '__main__':
    main()

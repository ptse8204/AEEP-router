"""Record exact task rights and register inert cases via the ordinary CLI."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.models import (
    AssessmentEnvironment,
    IntegrationCaseSet,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.registry import validate_json
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview, require_rights

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = HERE.parent
PRIVATE = ROOT / '.aeep/skillsbench-contained-graders-20261105/rights-bound'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o400)


def apply(identity):
    path = HERE/'operation-review.json'
    approval = read(HERE/'operator-approval.json')
    assert sha(path)==identity==approval['review_sha256'] and approval['approved'] is True
    review = read(path)
    pack_path = REPORTS/'skillsbench-transport-20261103/task-only-pack.json'
    assert sha(pack_path)==review['task_only_pack_file_sha256']
    original = BenchmarkPack.model_validate(read(pack_path))
    roots = ROOT/'.aeep/skillsbench-stack-9a1f4dd5'
    PRIVATE.mkdir(mode=0o700)
    manifest = PRIVATE/'aeep.json'
    database = PRIVATE/'definitions.sqlite3'
    write(manifest, {'version':'0.2','database':str(database),'executors':[]})
    env = {'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONPATH':str(ROOT/'src'),
           'HOME':str(PRIVATE),'PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}

    def cli(*argv):
        process = subprocess.run([sys.executable,'-B',*argv], env=env, cwd=ROOT,
                                 capture_output=True,text=True,timeout=30)
        assert process.returncode==0, process.stderr[-500:]
        return json.loads(process.stdout)

    refs = {}
    for row in review['records']:
        name = row['task_id']
        record = HERE/row['draft_decision_file']
        assert sha(record)==row['decision_file_sha256']
        decision = TaskRightsReview.model_validate(read(record))
        assert content_digest(decision)==row['decision_digest']
        assert decision.assets=={item.path:item.sha256 for item in original.task(name).assets}
        assert task_input(original,roots,name)['task_archive_sha256']==row['original_public_archive_sha256']
        defined = cli('-m','aeep_toolkit','workflow','define-rights','--file',str(record),'--manifest',str(manifest))
        reference = row['decision_digest']
        assert defined=={'rights_review_ref':reference,'reviewed':False,'execution_authorized':False}
        reviewed = cli('-m','aeep','assess','--manifest',str(manifest),'review',reference)
        assert reviewed=={'digest':reference,'reviewed':True}
        refs[name] = reference

    pack = original.model_copy(update={'tasks':tuple(
        task.model_copy(update={'rights_review_ref':refs[task.task_id]}) if task.task_id in refs else task
        for task in original.tasks)})
    pack_digest = content_digest(pack.model_dump(mode='json'))
    bound_pack = PRIVATE/'task-only-pack.json'
    write(bound_pack,pack.model_dump(mode='json'))
    with ReceiptStore(database) as store:
        require_rights(AssessmentRepository(store),pack,tuple(refs))

    evidence = []
    workflow = read(PRIVATE.parent/'recipes/workflow-preview.json')
    for configuration,role in (('document-data','sales'),('software-engineering','spring')):
        old_recipe = PRIVATE.parent/'recipes'/(role+'-recipe.json')
        data = read(old_recipe)
        task_id = data['variations'][0]
        task = task_input(pack,roots,task_id)
        prior_task = task_input(original,roots,task_id)
        assert {k:v for k,v in task.items() if k!='benchmark_pack_sha256'}=={
            k:v for k,v in prior_task.items() if k!='benchmark_pack_sha256'}
        data['dependencies']['benchmark_pack'] = pack_digest
        data['input_schema']['properties']['benchmark_pack_sha256']['const'] = pack_digest
        recipe = RecipeDefinition.model_validate(data)
        validate_json(task,recipe.input_schema,label='reviewed upstream task')
        recipe_file = PRIVATE/(role+'-recipe.json')
        write(recipe_file,recipe.model_dump(mode='json'))
        result = cli('-m','aeep','assess','--manifest',str(manifest),'define',str(recipe_file))
        assert result=={'recipe_id':recipe.recipe_id,'digest':content_digest(recipe),'reviewed':False}
        verifier_folder = ('skillsbench-sales-dependencies-20261105' if role=='sales'
                           else 'skillsbench-contained-graders-20261105')
        grader = REPORTS/verifier_folder/'grader-execution'
        assert read(grader/'summary.json')['results'][role]['passed']
        environment = AssessmentEnvironment.model_validate(read(grader/(role+'-environment.json')))
        case_set = IntegrationCaseSet.model_validate({
            'request_id':'skillsbench-'+role+'-rights-bound','recipe_digest':content_digest(recipe),
            'environment_digest':content_digest(environment),'benchmark_pack_digest':pack_digest,'seed':0,
            'cases':[{'case_id':task_id,'split':'qualification',
                      'action':{'capability':recipe.capability,'input':task},
                      'variation':task_id,'template_family':'skillsbench:'+task_id,
                      'validators':[{'kind':'exact_match','config':{
                          'expected':{'task_archive_sha256':task['task_archive_sha256']}}}]}],
        })
        case_file = PRIVATE/(role+'-integration-cases.json')
        write(case_file,case_set.model_dump(mode='json'))
        cases = cli('-m','aeep','assess','--manifest',str(manifest),'define-integration-cases',str(case_file))
        assert cases=={'integration_case_set_id':content_digest(case_set),'reviewed':False,'execution_authorized':False}
        selected = workflow['configurations'][configuration]
        selected['benchmark'] = {'path':str(bound_pack),'sha256':sha(bound_pack)}
        selected['benchmark_recipe'] = {'path':str(recipe_file),'sha256':sha(recipe_file)}
        evidence.append({'configuration':configuration,'rights_review_ref':refs[task_id],
             'task_id':task_id,'archive_sha256':task['task_archive_sha256'],
             'recipe_digest':content_digest(recipe),'integration_case_set_id':content_digest(case_set),
             'grader_environment_digest':content_digest(environment),'grader_image_id':environment.container_image,
             'plan_draft_created':False,'model_turns':0})
    workflow_file = PRIVATE/'workflow.json'
    write(workflow_file,workflow)
    for row in evidence:
        preview = cli('-m','aeep_toolkit','workflow','plan','--workflow',str(workflow_file),
                      '--configuration',row['configuration'])
        assert not any('asset rights have no exact review' in item for item in preview['blockers'])
        assert preview['benchmark']['tasks'][0]['rights_review_ref']==row['rights_review_ref']
        row.update(preview_sha256=preview['review_sha256'],remaining_blockers=preview['blockers'])
    write(HERE/'result.json',{'review_sha256':identity,'pack_content_digest':pack_digest,
        'workflow_sha256':sha(workflow_file),'records':evidence,'provider_dispatch_authorized':False,
        'model_turns':0,'comparisons':'PAUSED','applied_at':datetime.now(UTC).isoformat()})
    print(json.dumps({'recorded':len(evidence),'models':0,'dispatch_authorized':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-approved',required=True)
    args = parser.parse_args()
    apply(args.apply_approved)

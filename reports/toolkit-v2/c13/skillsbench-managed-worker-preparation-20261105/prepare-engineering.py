"""Freeze the two role pairs for the already approved SkillsBench scope."""

import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep_toolkit.candidate import inspect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = HERE.parent
PRIVATE = ROOT/'.aeep'/HERE.name/'engineering'
DEFINITIONS = ROOT/'.aeep/skillsbench-contained-graders-20261105/rights-bound'
PRIOR = REPORTS/'worker-readiness-correction-20261103'
SKILL = PRIOR/'candidate'
DOMAIN = {'document-data':'sales', 'software-engineering':'spring'}
ARTIFACTS = {
    'sales': ('workbook_b64', 'demographic_analysis.xlsx', 300000),
    'spring': ('workspace_b64', 'workspace.zip', 256000),
}
COMMON_INSTRUCTIONS = (
    'Read the exact upstream task in the supplied task JSON. Use Python zipfile to unpack the '
    'bound skillsbench-task.zip into your private workspace and find the original inputs under '
    'the selected task environment directory. Treat original absolute paths as private workspace '
    'paths. Use the supplied stack-check skill for isolation and output discipline. Follow the '
    'actual task below and write the requested artifact to its bound output path. Do not install '
    'software, connect to other services, search for answers, or put encoded data into your response. '
    'After writing the artifact return the required completion JSON.\nTask and artifact paths:\n{input}'
)
INSTRUCTIONS = {
    'sales': (
        'Sales Pivot input files are population.pdf and income.xlsx. Python already has openpyxl. '
        'Use pypdf with sys.path.insert(0, "/opt/aeep-task-tools/pypdf-6.21.4-py3-none-any.whl") '
        'and extract_text(extraction_mode="layout") to read the supplied PDF. '
        'The output is the requested workbook, not a text or JSON substitute. '
        'Keep the original ABS source attribution. '
    ),
    'spring': (
        'The original project lives in the extracted environment/workspace directory. '
        'The exact installed toolchain is under /opt/aeep-task-tools/spring. Set JAVA_HOME to '
        'its java directory, and invoke its maven/bin/mvn with --offline, --settings pointing '
        'to its settings.xml, and -Dmaven.repo.local=/opt/aeep-task-tools/spring/cache. '
        'The offline cache contains Spring Boot 3.2.0. Run the original compile and test goals. '
        'Write the bound ZIP containing pom.xml and the original src file paths relative to '
        'the project root, without target, caches or enclosing folders. '
    ),
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o400)


def require_review():
    path = HERE/'engineering-dispatch-review.json'
    review = read(path)
    approval = read(HERE/'engineering-operator-approval.json')
    assert approval['approved'] is True and sha(path)==approval['review_sha256']
    assert verification_source_digest(ROOT)==review['source_sha256']
    assert all(sha(path)==pin for path,pin in review['pins'].items())
    assert review['maximum_model_turns']==2 and review['maximum_cash_usd']=='0'
    assert review['comparisons']=='PAUSED' and review['evaluator']=='managed'
    return review


def pairs(review):
    helper = importlib.util.spec_from_file_location('reviewed_neutral_worker_pair', PRIOR/'integration.py')
    assert helper and helper.loader
    previous = importlib.util.module_from_spec(helper)
    helper.loader.exec_module(previous)
    selected = {}
    for row in review['cases']:
        config, task = row['configuration'], row['task_id']
        domain = DOMAIN[config]
        candidate = review['worker_image_ids'][domain+'-candidate']
        old_pair, old_shared = previous.pair(candidate,review['source_sha256'])
        raw = old_pair.model_dump(mode='json')
        recipe_file = DEFINITIONS/(domain+'-recipe.json')
        recipe = RecipeDefinition.model_validate_json(recipe_file.read_bytes())
        assert content_digest(recipe)==row['recipe_digest']
        output_field, output_name, maximum = ARTIFACTS[domain]
        task_files = read(DEFINITIONS/(domain+'-integration-cases.json'))['cases'][0]['action']['input']
        assert task_files['task_id']==task and task_files['task_archive_sha256']==row['archive_sha256']
        images = {'control':review['worker_image_ids'][domain+'-control'], 'treatment':candidate}
        shared = old_shared | {
            'purpose':'Protected SkillsBench engineering only', 'recipe':content_digest(recipe),
            'worker_images':images, 'archive_sha256':row['archive_sha256'],
            'candidate_sha256':inspect(SKILL).sha256,
        }
        reference = content_digest(shared)
        inventory = raw['differential']['control_inventory'] | {'common_profile':reference}
        raw['differential'].update(shared_definition_digest=reference,control_inventory=inventory,
            treatment_inventory=inventory|raw['differential']['candidate_inventory'])
        for role, image in images.items():
            executor = raw[role]
            executor.update(id='skillsbench-'+domain+'.'+role, capability=recipe.capability,
                input_schema=recipe.input_schema,output_schema=recipe.output_schema)
            cfg = executor['config']
            cfg.pop('assessment_adapter',None)
            cfg.update(adapter_id='codex-app-server:skillsbench-'+domain+'-'+role,
                artifact={'input_field':'task_archive_b64','output_field':output_field,
                          'input_name':'skillsbench-task.zip','output_name':output_name,'max_bytes':maximum},
                instructions=INSTRUCTIONS[domain]+COMMON_INSTRUCTIONS,timeout_seconds=900)
            cfg['managed_worker'].update(worker_id='skillsbench-'+domain+'-'+role,image=image)
        pair = WorkerPairInspection.model_validate(raw)
        assert pair.control.managed_host_config().artifact==pair.treatment.managed_host_config().artifact
        assert pair.control.managed_host_config().store_output is False
        assert pair.control.managed_host_config().store_prompt is False
        selected[domain]=(row,recipe,pair,shared)
    return selected


if __name__=='__main__':
    review = require_review()
    PRIVATE.mkdir(mode=0o700)
    summary = {}
    for domain,(row,recipe,pair,shared) in pairs(review).items():
        write(PRIVATE/(domain+'-pair.json'),pair.model_dump(mode='json'))
        write(PRIVATE/(domain+'-shared.json'),shared)
        summary[domain]={'task_id':row['task_id'],'recipe_digest':content_digest(recipe),
                         'pair_digest':content_digest(pair),'supporting_tools_bound':True}
    write(HERE/'engineering-pair-preflight.json',{'models':0,'pairs':summary,
        'source_sha256':review['source_sha256'],'comparisons':'PAUSED','workers_started':False})
    print(json.dumps(summary))

"""Bind the new observer/runtime definitions as data without changing case splits."""
import base64
import hashlib
import json
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment,AssessmentSubject,RecipeDefinition,
    RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest)
from aeep.assessment.repository_suites import archive_files,pack_files
from aeep.assessment.verification import verification_source_digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior=HERE.parent/'repository-suite-integration-20261022/grader-operation-review.json'
    old=json.loads(prior.read_text())
    metadata=json.loads((HERE/'prepared-plugin-cases.json').read_text())
    recipe=RecipeDefinition.model_validate_json((ROOT/metadata['recipe_file']).read_text())
    assert recipe.dependencies['program']!=old['recipe']['dependencies']['program']
    runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies())
    environment=AssessmentEnvironment.model_validate(next(item['document'] for item in old['documents'].values() if item['kind']=='environment'))
    subject=AssessmentSubject(kind='command',location=str((ROOT/metadata['recipe_file']).parent),
        dependency_digests={str(ROOT/metadata['recipe_file']):sha(ROOT/metadata['recipe_file'])},
        description='Unexecuted v2 observer envelope. New qualification-labelled source candidates stay separate from development recipe cases.')
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),
        environment_digest=content_digest(environment),authorization_id='onboarding',seed=48,
        definition_digests=[content_digest(recipe),content_digest(environment),content_digest(runtime)],runtime_dependencies=runtime.dependencies)
    documents={content_digest(value):{'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
        for kind,identity,value in [('subject',subject.subject_id,subject),('recipe',recipe.recipe_id,recipe),
            ('environment',environment.environment_id,environment),('recipe_runtime',content_digest(runtime),runtime),
            ('recipe_materialization_request',request.plan_id,request)]}
    wheels=json.loads((HERE/'runtime-wheel-review.json').read_text())
    versions={item['project']:item['version'] for item in wheels['pins']}
    probes=[]
    for item in old['probes']:
        payload=json.loads((ROOT/item['payload']).read_text())
        files=archive_files(base64.b64decode(payload['archive']))
        if item['name']=='boundary':
            code=files['tests/test_boundary.py'].decode().replace('def test_boundary():','def test_boundary(mocker):')
            code+='\n    import importlib.metadata, sys\n    assert sys.version_info[:3] == (3,13,15)\n'
            code+='    versions='+repr(versions)+'\n    assert all(importlib.metadata.version(name)==version for name,version in versions.items())\n'
            code+='    assert mocker.Mock(return_value="explicit-plugin")() == "explicit-plugin"\n'
            code+='    import numpy, orjson, psutil, aioshutil, pyparsing, github, requests\n'
            code+='    assert int(numpy.array([1,2]).sum()) == 3\n    assert orjson.loads(b"[1,2]")==[1,2]\n    assert psutil.Process().pid > 0\n'
            code+='    from nacl.signing import SigningKey\n    key=SigningKey(bytes(32))\n    assert key.verify_key.verify(key.sign(b"synthetic fixture"))==b"synthetic fixture"\n'
            code+='    from cryptography.hazmat.primitives import hashes\n    digest=hashes.Hash(hashes.SHA256())\n    digest.update(b"synthetic fixture")\n    assert len(digest.finalize())==32\n'
            files['tests/test_boundary.py']=code.encode()
        archive=pack_files(files)
        payload.update(archive=base64.b64encode(archive).decode(),archive_sha256=hashlib.sha256(archive).hexdigest(),
            pytest_plugins=['pytest_mock'],source_modules=[])
        probes.append({**item,'payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),
            'archive_sha256':payload['archive_sha256'],'payload_bytes':len(json.dumps(payload,separators=(',',':')).encode())})
    value={'source_digest':verification_source_digest(ROOT),'prior_definition_only':str(prior.relative_to(ROOT)),
        'prior_review_sha256':sha(prior),'recipe':recipe.model_dump(mode='json'),'documents':documents,
        'request':request.model_dump(mode='json'),'authorization_digest':old['authorization_digest'],
        'image':environment.container_image,'docker':old['docker'],'socket':old['socket'],'host_canary':old['host_canary'],
        'probes':probes,'external_execution':False,'old_conformance_applies_to_new_observer':False}
    with (HERE/'observer-envelope.json').open('x') as stream: json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps({'observer_envelope_sha256':sha(HERE/'observer-envelope.json'),'probes':len(probes),
        'recipe_digest':content_digest(recipe),'external_execution':False}))


if __name__=='__main__': main()

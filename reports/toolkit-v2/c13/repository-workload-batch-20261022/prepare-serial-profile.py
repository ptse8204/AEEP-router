"""Predeclare serial pytest execution without changing task assertions."""
import configparser
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import tomllib

from aeep.assessment.repository_suites import pack_files

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def main():
    spec=importlib.util.spec_from_file_location('existing_inert_packer',HERE.parent/'repository-suite-integration-20261022/prepare-development-assets.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=next(x for x in json.loads((HERE/'source-review.json').read_text())['sources'] if x['instance_id']=='joshuadavidthomas__django-bird-239')
    old=ROOT/source['private_cache'];files,_=module.normalize((old/'source.tar.gz').read_bytes());assert 'pytest.ini' not in files
    options=tomllib.loads(files['pyproject.toml'].decode())['tool']['pytest']['ini_options']
    assert shlex.split(options['addopts'])==['--create-db','-n','auto','--dist','loadfile','--doctest-modules']
    normalized={k:'\n'.join(map(str,v)) if isinstance(v,list) else str(v).lower() if isinstance(v,bool) else str(v) for k,v in options.items()}
    normalized['addopts']='--create-db --doctest-modules'
    config=configparser.ConfigParser(interpolation=None);config['pytest']=normalized
    stream=io.StringIO();config.write(stream);profile=stream.getvalue().encode();files['pytest.ini']=profile
    target=ROOT/'.aeep/repository-workload-batch-20261022-django-serial-source';target.mkdir(exist_ok=False)
    shutil.copyfile(old/'row.json',target/'row.json');archive=pack_files(files);(target/'source-only.tar.gz').write_bytes(archive)
    entry={**source,'status':'SOURCE_SCOPE_REVIEW_REQUIRED','private_cache':str(target.relative_to(ROOT)),
        'normalized_archive_bytes':len(archive),'normalized_archive_sha256':hashlib.sha256(archive).hexdigest(),
        'scope':'Complete original source archive plus a reviewed pytest.ini retaining the original pyproject pytest options except automatic xdist workers/dispatch. Serial execution matches this grader. No upstream assertion or Python source changed.',
        'authored_runtime_configuration':{'path':'pytest.ini','sha256':hashlib.sha256(profile).hexdigest(),'original_pyproject_preserved':True,'removed_args':['-n','auto','--dist','loadfile'],'all_other_pytest_options_retained':True,'reason':'Existing grader is serial; unrestricted n-auto would introduce unreviewed processes and resource concurrency.'}}
    scopes=json.loads((HERE/'source-scope-review-v2.json').read_text());scopes['sources'].append(entry);(HERE/'source-scope-review-v3.json').write_text(json.dumps(scopes,indent=2)+'\n')
    (HERE/'serial-profile-review.json').write_text(json.dumps(entry['authored_runtime_configuration'],indent=2)+'\n')
    print(json.dumps({'upstream_assertions_changed':False,'upstream_python_source_changed':False,'serial_profile_sha256':hashlib.sha256(profile).hexdigest(),'external_code_executed':False}))


if __name__=='__main__':main()

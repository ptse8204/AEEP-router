"""Narrow proposed dependencies and retain one needed source documentation file."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version
from aeep.assessment.repository_suites import archive_files, pack_files

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def main():
    cached=json.loads((HERE/'runtime-support-review.json').read_text())
    keep={'pydantic','pydantic-core','annotated-types','typing-inspection','email-validator','dnspython','django','asgiref','sqlparse','pytest-django','attrs','sybil','pytest-asyncio','pytz'}
    pins=[x for x in cached['pins'] if canonicalize_name(x['project']) in keep]
    assert len(pins)==14
    inherited=json.loads((HERE.parent/'repository-replacement-runtime-20261022/runtime-wheel-review.json').read_text())['pins']
    versions={canonicalize_name(x['project']):x['version'] for x in [*inherited,*pins]}
    checks=[]
    for pin in pins:
        for raw in pin['requires_dist']:
            req=Requirement(raw)
            extras={'','email'} if canonicalize_name(pin['project'])=='pydantic' else {''}
            if req.marker and not any(req.marker.evaluate({**cached['target_marker_environment'],'extra':extra}) for extra in extras):continue
            selected=versions.get(canonicalize_name(req.name));checks.append({'project':pin['project'],'requires':raw,'selected':selected,'satisfied':selected is not None and Version(selected) in req.specifier})
    assert all(c['satisfied'] for c in checks)
    review={**cached,'pins':pins,'active_requirement_checks':checks,'downloaded_wheel_bytes':sum(x['size_bytes'] for x in pins),'complete_static_dependency_closure':True,
        'cached_but_not_selected':[x['project'] for x in cached['pins'] if canonicalize_name(x['project']) not in keep],
        'narrowing_reason':'Only supports needed by the final prepared cases. Dead/Djpress and their unused dependencies remain excluded; no install includes those bytes.'}
    (HERE/'runtime-install-review.json').write_text(json.dumps(review,indent=2)+'\n')
    scope=json.loads((HERE/'source-scope-review.json').read_text())
    row=next(x for x in scope['sources'] if x['instance_id']=='hynek__svcs-140')
    old=ROOT/row['private_cache']; files=archive_files((old/'source-only.tar.gz').read_bytes())
    raw=(old/'full-upstream.tar.gz').read_bytes();assert len(raw)<=3_000_000
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=[m for m in archive if m.name.endswith('/CHANGELOG.md') and m.name.count('/')==1]
        assert len(members)==1 and members[0].isfile() and members[0].size<200_000
        content=archive.extractfile(members[0]).read()
    assert 'CHANGELOG.md' not in files;files['CHANGELOG.md']=content
    directory=ROOT/'.aeep/repository-workload-batch-20261022-svcs-full-reference-scope';directory.mkdir(exist_ok=False)
    shutil.copyfile(old/'row.json',directory/'row.json');packed=pack_files(files);(directory/'source-only.tar.gz').write_bytes(packed)
    row.update(private_cache=str(directory.relative_to(ROOT)),normalized_archive_sha256=hashlib.sha256(packed).hexdigest(),normalized_archive_bytes=len(packed),
        retained_regular_files=len(files),retained_bytes=sum(map(len,files.values())),scope=row['scope']+' Base CHANGELOG.md retained so its published documentation hunk applies inertly; source edits/assertions unchanged.',
        additional_retained={'path':'CHANGELOG.md','sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)},
        omitted=[x for x in row['omitted'] if x['path']!='CHANGELOG.md'])
    (HERE/'source-scope-review-v2.json').write_text(json.dumps(scope,indent=2)+'\n')
    print(json.dumps({'proposed_wheels':len(pins),'proposed_wheel_bytes':review['downloaded_wheel_bytes'],'closure_verified':True,'svcs_scope_bytes':len(packed),'external_execution':False}))


if __name__=='__main__':main()

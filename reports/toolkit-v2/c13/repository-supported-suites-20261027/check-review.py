"""Check exact assets and pure review derivation; never provision or dispatch."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile

from aeep.assessment.models import AssessmentEnvironment, RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    review=json.loads((HERE/'approval-bundle.json').read_text());digest=sha(HERE/'approval-bundle.json')
    assert verification_source_digest(ROOT)==review['source_digest']
    assert not any((HERE/name).exists() for name in ('operator-approval.json','execution-started.json','build-result.json'))
    for name,expected in review['assets'].items():
        path=Path(name);assert path.is_file() and not path.is_symlink() and sha(path)==expected
    # This fixture can write only review JSON in a temporary owned directory.
    # It grants nothing and never calls Docker, AssessmentService or an executor.
    with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-review-only-',dir=ROOT/'.aeep') as temp:
        fixture=Path(temp);out=fixture/'runtime-execution';out.mkdir()
        for name in ('run.py','classify.py','audit-execution.py'):shutil.copyfile(HERE/'runtime-execution'/name,out/name)
        (fixture/'approval-bundle.json').write_bytes((HERE/'approval-bundle.json').read_bytes())
        (fixture/'SYNTHETIC_FIXTURE_ONLY.json').write_text(json.dumps({'no_execution_authority':True,'scope':'Pure deterministic JSON derivation only'}))
        (fixture/'operator-approval.json').write_text(json.dumps({'approved':True,'review_sha256':digest,'operator_text':'SYNTHETIC FIXTURE ONLY; no actual user response or execution authority'}))
        synthetic_image='sha256:'+'f'*64
        (fixture/'build-result.json').write_text(json.dumps({'passed':True,'parent_review_sha256':digest,'image_id':synthetic_image,'fixture_only':True}))
        spec=importlib.util.spec_from_file_location('pure_derived_review_fixture',HERE/'derive-execution.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.HERE,module.ROOT,module.OUT=fixture,ROOT,out
        with contextlib.redirect_stdout(io.StringIO()):module.main()
        derived=json.loads((out/'operation-review.json').read_text());parent=json.loads((out/'parent-runtime-review.json').read_text())
        request=RecipeMaterializationRequest.model_validate(derived['request']);amendment=AssessmentScopeAmendment.model_validate(derived['amendment'])
        env_entry=next(x for x in parent['documents'].values() if x['kind']=='environment');environment=AssessmentEnvironment.model_validate(env_entry['document'])
        assert environment.container_image==synthetic_image and content_digest(environment)==request.environment_digest
        assert derived['assets']==review['assets'] and derived['expectations']==review['expectations']
        assert derived['active_case_ids']==review['active_case_ids']
        assert (derived['maximum_contained_calls'],derived['maximum_operations'],derived['maximum_reserved_seconds'])==(20,22,850)
        assert set(derived['driver_files'])=={'run.py','classify.py','audit-execution.py'}
        assert derived['probes']==parent['probes']
        assert amendment.environment_digests==[request.environment_digest]
    assert not fixture.exists()
    assert not any((HERE/name).exists() for name in ('operator-approval.json','execution-started.json','build-result.json'))
    checks={'passed':True,'review_sha256':digest,'assets_reopened':len(review['assets']),'source_unchanged':True,'deterministic_image_bound_derivation_fixture':True,
        'synthetic_fixture_removed':True,'actual_operator_approval_present':False,'new_builds_or_containers_or_installs':0,'model_turns':0,'authority_granted_by_fixture':False}
    (HERE/'static-bundle-audit.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks))


if __name__=='__main__':main()

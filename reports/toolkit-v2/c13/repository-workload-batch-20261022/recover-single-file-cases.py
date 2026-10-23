"""Recover two misclassified tasks by regrading identical retained payloads only."""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, archive_files, decode_patch, grade_suite_output, patch_artifact
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.models import ExecutionReceipt

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'repository-screening-curation-20261022'
OUT=ROOT/'.aeep/repository-recovered-single-file-20261022'
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def executable(data):
    class Strip(ast.NodeTransformer):
        def visit_Expr(self,node):
            return None if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) else self.generic_visit(node)
    return ast.dump(Strip().visit(ast.parse(data)),include_attributes=False)


async def main():
    review=json.loads((PRIOR/'operation-review.json').read_text());audit=json.loads((PRIOR/'completion-audit.json').read_text());execution=json.loads((PRIOR/'execution-result.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    oldcases=[RepositorySuiteCase.model_validate(x) for x in json.loads((ROOT/review['cases_file']).read_text())]
    variants=json.loads((ROOT/review['variants_file']).read_text());observations={x['name']:x for x in execution['observations']}
    OUT.mkdir(exist_ok=False);cases=[];records=[]
    for identity in ['fox-it__dissect.cstruct-120','kaste__mockito-python-93']:
        assert identity in audit['eligible_cases'];case=next(x for x in oldcases if x.input.task_id==identity)
        original=archive_files(case.truth.source.read());reference=decode_patch(json.loads(case.reference.read()))
        changed=[name for name,text in reference.files.items() if executable(original[name])!=executable(text)]
        assert len(changed)==1 and len(reference.files)==2
        value=case.model_dump(mode='json');value['input']['family']='single-file-repair';value['input']['task_id']+='-single-file-scope';binding=content_digest(value['input'])
        value['independent_case_id']=value['input']['task_id'];value['truth']['input_sha256']=binding
        reference.base_sha256=binding;artifact=patch_artifact(reference);path=OUT/(identity+'-reference.json');path.write_text(json.dumps(artifact,separators=(',',':')))
        value['reference']=SuiteAsset(path=str(path.resolve()),sha256=sha(path),size_bytes=path.stat().st_size).model_dump(mode='json')
        for fault in value['fault_outputs']:
            patch=decode_patch(fault);patch.base_sha256=binding;fault.update(patch_artifact(patch))
        value['provenance']+=' Separate pre-freeze family correction: exactly one Python AST body changes after stripping documentation strings. Reference still retains both original replacement files. Source,assertions,observer,wheels,expected test identities and every physical payload remain unchanged. Regraded retained observations only; no external rerun or model outcome. Old multi-file label is preserved in its historical record and is not counted.'
        adapted=RepositorySuiteCase.model_validate(value);proofs=[]
        for label in ('reference','counterexample'):
            name=identity+'-'+label;observed=observations[name];raw_path=PRIOR/observed['raw_file'];assert sha(raw_path)==observed['raw_sha256'];raw=json.loads(raw_path.read_text())
            receipt_record=next(x for x in execution['receipts'] if x['name']==name)
            database=BASE/review['request']['plan_id']/'recipe-operations'/(observed['operation_id']+'.sqlite3')
            with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as connection:
                rows=connection.execute('SELECT payload_json FROM receipts').fetchall();assert len(rows)==1
                receipt=ExecutionReceipt.model_validate_json(rows[0][0]);assert content_digest(receipt)==receipt_record['receipt_ref']
                row=connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?',(receipt.metadata['attempt_id'],)).fetchone();attempt=ExecutionAttempt.model_validate_json(row[0]);assert attempt.state is ExecutionAttemptState.COMPLETED and receipt.receipt_id in attempt.terminal_receipt_ids
            assert not subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--filter','name=^/'+receipt_record['container_name']+'$','--format','{{.ID}}'],timeout=15).strip()
            staged=next(x for x in variants if x['case']==identity and x['variant']==label)
            async def retained(payload):
                digest=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest();assert digest==staged['sha256']
                proofs.append({'variant':label,'unchanged_physical_payload_sha256':digest,'receipt_ref':receipt_record['receipt_ref'],'completed_attempt_reopened':True,'container_absent':True,'raw_file':str(raw_path.relative_to(ROOT)),'raw_sha256':observed['raw_sha256']});return raw['output']
            output=artifact if label=='reference' else patch_artifact(type(reference)(base_sha256=binding,files={}))
            grade=await grade_suite_output(adapted.input.model_dump(mode='json'),adapted.truth.model_dump(mode='json'),output,retained)
            assert grade.valid==(label=='reference') and grade.detail==('' if label=='reference' else 'test_failure')
        assert adapted.truth.fail_to_pass==case.truth.fail_to_pass and adapted.truth.pass_to_pass==case.truth.pass_to_pass
        assert adapted.truth.source==case.truth.source and adapted.truth.tests==case.truth.tests and adapted.truth.wheels==case.truth.wheels
        cases.append(adapted);records.append({'old_case_id':identity,'new_case_id':adapted.input.task_id,'executable_changed_files':changed,'reference_files_retained':list(reference.files),'required_test_identities':len(case.truth.fail_to_pass)+len(case.truth.pass_to_pass),'proofs':proofs})
    path=OUT/'cases.json';path.write_text(json.dumps([c.model_dump(mode='json') for c in cases],indent=2)+'\n')
    result={'passed':True,'authority':'Standing finite test-definition delegation; no new untrusted execution.','cases_file':str(path.relative_to(ROOT)),'cases_file_sha256':sha(path),'source_digest_of_original_execution':execution['source_digest'],'records':records,'case_count':2,'family':'single-file-repair','canonical_receipts_and_attempts_reopened':4,'new_external_calls':0,'new_model_turns':0,'new_canonical_operations':0,'old_results_changed':False,'cases_adopted':0,'stages_frozen':False,'current_source_runtime_conformance_transferred':False,'qualification':False,'comparative_usefulness':False,'selection':False}
    (HERE/'recovered-single-file-cases.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('passed','case_count','canonical_receipts_and_attempts_reopened','new_external_calls')}))


if __name__=='__main__':asyncio.run(main())

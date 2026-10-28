"""Freeze cached-source derivation and two existing native profiles; no dispatch."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,pack_files,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;PREV=HERE.parent/'repository-native-identity-20261028'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def main():
    source=verification_source_digest(ROOT);stable=json.loads((PREV/'validation/source-stability.json').read_text())
    assert stable['all_passed'] and stable['source_digest']==source and json.loads((PREV/'remaining-execution-result.json').read_text())['remaining_docs_passed']
    for name in ('native-scope-check.json','terminal-control-check-v2.json'):assert json.loads((HERE/name).read_text())['passed']
    meta=json.loads((HERE/'prepared-seeds.json').read_text());assert sha(ROOT/meta['cases_file'])==meta['cases_file_sha256'] and sha(ROOT/meta['records_file'])==meta['records_sha256']
    seeds=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/meta['cases_file']).read_text())];assert len(seeds)==3
    previous=json.loads((PREV/'operation-review.json').read_text());parent=json.loads((PREV/'observer-envelope.json').read_text());recipe=RecipeDefinition.model_validate(parent['recipe'])
    operator=recipe.extension.grader.config['argv'][-1];assert hashlib.sha256(operator.encode()).hexdigest()==sha(PREV/'observer-v6-integrated.py')
    default=operator.replace('OPERATOR_REVIEW = True','OPERATOR_REVIEW = False');assert default!=operator
    fixtures=[RepositorySuiteCase.model_validate(c).model_copy(update={'split':'development','used_for_development':True}) for c in recipe.generator_config['cases']]
    assert default==repository_suite_recipe(fixtures).extension.grader.config['argv'][-1]
    (HERE/'observer-operator.py').write_text(operator);(HERE/'observer-default.py').write_text(default)
    recipe.extension.reference=recipe.extension.reference.model_copy(deep=True)
    recipe.extension.reference.id='repository.suite.observe.default';recipe.extension.reference.config['argv']=['python3','-B','-c',default]
    method=sha(HERE/'native_scope.py');recipe.recipe_id='repository-native-batch-'+method[:16]
    recipe.dependencies.update(default_program=hashlib.sha256(default.encode()).hexdigest(),native_scope_derivation=method)
    recipe.generator_config['operator_native_scope_derivation']={'method_sha256':method,'seed_cases_sha256':meta['cases_file_sha256'],'algorithm_frozen_before_collection':True,'derived_truth_and_payloads_frozen_before_body':True,'all_expanded_nodes_required':True,'case_and_permission_bounds_unchanged':True}
    recipe=RecipeDefinition.model_validate(recipe.model_dump(mode='json'))
    env=AssessmentEnvironment.model_validate(next(x['document'] for x in parent['documents'].values() if x['kind']=='environment'))
    assert env.container_image==previous['parent_image'] and env.identity['source_digest']==source
    assert previous['request']['runtime_dependencies']==runtime_dependencies();runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies())
    documents={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('recipe',recipe.recipe_id,recipe),('environment',env.environment_id,env),('recipe_runtime',content_digest(runtime),runtime)]}
    identify=meta['portable_identify'];wheel=ROOT/identify['private_cache'];assert sha(wheel)==identify['sha256'] and identify['version']=='2.6.15'
    with zipfile.ZipFile(wheel) as z:module_sha=hashlib.sha256(z.read('identify/identify.py')).hexdigest()
    code='''import hashlib,importlib.metadata,pkgutil
def test_identify():
    import identify.identify as api
    assert importlib.metadata.version('identify')=='2.6.15'
    assert 'identify-2.6.15-py2.py3-none-any.whl/identify/' in api.__file__
    assert hashlib.sha256(pkgutil.get_data('identify','identify.py')).hexdigest()=='''+repr(module_sha)+'''
    assert 'python' in api.tags_from_filename('fixture.py')
def test_json_backends():
    for name,version in [('orjson','3.11.3'),('msgspec','0.19.0'),('freezegun','1.5.0')]:
        assert importlib.metadata.version(name)==version
        __import__(name)
def test_sopel_database():
    for name,version,module in [('SQLAlchemy','2.0.44','sqlalchemy'),('greenlet','3.2.4','greenlet'),('setuptools','75.8.2','pkg_resources'),('pytz','2025.2','pytz')]:
        assert importlib.metadata.version(name)==version
        __import__(module)
'''
    ast.parse(code);archive=pack_files({'tests/test_native_support.py':code.encode()});prototype=previous['probes'][0]['payload'];dead=seeds[0]
    support={'archive':base64.b64encode(archive).decode(),'archive_sha256':hashlib.sha256(archive).hexdigest(),'python':'3.13','pytest':'8.3.5','test_paths':['tests/test_native_support.py'],'pytest_plugins':[],'source_modules':[],
        'wheels':[{'filename':Path(a.path).name,'sha256':a.sha256,'data':base64.b64encode(a.read()).decode()} for a in dead.truth.wheels]}
    support_probe={'payload':support,'payload_sha256':hashlib.sha256(json.dumps(support,separators=(',',':')).encode()).hexdigest(),'archive_sha256':support['archive_sha256'],'nodes':['tests/test_native_support.py::'+n for n in ('test_identify','test_json_backends','test_sopel_database')]}
    paths=[HERE/n for n in ('native_scope.py','native-scope-check.json','terminal-control-check-v2.json','prepared-seeds.json','prepare-seeds.py','observer-operator.py','observer-default.py','run.py','run-runtime.py','audit-execution.py','classify.py','operator_output.py','review-budget.py')]
    paths += [ROOT/meta['cases_file'],ROOT/meta['records_file'],PREV/'validation/source-stability.json',PREV/'completion-audit.json',PREV/'remaining-execution-result.json',PREV/'provisional-pool.json',ROOT/'docs/ASSESSMENT_TESTING.md',ROOT/'docs/aeep-toolkit/CONTINUATION.md',ROOT/'docs/aeep-toolkit/DECISIONS.md']
    for c in seeds:paths += [Path(a.path) for a in (c.truth.source,c.truth.tests,c.reference,*c.truth.wheels)]
    for c in meta['collections']:paths.append(ROOT/c['payload'])
    for record in json.loads((ROOT/meta['records_file']).read_text()):
        folder=ROOT/record['source_cache'];paths += [folder/'row.json',folder/'source.tar.gz'];assert sha(folder/'row.json')==record['row_sha256'] and sha(folder/'source.tar.gz')==record['archive_sha256']
        for item in record.get('license_records',[]):paths.append(ROOT/item['path'])
    for item in identify['licenses']:
        p=ROOT/item['retained'];assert sha(p)==item['sha256'];paths.append(p)
    # Bind actual selected-install manifests,not broad cached-support lists.
    for folder,file in [('repository-workload-batch-20261022','runtime-install-review.json'),('repository-independent-sources-20261024','runtime-install-review.json'),('repository-independent-sources-20261024','build-result.json'),('repository-supported-suites-20261027','runtime-install-review.json'),('repository-supported-suites-20261027','build-result.json'),('repository-test-roots-20261027','runtime-support-review.json'),('repository-test-roots-20261027','build-result.json'),('repository-multifile-sources-20261027','build-result.json')]:paths.append(HERE.parent/folder/file)
    assets={str(p.resolve()):sha(p) for p in paths};assert all(Path(p).is_file() and not Path(p).is_symlink() for p in assets)
    subject=AssessmentSubject(kind='command',location=str((ROOT/meta['cases_file']).parent),dependency_digests=assets,description='Three exact cached public sources;exhaustive conservative native scope derivation before body trials;default observer profile qualification. No model/service/image/install authority.')
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(env),authorization_id='onboarding',seed=118,definition_digests=list(documents),runtime_dependencies=runtime.dependencies)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[content_digest(recipe)],environment_digests=[content_digest(env)],reviewed_digests=[*documents,*new])
    envelope={**{k:parent[k] for k in ('authorization_digest','image','docker','socket','host_canary')},'source_digest':source,'recipe':recipe.model_dump(mode='json'),'request':request.model_dump(mode='json'),'documents':documents,'external_execution':False}
    assert not(ROOT/envelope['host_canary']).exists();save(HERE/'observer-envelope.json',envelope);assets[str((HERE/'observer-envelope.json').resolve())]=sha(HERE/'observer-envelope.json')
    case_support={c.input.task_id:support_probe['nodes'][i] for i,c in enumerate(seeds)}
    review={'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'authorization_digest':parent['authorization_digest'],'assets':assets,'cases_file':meta['cases_file'],'records_file':meta['records_file'],'active_case_ids':[c.input.task_id for c in seeds],'case_summary':meta['cases'],'collections':meta['collections'],'derived_directory':str(((ROOT/meta['cases_file']).parent/'derived').relative_to(ROOT)),'method_sha256':method,
        'parent_review':str((HERE/'observer-envelope.json').relative_to(ROOT)),'parent_review_sha256':sha(HERE/'observer-envelope.json'),'driver_files':{n:sha(HERE/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},'request':request.model_dump(mode='json'),'new_documents':new,'reviewed_document_digests':[*documents,*new],'amendment':amendment.model_dump(mode='json'),
        'parent_image':env.container_image,'host_canary':envelope['host_canary'],'probes':previous['probes'],'native_fixtures':previous['native_fixtures'],'support_probe':support_probe,'case_support_nodes':case_support,
        'operator_conformance_reused':{'evidence':str((PREV/'completion-audit.json').relative_to(ROOT)),'sha256':sha(PREV/'completion-audit.json'),'same_source_environment_image_operator_program_and_permissions':True,'new_default_program_is_not_covered':True},
        'initial_contained_calls':17,'maximum_contained_calls':19,'maximum_operations':23,'maximum_reserved_seconds':965,'maximum_model_turns':0,'cash_usd':0,'maximum_builds':0,'maximum_downloads':0,
        'bounded_control_repairs':{'maximum_extra_calls':2,'maximum_additional_setup_analysis_operations':2,'allowed':'Exact recorded first-party report/receipt control correction after known canonical completion/cleanup,with unchanged software,source,test assertions,repair bytes,expansion algorithm,permissions and already sealed payloads. No automatic initial retry.','forbidden':'No rule/observer/candidate/test/reference/input change,scope weakening,new packages,models,cash,downloads,builds,services,credentials,release,retained-resource deletion,uncertain replay or refund.','accounting':'Cumulative23operations/965reservedseconds:19times35 plus at most two30setup/120analysis phases;initial17calls/19operations/745reservedseconds.'},
        'permissions':['Reuse retained9f473c49 only. No image build/pull/deletion,installation,download,model,cash,credentials,service,new destination,activation or release. Keep50GiB host reserve and all images.','Fresh default raw observer:four boundary/state/transport probes,two native fixtures and at most one derived reference selected by lexical case ID before body outcomes. The diagnostic operator profile reuses exact current completed conformance.','One first-party support probe loads only the exact cached identify2.6.15 ZIP wheel privately and inspects the declared inherited backend versions. Case-specific support failure excludes that case;known completion does not become an unknown infrastructure event.','At most three native collection calls over the exact cached Dead204,Python-json-logger39 and Sopel2653 snapshots. Freeze exhaustive disjoint matching groups and all generated selector/case/payload hashes before any body call. Missing/overlapping/conflicting/invalid/oversized scope rejects the case;no matched identity is dropped.','At most six reference/original body calls. Only the first-party selector literal changes by the frozen derivation rule;source/assertions/repair bytes remain. All expanded identities must pass the reference,and originals must show the frozen bug/preservation pattern. No outcome-based mapping or retrospective acceptance.','Maximum19calls/23existing-grant operations/965reservedseconds. Remove only new owned containers and unchanged canary;retain receipts/charges and up to8192bytes per failed public log. No budgets reset.'],
        'limitations':['Seed names are published aliases,not a certified final oracle. New authored full scopes become usable only after frozen derivation and successful reference/counterexample checks. No official benchmark score.','All63 historical pool bindings remain. New source/default-profile qualification is not implied by current source checks,old container conformance or fixtures. No model usefulness,selection,resource,human or release gate closes.','Current source13gates and wheel20checks are reused unchanged;no package reinstall or broad source rerun is justified.'],
        'approval_reason':'The completed native-identity review binds different sources and no identify payload. The user continuation reserves untrusted software execution and CONTINUATION.md requires applicable provisioning authority. This new exact cached-source/private-ZIP execution needs approval;routine data authoring remains delegated. No architecture,budget,image or installation decision is needed.'}
    assert shutil.disk_usage(ROOT).free>51*1024**3
    assert subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',env.container_image,'--format','{{.Id}}'],timeout=20).decode().strip()==env.container_image
    save(HERE/'operation-review.json',review);save(HERE/'preparation-checks.json',{'passed':True,'source_digest':source,'current_source13_and_installed20checks_reused':True,'subject_count':3,'seed_aliases':sum(c['required_aliases'] for c in meta['cases']),'derivation_method_frozen':True,'raw_default_profile_pinned':True,'assets_bound':len(assets),'actual_execution':False,'review_sha256':sha(HERE/'operation-review.json')})
    print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'subjects':3,'actual_execution':False}))

if __name__=='__main__':main()

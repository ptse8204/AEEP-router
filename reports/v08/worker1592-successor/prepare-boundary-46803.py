from pathlib import Path
import json,copy,hashlib
from pydantic import model_serializer
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentAuthorization,AssessmentScopeAmendment,content_digest
from aeep.assessment.boundary import BoundaryConformance
from aeep.models import StrictModel,ExecutorSpec,new_id
from aeep.hosts.workers import binding_from_config
class Envelope(StrictModel):
 definition:dict
class Inventory(StrictModel):
 values:dict[str,str]
 @model_serializer(mode='plain')
 def serialize(self):return self.values
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
try:
 current=json.loads((OUT/'conformance-46803-result.json').read_text());assert current['conformance_passed'];pair=q.get('worker_pair_definition',current['pair']['pair_definition_digest']);review=json.loads((OUT/'conformance-46803-review.json').read_text());defs={};records={}
 for role in ['control','treatment']:
  spec=ExecutorSpec.model_validate(pair[role]);worker=binding_from_config(spec.managed_host_config().managed_worker);assert worker
  rows=r.store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='boundary_conformance' AND json_extract(payload_json,'$.adapter')=? ORDER BY rowid DESC LIMIT 1",(spec.managed_host_config().adapter_id,)).fetchall();assert rows
  old=BoundaryConformance.model_validate_json(rows[0][0]);policy=q.get('effective_policy_definition',old.effective_policy_digest);policy=copy.deepcopy(policy);policy['definition']['image']=worker.image;policy['definition']['runtime_binary_sha256']=worker.binary_sha256;policy['definition']['runtime_package_sha256']=review['runtime_package_sha256']
  policy_obj=Envelope.model_validate(policy);pd=q.put('effective_policy_definition',content_digest(policy_obj),policy_obj);defs[pd]=policy_obj
  inventory=pair['differential'][role+'_inventory'];inv=Inventory(values=inventory);idg=q.put('reviewed_inventory',content_digest(inv),inv);defs[idg]=inv
  wd=q.put('worker_binding',worker.digest(),worker);defs[wd]=worker
  enforcement=copy.deepcopy(q.get('enforcement_definition',old.enforcement_definition_digest));e=enforcement['definition'];e.update(worker_digest=worker.digest(),effective_policy_digest=pd,immutable_image=worker.image,source_digest=current['source_digest'],runtime_package_sha256=review['runtime_package_sha256'],binary_sha256=worker.binary_sha256,prior_enforcement_digest=old.enforcement_definition_digest,successor_setup_review_sha256=hashlib.sha256((OUT/'setup-review.json').read_bytes()).hexdigest(),successor_build_result_sha256=hashlib.sha256((OUT/'build-correction-result.json').read_bytes()).hexdigest(),successor_review='Same protected volumes/configuration/proxy and exact old base; immutable official0.159.2 binary/helpers/resources in the reviewed flattened /opt/codex layout. Package manifest recognition is absent; exact helper sibling fallback readiness passed current zero-model protocol probes. Current paired probes freshly observed effective policy and container controls; historical observations are retained separately.')
  codepaths=['src/aeep/hosts/workers.py','src/aeep/hosts/codex_app_server.py','src/aeep/hosts/codex_pair_inspection.py','src/aeep/assessment/boundary.py'];e['implementation_sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in codepaths}
  en=Envelope.model_validate(enforcement);ed=q.put('enforcement_definition',content_digest(en),en);defs[ed]=en
  record=old.model_copy(update={'conformance_id':new_id('conformance'),'source_digest':current['source_digest'],'worker_digest':worker.digest(),'image_digest':worker.image,'binary_digest':worker.binary_sha256,'effective_policy_digest':pd,'reviewed_inventory_digest':idg,'identity_digest':current['workers'][role]['identity_digest'],'enforcement_definition_digest':ed,'probe_digests':current['pair']['workers'][role]['probe_digests'],'configuration_digest':worker.configuration_digest,'effective_inventory':inventory})
  rd=q.put('boundary_conformance',record.conformance_id,record);defs[rd]=record;records[role]=rd
  for probe in record.probe_digests:
   definition=q.get('boundary_probe',probe)['implementation_digest'];defs[definition]=q.get('boundary_probe_definition',definition)
 source=review['requests'][0]
 for kind,key in [('subject','subject_digest'),('recipe','recipe_digest'),('environment','environment_digest')]:defs[source[key]]=q.get(kind,source[key])
 grant=AssessmentAuthorization.model_validate(q.get('authorization','onboarding'));amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[source['subject_digest']],recipe_digests=[source['recipe_digest']],environment_digests=[source['environment_digest']],reviewed_digests=list(defs))
 result={'helper_result_sha256':hashlib.sha256((OUT/'helper-46803-result.json').read_bytes()).hexdigest(),'authority':'Standing finite assessment amendments, successor enforcement review required before existing verifier acceptance; no asserted pass boolean','source_digest':current['source_digest'],'conformance_records':records,'definitions':{d:o.model_dump(mode='json') if hasattr(o,'model_dump') else o for d,o in defs.items()},'amendment':amendment.model_dump(mode='json'),'paired_inspection_full_conformance_remains_false':True,'connectivity_required_separately':True,'no_workbook_execution':True,'no_admission':True}
 (OUT/'boundary-46803-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'records':records,'review_sha256':hashlib.sha256((OUT/'boundary-46803-review.json').read_bytes()).hexdigest()}))
finally:r.store.close()

import asyncio,json,runpy,subprocess,sys,time
from pathlib import Path
from aeep.router import Router
from aeep.tasks import change_state,inspect
from aeep.assessment.verification import verification_source_digest
root=Path.cwd();run=root/'reports/v08/sol-agent-smoke-20260929T215826Z';p=json.loads((run/'plan.json').read_text());project=Path(p['project'])
grader=runpy.run_path(str(root/'integrations/assessment-runtime/workbook_grader.py'))['grade']
checks=[]
for case in json.loads((run/'private-expected.json').read_text()):
 label=case['label'];value=json.loads((project/(label+'-input.json')).read_text());out=json.loads((project/(label+'-result.json')).read_text())
 valid=bool(out.get('ok') and grader({'input':value,'output':out['output'],'expected':case['expected']}))
 checks.append({'task':label,'independent_grader_passed':valid,'receipt_ids':[r['receipt_id'] for r in out.get('receipts',[])],'summary':out.get('summary'),'verification':out.get('verification'),'recovery_state':out.get('recovery_state')})
 assert valid,checks[-1]
rows=[]
def rejected(arguments):
 result=subprocess.run([sys.executable,'-m','aeep','tool-call',p['tool_name'],'--profile','task','--task-activation',p['activation_id'],'-m',p['manifest'],'-a',json.dumps(arguments)],capture_output=True,text=True,timeout=15)
 assert result.returncode!=0,(result.returncode,result.stdout[:500])
 parsed=json.loads(result.stdout);rows.append({'exit_code':result.returncode,'response':parsed})
async def finish():
 router=Router.from_manifest(p['manifest'])
 try:
  before=inspect(router,p['activation_id']);assert before['attempts_used']==2,before
  change_state(router,p['activation_id'],'pause')
  value=json.loads((project/'small-input.json').read_text());rejected(value)
  change_state(router,p['activation_id'],'resume')
  rejected({**value,'allow_network':True})
  rejected(value)
  final=change_state(router,p['activation_id'],'uninstall')
  assert final['attempts_used']==2 and final['overlay']=='absent' and final['accounting_retained'],final
  return final
 finally: await router.close()
final=asyncio.run(finish())
report={'kind':p['kind'],'requested_agent_model':p['model_requested'],'source_digest':verification_source_digest(root),'tasks':checks,'rejections':rows,'cleanup':final,'agent_summary':(project/'agent-summary.txt').read_text(),'limitations':['Explicit CLI guidance; no automatic Codex tool discovery tested','Same host filesystem, not a controlled isolated comparison','Reference capability selected in advance; no marginal-benefit claim','Independent grading happened after task receipts; receipts correctly report incomplete task verification','No live SkillsBench reproduction or full qualification','Subagent token/account costs unavailable from this interface; not counted as zero']}
(run/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

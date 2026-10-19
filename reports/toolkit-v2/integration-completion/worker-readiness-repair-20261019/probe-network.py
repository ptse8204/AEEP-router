"""Check the existing reviewed proxy path with one no-credential diagnostic worker."""
import asyncio,hashlib,ipaddress,json,pathlib,shutil,subprocess,sys,time
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
OUT=pathlib.Path(__file__).resolve().parent;ROOT=OUT.parents[3]
PROGRAM=r'''
import socket,ssl,json,sys
results=[]
for address in dict.fromkeys(sys.argv[1:]):
 row={'proxy_address':address}
 try:
  with socket.create_connection((address,3128),timeout=6) as sock:
   row['tcp_connected']=True;sock.sendall(b'CONNECT chatgpt.com:443 HTTP/1.1\r\nHost: chatgpt.com:443\r\n\r\n');header=b''
   while b'\r\n\r\n' not in header and len(header)<8192:
    chunk=sock.recv(1024)
    if not chunk:break
    header+=chunk
   fields=header.split(b'\r\n',1)[0].split();row['connect_status']=int(fields[1]) if len(fields)>1 and fields[1].isdigit() else None
   if row['connect_status']==200:
    with ssl.create_default_context().wrap_socket(sock,server_hostname='chatgpt.com') as tls:row['tls_verified']=True;row['tls_version']=tls.version()
 except Exception as exc:row['error_type']=type(exc).__name__
 results.append(row)
print(json.dumps({'checks':results,'credentials_present':False,'model_calls':0}))
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args,timeout=20):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=timeout,stderr=subprocess.DEVNULL).strip()
async def main():
 f=OUT/'network-review.json';assert len(sys.argv)==2 and sha(f)==sys.argv[1];review=json.loads(f.read_text());assert sha(pathlib.Path(__file__))==review['runner_sha256'];assert hashlib.sha256(PROGRAM.encode()).hexdigest()==review['program_sha256'];assert verification_source_digest(ROOT)==review['source_digest'];assert shutil.disk_usage(ROOT).free>51*1024**3
 with (OUT/'network-started.json').open('x') as stream:json.dump({'review_sha256':sys.argv[1]},stream)
 config=json.loads((ROOT/'reports/toolkit-v2/c07/edit-study-preparation/qualification-execution-review.json').read_text())
 inspect=lambda:json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',config['proxy_name']))
 initial=inspect();assert initial['Id'].startswith(config['proxy_id_prefix']) and initial['Image']==config['proxy_image'] and not initial['Running'];assert not docker('ps','-a','-q','--filter','name=^/'+review['container_name']+'$')
 base=pathlib.Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3');r=Router.from_manifest(base/'aeep.json');s=AssessmentService(r,base/'.aeep/assessments');q=s.repository;p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest']
 result={'review_sha256':sys.argv[1],'model_calls':0,'credential_mounts':0,'image':review['image'],'container_name':review['container_name']};reserved=False;began=time.monotonic()
 try:
  q.reserve(p,p.plan_id+':network_diagnostic_20261019',AssessmentLimits(max_operations=1,max_elapsed_seconds=180,max_model_turns=0,max_cash_usd=0),stage='network_diagnostic');reserved=True
  docker('start',config['proxy_name']);live=inspect();network=next(v for v in live['Networks'].values() if v['NetworkID']==config['network_id']);actual=network['IPAddress'];assert ipaddress.ip_address(actual) in ipaddress.ip_network('172.18.0.0/16');result['actual_proxy_address']=actual;result['expected_proxy_address']='172.18.0.2';result['proxy_address_matches_review']=actual=='172.18.0.2'
  result['network_checks']=json.loads(docker('run','--rm','--name',review['container_name'],'--label','aeep.toolkit-review='+sys.argv[1],'--network',config['network_id'],'--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=32','--memory=128m','--cpus=0.5','--user=65534:65534','--entrypoint','/usr/local/bin/python3',review['image'],'-I','-c',PROGRAM,'172.18.0.2',actual,timeout=45))
 except BaseException as exc:result['error_type']=type(exc).__name__
 finally:
  owned=docker('ps','-a','-q','--filter','name=^/'+review['container_name']+'$')
  if owned:
   identity=json.loads(docker('inspect','--format','{"Image":{{json .Image}},"Review":{{json (index .Config.Labels "aeep.toolkit-review")}}}',review['container_name']));assert identity=={'Image':review['image'],'Review':sys.argv[1]}
   docker('stop','--time','2',review['container_name'])
   if docker('ps','-a','-q','--filter','name=^/'+review['container_name']+'$'):docker('rm',review['container_name'])
  result['worker_removed']=not docker('ps','-a','-q','--filter','name=^/'+review['container_name']+'$')
  if inspect()['Running']:docker('stop','--time','5',config['proxy_name'])
  result['proxy_restored']=not inspect()['Running'];result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
  if reserved:q.finish_operation(p.plan_id+':network_diagnostic_20261019',elapsed_seconds=time.monotonic()-began)
  await r.close();(OUT/'network-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())

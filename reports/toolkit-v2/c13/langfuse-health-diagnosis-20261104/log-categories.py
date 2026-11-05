"""Filter a stopped owned container's log in memory; print no raw stream."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--container',required=True);parser.add_argument('--review',required=True);args=parser.parse_args()
p=HERE/'operation-review.json';assert hashlib.sha256(p.read_bytes()).hexdigest()==args.review
review=json.loads(p.read_bytes());assert args.container in review['owned_container_ids'].values()
env={'PATH':'/usr/bin:/bin','HOME':review['work'],'DOCKER_CONFIG':review['docker_config'],'DOCKER_HOST':'unix://'+review['docker_socket'],'LC_ALL':'C'}
command=[review['docker'],'--config',review['docker_config'],'--host',env['DOCKER_HOST'],'logs','--tail','40',args.container]
response=subprocess.run(command,env=env,capture_output=True,timeout=15,check=False)
body=response.stdout+b'\n'+response.stderr;text=body.decode('utf-8',errors='replace');lower=text.lower()
print(json.dumps({'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'categories':[key for key in review['diagnostic_categories'] if key in lower],'public_paths':[path for path in review['diagnostic_public_paths'] if path in text],'raw_text_retained':False,'docker_exit_code':response.returncode}))
raise SystemExit(response.returncode)

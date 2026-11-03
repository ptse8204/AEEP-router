"""Keep SDK and offline-docs attempts independent; never replay terminal SDK work."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved',required=True);parser.add_argument('--component',choices=('all','sdk','docs'),default='all');args=parser.parse_args()
 identity=hashlib.sha256((HERE/'operation-review.json').read_bytes()).hexdigest()
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
 result={};uncertain=False
 if args.component in {'all','sdk'}:
  assert not (HERE/'execution-started.json').exists(),'SDK attempt exists; inspect it instead of replaying'
  try:
   process=subprocess.run([sys.executable,str(HERE/'run-review.py'),'--execute-approved',identity],timeout=180)
   summary=HERE/'execution/summary.json'
   if summary.exists():
    sdk=json.loads(summary.read_bytes());result['sdk']={'passed':sdk['passed'],'exit_code':process.returncode}
    uncertain=(not sdk.get('source_unchanged',True)) or sdk.get('cleanup_uncertain',False) or any(row['elapsed_seconds'] is None for row in sdk['operation_ledger']['operations'])
   else:
    result['sdk']={'passed':False,'exit_code':process.returncode,'summary_present':False}
    uncertain=(HERE/'execution-started.json').exists()
  except subprocess.TimeoutExpired:
   uncertain=True;result['sdk']={'passed':False,'error_type':'OuterControllerTimeout','effects':'UNKNOWN; inspect retained native state'}
 if uncertain:result['common_stop']='Unresolved SDK accounting; retain all resources'
 elif args.component in {'all','docs'}:
  try:
   process=subprocess.run([sys.executable,str(HERE/'run-docs.py'),'--execute-approved',identity],timeout=200)
   completed=HERE/'docs-complete.json';result['docs']={'passed':completed.exists(),'exit_code':process.returncode}
  except subprocess.TimeoutExpired:result['docs']={'passed':False,'error_type':'OuterControllerTimeout','effects':'UNKNOWN; inspect retained tool state'}
 with (HERE/f'bundle-result-{time.time_ns()}.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result))

if __name__=='__main__':main()

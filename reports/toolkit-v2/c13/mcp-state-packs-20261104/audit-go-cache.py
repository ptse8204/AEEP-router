"""Inspect only public pinned module cache hints; do not trust or execute archives."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
source=ROOT/'.aeep/toolhive-source-preparation-20261104/go.sum'
cache=Path.home()/'go/pkg/mod/cache/download'
expected={}
for line in source.read_text().splitlines():
 module,version,digest=line.split()
 if not version.endswith('/go.mod'):expected[module,version]=digest

def escape(value):
 return ''.join('!'+c.lower() if c.isupper() else c for c in value)
rows=[]
for (module,version),digest in sorted(expected.items()):
 assert re.fullmatch(r'[A-Za-z0-9._~+/-]+',module) and '..' not in module.split('/')
 base=cache/escape(module)/'@v'/escape(version)
 archive=Path(str(base)+'.zip');hint=Path(str(base)+'.ziphash')
 entry={'module':module,'version':version,'go_sum_h1':digest,'archive_present':archive.is_file() and not archive.is_symlink(),
  'cached_ziphash_matches':False,'archive_verified':False,'license_reviewed':False}
 if hint.is_file() and not hint.is_symlink() and hint.stat().st_size<256:
  entry['cached_ziphash_matches']=hint.read_text().strip()==digest
 rows.append(entry)
record={'evidence_kind':'cache_hints_only_not_archive_integrity_or_license_evidence','cache_root':str(cache),
 'source_revision':'33ba170aad633e20520f380500a45cd158f24aed','pinned_module_versions_with_archive_checksums':len(rows),
 'archives_present':sum(r['archive_present'] for r in rows),'ziphash_hints_match':sum(r['cached_ziphash_matches'] for r in rows),
 'archives_verified':0,'compiler_executed':False,'downloads':0,'existing_cache_modified':False,'rows':rows}
(HERE/'toolhive-cache-hints.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='rows'}))

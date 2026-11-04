"""Exact remaining source preparation. No Cargo, compiler or package script runs."""
import json
from pathlib import Path
from vendor import prepare
HERE=Path(__file__).resolve().parent
review=json.loads((HERE/'operation-review.json').read_bytes())
metadata=json.loads((HERE/'registry-metadata-audit.json').read_bytes())
assert metadata['passed'] and len(metadata['rows'])==86
licenses={(row['name'],row['version']):row['license_expression'] for row in metadata['rows']}
lock=json.loads((HERE/'locked-crates.json').read_bytes())
assert metadata['source_lock_sha256']==lock['Cargo_lock_sha256']
runtime=Path(review['runtime'])
rows=prepare(lock,runtime/'vendor',runtime/'archives',licenses=licenses,cached_archives=review['cached_archives'])
(runtime/'crate-inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'passed':len(rows)==86,'crates':len(rows),'cached_archives_reused':len(review['cached_archives']),'archive_downloads':86-len(review['cached_archives']),'compressed_bytes':sum(r['compressed_bytes'] for r in rows),'expanded_bytes':sum(r['expanded_bytes'] for r in rows),'compiled':False,'models':0}))

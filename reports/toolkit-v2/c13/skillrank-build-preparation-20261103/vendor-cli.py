"""Approved source preparation only; never starts a compiler or installer."""
import json
from pathlib import Path
from vendor import prepare

HERE = Path(__file__).resolve().parent
review = json.loads((HERE / 'operation-review.json').read_bytes())
runtime = Path(review['runtime'])
rows = prepare(json.loads((HERE / 'locked-crates.json').read_bytes()),
               runtime / 'vendor', runtime / 'archives')
(runtime / 'crate-inventory.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps({'passed': len(rows) == 86, 'crates': len(rows),
                  'compressed_bytes': sum(r['compressed_bytes'] for r in rows),
                  'expanded_bytes': sum(r['expanded_bytes'] for r in rows),
                  'compiled': False, 'models': 0}))

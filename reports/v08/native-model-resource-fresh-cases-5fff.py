"""Report-owned resource fixtures; generator/oracle never staged inside native host."""
import asyncio,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SEED=2026093047
SPLIT='resource_evaluation_model'
INDICES=(0,10)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def input_hashes(document):
    found=set()
    def walk(value):
        if isinstance(value,dict):
            if isinstance(value.get('input'),dict):found.add(digest(value['input']))
            for key,item in value.items():
                if key in {'input_hash','input_digest','input_sha256'} and isinstance(item,str):found.add(item.removeprefix('sha256:'))
                if key in {'input_hashes','input_digests'} and isinstance(item,list):found.update(x.removeprefix('sha256:') for x in item if isinstance(x,str))
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(document);return found

async def create_or_load(store,python,path,definition_sha256,create):
    path=Path(path)
    if not create:
        document=json.loads(path.read_text());assert document['definition_sha256']==definition_sha256
        assert document['seed']==SEED and document['split']==SPLIT and document['selected_indices']==list(INDICES)
        assert document['input_hashes']==[digest(c['input']) for c in document['selected_cases']]
        return document['selected_cases'],document
    assert not path.exists(), 'Fresh resource fixture record already exists; no unchanged reuse'
    # Every existing canonical assessment definition contributes exact input/hash exclusions.
    existing=set();records=0
    for kind,identifier,payload in store._connection.execute('SELECT kind,id,payload_json FROM assessment_records'):
        existing.update(input_hashes(json.loads(payload)));records+=1
        await asyncio.sleep(0)
    historical=json.loads((ROOT/'reports/v08/native-model-resource-baseline-tmpdir-ade3-result.json').read_text())
    existing.update(historical['input_hashes'])
    request={'seed':SEED,'stages':[{'split':SPLIT,'count':11}]}
    process=await asyncio.create_subprocess_exec(str(python),'-I',str(ROOT/'integrations/assessment-runtime/workbook_program.py'),'generate',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(json.dumps(request).encode()),15)
        assert process.returncode==0 and len(stdout)<=16777216,'protected generator failed/bounded output'
    finally:
        if process.returncode is None:
            process.kill();await asyncio.wait_for(process.wait(),5)
    cases=json.loads(stdout)['cases'];assert len(cases)==11
    hashes=[digest(c['input']) for c in cases];assert len(set(hashes))==11 and not set(hashes)&existing,'Resource input collision with existing assessment/calibration definitions'
    selected=[{'input':cases[i]['input'],'expected':cases[i]['output']} for i in INDICES]
    document={'definition_sha256':definition_sha256,'seed':SEED,'split':SPLIT,'selected_indices':list(INDICES),'generated_count':11,'all_generated_input_hashes':hashes,'input_hashes':[digest(c['input']) for c in selected],'selected_cases':selected,'prior_canonical_record_count':records,'prior_input_hash_count':len(existing),'input_disjointness_passed':True,'classification':'Protected resource-only synthetic fixture/oracle record, outside evaluated host; not campaign holdout inputs'}
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(document,sort_keys=True)+'\n');path.chmod(0o600)
    return selected,document

import hashlib
import json

import pytest
from synthetic_edit import PREFIX, edit


def test_complex_edits_preserve_unrelated_content_and_use_real_files(tmp_path):
    files={'service.py':'# preserve\ndef price(x):\n    return x * 2\n',
           'client.py':'from service import price\nresult = price(3)\n',
           'NOTES.txt':'Do not change this.\n'}
    replacements=[{'file':'service.py','old':'def price(x):','new':'def total_price(x):'},
                  {'file':'client.py','old':'import price','new':'import total_price'},
                  {'file':'client.py','old':'price(3)','new':'total_price(3)'}]
    result=json.loads(edit(PREFIX+json.dumps({'files':files,'replacements':replacements}),tmp_path))
    expected={'service.py':'# preserve\ndef total_price(x):\n    return x * 2\n',
              'client.py':'from service import total_price\nresult = total_price(3)\n',
              'NOTES.txt':'Do not change this.\n'}
    assert result['files']==expected
    assert {p.name:p.read_text() for p in tmp_path.iterdir()}==expected
    assert result['file_tree_sha256']==hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def test_adjacent_case_preserves_all_bytes(tmp_path):
    files={'NOTES.txt':'ordinary baseline task\n'}
    assert json.loads(edit(PREFIX+json.dumps({'files':files,'replacements':[]}),tmp_path))['files']==files


@pytest.mark.parametrize('files,replacements',[
    ({'../outside':'unsafe'},[]),
    ({'auth.json':'excluded'},[]),
    ({'file.txt':'repeat repeat'},[{'file':'file.txt','old':'repeat','new':'changed'}]),
    ({'file.txt':'okay'},[{'file':'other.txt','old':'okay','new':'changed'}]),
])
def test_invalid_or_ambiguous_edits_fail(tmp_path,files,replacements):
    with pytest.raises(ValueError):
        edit(PREFIX+json.dumps({'files':files,'replacements':replacements}),tmp_path)

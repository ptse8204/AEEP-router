"""Validate relocated operator inputs before any dispatch, separately from outputs."""
import hashlib,json
from pathlib import Path

def verify_inputs(review):
    facts={}
    for name in ('server_source','host_boundary_source','controller_profile','toolhive'):
        path=Path(review[name]);assert path.is_absolute() and path.is_file() and not path.is_symlink()
        assert str(path) in review['assets']
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        assert actual==review['assets'][str(path)],name
        facts[name]=actual
    profile=Path(review['controller_profile']).read_text()
    assert str(Path(review['host_boundary_source']).parent) in profile
    assert str(Path(review['work'])) in profile
    assert review['format_schema']['properties']['text']['maxLength']==1024
    return facts

def verify_image(review,image):
    assert image['Id']==review['retained_image_id']
    assert image['RootFS']['Layers']==review['retained_image_layers']
    assert image['Config']['User']=='65534:65534'
    assert image['Config']['Entrypoint']==['/usr/local/bin/python3','-I','-B','/opt/aeep-reviewed-mcp.py']

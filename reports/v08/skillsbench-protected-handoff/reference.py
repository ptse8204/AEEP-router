import base64,io,json,re,sys,zipfile
from xml.etree import ElementTree as ET
W="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
def _filled(template: bytes, data: dict[str, str], *, remove_paragraph: bool = False) -> str:
    """Independent fixture builder using OOXML, not the grader's text walk."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template)) as original, zipfile.ZipFile(output, 'w') as filled:
        for member in original.infolist():
            raw = original.read(member)
            if member.filename.startswith('word/') and member.filename.endswith('.xml'):
                root = ET.fromstring(raw)
                for paragraph in root.iter(W + 'p'):
                    texts = list(paragraph.iter(W + 't'))
                    if not texts:
                        continue
                    joined = ''.join(node.text or '' for node in texts)
                    if data['RELOCATION_PACKAGE'] != 'Yes':
                        joined = re.sub(r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}', '', joined)
                    else:
                        joined = joined.replace('{{IF_RELOCATION}}', '').replace('{{END_IF_RELOCATION}}', '')
                    joined = re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: data[match.group(1)], joined)
                    texts[0].text = joined
                    for node in texts[1:]:
                        node.text = ''
                if member.filename == 'word/document.xml' and remove_paragraph:
                    body = root.find('.//' + W + 'body')
                    assert body is not None
                    paragraph = next(child for child in body if child.tag == W + 'p')
                    body.remove(paragraph)
                raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            filled.writestr(member, raw)
    return base64.b64encode(output.getvalue()).decode('ascii')
value=json.load(sys.stdin)
print(json.dumps({'outputs':[{'document_b64':_filled(base64.b64decode(v['template_b64'],validate=True),v['employee_data'])} for v in value['inputs']]}))

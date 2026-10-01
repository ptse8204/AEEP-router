import base64,io,json,re,sys,zipfile
from xml.etree import ElementTree as ET
class ConfigurationError(ValueError): pass
_W="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SPLIT_FIELDS=('DATE', 'CANDIDATE_FULL_NAME', 'CITY', 'STATE', 'ZIP_CODE', 'POSITION', 'DEPARTMENT', 'RESPONSE_DEADLINE', 'HR_NAME', 'PTO_DAYS')
_NESTED_FIELDS=('POSITION', 'DEPARTMENT', 'BASE_SALARY', 'SIGNING_BONUS', 'EQUITY_SHARES', 'MANAGER_NAME')
def _document(encoded: str) -> tuple[bytes, dict[str, ET.Element], list[str], list[str]]:
    if not isinstance(encoded, str) or len(encoded) > 200000:
        raise ConfigurationError('offer-letter artifact exceeds its encoded bound')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 150000:
            raise ConfigurationError('offer-letter artifact exceeds its byte bound')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (len(members) > 100 or len(names) != len(set(names))
                    or sum(member.file_size for member in members) > 2_000_000
                    or any(name.startswith('/') or '\\' in name or '..' in name.split('/')
                           or any(bad in name.lower() for bad in ('vba', 'externallink', 'embeddings'))
                           for name in names)
                    or 'word/document.xml' not in names):
                raise ConfigurationError('offer-letter artifact has an unsafe package structure')
            roots: dict[str, ET.Element] = {}
            for name in names:
                if not name.endswith(('.xml', '.rels')):
                    continue
                xml = archive.read(name)
                decoded = xml.decode('utf-8-sig')
                declaration = re.match(r'<\?xml[^>]*encoding=[\'\"]([^\'\"]+)', decoded, re.IGNORECASE)
                if declaration and declaration.group(1).lower() != 'utf-8':
                    raise ConfigurationError('offer-letter artifact has an unsupported XML encoding')
                if '\x00' in decoded or '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
                    raise ConfigurationError('offer-letter artifact contains an XML declaration')
                root = ET.fromstring(decoded)
                stack = [(root, 1)]
                count = 0
                while stack:
                    node, depth = stack.pop()
                    count += 1
                    if count > 50000 or depth > 64:
                        raise ConfigurationError('offer-letter XML exceeds its node or depth bound')
                    stack.extend((child, depth + 1) for child in node)
                if any(node.get('TargetMode') == 'External' for node in root.iter()):
                    raise ConfigurationError('offer-letter artifact contains an external relationship')
                roots[name] = root
    except (ValueError, UnicodeError, zipfile.BadZipFile, ET.ParseError, RuntimeError, OSError) as exc:
        raise ConfigurationError('offer-letter artifact is not valid bounded DOCX') from exc
    all_text: list[str] = []
    nested_text: list[str] = []
    for name in sorted(roots):
        root = roots[name]
        if name != 'word/document.xml' and not re.fullmatch(r'word/(?:header|footer)\d+\.xml', name):
            continue
        parents = {child: parent for parent in root.iter() for child in parent}
        for paragraph in root.iter(_W + 'p'):
            text = ''.join(node.text or '' for node in paragraph.iter(_W + 't'))
            all_text.append(text)
            depth = 0
            cursor = parents.get(paragraph)
            while cursor is not None:
                depth += cursor.tag == _W + 'tbl'
                cursor = parents.get(cursor)
            if name == 'word/document.xml' and depth >= 2:
                nested_text.append(text)
    return raw, roots, all_text, nested_text

def grade_artifact(encoded: str, template_encoded: str, data: dict[str, str]) -> dict[str, bool]:
    """Return pinned upstream checks and separate adapted text/structure checks."""
    _raw, roots, all_parts, nested_parts = _document(encoded)
    _template_raw, template_roots, template_parts, _ = _document(template_encoded)
    all_text = '\n'.join(all_parts)
    nested_text = '\n'.join(nested_parts)
    markers_absent = '{{IF_RELOCATION}}' not in all_text and '{{END_IF_RELOCATION}}' not in all_text
    upstream = (data['RELOCATION_PACKAGE'] == 'Yes'
        and not re.search(r'\{\{[A-Z_]+\}\}', all_text)
        and all(data[field] in all_text for field in _SPLIT_FIELDS)
        and all(data[field] in nested_text for field in _NESTED_FIELDS)
        and markers_absent
        and all(data[field] in all_text for field in ('RELOCATION_AMOUNT', 'RELOCATION_DAYS')))
    def expected_text(part: str) -> str:
        if data['RELOCATION_PACKAGE'] == 'Yes':
            part = part.replace('{{IF_RELOCATION}}', '').replace('{{END_IF_RELOCATION}}', '')
        else:
            part = re.sub(r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}', '', part)
        return re.sub(r'\{\{([A-Z_]+)\}\}', lambda match: data[match.group(1)], part)
    expected_parts = [expected_text(part) for part in template_parts]
    text_preserved = all_parts == expected_parts
    body = roots['word/document.xml']
    template_body = template_roots['word/document.xml']
    structure = (set(roots) == set(template_roots)
        and len(list(body.iter(_W + 'tbl'))) == len(list(template_body.iter(_W + 'tbl')))
        and len(list(body.iter(_W + 'p'))) == len(list(template_body.iter(_W + 'p'))))
    result = {'upstream_equivalent': bool(upstream), 'text_preserved': bool(text_preserved),
        'structure_counts_match': bool(structure)}
    if data['RELOCATION_PACKAGE'] != 'Yes':
        markers = [index for index, part in enumerate(template_parts) if '{{IF_RELOCATION}}' in part]
        result['no_relocation_block'] = (len(markers) == 1 and len(all_parts) == len(expected_parts)
            and all_parts[markers[0]] == expected_parts[markers[0]] and markers_absent)
    return result
value=json.load(sys.stdin)
results=[]
for example in value['examples']:
    try:
        output=example['output']; truth=example['expected']
        valid=set(output)=={'document_b64'} and all(grade_artifact(output['document_b64'],truth['template_b64'],truth['employee_data']).values())
    except (ValueError,KeyError,TypeError): valid=False
    results.append(valid)
print(json.dumps({'valid':results}))

"""Require descriptors and artifact bytes for every selected Maven node."""
import hashlib
import re


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_graph(raw, cache, required):
    raw = re.sub(r'\x1b\[[0-9;]*m', '', raw)
    body, marker, _ = raw.partition('\n#\n')
    assert marker
    nodes = [line.split(None, 1) for line in body.splitlines() if line.strip()]
    assert nodes[0][1] == 'com.example:userservice:jar:1.0.0'
    assert 2 <= len(nodes) <= 1000
    paths = set(required)
    groups = set()
    for number, coordinate in nodes[1:]:
        assert number.isdigit()
        fields = coordinate.split(':')
        assert len(fields) in (5, 6) and all(re.fullmatch(r'[A-Za-z0-9_.+-]+', x) for x in fields)
        group, artifact, kind = fields[:3]
        version, scope = fields[-2:]
        classifier = '-'+fields[3] if len(fields) == 6 else ''
        assert kind == 'jar' and scope in ('compile', 'runtime', 'test', 'provided') and 'SNAPSHOT' not in version
        assert all(part not in ('.', '..') for part in group.split('.')+[artifact, version])
        base = f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}"
        paths.update((base+'.pom', base+classifier+'.jar'))
        groups.add((group, artifact))
    absent = sorted(path for path in paths if not (cache/path).is_file())
    if absent:
        raise ValueError('missing_descriptors_or_jars:' + ','.join(absent))
    assert {
        ('jakarta.persistence', 'jakarta.persistence-api'),
        ('org.springframework.data', 'spring-data-jpa'),
        ('org.springframework', 'spring-tx'),
        ('org.apache.tomcat.embed', 'tomcat-embed-core'),
        ('org.hibernate.orm', 'hibernate-core'),
    } <= groups
    return {'selected_nodes':len(nodes)-1, 'required_files':len(paths),
            'files':{path:sha(cache/path) for path in sorted(paths)}}

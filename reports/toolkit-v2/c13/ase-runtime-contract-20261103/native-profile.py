"""Use the existing native SDK boundary; deny home, volume and shared-temp data."""
from __future__ import annotations
import json
from pathlib import Path

def profile(runtime,tools,work,probe):
    system=[Path(p) for p in ['/System','/usr/lib','/usr/share','/usr/bin','/bin','/Library/Frameworks/Python.framework','/Applications/Xcode.app/Contents/Developer/usr','/private/var/db/timezone','/var/db/timezone']]
    readable=[*system,runtime,tools,work]
    literal=[probe,Path('/dev/null'),Path('/dev/urandom'),Path('/dev/random'),Path('/dev/zero'),Path('/etc/localtime'),Path('/private/etc/localtime')]
    metadata=set()
    for path in [*readable,*literal]:
      metadata.update(str(p) for p in path.parents)
      if path.is_dir():metadata.add(str(path))
    q=lambda p:json.dumps(str(p))
    text='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
    for blocked in ['/Users','/Volumes','/private/tmp','/tmp','/private/var/folders','/var/folders']:
      text+='(deny file-read* (subpath '+q(blocked)+'))\n'
    text+='(allow file-write* (literal "/dev/null"))\n(allow file-write* (subpath '+q(work)+'))\n'
    text+='(deny file-write* (subpath '+q(work/'responses')+'))\n(deny file-write* (subpath '+q(work/'candidate')+'))\n'
    for path in readable:text+='(allow file-read* (subpath '+q(path)+'))\n'
    text+='(allow file-read* '+' '.join('(literal '+q(path)+')' for path in literal)+')\n'
    text+='(allow file-read-metadata '+' '.join('(literal '+q(p)+')' for p in sorted(metadata))+')\n'
    return text

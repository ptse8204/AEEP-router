"""Bounded scripted file edits for offline plumbing tests; never model evidence."""
import hashlib
import json
import re

PREFIX='AEEP_SYNTHETIC_EDIT_V1\n'


def edit(prompt,workspace):
    task=json.loads(prompt.removeprefix(PREFIX))
    if set(task)!={'files','replacements'} or not isinstance(task['files'],dict) or not 1<=len(task['files'])<=8 or not isinstance(task['replacements'],list) or len(task['replacements'])>32:
        raise ValueError('invalid synthetic edit task')
    for name,text in task['files'].items():
        if (not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}',name) or name.casefold() in {'auth.json','credentials.json'}
                or not isinstance(text,str) or len(text.encode())>8192):
            raise ValueError('invalid synthetic file')
        (workspace/name).write_text(text,encoding='utf-8')
    for change in task['replacements']:
        if (not isinstance(change,dict) or set(change)!={'file','old','new'} or change['file'] not in task['files']
                or not isinstance(change['old'],str) or not change['old'] or not isinstance(change['new'],str)
                or len(change['new'].encode())>8192):
            raise ValueError('invalid literal edit')
        file=workspace/change['file']
        text=file.read_text(encoding='utf-8')
        if text.count(change['old'])!=1:
            raise ValueError('literal edit must select one occurrence')
        updated=text.replace(change['old'],change['new'],1)
        if len(updated.encode())>8192:
            raise ValueError('edited file exceeds fixture bound')
        file.write_text(updated,encoding='utf-8')
    files={name:(workspace/name).read_text(encoding='utf-8') for name in task['files']}
    canonical=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    if len(canonical)>24000:
        raise ValueError('synthetic artifact exceeds output bound')
    return json.dumps({'files':files,'file_tree_sha256':hashlib.sha256(canonical).hexdigest()},sort_keys=True)

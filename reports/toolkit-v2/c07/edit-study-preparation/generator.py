"""First-party bounded editing fixtures; expected artifacts never enter model inputs."""
import json
import random
import sys

FAMILIES = ('easy', 'multi_file', 'adjacent')


def modules(function, parameter, variant):
    newline = '\r\n' if variant == 6 else '\n'
    comment = '# Keep the historical names in comments and strings: old_name old_arg'
    core = f'{comment}\ndef {function}({parameter}, factor=2):\n    """Preserve this documentation."""\n    return {parameter} * factor\n'
    clients = [f'from core import {function}\nresult = {function}({parameter}=3)\n',
               f'import core\nresult = core.{function}(4, factor=3)\n',
               f'from core import {function} as compute\nresult = compute({parameter}=5)\n']
    files = {'core.py': core, 'client.py': clients[variant % 3],
             'batch.py': f'from core import {function}\nvalues = [{function}({parameter}=n) for n in range(3)]\n',
             'NOTES.txt': 'Keep old_name and old_arg here. Zoë 東京\n'}
    return {k: v.replace('\n', newline) for k, v in files.items()}


def case(family, variant, nonce):
    if family == 'easy':
        old, new = 'helo_' + nonce, 'hello_' + nonce
        before = ('Heading\n' + old + '\n' + ('Zoë 東京\n' if variant % 2 else '') + old + '\n')
        files = {'message.txt': before, 'NOTES.txt': old + ' must stay unchanged here.\n'}
        task = {'operation': 'literal_replace', 'file': 'message.txt', 'old': old, 'new': new}
        expected = {'files': {**files, 'message.txt': before.replace(old, new)}, 'answer': None}
    elif family == 'multi_file':
        files = modules('old_name', 'old_arg', variant)
        files['NOTES.txt'] += nonce + '\n'
        names = {'old_name': 'price_' + nonce, 'old_arg': 'quantity_' + nonce}
        task = {'operation': 'python_name_rename', 'files': ['core.py', 'client.py', 'batch.py'], 'names': names}
        after = modules(names['old_name'], names['old_arg'], variant)
        after['NOTES.txt'] += nonce + '\n'
        expected = {'files': after, 'answer': None}
    else:
        assert family == 'adjacent'
        lines = ['ok ' + nonce, 'error ' + nonce, '  error indented', 'error another']
        lines += ['ok'] * variant
        files = {'log.txt': '\n'.join(lines) + '\n', 'NOTES.txt': 'Preserve every byte.\n'}
        task = {'operation': 'count_prefix', 'file': 'log.txt', 'prefix': 'error '}
        expected = {'files': files.copy(), 'answer': 2}
    variation = f'{family}-{variant}'
    return {'input': {'family': family, 'variation': variation, 'files': files, 'task': task},
            'output': expected, 'variation': variation, 'template_family': 'edit:' + family}


def generate(payload):
    rng = random.Random(payload['seed'])
    cases = []
    for stage in payload['stages']:
        for index in range(stage['count']):
            family = FAMILIES[index % 3]
            variant = (index // 3) % 7
            nonce = f'n{rng.getrandbits(96):024x}'
            cases.append(case(family, variant, nonce))
    return {'cases': cases}


if __name__ == '__main__':
    print(json.dumps(generate(json.load(sys.stdin))))

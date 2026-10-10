"""Independent tokenizer reference; treats returned Python as inert text."""
import io
import json
import sys
import tokenize


def transform(value):
    files = value['files'].copy()
    task = value['task']
    answer = None
    if task['operation'] == 'literal_replace':
        files[task['file']] = files[task['file']].replace(task['old'], task['new'])
    elif task['operation'] == 'python_name_rename':
        for name in task['files']:
            stream = tokenize.generate_tokens(io.StringIO(files[name]).readline)
            tokens = [token._replace(string=task['names'].get(token.string, token.string))
                      if token.type == tokenize.NAME else token for token in stream]
            files[name] = tokenize.untokenize(tokens)
    elif task['operation'] == 'count_prefix':
        answer = sum(line.startswith(task['prefix']) for line in files[task['file']].splitlines())
    else:
        raise ValueError('unknown operation')
    return {'files': files, 'answer': answer}


if __name__ == '__main__':
    print(json.dumps({'outputs': [transform(value) for value in json.load(sys.stdin)['inputs']]}))

import io
import json
import sys
import tokenize


def rename_tokens(source, names):
    """Replace exact NAME tokens without reconstructing whitespace."""
    offsets = [0]
    for line in source.split('\n'):
        offsets.append(offsets[-1] + len(line) + 1)

    edits = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME and token.string in names:
            start = offsets[token.start[0] - 1] + token.start[1]
            end = offsets[token.end[0] - 1] + token.end[1]
            edits.append((start, end, names[token.string]))

    for start, end, replacement in reversed(edits):
        source = source[:start] + replacement + source[end:]
    return source


def solve(case):
    """Return the complete files map and answer; never mutate the input."""
    files = dict(case['files'])
    task = case['task']
    operation = task['operation']
    answer = None

    if operation == 'literal_replace':
        path = task['file']
        files[path] = files[path].replace(task['old'], task['new'])
    elif operation == 'python_name_rename':
        names = task['names']
        if not isinstance(names, dict) or not all(
            isinstance(old, str) and isinstance(new, str)
            for old, new in names.items()
        ):
            raise ValueError('names must map strings to strings')
        # Read each original file so duplicate paths cannot cascade renames.
        for path in dict.fromkeys(task['files']):
            files[path] = rename_tokens(case['files'][path], names)
    elif operation == 'count_prefix':
        answer = sum(
            line.startswith(task['prefix'])
            for line in files[task['file']].splitlines()
        )
    else:
        raise ValueError('Unsupported operation: ' + str(operation))

    return {'files': files, 'answer': answer}


def main():
    case = json.load(sys.stdin)
    result = solve(case)
    json.dump(result, sys.stdout, ensure_ascii=True)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()

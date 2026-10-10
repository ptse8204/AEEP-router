"""Exact artifact grader; no code execution, imports or file writes from outputs."""
import json
import sys


def valid(example):
    actual, expected = example['output'], example['expected']
    if not isinstance(actual, dict) or set(actual) != {'files', 'answer'}:
        return False
    if not isinstance(actual['files'], dict) or set(actual['files']) != set(example['input']['files']):
        return False
    if any(not isinstance(value, str) for value in actual['files'].values()):
        return False
    answer = actual['answer']
    if answer is not None and type(answer) is not int:
        return False
    return actual == expected


if __name__ == '__main__':
    print(json.dumps({'valid': [valid(example) for example in json.load(sys.stdin)['examples']]}))

"""Shared, deliberately narrow normalization of diagnostic object identities."""
import base64
import hashlib
import pathlib
import re


def normalize(text):
    text = re.sub(r'\b(table|thread|userdata): (?:0x)?[0-9a-fA-F]+\b', r'\1: <identity>', text)
    text = re.sub(r'(org\.luaj\.vm2\.luajc\.JavaLoader )@[0-9a-fA-F]+\b', r'\1@<identity>', text)
    text = re.sub(r'(debug\.upvalueid\([^\n]*?\)\t)\d+\.\.\.', r'\1<identity>...', text)
    return text.replace('\r\n', '\n')


def digest(text):
    return hashlib.sha256(normalize(text).encode('utf-8', errors='surrogateescape')).hexdigest()


def read_results(directory):
    directory = pathlib.Path(directory)
    result = {}
    for line in (directory / 'tests.tsv').read_text().splitlines():
        key, status, error_type, trace = line.split('\t')
        if key in result:
            raise ValueError('Duplicate test case: ' + key)
        message = base64.b64decode(trace).decode('utf-8').split('\n\tat ', 1)[0]
        record = {'status':status, 'error_type':error_type, 'message_sha256':digest(message)}
        cls, method = key.split('#')
        output = directory / 'output' / (cls + '.' + method[4:].lower() + '.actual')
        if output.exists():
            record['output_sha256'] = digest(output.read_text(encoding='utf-8', errors='surrogateescape'))
        result[key] = record
    return result

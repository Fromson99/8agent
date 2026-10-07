"""Replace only the approved search method, preserving other installed code."""
import ast
import hashlib
import textwrap

TARGET = '02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def method(raw):
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RelationsTools')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'search')
    if node.decorator_list:
        raise ValueError('unexpected decorated search method')
    lines = text.splitlines(keepends=True)
    return node, ''.join(lines[node.lineno-1:node.end_lineno]), lines

def ast_sha(raw):
    node, _, _ = method(raw)
    return sha(ast.dump(node, include_attributes=False).encode())

def transform(raw, before, after):
    current, _, lines = method(raw)
    if ast_sha(raw) == ast_sha(after):
        return raw
    if ast_sha(raw) != ast_sha(before):
        raise ValueError('unknown search method; install FULLTEXT_DIAGNOSTICS R1 first or return this error; no changes')
    _, replacement, _ = method(after)
    result = (''.join(lines[:current.lineno-1]) + replacement + ''.join(lines[current.end_lineno:])).encode()
    compile(result, TARGET, 'exec')
    assert ast_sha(result) == ast_sha(after)
    return result

def function(raw, namespace):
    _, source, _ = method(raw)
    # This offline runner calls only fulltext. Its inherited non-fulltext branch
    # is unreachable; all production globals/imports come from the checkout.
    body = textwrap.dedent(source)
    local = {}
    exec(compile(body, '<frozen-fulltext-search>', 'exec'), namespace, local)
    return local['search']

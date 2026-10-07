"""Preserve installed bytes except explicitly approved preparation functions."""
import ast
import hashlib
import json


def signature(node):
    def canonical(value):
        if isinstance(value,ast.AST):
            fields={}
            for name,child in ast.iter_fields(value):
                if name=='type_params':
                    if child:raise ValueError('generic type parameters unsupported')
                    continue
                fields[name]=canonical(child)
            return {'node':type(value).__name__,'fields':fields}
        if isinstance(value,list):return [canonical(x) for x in value]
        return value
    return hashlib.sha256(json.dumps(canonical(node),sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def function(raw,qualified):
    parts=qualified.split('.')
    nodes=ast.parse(raw.decode()).body
    for i,name in enumerate(parts):
        matches=[n for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
        if len(matches)!=1:raise ValueError('missing/ambiguous function: '+qualified)
        node=matches[0]
        if i<len(parts)-1:nodes=node.body
    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):raise ValueError('not a function: '+qualified)
    return node


def span(node):
    return min([node.lineno]+[d.lineno for d in node.decorator_list])-1,node.end_lineno


def transform(raw,qualified,before,after):
    node=function(raw,qualified)
    current=signature(node)
    wanted=signature(function(after,qualified))
    if current==wanted:return raw
    if current!=signature(function(before,qualified)):
        raise ValueError('unknown preparation function; no writes: '+qualified)
    lines=raw.decode().splitlines(keepends=True);start,end=span(node)
    newlines=after.decode().splitlines(keepends=True);a,b=span(function(after,qualified))
    result=(''.join(lines[:start])+''.join(newlines[a:b])+''.join(lines[end:])).encode()
    compile(result,qualified,'exec')
    assert signature(function(result,qualified))==wanted
    return result

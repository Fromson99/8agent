"""Explicit case-fact identity for typed assumptions; no synonym inference."""
from copy import deepcopy
import re
from ..contracts import digest
from .errors import ContractError


def options(state):
    rows = {}
    for fact in state.get('facts', []):
        row = {k: fact[k] for k in ('name', 'value')}
        rows['F' + digest(row)] = row
    return [{'id': key, **deepcopy(row)} for key, row in rows.items()]


def typed_value(text, field, *, written_units=False):
    """Accept exact literals and unambiguous written units, never infer magnitude."""
    from lawrag.legal_knowledge.ontology import validate_expression
    from lawrag.legal_knowledge.contracts import KnowledgeError
    if not isinstance(text,str):return None
    value = text.strip()
    if field['type'] in ('money', 'decimal', 'ratio', 'duration'):
        if written_units and field['type']=='money' and field['unit']=='KRW':
            match=re.fullmatch(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(천|만|억)\s*(?:원|KRW)',value)
            if match:
                from decimal import Decimal, localcontext
                with localcontext() as precision:
                    precision.prec=max(28,len(match.group(1))+10)
                    value=format(Decimal(match.group(1).replace(',',''))*{'천':1000,'만':10000,'억':100000000}[match.group(2)],'f')
        units = [field['unit']] if field['unit'] else []
        if field['unit'] == 'KRW': units.append('원')
        for unit in sorted(units, key=len, reverse=True):
            if value.endswith(unit):
                value = value[:-len(unit)].strip()
                break
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', value):
            return None
        value = value.replace(',', '')
    elif field['type'] == 'boolean':
        if value not in ('true', 'false'): return None
        value = value == 'true'
    elif field['type'] == 'set':
        return None  # No implicit delimiter/splitting convention for case text.
    literal = {'type': field['type'], 'unit': field['unit'], 'value': value}
    try: validate_expression({'literal': literal})
    except KnowledgeError: return None
    return literal


def bind(state, fields, supplied=None):
    if supplied is not None and not isinstance(supplied, dict):
        raise ContractError('scenario bindings must map fields to offered fact IDs')
    supplied = supplied or {}
    if set(supplied) - fields.keys(): raise ContractError('unregistered fact binding field')
    choices = options(state); by_id = {r['id']: r for r in choices}
    bindings = {}; values = {}; occupied = set()
    for key, field in fields.items():
        if field['kind'] != 'FACT':
            if key in supplied: raise ContractError('rule constants cannot bind to case facts')
            continue
        exact = [r['id'] for r in choices if r['name'] == key]
        ids = supplied.get(key, exact)
        if not isinstance(ids, list) or any(not isinstance(i, str) or i not in by_id for i in ids) or len(ids) != len(set(ids)):
            raise ContractError('scenario fact binding is stale, duplicate or unoffered')
        if set(exact) - set(ids): raise ContractError('binding cannot leave an exact field fact active')
        names = {by_id[i]['name'] for i in ids}
        if any(r['name'] in names and r['id'] not in ids for r in choices):
            raise ContractError('binding must account for every version of the selected fact name')
        if occupied & set(ids): raise ContractError('one case fact cannot supply two scenario fields')
        occupied.update(ids); bindings[key] = list(ids)
        literals = [typed_value(by_id[i]['value'], field) for i in ids]
        if literals and all(v is not None for v in literals):
            if any(v != literals[0] for v in literals):
                raise ContractError('selected case facts disagree; resolve the fact conflict first')
            values[key] = literals[0]
    return bindings, values, choices


def effective(state, changes, bindings, kind):
    replaced = {i for k, ids in bindings.items() if kind == 'FACT' and k in changes for i in ids}
    rows = [dict(name=r['name'], value=r['value']) for r in options(state) if r['id'] not in replaced]
    if kind == 'FACT':
        for key, value in changes.items():
            raw = value['value']
            if isinstance(raw, bool): raw = 'true' if raw else 'false'
            elif isinstance(raw, list):
                import json
                raw = json.dumps(raw, ensure_ascii=False)
            rows.append({'name': key, 'value': str(raw) + (' ' + value['unit'] if value['unit'] else '')})
    return rows

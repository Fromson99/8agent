"""Dataiku-derived navigation rows, bounded to one document at a time."""
import json
from pathlib import Path
import re
import sqlite3

from semantic_runtime.oracle_dp_io import DPError, digest
from semantic_runtime.oracle_query_catalog import record
from semantic_runtime.navigation_match import norm, spaced, ReverseMatcher


def surface(group,label,value,identity,document_id=None):
    key=spaced(label) if group=='body' else norm(label)
    if not key:
        return
    yield record('native.surface',{'group':group,'key':key,'value':value},key=identity,
                 document_id=document_id,lookup_id=group+':'+key[:2],owner_id=group,target_id=digest(key))


def structures(path):
    from .oracle_migration import source_open
    from semantic_runtime.inherited_navigation import _derive_bindings
    from semantic_runtime.multi_entry_navigation import validate_structure
    from types import SimpleNamespace
    db=source_open(path)
    try:
        for did, in db.execute('SELECT document_id FROM document ORDER BY document_id'):
            units={}
            for row in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=? ORDER BY CAST(unit_id AS INTEGER)',(did,)):
                raw=json.loads(row['json']);parent=str(row['parent_id']) if row['parent_id'] is not None else None
                if raw.get('parent') is not None and str(raw['parent'])!=parent:
                    raise DPError('QUERY_STRUCTURE: source parent mismatch')
                units[(did,str(row['unit_id']))]={**raw,'parent':parent,'raw_structure':raw}
            # Use the existing structural validator and ancestry interpretation
            # once at publication, never rescan every unit at request startup.
            validate_structure(SimpleNamespace(units=units),[did])
            units,coordinates=_derive_bindings(units)
            yield record('native.structure_proof',{'document_id':did,'unit_count':len(units)},key=did,document_id=did,lookup_id=did)
            for (did,uid),unit in units.items():
                coordinate=coordinates[(did,uid)]
                yield record('native.unit',{'document_id':did,'unit_id':uid,'unit':unit,'coordinate':coordinate.as_dict() if coordinate else None},
                             key=[did,uid],document_id=did,lookup_id=digest([did,uid]),owner_id=unit['parent'])
                if (coordinate and coordinate.unit=='조' and unit.get('coordinate_scope')=='body'
                        and unit.get('coordinate_binding',{}).get('mode')!='unresolved'):
                    yield record('native.coordinate',{'unit_id':uid},key=[did,uid],document_id=did,
                                 lookup_id=digest([did,coordinate.canonical_surface()]))
                raw=unit['raw_structure'];family=raw.get('family','');label=raw.get('surface','');ordinal=raw.get('ordinal')
                labels=[]
                if re.fullmatch(r'제\s*\d+(?:-\d+)?\s*[편장절관조항호](?:의\s*\d+)?',label):
                    labels.append(label)
                if isinstance(ordinal,list) and len(ordinal)==1 and isinstance(ordinal[0],int):
                    kind='호' if family=='dot_number:1' else '항' if family=='circled' else None
                    if kind: labels.append(f'제{ordinal[0]}{kind}')
                title=re.sub(r'^제\s*\d+(?:-\d+)?\s*[편장절관조항호](?:의\s*\d+)?\s*','',raw.get('title','')).strip(' ()')
                for label,kind in [(x,'LOCATOR') for x in sorted(set(labels))]+([(title,'TITLE')] if len(norm(title))>=2 else []):
                    value={'document_id':did,'unit_id':uid,'kind':kind,'family':family}
                    yield from surface('structure',label,value,['structure',did,uid,kind,label],did)
    finally:
        db.close()


def navigation(path,store_path):
    from .oracle_migration import source_open
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    original=source_open(store_path)
    try:
        for did, in db.execute('SELECT DISTINCT document_id FROM source ORDER BY document_id'):
            parents={str(uid):str(parent) if parent is not None else None for uid,parent in original.execute(
                'SELECT unit_id,parent_id FROM source_unit WHERE document_id=?',(did,))}
            for sid,body in db.execute('SELECT id,json FROM source WHERE document_id=? ORDER BY id',(did,)):
                value=json.loads(body)
                yield record('native.source', {k:value[k] for k in ('id','document_id','unit_id','heading')},key=sid,document_id=did,lookup_id=sid)
                current=str(value['unit_id']) if value['unit_id'] is not None else None
                seen=set()
                while current is not None:
                    if current in seen: raise DPError('QUERY_STRUCTURE: ancestor cycle')
                    seen.add(current)
                    yield record('native.member',{'source_id':sid},key=[did,current,sid],document_id=did,lookup_id=digest([did,current]),owner_id=sid)
                    current=parents.get(current)
        for tid,body in db.execute('SELECT id,json FROM term ORDER BY id'):
            term=json.loads(body);label=term.get('label')
            if not tid.startswith(ReverseMatcher.INDEX_PREFIXES) or not label:
                continue
            key=spaced(label)
            if len(key.replace(' ',''))>=2 or (len(key)==1 and tid.startswith(ReverseMatcher.EVERYDAY_PREFIX)):
                did=term.get('scope_document_id')
                yield from surface('body',label,None,['term',tid],did)
                yield record('native.index_label',{'term_id':tid},key=tid,document_id=did,lookup_id=digest(key))
        from semantic_runtime.term_index import definition_summary
        for did,ident,body in db.execute('SELECT document_id,id,json FROM definition ORDER BY id'):
            row=definition_summary(ident,json.loads(body))
            yield record('native.definition_summary',{**dict(zip(('id','source_id','key','normalized','scope_status'),row)),
                         'surface_key':norm(row[2])},
                         key=ident,document_id=did,lookup_id=ident,owner_id=row[1])
    finally:
        db.close();original.close()


def glossary(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        for label,key in db.execute("SELECT DISTINCT label,key FROM label WHERE length(key)>=2 AND source IN ('dictionary','fibo') ORDER BY label,key"):
            yield from surface('body',label,key,['glossary',label,key])
    finally:
        db.close()


def records(path,relative,source_release):
    manifest=source_release['source_manifest']
    if relative=='store.sqlite':
        yield from structures(path)
    navigation_path=(manifest.get('navigation') or {}).get('path')
    if navigation_path and relative==navigation_path+'/navigation.sqlite':
        root=Path(path)
        for _ in Path(relative).parts: root=root.parent
        yield from navigation(path,root/'store.sqlite')
    binding=manifest.get('glossary') or {}
    if binding.get('cache') and relative.startswith(binding['cache']+'/') and relative.endswith('.sqlite'):
        yield from glossary(path)

"""Durable aliases in the existing request journal, scoped by its full binding."""
from copy import deepcopy
import json,re
from ..contracts import digest
from .errors import ContractError
from .repository import encoded

VERSION='investigation-references-v2'
FIELD='reference_registry'
SHORT=re.compile(r'^[A-Z][1-9][0-9]*$')

def identities(view):
    from .navigation_input import OPAQUE,TEXT_FIELDS
    found=set();strings=set()
    def walk(v,key=None):
        if key in (FIELD,'minimal_input_binding','view_id','presentation_id','source_stage','phase','base_state_revision','evidence_revision','state_version'):return
        if isinstance(v,str):
            strings.add(v)
            if key not in TEXT_FIELDS and key!='document_id' and (OPAQUE.fullmatch(v) or SHORT.fullmatch(v)):found.add(v)
        elif isinstance(v,list):
            for x in v:walk(x,key)
        elif isinstance(v,dict):
            for k,x in v.items():
                if key in ('new_reviews','revisions') and (OPAQUE.fullmatch(k) or SHORT.fullmatch(k)):found.add(k)
                walk(x,k)
    walk(view);return found,strings

def documents(view, canonical_names=None):
    from .compact_model_input import TEXT,SERVER_TOP
    found={}
    catalogue = canonical_names if canonical_names is not None else view.get('minimal_input_binding',{}).get('document_names',{})
    if not isinstance(catalogue,dict) or any(not isinstance(k,str) or not isinstance(v,str) or not k or not v for k,v in catalogue.items()):
        raise ContractError('invalid authoritative document catalogue binding')
    def walk(v,key=None):
        if key in TEXT or key in SERVER_TOP or key==FIELD:return
        if isinstance(v,dict):
            did=v.get('document_id');name=v.get('document_name') or v.get('document') or v.get('name')
            if isinstance(did,str) and did in catalogue:name=catalogue[did]
            if isinstance(did,str) and isinstance(name,str) and did and name:
                if did in found and found[did]!=name:raise ContractError('document identity has conflicting names')
                found[did]=name
            for k,x in v.items():walk(x,k)
        elif isinstance(v,list):
            for x in v:walk(x,key)
    walk(view);return found

def checked(registry):
    if (not isinstance(registry,dict) or registry.get('version')!=VERSION
        or registry.get('hash')!=digest({k:v for k,v in registry.items() if k!='hash'})):
        raise ContractError('stable reference registry hash/version mismatch')
    pairs=list(registry['mapping'].values())+[r['id'] for r in registry['documents']]
    if len(pairs)!=len(set(pairs)) or any(not SHORT.fullmatch(x) for x in pairs):
        raise ContractError('stable reference registry alias collision')
    from .navigation_input import OPAQUE
    if any(not (OPAQUE.fullmatch(x) or SHORT.fullmatch(x)) for x in registry['mapping']):raise ContractError('invalid canonical reference')
    return registry

def bind(repo,body):
    # Called inside save_view's transaction: aliases and view either both persist or neither.
    binding=repo.run()['binding_hash']
    rows=repo.db.execute("SELECT handle,kind,identity_json,binding_hash FROM navigation_handle WHERE kind IN ('model-reference-v2','model-document-v2')").fetchall()
    mapping={};docs={};used=set();changed=[]
    for handle,kind,raw,owner in rows:
        if owner!=binding:raise ContractError('stable reference journal binding changed')
        ident=json.loads(raw);handle=handle.removeprefix('@model:');used.add(handle)
        if kind=='model-reference-v2':mapping[ident]=handle
        else:docs[ident['document_id']]={**ident,'id':handle}
    found,strings=identities(body)
    def allocate(prefix,kind,ident):
        n=1
        while prefix+str(n) in used or prefix+str(n) in strings:n+=1
        short=prefix+str(n)
        repo.db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)',('@model:'+short,kind,encoded(ident),binding))
        used.add(short);changed.append(short);return short
    for ident in sorted(found-mapping.keys()):mapping[ident]=allocate(ident[0],'model-reference-v2',ident)
    for did,name in sorted(documents(body).items()):
        if did in docs:
            if docs[did]['name']!=name:raise ContractError('stable document name changed within bound generation')
        else:
            value={'document_id':did,'name':name};docs[did]={**value,'id':allocate('D','model-document-v2',value)}
    registry={'version':VERSION,'binding':binding,'mapping':mapping,'documents':sorted(docs.values(),key=lambda r:int(r['id'][1:]))}
    registry['hash']=digest(registry);checked(registry)
    if changed:repo.event('MODEL_REFERENCE_REGISTERED',{'version':VERSION,'binding':binding,'added':changed,'hash':registry['hash']})
    return {**body,FIELD:registry}

def verify(repo,registry):
    checked(registry)
    if registry['binding']!=repo.run()['binding_hash']:raise ContractError('stable reference view binding changed')
    expected=[(short,'model-reference-v2',encoded(ident)) for ident,short in registry['mapping'].items()]
    expected += [(r['id'],'model-document-v2',encoded({k:v for k,v in r.items() if k!='id'})) for r in registry['documents']]
    for short,kind,raw in expected:
        row=repo.db.execute('SELECT kind,identity_json,binding_hash FROM navigation_handle WHERE handle=?',('@model:'+short,)).fetchone()
        if row is None or tuple(row)!=(kind,raw,registry['binding']):raise ContractError('stable reference differs from durable journal')


def verify_document_catalogue(view):
    binding=view.get('minimal_input_binding',{})
    if 'document_names' not in binding:return
    names=binding['document_names']
    if binding.get('stable_references') is not True or not isinstance(names,dict):
        raise ContractError('document catalogue requires stable references')
    registry=checked(view.get(FIELD))
    known={r['document_id']:r['name'] for r in registry['documents']}
    if any(not isinstance(k,str) or not isinstance(v,str) or known.get(k)!=v for k,v in names.items()):
        raise ContractError('document catalogue differs from durable registry')
    if documents(view,canonical_names=names)!=names:
        raise ContractError('document catalogue does not match presented identities')

from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3];C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1107/stable-judgment-r1/snapshot';AG=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=AG/n;t=p.read_text();assert t.count(a)==1,(n,a[:80],t.count(a));p.write_text(t.replace(a,b))
(AG/'stable_references.py').write_text('''"""Durable aliases in the existing request journal, scoped by its full binding."""
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
        if key in (FIELD,'minimal_input_binding'):return
        if isinstance(v,str):
            strings.add(v)
            if key not in TEXT_FIELDS and OPAQUE.fullmatch(v):found.add(v)
        elif isinstance(v,list):
            for x in v:walk(x,key)
        elif isinstance(v,dict):
            for k,x in v.items():
                if key in ('new_reviews','revisions') and OPAQUE.fullmatch(k):found.add(k)
                walk(x,k)
    walk(view);return found,strings

def documents(view):
    from .compact_model_input import TEXT,SERVER_TOP
    found={}
    def walk(v,key=None):
        if key in TEXT or key in SERVER_TOP or key==FIELD:return
        if isinstance(v,dict):
            did=v.get('document_id');name=v.get('document_name') or v.get('document') or v.get('name')
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
    if any(not OPAQUE.fullmatch(x) for x in registry['mapping']):raise ContractError('invalid canonical reference')
    return registry

def bind(repo,body):
    # Called inside save_view's transaction: aliases and view either both persist or neither.
    binding=repo.run()['binding_hash']
    rows=repo.db.execute("SELECT handle,kind,identity_json,binding_hash FROM navigation_handle WHERE kind IN ('model-reference-v2','model-document-v2')").fetchall()
    mapping={};docs={};used=set();changed=[]
    for handle,kind,raw,owner in rows:
        if owner!=binding:raise ContractError('stable reference journal binding changed')
        ident=json.loads(raw);used.add(handle)
        if kind=='model-reference-v2':mapping[ident]=handle
        else:docs[ident['document_id']]={**ident,'id':handle}
    found,strings=identities(body)
    def allocate(prefix,kind,ident):
        n=1
        while prefix+str(n) in used or prefix+str(n) in strings:n+=1
        short=prefix+str(n)
        if repo.db.execute('SELECT 1 FROM navigation_handle WHERE handle=?',(short,)).fetchone():
            raise ContractError('model alias conflicts with existing navigation handle')
        repo.navigation_save('navigation_handle',(short,kind,encoded(ident),binding))
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
        row=repo.db.execute('SELECT kind,identity_json,binding_hash FROM navigation_handle WHERE handle=?',(short,)).fetchone()
        if row is None or tuple(row)!=(kind,raw,registry['binding']):raise ContractError('stable reference differs from durable journal')
''')
edit('relations_repository.py',"        with self.transaction():\n            view = super().save_view(phase, body, evidence_ids)","        with self.transaction():\n            if body.get('minimal_input_binding', {}).get('stable_references'):\n                from .stable_references import bind\n                body=bind(self,body)\n            view = super().save_view(phase, body, evidence_ids)")
edit('relations_repository.py',"                verified=NavigationReferences(stored)","                if stored.get('reference_registry'):\n                    from .stable_references import verify\n                    verify(self,stored['reference_registry'])\n                verified=NavigationReferences(stored)")
edit('relations_repository.py',"set(binding) != {'version', 'selection_refs'}", "set(binding) not in ({'version', 'selection_refs'}, {'version','selection_refs','stable_references'})")
edit('navigation_input.py',"        identities=set();strings=set()", "        registry=view.get('reference_registry')\n        if registry is not None:\n            from .stable_references import checked,identities as collect\n            checked(registry);found,_=collect(view)\n            if found-registry['mapping'].keys():raise ProposalError('unregistered stable reference')\n            self.forward={k:v for k,v in registry['mapping'].items() if k in found}\n            self.reverse={v:k for k,v in self.forward.items()}\n            self.ids={'navigation':sorted(found),'claims':[]}\n            self.stable=True\n            return\n        self.stable=False\n        identities=set();strings=set()")
edit('navigation_input.py',"        if isinstance(value,dict):return {k:self._map(v,mapping,k) for k,v in value.items()}","        if isinstance(value,dict):\n            if key=='reference_registry':return deepcopy(value)\n            return {(mapping.get(k,k) if key in ('new_reviews','revisions') else k):self._map(v,mapping,k) for k,v in value.items()}")
edit('navigation_input.py',"if k=='properties':out[k]={name:walk(child,name) for name,child in v.items()}","if k=='properties':out[k]={(self.forward.get(name,name) if key in ('new_reviews','revisions') else name):walk(child,name) for name,child in v.items()}")
edit('navigation_input.py',"    def receipt(self,view):return {'schema_version':'navigation-handles-v1','view_hash':digest(view),'mapping':dict(self.forward)}", "    def receipt(self,view):return {'schema_version':'navigation-handles-v2' if self.stable else 'navigation-handles-v1','view_hash':digest(view),'mapping':dict(self.forward)}")
# Keep nested schema diagnostics and prose ID references in the same vocabulary.
edit('navigation_input.py',"        if isinstance(value,str):return mapping.get(value,value) if key not in TEXT_FIELDS else value", "        if isinstance(value,str):\n            if key in ('contract_error','error','expected_constraint','path','related_paths'):\n                for ident,alias in sorted(mapping.items(),key=lambda p:-len(p[0])):value=value.replace(ident,alias)\n                return value\n            return mapping.get(value,value) if key not in TEXT_FIELDS else value")
edit('compact_model_input.py',"def bind(data, schema):\n    return {**data, 'minimal_input_binding': {'version': VERSION, 'selection_refs': sorted(_enum_strings(schema))}}", "def bind(data, schema, *, stable=False):\n    return {**data, 'minimal_input_binding': {'version': VERSION, 'selection_refs': sorted(_enum_strings(schema)),\n        **({'stable_references':True} if stable else {})}}")
edit('bounded_source_session.py',"data = minimal.bind(data, schema)","data = minimal.bind(data, schema, stable=self.profile.get('candidate_navigation',{}).get('stable_navigation_references',False))")
edit('compact_model_input.py',"    'minimal_input_binding', 'catalogue'", "    'minimal_input_binding', 'reference_registry', 'catalogue'")
edit('compact_model_input.py',"    names = OrderedDict((name, \"D\" + str(i + 1)) for i, name in enumerate(sorted(names)))", "    registry=view.get('reference_registry')\n    if registry is not None:\n        from .stable_references import checked\n        checked(registry)\n        docrows=registry['documents'];by_id={r['document_id']:r['name'] for r in docrows}\n        # Ambiguous same-name documents keep their real name unless a document ID binds them.\n        counts={n:sum(r['name']==n for r in docrows) for n in names}\n        names=OrderedDict((r['name'],r['id']) for r in docrows if counts.get(r['name'],0)==1)\n        docrefs={r['document_id']:r['id'] for r in docrows}\n    else:\n        names = OrderedDict((name, \"D\" + str(i + 1)) for i, name in enumerate(sorted(names)))\n        docrefs={did:names[name] for did,name in by_id.items()}")
edit('compact_model_input.py',"result.setdefault('document', names[by_id[child]])", "result.setdefault('document', docrefs[child])")
edit('compact_model_input.py',"result['document'] = names[by_id[value['document_id']]]", "result['document'] = docrefs[value['document_id']]")
edit('compact_model_input.py',"row['document'] = names[by_id[scope['document_id']]]", "row['document'] = docrefs[scope['document_id']]")
edit('compact_model_input.py',"    if names:\n        result['documents'] = [{'id': short, 'name': name} for name, short in names.items()]", "    if registry is not None:\n        result['documents']=[{'id':r['id'],'name':r['name']} for r in registry['documents']]\n    elif names:\n        result['documents'] = [{'id': short, 'name': name} for name, short in names.items()]")
# Remove audit hashes/coordinates only in model copy, preserving originals and visible meaning.
edit('compact_model_input.py',"'span_hash', 'block_hash', 'source_hash', 'schema_version', 'revision'}", "'span_hash', 'block_hash', 'source_hash', 'schema_version', 'revision',\n    'state_hash','receipt_sha256','request_key','material','seen_material','originals','previous_final_review'}")
edit('decision_projection.py',"add(target, {'document': document, **{k: value[k] for k in hint_fields if k in value}})", "add(target, {'document': document, 'document_id':expected or document_id, **{k: value[k] for k in hint_fields if k in value}})")
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';d=json.loads(p.read_text());d['candidate_navigation'].update(stable_navigation_references=True,new_read_reviews=True,independent_read_recovery=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for p in AG.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Stable reference implementation staged, not executed')

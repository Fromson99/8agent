from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];AG=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1107/stable-judgment-r1/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=AG/n;t=p.read_text();assert t.count(a)==1,(n,a[:70],t.count(a));p.write_text(t.replace(a,b))
# Distinct storage namespace avoids colliding with existing executable handles.
edit('stable_references.py',"ident=json.loads(raw);used.add(handle)","ident=json.loads(raw);handle=handle.removeprefix('@model:');used.add(handle)")
edit('stable_references.py',"        if repo.db.execute('SELECT 1 FROM navigation_handle WHERE handle=?',(short,)).fetchone():\n            raise ContractError('model alias conflicts with existing navigation handle')\n        repo.navigation_save('navigation_handle',(short,kind,encoded(ident),binding))", "        repo.db.execute('INSERT INTO navigation_handle VALUES(?,?,?,?)',('@model:'+short,kind,encoded(ident),binding))")
edit('stable_references.py',"(short,)).fetchone()", "('@model:'+short,)).fetchone()")
edit('stable_references.py',"if key not in TEXT_FIELDS and OPAQUE.fullmatch(v):found.add(v)", "if key not in TEXT_FIELDS and key!='document_id' and (OPAQUE.fullmatch(v) or SHORT.fullmatch(v)):found.add(v)")
edit('stable_references.py',"if key in ('new_reviews','revisions') and OPAQUE.fullmatch(k):found.add(k)", "if key in ('new_reviews','revisions') and (OPAQUE.fullmatch(k) or SHORT.fullmatch(k)):found.add(k)")
edit('stable_references.py',"if any(not OPAQUE.fullmatch(x) for x in registry['mapping'])", "if any(not (OPAQUE.fullmatch(x) or SHORT.fullmatch(x)) for x in registry['mapping'])")
edit('navigation_input.py',"        if isinstance(value,str):\n            if key in", "        if isinstance(value,str):\n            if self.stable and key=='document_id':return value\n            if key in")
edit('decision_projection.py',"            value,_=judgment.normalize_review(value,judgment_context)\n            judgment.validate_review(value,judgment_context,current,issues,owner=inv.s)", "            reviewed,_=judgment.normalize_review(value,judgment_context)\n            judgment.validate_review(reviewed,judgment_context,current,issues,owner=inv.s)")
# Stable views are explicit, while old sessions without that profile flag retain v1 behavior.
edit('navigation_input.py',"'conclusion','reason','sufficiency_reason'", "'finding','conclusion','reason','sufficiency_reason'")
# Registry is a server field; do not let document scan register its own nested rows twice.
edit('compact_model_input.py',"                if k not in TEXT:\n                    scan(child)", "                if k not in TEXT and k not in SERVER_TOP:\n                    scan(child)")
# For a known document ID, it takes precedence over name-only lookup, including duplicate names.
edit('compact_model_input.py',"result['document'] = names[child]", "result['document'] = docrefs.get(value.get('document_id'),names[child])")
for p in AG.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Inspection fixes staged before first contract run')

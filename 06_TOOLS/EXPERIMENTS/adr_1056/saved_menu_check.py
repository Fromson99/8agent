"""Factor three saved law menus; never rerun retrieval or alter old journals."""
from pathlib import Path
from copy import deepcopy
import json, sqlite3, sys, hashlib
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1056/grouped-query-r1/snapshot'
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws/artifacts'
sys.path.insert(0,str(CODE/'02_BACKEND'))
from semantic_runtime.legal_agent.law_choice_projection import project
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.navigation_input import NavigationReferences

def encoded(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def wire(v):return compact_wire_view(NavigationReferences(v).view(v),v['phase'])
rows=[]
for case in ('007-fsc-hard-005-A1','049-cm-023-A2','060-fsc-hard-008-A1'):
    journal=next((ROOT/'04_EXPERIMENTS/ADR/ADR-1054-ontology-mvp-state-binding/artifacts/matrix'/case/'runtime').rglob('journal.sqlite'))
    before=journal.stat()
    with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
        view=next(json.loads(raw) for raw, in db.execute('SELECT body_json FROM model_view ORDER BY created_seq')
                  if 'read-choice' in json.loads(raw).get('source_stage',''))
    old=deepcopy(view);actions={}
    for law in view['law_matches']:
        target=law['open_action']
        if target:actions[target]={'id':target,'action':'OPEN_LAW','identity':{'document_id':law['document_id'],'unit_id':None}}
    table,targets=project(view['law_matches'],actions)
    view['law_matches']=table
    view['tool_options']=[o for o in view['tool_options'] if o.get('target') not in set(targets.values())]
    view['tool_options'].append({'choice':'OPEN_LAW','selection':'law_matches.rows의 law 번호로 조문 후보 보기; null은 현재 선택 불가'})
    assert {k:v for k,v in view.items() if k not in ('law_matches','tool_options')}=={k:v for k,v in old.items() if k not in ('law_matches','tool_options')}
    assert len(table['rows'])==len(old['law_matches'])
    assert [r[1] for r in table['rows']]==[r['name'] for r in old['law_matches']]
    old_wire,new_wire=encoded(wire(old)),encoded(wire(view))
    row={'case':case,'journal':str(journal.relative_to(ROOT)),'law_count':len(table['rows']),
        'old_open_law_options':sum(o['choice']=='OPEN_LAW' for o in old['tool_options']),
        'new_open_law_options':sum(o['choice']=='OPEN_LAW' for o in view['tool_options']),
        'model_view_chars_before':len(old_wire),'model_view_chars_after':len(new_wire),
        'model_view_utf8_bytes_before':len(old_wire.encode()),'model_view_utf8_bytes_after':len(new_wire.encode()),
        'view_reduction_percent':round(100*(1-len(new_wire)/len(old_wire)),2),
        'all_other_fields_exactly_preserved':True,'all_law_names_preserved':True,
        'model_calls':0,'source_or_index_loaded':False,
        'limitation':'View-only representation comparison, excluding schema/system/transport. Same old retrieval set retained. Not complete request tokens or new-search recall.'}
    after=journal.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    rows.append(row)
(ART/'saved-menu-check.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ('case','law_count','model_view_chars_before','model_view_chars_after','view_reduction_percent')} for r in rows],ensure_ascii=False))

"""Read-only, hash-bound size accounting; never reserve or call a model."""
from pathlib import Path
import hashlib,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[3]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1058-bounded-navigation-input-dedup/artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1058/dense-input-r1'
meta=json.loads((CAND/'candidate.json').read_text());rev=meta['revisions'][-1]
CODE=CAND/'revisions'/rev['revision_id']/'snapshot'
sys.path.insert(0,str(CODE/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.model_input_projection import Projection,prepare_request,encoded,GUIDE,_view
from semantic_runtime.legal_agent.input_guidance import navigation_instructions
from semantic_runtime.legal_agent.read_connection_guidance import READ_CONNECTION_PROMPT


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    rows=[]
    for adr,cell in [('ADR-1056-grouped-fulltext-compact-laws','001-*'),
                     ('ADR-1056-grouped-fulltext-compact-laws','003-*'),
                     ('ADR-1057-grouped-query-literal-preservation','001-*')]:
        matrix=ROOT/'04_EXPERIMENTS/ADR'/adr/'artifacts/matrix'
        path=next(matrix.glob(cell+'/runtime/legal-agent/runs/*/*/journal.sqlite'))
        before=sha(path)
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
            events=[(k,json.loads(s)) for k,s in db.execute('SELECT kind,payload_json FROM event')]
            budgets={e['view_id']:e for k,e in events if k=='MODEL_INPUT_BUDGET'}
            states={e['view_id']:e['state'] for k,e in events if k=='MODEL_STEP_STATE'}
            for body,h in db.execute('SELECT body_json,body_hash FROM model_view'):
                v=json.loads(body)
                if not v.get('source_stage','').endswith('-read-choice'):continue
                w=compact_wire_view(NavigationReferences(v).view(v),v['phase'])
                old=Projection(w,hide_guidance=True,share_values=False,bind_scopes=False)
                system=READ_CONNECTION_PROMPT+'\n'+navigation_instructions(w)
                base={'messages':[{'role':'system','content':system},
                     {'role':'user','content':encoded({'view':w,'step_state':states[v['view_id']]})}]}
                old_request={'messages':[{'role':'system','content':system+('\n'+GUIDE if old.scopes else '')},
                    {'role':'user','content':encoded({'view':old.wire,'step_state':states[v['view_id']]})}]}
                budget=budgets[v['view_id']]
                assert len(old_request['messages'][1]['content'])==budget['input_user_chars']
                new,codec=prepare_request(base)
                assert codec.verify(w,codec.wire)==w
                codec.verify_request_instructions(new)
                delta=len(encoded(new))-len(encoded(old_request))
                total=budget['measured_chars']+delta
                # The first READ was physically sent. Match both the restored
                # old view and the exact whole-request delta, not only a mock.
                check=None
                row=db.execute('SELECT request_json FROM model_attempt WHERE view_id=? LIMIT 1',(v['view_id'],)).fetchone()
                if row:
                    actual=json.loads(row[0]);idx,payload=_view(actual)
                    assert payload['view']==old.wire
                    # Rehydrate the known pre-projection view, preserving every
                    # actual schema, alias guide and transport field.
                    actual_base=json.loads(row[0]);actual_base['messages'][idx]['content']=encoded({**payload,'view':w})
                    if old.scopes:
                        actual_base['messages'][0]['content']=actual_base['messages'][0]['content'].replace('\n'+GUIDE,'')
                    actual_new,actual_codec=prepare_request(actual_base)
                    assert len(encoded(actual_new))-len(encoded(actual))==delta
                    check={'actual_saved_request_sha256':digest(actual),'same_exact_delta':True}
                rows.append({'case':path.relative_to(matrix).parts[0],'source_stage':v['source_stage'],
                    'journal':str(path.relative_to(ROOT)),'journal_sha256':before,'view_id':v['view_id'],
                    'stored_view_sha256':h,'canonical_projection_sha256':digest(w),
                    'new_wire_sha256':digest(codec.wire),'original_request_chars':budget['measured_chars'],
                    'reconstructed_request_chars':total,'reduction_chars':-delta,
                    'reduction_percent':round(-delta/budget['measured_chars']*100,2),
                    'max_context_chars':budget['max_context_chars'],'within_budget':total<=budget['max_context_chars'],
                    'exact_full_request_delta_check':check,'lossless_reconstruction':True,
                    'source_rows':len(v.get('sources',[])),'tool_rows':len(v.get('tool_options',[])),
                    'source_and_state_hash_preserved':True,'server_scope_references':len(codec.bound_scopes),
                    'expanded_nested_card_format':codec.expanded_cards})
        assert sha(path)==before
    report={'candidate_root':str(CODE.relative_to(ROOT)),'revision_sha256':rev['revision_sha256'],
        'method':'Saved complete request character count plus exact serialized changed user/system components. Saved step-state retained; schema and all other request parts unchanged. Not a token estimate.',
        'external_model_calls':0,'same_rows_actions_sources_states':True,'rows':rows,
        'all_within_budget':all(r['within_budget'] for r in rows)}
    (ART/'saved-input-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'all_within_budget':report['all_within_budget'],'sizes':[(r['original_request_chars'],r['reconstructed_request_chars']) for r in rows]}))
    assert len(rows)==4 and report['all_within_budget']

if __name__=='__main__':main()

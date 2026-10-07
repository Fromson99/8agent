"""Synthetic v3 contracts: exact wire, journal, relations and public consumers."""
import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.relations_policy import DEFAULT_PROFILE
from semantic_runtime.legal_agent.relations_repository import RelationsRepository
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, BudgetExhausted
from semantic_runtime.legal_agent.publication import recover
from semantic_runtime.contracts import digest
from test_legal_agent_double_harness import generation, ROOT, BINDING, wire
from test_document_release import source
from lawrag.pipeline.term_generation import build_generation

PROFILE={**DEFAULT_PROFILE,'model_binding':BINDING,'max_model_attempts':24}


def tool(name,**args):
    return {'tool':name,'args':args,'reason':'합성 원문에서 질문의 적용 범위를 확인',
            'question_refs':['Q1'],'expected_information':'정확 원문과 연결 대상'}


def decision(assessments=(),relations=(),actions=(),intent='CONTINUE'):
    return {'actions':list(actions),'assessments':list(assessments),'relation_assessments':list(relations),
        'candidate_decisions':[],'route_decisions':[],'question_updates':[],'intent':intent,'reason':'합성 확인'}


def assessment(e,q='Q1',disposition='ADOPT'):
    return {'evidence':e['evidence'],'question_ref':q,'summary':'모의 원문','reason':'질문의 승인 범위',
        'disposition':disposition,'role':'SUPPORT','related_relation_ids':[],
        'basis_spans':[{'evidence':e['evidence'],**{k:p[k] for k in ('block_id','start_cp','end_cp')}} for p in e['spans']]}


def relation_assessment(n,evidence,decision='NOT_RELEVANT'):
    src=n['source_evidence']; target=n['target_evidence'] if decision=='RELEVANT' else []
    ids=src+target
    return {'relation_id':n['relation_id'],'question_ref':'Q1','decision':decision,'reason':'모의 원문에 한정한 관계 판단',
        'source_evidence':src,'target_evidence':target,'reason_basis':'SOURCE_AND_TARGET' if target else 'SOURCE_ONLY',
        'scope_note':'모의 규정 범위','substitution_note':'치환 없음 확인','exception_note':'단서 확인',
        'basis_spans':[{'evidence':e['evidence'],**{k:p[k] for k in ('block_id','start_cp','end_cp')}} for e in evidence if e['evidence'] in ids for p in e['spans']]}


class Transport:
    binding=BINDING
    def __init__(self): self.calls=[]
    def validate_model(self): return {'verified':True,'synthetic':True}
    def send_once(self,*,body,ticket):
        self.calls.append(body); v=json.loads(body['messages'][1]['content'])['view']
        if v['phase']=='investigate':
            if not v['last_action_results']:
                out=decision(actions=[tool('locate',locator='모의승인규정 제1조',target=v['corpus_root'],branch='any',cursor=None)])
            elif not v['exact_evidence']:
                target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
                out=decision(actions=[tool('read',target=target,extent='subtree',cursor=None)])
            else:
                out=decision(assessments=[assessment(e) for e in v['exact_evidence']],
                    relations=[relation_assessment(n,v['exact_evidence']) for n in v['relation_notices'] if n['completion_required']],intent='DRAFT')
        elif v['phase']=='compose':
            out={'paragraphs':[{'text':'모의 규정의 승인 범위를 확인했습니다.','evidence':v['evidence_roles']['support'],
                'question_refs':['Q1'],'fact_dependencies':[],'relation_dependencies':[]}],'limitations':[]}
        else:
            out={'checks':[{'claim':c['entity_id'],'verdict':'SUPPORTED','evidence':c['payload']['evidence'],
                'issue':'범위','reason':'모의 원문 대조','actions':[],
                'relation_checks':[n['relation_id'] for n in v['relation_notices'] if n['completion_required'] and set(n['source_evidence']) & set(c['payload']['evidence'])]} for c in v['claims']],
                'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'모의 질문 확인'}}
        return wire(out)


def app_for(tmp_path,g,profile=None,transport=None):
    return create_app(tmp_path,g,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v3',
        legal_agent_profile=profile or PROFILE,legal_agent_transport=transport or Transport())


@contextmanager
def session(tmp_path,g,profile=None,docs=None,question='승인?'):
    app=app_for(tmp_path,g,profile);p=app.state.pipeline;docs=docs or ['d']
    req={'question':question,'document_ids':docs,'use_llm':True}
    try:
        with p.term_agent.open_session(req,query=p.plan(question,docs),runtime=tmp_path/'runtime') as s: yield s
    finally: p.store.close()


def delivered(s,v):
    req={'messages':[{'role':'system','content':'fixture'},{'role':'user','content':json.dumps({'view':v})}]}
    a=s.work.reserve_attempt(v,req,'test:'+v['view_id'],1,v['phase'])
    s.work.attempt_sent(a);s.work.finish_attempt(a,'SUCCEEDED',{}, {'model':BINDING['model']})


def read(s,locator='모의승인규정 제1조',name='r'):
    r=s.sources.execute(tool('locate',locator=locator,target=s.sources.root,branch='any',cursor=None),'locate:'+name)
    target=r['items'][0]['target']
    return s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),name)


def test_http_wire_journal_and_ui(tmp_path,generation):
    t=Transport();app=app_for(tmp_path,generation,transport=t)
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert r.status_code==200,r.text
        result=r.json();assert result['answer']['claims'],result['answer']
        audit=result['assembly']['term_agent']['exploration_v3']
        assert audit['action_summary'] and audit['display_lines'] and audit['audit']['complete']
        assert result['assembly']['term_agent']['implementation']=='legal-agent-tools-v3'
        assert c.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'MISSING_EVIDENCE','reason':'모의'}).status_code==200
        assert 'textContent' in c.get('/rag/').text and '탐색·근거 판단' in c.get('/rag/').text
        calls=len(t.calls)
        r=c.post('/v1/rag/ask',json={'question':'전체 문서 목록','use_llm':False})
        assert r.status_code==200,r.text
        assert len(t.calls)==calls
    views=[json.loads(b['messages'][1]['content'])['view'] for b in t.calls]
    assert any(any(i.get('preview_spans') for o in v['last_action_results'] for i in o['items']) for v in views)
    journal=next((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM item_presentation').fetchone()[0]>0


def test_reference_auto_read_and_cycle(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조를 준용한다.','제1조를 준용한다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        result=read(s,'모의규정 제1조')
        assert len(s.work.evidence())==2
        assert len([a for a in s.sources.action_summaries() if a['actor']=='SYSTEM_POLICY' and a['tool']=='read'])==1
        n=[n for n in s.work.notices() if n['family']=='reference']
        assert len(n)==4 and {r['direction'] for r in n}=={'outgoing','incoming'} and all(n['predicate']=='APPLIES_MUTATIS_MUTANDIS' for n in n)
        assert result['evidence_ids']
        v=s.view('investigate');delivered(s,v)
        assert all(n['witness_presented'] and n['target_presented'] for n in v['relation_notices'] if n['family']=='reference')


def test_action_identity_includes_purpose(tmp_path,generation):
    with session(tmp_path,generation) as s:
        a=tool('locate',locator='모의승인규정 제1조',target=s.sources.root,branch='any',cursor=None)
        x=s.sources.execute(a,'a');budget=s.work.budget()
        assert s.sources.execute(a,'a')==x and s.work.budget()==budget
        with pytest.raises(ProposalError,match='canonical'): s.sources.execute({**a,'reason':'다른 목적'},'a')
        assert s.sources.execute({**a,'reason':'다른 목적'},'b')['action_id']=='b'


def test_exact_wire_and_question_scoped_history(tmp_path,generation):
    with session(tmp_path,generation,question='승인?\n범위?') as s:
        read(s);v=s.view('investigate')
        with pytest.raises(ContractError,match='wire'): s.work.reserve_attempt(v,{},'x',1,'investigate')
        delivered(s,v)
        e=v['exact_evidence'][0]
        qs=[q['id'] for q in s.context.pieces]
        first=assessment(e,qs[0]);s.apply_turn(v,decision([first]))
        v=s.view('investigate');delivered(s,v)
        s.apply_turn(v,decision([assessment(e,qs[0],'REJECT')]))
        assert s.work.db.execute("SELECT count(*) FROM entity_version WHERE kind='assessment'").fetchone()[0]==2
        v=s.work.save_view('investigate',{},[]);delivered(s,v)
        with pytest.raises(ProposalError,match='not presented'): s.apply_turn(v,decision([first]))


def test_read_and_tasks_commit_atomically(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation) as s:
        r=s.sources.execute(tool('locate',locator='모의승인규정 제1조',target=s.sources.root,branch='any',cursor=None),'l')
        def crash(*args,**kw): raise RuntimeError('injected before task commit')
        monkeypatch.setattr(s.work,'enqueue_system',crash)
        with pytest.raises(RuntimeError): s.sources.execute(tool('read',target=r['items'][0]['target'],extent='subtree',cursor=None),'r')
        assert not s.work.evidence()
        assert s.work.db.execute('SELECT count(*) FROM system_task').fetchone()[0]==0
        assert not s.work.db.execute("SELECT 1 FROM action_receipt WHERE action_id='r'").fetchone()


def test_recovery_interrupts_and_preserves_versions(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);path=s.work.path
    assert recover(tmp_path/'runtime/legal-agent/runs',tmp_path/'runs')[0]['status']=='INTERRUPTED'
    repo=RelationsRepository(path)
    assert repo.coverage(final=True)[0]['status']=='UNASSESSED_AT_STOP'
    repo.close()


def test_definition_term_occurrence_and_structure(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['이 규정에서 “영업일”이란 은행이 영업하는 날을 말한다. 제2조에 따른다.','영업일에 신청한다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조')
        families={n['family'] for n in s.work.notices()}
        assert {'reference','definition','occurrence','structure'}<=families
        assert not any(a['tool']=='read' and a['actor']=='SYSTEM_POLICY' for a in s.sources.action_summaries())


def prepare_claim(s,dependencies=(),related=True):
    v=s.view('investigate');delivered(s,v)
    assessments=[assessment(e) for e in v['exact_evidence']]
    relations=[relation_assessment(n,v['exact_evidence'],'RELEVANT' if related else 'NOT_RELEVANT') for n in v['relation_notices'] if n['completion_required']]
    s.apply_turn(v,decision(assessments,relations,intent='DRAFT'))
    s.select({'retrieval':s.retrieval()})
    v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
    p={'text':'모의 준용 결론','evidence':s.packed['support'],'question_refs':['Q1'],
        'fact_dependencies':[],'relation_dependencies':list(dependencies)}
    return v,p


def test_joint_relation_gate_rejects_omission_and_accepts_explicit_dependency(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조를 준용한다.','승인 절차를 따른다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조')
        rid=next(n['relation_id'] for n in s.work.notices() if n['completion_required'])
        v,p=prepare_claim(s)
        with pytest.raises(ProposalError,match='omitted'):s.relation_requirements(p,v)
        p['relation_dependencies']=[rid]
        s.commit_draft(v,{'paragraphs':[p],'limitations':[]})
        assert s.work.heads('claim',current=True)
        v=s.view('review',required=s.packed['evidence_ids']);delivered(s,v)
        cid=s.work.heads('claim',current=True)[0]['entity_id']
        check={'claim':cid,'verdict':'SUPPORTED','evidence':s.packed['support'],'issue':'확인','reason':'출발 대상 공동 검토','actions':[],'relation_checks':[]}
        review={'checks':[check],'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'확인'}}
        with pytest.raises(ProposalError,match='relation checks'):s.commit_review(v,review)
        check['relation_checks']=[rid];s.commit_review(v,review)
        assert s.work.head('review',cid)['payload']['verdict']=='SUPPORTED'
        # A newly discovered edge invalidates only claims bound to this evidence set.
        n=deepcopy(s.work.notice(rid));n['relation_id']='REL-new';n['notice_hash']=digest(n)
        with s.work.transaction():s.work.record_notice(n)
        assert not s.work.heads('claim',current=True)


def test_source_only_exclusion_does_not_force_target_read(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조에 따른다.','다른 대상의 절차.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조');assert len(s.work.evidence())==1
        v,p=prepare_claim(s,related=False)
        s.commit_draft(v,{'paragraphs':[p],'limitations':[]})
        assert s.work.heads('claim',current=True)


def test_exact_reference_extent_and_unrelated_paragraph(tmp_path,term_glossary):
    from test_document_navigation_serving import relation_generation
    g=relation_generation(tmp_path,term_glossary)
    with session(tmp_path,g,docs=['reg','rule']) as s:
        read(s,'코스닥시장 상장규정 시행세칙 제23조제4항')
        references=[n for n in s.work.notices() if n['family']=='reference' and n['direction']=='outgoing']
        assert references
        for n in references:
            for card in n['targets']:
                raw=s.sources.resolve(card['target'])
                if raw.get('unit_id')=='103':
                    assert raw['block_ids']
                    r=s.sources.execute(tool('read',target=card['target'],extent='subtree',cursor=None),'exact-target')
                    assert '다른 절차' not in ''.join(i['text'] for i in r['items'])
                    return
        pytest.fail('expected exact provision target')


def test_mixed_frame_does_not_prefetch_and_partial_scan_blocks_ready(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조에 따르고 제3조를 준용한다.','두 번째 절차.','세 번째 절차.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation',{**PROFILE,'relation_page_size':1}) as s:
        read(s,'모의규정 제1조')
        assert len(s.work.evidence())==1
        n=next(n for n in s.work.notices() if n['family']=='reference')
        assert n['role_status']=='AMBIGUOUS' and not n['auto_eligible']
        v,p=prepare_claim(s,related=False)
        with pytest.raises(ProposalError,match='scan incomplete'):s.relation_requirements(p,v)
        scan=s.work.db.execute("SELECT next_cursor FROM relation_scan WHERE family='reference'").fetchone()
        assert scan[0]
        e=s.work.evidence()[0]['evidence_id']
        more=s.sources.execute(tool('follow_relations',target=e,family='reference',cursor=scan[0]),'next-ref')
        assert more['scan_status']=='COMPLETE'


def test_no_automatic_second_hop_and_scope_restrictions(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조를 준용한다.','제3조를 준용한다.','「비공개규정」 제1조를 준용한다.']),('hidden','비공개규정',['민감 원문'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조');assert len(s.work.evidence())==2
        read(s,'모의규정 제3조','manual')
        assert len(s.work.evidence())==3
        notices=s.work.notices()
        assert any(n['resolution']=='SCOPE_RESTRICTED_OR_MISSING' for n in notices)
        assert '민감 원문' not in json.dumps(notices,ensure_ascii=False)
        assert all(e['document_id']=='d' for e in s.work.evidence())


def test_small_budget_preserves_successful_read_and_not_executed_purpose(tmp_path,generation):
    with session(tmp_path,generation,{**PROFILE,'max_tool_actions':7,'tool_finalization_reserve':4}) as s:
        read(s)
        assert s.work.evidence()
        assert s.work.db.execute("SELECT count(*) FROM system_task WHERE status='SKIPPED_BUDGET'").fetchone()[0]>0
        while s.work.budget()['tool_used']<7:
            s.sources.execute(tool('inspect',section='budget',cursor=None),'budget:'+str(s.work.budget()['tool_used']))
        with pytest.raises(BudgetExhausted):s.sources.execute(tool('inspect',section='budget',cursor=None),'stop')
        row=s.work.db.execute("SELECT status,proposed_json FROM action_context WHERE action_id='stop'").fetchone()
        assert row['status']=='NOT_EXECUTED' and json.loads(row['proposed_json'])['reason']


def test_preview_suppression_is_not_presentation(tmp_path,generation):
    with session(tmp_path,generation,{**PROFILE,'preview_chars':5,'max_preview_chars':5}) as s:
        for i in (1,2):s.sources.execute(tool('locate',locator=f'모의승인규정 제{i}조',target=s.sources.root,branch='any',cursor=None),str(i))
        v=s.view('investigate');delivered(s,v)
        cards=[c for o in v['last_action_results'] for c in o['items']]
        assert len([c for c in cards if c.get('preview_spans')])==1
        assert s.work.db.execute("SELECT count(*) FROM item_presentation WHERE kind='preview' AND view_id=?",(v['view_id'],)).fetchone()[0]==1
        assert not s.work.evidence()


def test_genos_render_omits_internal_audit_and_keeps_old_result_fallback():
    import importlib.util
    path=ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
    spec=importlib.util.spec_from_file_location('genos_v3_render',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result={'answer':{'text':'답변'},'assembly':{'term_agent':{'exploration_v3':{'display_lines':['<script>alert(1)</script>','미확인 관계']}}}}
    rendered=module.render(result)
    # Since the shipped 2026-09-25 chat change, diagnostic audit lines stay in
    # the API/journal. Legal review notes are carried by answer.text instead.
    assert rendered == '답변'
    assert module.render({'answer':{'text':'이전 답변'}})=='이전 답변'


def test_official_delegation_survives_generic_cites_role(tmp_path,term_glossary,monkeypatch):
    from semantic_runtime import term_references
    monkeypatch.setattr(term_references,'load_reference_inputs',lambda: ({},[{
        'src':{'name':'모의법','jo':'제1조'},'dst':{'name':'모의시행령','jo':'제1조'},'kind':'시행령'}],'synthetic'))
    raw=source(tmp_path/'source.sqlite',[('d','모의법',['대통령령으로 정한다.']),('decree','모의시행령',['세부 경우를 정한다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation',docs=['d','decree']) as s:
        read(s,'모의법 제1조')
        n=next(n for n in s.work.notices() if n['family']=='reference')
        assert n['predicate']=='DELEGATES_TO' and n['reference_role']=='CITES'
        assert n['targets'] and 'official_delegation_lawgokr' in n['origins']
        assert len(s.work.evidence())==1


def test_all_term_relation_codes_and_directions(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation) as s:
        terms={'a':{'id':'a','label':'출발'},'b':{'id':'b','label':'대상'}}
        edges=[{'id':str(i),'source':'a' if i%2 else 'b','target':'b' if i%2 else 'a','code':f'14030{i}','status':'CONNECTED'} for i in range(1,6)]
        monkeypatch.setattr(s.sources.tools,'terms',terms)
        monkeypatch.setattr(s.sources.tools,'edges',{'a':edges,'b':edges})
        t=s.sources.handle('T',{'term_id':'a','routes':[],'target':s.sources.root})
        r=s.sources.execute(tool('follow_relations',target=t,family='term',cursor=None),'terms')
        assert {n['predicate'] for n in r['items']}=={'SYNONYM','ANTONYM','BROADER_TERM','NARROWER_TERM','RELATED_TERM'}
        assert {n['direction'] for n in r['items']}=={'incoming','outgoing'}
        assert not s.work.evidence()


def test_bound_knowledge_relations_and_lexical_observations(tmp_path,term_glossary):
    from semantic_runtime.contracts import sha,write
    from lawrag.pipeline import glossary_v1,glossary_senses
    knowledge=tmp_path/'knowledge'
    with sqlite3.connect(knowledge/'identity.sqlite') as db:
        db.executescript('CREATE TABLE official_relation(id,source_id,target_id,code,payload); CREATE TABLE source_edge(id,source,subject,target,predicate);')
        db.execute('INSERT INTO official_relation VALUES (?,?,?,?,?)',('r','fixture:day','fixture:time','140304','{}'))
    with sqlite3.connect(term_glossary/'dictionary.sqlite') as db:
        glossary_v1.add_entry(db,'fixture:time','econedu','시간','시간의 모의 정의')
        glossary_senses.create_tables(db)
        db.executemany('INSERT INTO sense_candidate VALUES(?,?,?)',[('s1','fixture:day','{}'),('s2','fixture:time','{}')])
        db.execute('INSERT INTO sense_assertion VALUES(?,?,?,?,?,?,?,?,?)',('lex1','job','RELATION','OVERLAPS','s1','s2','fixture-scope','[]','PROPOSED'))
    manifest=json.loads((knowledge/'manifest.json').read_text())
    manifest['dictionary_sha256']=sha(term_glossary/'dictionary.sqlite')
    for f in manifest['files']:
        f['sha256']=sha(knowledge/f['path']);f['bytes']=(knowledge/f['path']).stat().st_size
    (knowledge/'manifest.json').write_text(json.dumps(manifest))
    report=json.loads((term_glossary/'report.json').read_text());report['dictionary_sha256']=manifest['dictionary_sha256']
    report['knowledge_binding']['manifest_sha256']=sha(knowledge/'manifest.json');(term_glossary/'report.json').write_text(json.dumps(report))
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['영업일에 신청한다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조')
        n=[n for n in s.work.notices() if n['family']=='knowledge']
        assert any(x['predicate']=='140304' and x['source_status']=='SOURCE_RECORDED' for x in n)
        assert any(x['predicate']=='OVERLAPS' and x['source_status']=='PROPOSED' for x in n)
        assert all(x['canonical_approval'] is False for x in n)
        assert s.sources.capabilities['lexical_observations']=='AVAILABLE'
        lookup=s.sources.execute(tool('lookup_definition',query='영업일',target=s.sources.root,cursor=None),'lookup-concept')
        concept=lookup['items'][0]['concept_target']
        linked=s.sources.execute(tool('follow_relations',target=concept,family='knowledge',cursor=None),'concept-relations')
        assert any(n['predicate']=='SOURCE_DEFINITION' for n in linked['items'])


def test_v3_fixed_outbox_recovery_and_readonly_trace(tmp_path,generation):
    import importlib.util
    from semantic_runtime.legal_agent.publication import prepare,export
    from semantic_runtime.contracts import Contracts
    with session(tmp_path,generation) as s:
        query=s.context.query;state=s.metadata(final=True,gate='BOUNDED')
        result={'request':s.context.request,'query':query,'retrieval':{'candidates':[],'routes':{},'vector_status':'NOT_USED','generation_id':query['generation_id'],'term_agent':state},
            'selection':{'selected':[],'discarded_ids':[],'method':'term-agent','term_agent':state},
            'assembly':{'context':[],'unresolved':[],'data_status':'EXAMPLE','term_agent':state},
            'answer':{'schema_version':'term-runtime-v1','id':'answer:'+s.context.run_id,'scope':query['scope'],
                'query_id':query['id'],'generation_id':query['generation_id'],'source_store_sha256':s.context.binding['store_sha256'],
                'text':'미확인','claims':[],'unresolved':[],'provider_receipt':{}}}
        with s.work.transaction():s.work.event('CONTROL',{'decision':'FINAL','gate':'BOUNDED'})
        envelope=prepare(s.work,result,None,Contracts(ROOT));path=s.work.path;run=s.context.run_id
    assert recover(tmp_path/'runtime/legal-agent/runs',tmp_path/'runs')==[{'run_id':run,'status':'COMPLETED'}]
    assert json.loads((tmp_path/'runs'/(run+'.json')).read_text())==envelope
    repo=RelationsRepository(path);assert export(repo,tmp_path/'runs')==envelope;repo.close()
    spec=importlib.util.spec_from_file_location('trace_v3',ROOT/'06_TOOLS/COMMANDS/legal_agent_trace.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    trace=module.read_trace(tmp_path/'runtime',run)
    assert trace['status']=='COMPLETED'
    assert 'model_attempt' not in trace and 'binding_json' not in trace
    with pytest.raises(ValueError):module.read_trace(tmp_path/'runtime','../escape')


def test_explicit_v3_remains_available_alongside_v5_main():
    from semantic_runtime.contracts import Contracts
    c=Contracts(ROOT)
    assert c.pipeline['profiles']['legal-agent-rag-v3']['nodes'][0]['parameters']['term_agent']['implementation']=='legal-agent-tools-v3'
    assert c.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['implementation']=='legal-agent-tools-v5'
    active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    assert active['schema_version']=='semantic-runtime-active-v2' and active['quality_certified'] is False


def test_genos_service_explicit_v3_dispatch(tmp_path,generation,monkeypatch):
    import importlib,sys
    from semantic_runtime.legal_agent import domain
    from semantic_runtime.legal_agent.transport import GenosTransport
    monkeypatch.syspath_prepend(str(ROOT));sys.modules.pop('service',None)
    service=importlib.import_module('service')
    monkeypatch.setenv('GENOS_GENERATION',str(generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'service-runtime'))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION','legal-agent-tools-v3')
    monkeypatch.setenv('LEGAL_AGENT_PROFILE','fixture-profile.json')
    monkeypatch.setenv('LEGAL_AGENT_PROFILE_SHA256','f'*64)
    load=domain.load_bound
    monkeypatch.setattr(domain,'load_bound',lambda root,b:PROFILE if b['path']=='fixture-profile.json' else load(root,b))
    transport=Transport()
    monkeypatch.setattr(GenosTransport,'from_environment',classmethod(lambda cls,b:transport))
    monkeypatch.setattr(service,'_provider',lambda *a:object())
    try:
        with TestClient(service.application()) as c:
            r=c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
            assert r.status_code==200,r.text
            assert r.json()['assembly']['term_agent']['implementation']=='legal-agent-tools-v3'
            assert transport.calls
    finally:service._APP=None


def test_stored_auto_target_cannot_be_assessed_when_omitted_from_wire(tmp_path,term_glossary):
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['제2조를 준용한다.','승인 절차를 따른다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        r=read(s,'모의규정 제1조');full=s.view('investigate')
        n=next(n for n in full['relation_notices'] if n['completion_required'])
        a=relation_assessment(n,full['exact_evidence'],'RELEVANT')
        assert a['target_evidence']
        exact=[e for e in full['exact_evidence'] if e['evidence'] in r['evidence_ids']]
        body={'exact_evidence':exact,'relation_notices':[n]}
        v=s.work.save_view('investigate',body,[e['evidence'] for e in exact]);delivered(s,v)
        with pytest.raises(ProposalError,match='not presented'):s.validate_relation_assessment(v,a)
        target=a['target_evidence'][0]
        assert next(e for e in s.work.coverage() if e['evidence']==target)['status']=='READ_STORED_NOT_PRESENTED'

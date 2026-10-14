"""Paired native HTTP source-path contracts on synthetic originals."""
import json
import sqlite3
from pathlib import Path
import pytest
from test_investigation_completion_adr0678 import CompletionTransport, decision
from test_unit_fulltext_adaptive_read import tree
from test_unified_legal_agent import ok
from test_memory_runtime_v2 import command
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from semantic_runtime.app import create_app
from fastapi.testclient import TestClient


class CurrentTransport(CompletionTransport):
    def __init__(self):
        super().__init__();self.target='0';self.search_once=False;self.views=[]
    def send_once(self, *, body, ticket):
        v=json.loads(body['messages'][1]['content'])['view']
        phase=v.get('source_stage',v['phase']);self.views.append((phase,v))
        if phase==self.fail:raise RuntimeError('injected current turn failure')
        if phase.startswith('source-law-navigation-'):
            if self.search_once:
                self.search_once=False;self.phases.append(phase)
                target=next(a['id'] for a in v['actions'] if a['action']=='RESEARCH')
                out=decision(v,'RESEARCH',target);out.update(queries=['긴급 승인'],reason='추가 근거 탐색')
                return wire(out)
            if self.target=='exact' and not v['sources']:
                cards=[c for law in v['laws'] for c in law.get('articles',[])]
                card=next(c for c in cards if c.get('read_options'))
                actions=card['read_options']
                # A changed research goal can choose a different final subsection.
                target=next((a['action'] for a in actions if a['extent']=='exact'),None)
                if target:
                    self.target=None
                    self.phases.append(phase)
                    return wire(decision(v,'READ_SCOPE',target))
        return super().send_once(body=body,ticket=ticket)


@pytest.fixture
def core_api(tmp_path,tree):
    gen,idx=tree;t=CurrentTransport()
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'max_transport_retries':0,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True}}
    principal={'user_id':'u','team_id':'t','document_ids':['d'],'authenticated':True}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    active=bool(app.state.pipeline.contracts.pipeline['shortcut_v4']['features'].get('core_evidence_route'))
    runtime=tmp_path/'90_RUNTIME/semantic'
    with TestClient(app) as api:
        n=0
        def send(c=None,**kwargs):
            nonlocal n;n+=1
            if c is not None:t.command=c
            return api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?',
                'session_id':'s','request_id':'r'+str(n),**kwargs})
        yield api,send,t,runtime,active


def event_kinds(runtime,run):
    journal=next((runtime/'legal-agent/runs').glob('*/'+run+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:return [r[0] for r in db.execute('SELECT kind FROM event')]


def core_pages(runtime):
    with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
        return [json.loads(r[0]) for r in db.execute("SELECT k.payload FROM sw_unit u JOIN sw_knowledge k ON k.unit=u.id AND k.revision=u.head WHERE u.id LIKE 'unit:core:%'")]


def test_native_direct_path_and_current_assessment(core_api,record_property):
    api,send,t,runtime,active=core_api
    first=ok(send());second=ok(send(session_id='s2'))
    kinds=event_kinds(runtime,second['run_id'])
    assert second['answer']['claims']
    assert 'memory-assess' in t.phases
    assert ('CORE_EVIDENCE_ROUTE_USED' in kinds)==active
    assert ('LAW_FULLTEXT_DIRECTORY' in kinds)==(not active)
    assert len(core_pages(runtime))==(2 if active else 0)
    record_property('source_path',json.dumps({'core_enabled':active,'direct_path':active,
        'initial_fulltext':not active,'final_sources':len(second['answer']['claims'][0]['source_ids'])}))
    # Repeated HTTP request retains the same publication and unit head.
    again=ok(send(session_id='s2',request_id='r2'))
    assert again==second
    assert len(core_pages(runtime))==(2 if active else 0)


def test_interrupted_followup_retires_then_replaces_current_head(core_api):
    api,send,t,runtime,active=core_api
    first=ok(send());gid=first['question_id']
    t.fail='memory-assess'
    c=command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'변경'}])
    failed=send(c,request_id='retry')
    assert failed.status_code in (502,503),failed.text
    if active:
        from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
        p={'user_id':'u','team_id':'t','document_ids':['d'],'authenticated':True}
        r=ShortcutRepository(runtime/'case-memory/cases-v4.sqlite')
        try:assert r.search(p)['pages']==[]
        finally:r.close()
    t.fail=None
    fixed=ok(send(request_id='retry'))
    assert fixed['revision']>first['revision']
    if active:
        pages=core_pages(runtime);assert len(pages)==1
        assert pages[0]['core_evidence_route']['goal_revision']==fixed['revision']
        with sqlite3.connect(runtime/'case-memory/cases-v4.sqlite') as db:
            assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==2


def test_direct_path_research_falls_back_to_native_fulltext(core_api):
    _,send,t,runtime,active=core_api
    ok(send());t.search_once=True
    second=ok(send(session_id='s2'))
    kinds=event_kinds(runtime,second['run_id'])
    assert 'LAW_FULLTEXT_DIRECTORY' in kinds
    if active:assert 'CORE_EVIDENCE_ROUTE_USED' in kinds
    assert second['answer']['claims']


def test_multiturn_replan_replaces_original_span_roots(core_api):
    _,send,t,runtime,active=core_api
    first=ok(send());gid=first['question_id']
    old=core_pages(runtime)
    t.target='exact'
    changed=ok(send(command('RESEARCH_REPLAN',target=gid,queries=['긴급 승인'])))
    assert changed['question_id']==gid
    assert 'SELECT' in changed['executed']
    if active:
        now=core_pages(runtime)
        assert len(now)==1
        assert now[0]['core_evidence_route']['goal_revision']==changed['revision']
        assert now[0]['core_evidence_route']['targets']!=old[0]['core_evidence_route']['targets']
        old_blocks={s['block_id'] for v in old[0]['core_evidence_route']['targets'] for s in v['spans']}
        new_blocks={s['block_id'] for v in now[0]['core_evidence_route']['targets'] for s in v['spans']}
        assert new_blocks!=old_blocks


def test_legal_wiki_projection_reads_source_route(core_api,tmp_path):
    _,send,t,runtime,active=core_api
    first=ok(send())
    stored=ok(send(command('EXPERIENCE_CONFIRM',target=first['question_id'])))
    assert stored['status']=='STORED'
    if active:
        pointers=list((runtime/'case-memory/wikis/legal_wiki').glob('*/CURRENT.json'))
        assert len(pointers)==1
        pointer=json.loads(pointers[0].read_text())
        value=json.loads((pointers[0].parent/pointer['build']/'index.json').read_text())
        assert 'core-evidence-route-v1' in json.dumps(value)
    else:
        assert list((runtime/'case-memory/wikis').glob('*/legal_wiki/index.json'))

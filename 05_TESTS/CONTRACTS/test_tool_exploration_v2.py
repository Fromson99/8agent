"""Synthetic v2 tool/state/HTTP contracts; no external model or quality scoring."""
import json
import sqlite3
from copy import deepcopy
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.tools_policy import DEFAULT_PROFILE
from semantic_runtime.legal_agent.tools_repository import ToolsRepository
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.publication import recover
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_legal_agent_double_harness import generation, BINDING, ROOT, wire, tool

PROFILE = {**DEFAULT_PROFILE, 'model_binding': BINDING, 'max_model_attempts': 24, 'max_cycles': 4}


def decision(actions=(), assessments=(), intent='CONTINUE', **kw):
    return {'actions': list(actions), 'assessments': list(assessments), 'candidate_decisions': [],
            'route_decisions': [], 'question_updates': [], 'intent': intent, 'reason': '모의 검사', **kw}


class Transport:
    binding = BINDING
    def __init__(self, *, research=False, dispute=False, invalid=False):
        self.calls = []; self.research = research; self.dispute = dispute; self.invalid = invalid
    def validate_model(self): return {'verified': True, 'synthetic': True}
    def send_once(self, *, body, ticket):
        self.calls.append(body)
        v = json.loads(body['messages'][1]['content'])['view']
        phase = v['phase']; results = v.get('last_action_results', [])
        if phase == 'investigate':
            if not results:
                out = decision([tool('locate', locator='모의승인규정 제1조', target=v['corpus_root'], branch='any', cursor=None)])
            elif results[-1]['tool']=='locate':
                target = results[-1]['items'][0]['target']
                out = decision([tool('read', target=target, extent='subtree', cursor=None)])
            elif not any(o['tool']=='read' for o in results):
                raise AssertionError('missing read result')
            elif self.invalid:
                self.invalid = False
                out = decision(assessments=[{'evidence':'P999','summary':'오류','disposition':'ADOPT','role':'SUPPORT','reason':'오류','question_refs':['Q1']}], intent='DRAFT')
            else:
                out = decision(assessments=[{'evidence':e['evidence'],'summary':'모의 규정','disposition':'ADOPT',
                                            'role':'SUPPORT','reason':'질문과 관련','question_refs':['Q1']} for e in v['exact_evidence']], intent='DRAFT')
        elif phase == 'compose':
            out = {'paragraphs':[{'text':'모의 규정에 따르면 승인 요건과 위임 예외를 확인해야 합니다.',
                                  'evidence':v['evidence_roles']['support'], 'question_refs':['Q1'], 'fact_dependencies':[]}], 'limitations':[]}
        elif phase == 'rebuttal':
            out = {'claim':v['claim']['entity_id'], 'evidence':v['claim']['payload']['evidence'],
                   'reason':'원문과 초안이 일치합니다.', 'requested_resolution':'REVIEW_AGAIN'}
        else:
            do_research = self.research; self.research = False
            do_dispute = self.dispute; self.dispute = False
            out = {'checks':[{'claim':c['entity_id'], 'verdict':'NEEDS_RESEARCH' if do_research else 'NEEDS_REWRITE' if do_dispute else 'SUPPORTED',
                              'evidence':c['payload']['evidence'], 'issue':'모의 검토', 'reason':'원문 대조',
                              'actions':[tool('locate', locator='모의승인규정 제2조', target=v['corpus_root'], branch='any', cursor=None)] if do_research else []} for c in v['claims']],
                   'question':{'status':'PARTIAL' if do_research or do_dispute else 'RESOLVED', 'question_refs':['Q1'], 'reason':'질문 직접 대조'}}
        return wire(out)


def app_for(tmp_path, generation, transport=None, profile=None, *, explicit=True):
    return create_app(tmp_path, generation, contracts_root=ROOT, provider=object(),
                      implementation='legal-agent-tools-v2' if explicit else None,
                      legal_agent_profile=profile or PROFILE, legal_agent_transport=transport or Transport())


@contextmanager
def session(tmp_path, generation, profile=None, documents=None):
    app = app_for(tmp_path, generation, profile=profile)
    p = app.state.pipeline
    docs = documents or ['d']
    request = {'question':'승인?', 'document_ids':docs, 'use_llm':True}
    with p.term_agent.open_session(request, query=p.plan('승인?', docs), runtime=tmp_path/'runtime') as s:
        yield s
    p.store.close()


def locate(s, text='모의승인규정 제1조', ident='locate'):
    return s.sources.execute(tool('locate', locator=text, target=s.sources.root, branch='any', cursor=None), ident)['items'][0]['target']


def delivered(s, view):
    a = s.work.reserve_attempt(view, {}, 'test:'+view['view_id'], 1, view['phase'])
    s.work.attempt_sent(a); s.work.finish_attempt(a, 'SUCCEEDED', {}, {'model':BINDING['model']})


@pytest.mark.parametrize('options', [{}, {'research':True}, {'dispute':True}, {'invalid':True}])
def test_main_http_tools_review_publish_and_feedback(tmp_path, generation, options):
    transport = Transport(**options)
    app = app_for(tmp_path, generation, transport, explicit=False)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json={'question':'승인?', 'document_ids':['d']})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['answer']['claims'], result['answer']
        assert result['assembly']['term_agent']['implementation']=='legal-agent-tools-v2'
        assert result['assembly']['term_agent']['final']
        assert client.post('/v1/rag/feedback', json={'run_id':result['run_id'], 'signal':'MISSING_EVIDENCE', 'reason':'모의'}).status_code==200
        assert client.get('/health').json()['rag_mode']=='legal-agent-tools-v2'
        count = len(transport.calls)
        meta = client.post('/v1/rag/ask', json={'question':'문서 목록', 'use_llm':False})
        assert meta.status_code==200, meta.text
        assert not meta.json()['answer']['claims'] and len(transport.calls)==count
    views = [json.loads(b['messages'][1]['content'])['view'] for b in transport.calls]
    assert views[0]['last_action_results']==[]  # no forced catalogue/tree
    assert all(set(v['tool_capabilities']) >= {'browse','search','match_terms','read'} for v in views)
    assert any(v['exact_evidence'] for v in views[1:])
    if options.get('dispute'): assert any(v['phase']=='rebuttal' for v in views)
    path = next(p for p in (tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite') if p.parent.name==result['run_id'])
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==2
        assert db.execute('SELECT status FROM run').fetchone()[0]=='COMPLETED'
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert json.loads((tmp_path/'90_RUNTIME/semantic/runs'/(result['run_id']+'.json')).read_text())==result


def test_read_cursor_coverage_rehydrate_and_duplicate_action(tmp_path, generation):
    with session(tmp_path, generation, {**PROFILE,'max_read_chars':12,'page_size':1}) as s:
        target = locate(s)
        action = tool('read', target=target, extent='subtree', cursor=None)
        result = s.sources.execute(action, 'r1')
        assert result['status']=='PARTIAL' and not result['coverage']['complete']
        budget = s.work.budget()['tool_used']
        assert s.sources.execute(action, 'r1')==result
        assert s.work.budget()['tool_used']==budget
        cursor = result['next_cursor']; n=1
        while cursor:
            n+=1
            result = s.sources.execute(tool('read', target=target, extent='subtree', cursor=cursor), f'r{n}')
            cursor = result['next_cursor']
        assert result['coverage']['complete']
        e = result['evidence_ids'][0]
        hydrated = s.sources.execute(tool('read', target=e, extent='exact', cursor=None), 'rehydrate')
        assert hydrated['status']=='REUSED' and hydrated['items'][0]['text']
        bad = s.sources.execute(tool('browse', target=s.sources.root, relation='self', view='outline', depth=1, cursor='other'), 'bad')
        assert bad['status']=='DENIED'


def test_turn_atomic_unknown_handle_unpresented_evidence_and_last_result(tmp_path, generation):
    with session(tmp_path, generation) as s:
        target = locate(s)
        result = s.sources.execute(tool('read', target=target, extent='subtree', cursor=None), 'read')
        e = result['evidence_ids'][0]
        v=s.view('investigate'); delivered(s,v)
        a={'evidence':e,'summary':'원문','disposition':'ADOPT','role':'SUPPORT','reason':'연관','question_refs':['Q1']}
        bad=decision([tool('read', target='U999',extent='subtree',cursor=None)], [a])
        with pytest.raises(ProposalError): s.apply_turn(v,bad)
        assert not s.work.heads('assessment')
        valid=decision(assessments=[a],intent='DRAFT')
        s.apply_turn(v,valid)
        assert s.apply_turn(v,valid) is False
        v=s.work.save_view('investigate',{'omitted':e},[]); delivered(s,v)
        with pytest.raises(ProposalError,match='not presented'): s.apply_turn(v,valid)


def test_scope_root_recovery_search_and_browse(tmp_path, generation):
    with session(tmp_path, generation) as s:
        target=locate(s)
        d=s.sources.location(target)['document']
        for mode in ('literal','title'):
            r=s.sources.execute(tool('search', query='승인' if mode=='literal' else '정의',target=d,mode=mode,cursor=None),mode)
            assert r['items'] and r['search_receipt']['mode']==mode
        r=s.sources.execute(tool('browse',target=target,relation='document',view='outline',depth=1,cursor=None),'outline')
        assert len(r['items'])==2
        r=s.sources.execute(tool('browse',target=target,relation='root',view='outline',depth=1,cursor=None),'root')
        assert len(r['items'])==1 and r['items'][0]['name']=='모의승인규정'
        r=s.sources.execute(tool('search',query='범위 밖',target=s.sources.root,mode='literal',cursor=None),'empty')
        assert r['status']=='EMPTY' and not r['items']


def test_v1_reader_rejects_v2_and_recovery_interrupts_running(tmp_path,generation):
    with session(tmp_path,generation) as s:
        path=s.work.path
        with pytest.raises(ContractError,match='migration'): WorkRepository(path)
    result=recover(tmp_path/'runtime/legal-agent/runs',tmp_path/'runs')
    assert result[0]['status']=='INTERRUPTED'
    repo=ToolsRepository(path)
    assert repo.run()['status']=='INTERRUPTED'
    repo.close()


def test_registry_schema_is_product_registered():
    from semantic_runtime.contracts import Contracts
    from semantic_runtime.legal_agent.tools_protocol import SCHEMA
    c=Contracts(ROOT)
    assert c.schemas[SCHEMA['$id']]==SCHEMA
    assert c.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['implementation']=='legal-agent-tools-v2'


def test_real_fts_ranking_matches_bound_index_and_does_not_degrade_to_literal(tmp_path,generation,monkeypatch):
    from semantic_runtime.fulltext import build,FulltextIndex,question_terms
    from semantic_runtime.document_agent import ServingDocumentAgent
    build(generation/'navigation',generation/'fulltext',workers=1)
    index=FulltextIndex(generation/'fulltext',json.loads((generation/'navigation/manifest.json').read_text()))
    monkeypatch.setattr(ServingDocumentAgent,'get_fulltext',lambda self:index)
    with session(tmp_path,generation) as s:
        r=s.sources.execute(tool('search',query='승인받는다',target=s.sources.root,mode='fulltext',cursor=None),'fts')
        expected=index.rank(s.sources.matcher.fulltext_db,question_terms('승인받는다'),set(s.sources.sources_in(s.sources.root)))
        assert r['items'] and r['search_receipt']['tokenizer']==index.manifest['tokenizer']
        actual=[s.sources.resolve(c['target'])['source_id'] for c in r['items']]
        assert actual==expected
        literal=s.sources.execute(tool('search',query='승인받는다',target=s.sources.root,mode='literal',cursor=None),'literal')
        assert literal['status']=='EMPTY'


def test_definition_terms_occurrences_reference_and_inspect_handlers(tmp_path,term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    raw=source(tmp_path/'terms.sqlite',[('d','모의규정',['이 규정에서 “영업일”이란 은행이 영업하는 날을 말한다. 제2조에 따른다.','영업일에 신청한다.'])])
    build_generation(raw,term_glossary,tmp_path/'terms',serving=True)
    with session(tmp_path,tmp_path/'terms/generation') as s:
        match=s.sources.execute(tool('match_terms',text='영업일',target=s.sources.root,strategy='auto',cursor=None),'match')
        assert match['items']
        terms=[x['term'] for x in match['items']]
        occ=s.sources.execute(tool('term_occurrences',terms=terms,target=s.sources.root,match='any',cursor=None),'occ')
        assert occ['items'] and all(c['routes'] for c in occ['items'])
        definitions=s.sources.execute(tool('lookup_definition',query='영업일',target=s.sources.root,cursor=None),'def')
        assert definitions['items'] and definitions['definition_kind']=='document'
        target=locate(s,'모의규정 제1조')
        read=s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),'r')
        refs=s.sources.execute(tool('follow_reference',evidence=read['evidence_ids'][0],direction='outgoing',cursor=None),'refs')
        assert refs['items'] and refs['items'][0]['targets']
        for section in ('history','evidence','candidates','questions','challenges','budget'):
            result=s.sources.execute(tool('inspect',section=section,cursor=None),'inspect:'+section)
            assert result['status'] in ('OK','EMPTY')


def test_budget_exhaustion_is_bounded_and_never_auto_adopts(tmp_path,generation):
    settings={**PROFILE,'max_model_attempts':3,'finalization_reserve':3}
    app=app_for(tmp_path,generation,profile=settings)
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert r.status_code==200,r.text
        assert not r.json()['answer']['claims']
        assert r.json()['assembly']['term_agent']['status']=='BOUNDED'


def test_required_challenge_must_be_present_and_addressed(tmp_path,generation):
    with session(tmp_path,generation) as s:
        es=[]
        for n in (1,2):
            u=locate(s,f'모의승인규정 제{n}조',f'l{n}')
            es.extend(s.sources.execute(tool('read',target=u,extent='subtree',cursor=None),f'r{n}')['evidence_ids'])
        v=s.view('investigate');delivered(s,v)
        assessments=[{'evidence':e,'summary':'원문','disposition':'ADOPT' if i==0 else 'REJECT',
                      'role':'SUPPORT' if i==0 else 'CHALLENGE','reason':'적용 검토','question_refs':['Q1']} for i,e in enumerate(es)]
        s.apply_turn(v,decision(assessments=assessments,intent='DRAFT'))
        s.select({'retrieval':s.retrieval()})
        assert es[1] in s.packed['challenge']
        v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
        s.commit_draft(v,{'paragraphs':[{'text':'승인 필요','evidence':[es[0]],'question_refs':['Q1'],'fact_dependencies':[]}],'limitations':[]})
        claims=s.work.heads('claim',current=True)
        v=s.view('review',required=s.packed['evidence_ids']);delivered(s,v)
        review={'checks':[{'claim':claims[0]['entity_id'],'verdict':'SUPPORTED','evidence':[es[0]],'issue':'확인','reason':'확인','actions':[]}],
                'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'확인'}}
        with pytest.raises(ProposalError,match='challenge'):s.commit_review(v,review)
        review['checks'][0]['evidence']=es
        s.commit_review(v,review)


def test_wire_scope_menu_defaults_to_whole_corpus(tmp_path,generation):
    app=app_for(tmp_path,generation)
    with TestClient(app) as c:
        scopes=c.get('/v1/rag/scopes').json()['scopes']
        assert [s['name'] for s in scopes if s['default']]==['전체']
        assert len(app.state.pipeline.plan('승인?')['scope']['document_version_ids'])==2


def test_nested_structure_locate_exact_read_and_reference_extent(tmp_path,term_glossary):
    from test_document_navigation_serving import relation_generation
    g=relation_generation(tmp_path,term_glossary)
    with session(tmp_path,g,documents=['reg','rule']) as s:
        target=locate(s,'코스닥시장 상장규정 시행세칙 제23조제4항')
        assert s.sources.resolve(target)['unit_id']=='204'
        children=s.sources.execute(tool('browse',target=target,relation='self',view='children',depth=1,cursor=None),'children')
        assert {s.sources.resolve(c['target'])['unit_id'] for c in children['items']}=={'2041','2042'}
        outline=s.sources.execute(tool('browse',target=target,relation='document',view='outline',depth=1,cursor=None),'outline')
        assert [s.sources.resolve(c['target'])['unit_id'] for c in outline['items']]==['200']
        exact=s.sources.execute(tool('read',target=target,extent='exact',cursor=None),'exact')
        assert len(exact['evidence_ids'])==1
        assert '종업원' not in exact['items'][0]['text']
        subtree=s.sources.execute(tool('read',target=target,extent='subtree',cursor=None),'subtree')
        text=''.join(i['text'] for i in subtree['items'])
        assert '종업원' in text and '전문투자자' in text and '다른 절차' not in text
        ref=s.sources.execute(tool('follow_reference',evidence=subtree['evidence_ids'][0],direction='outgoing',cursor=None),'ref')
        assert ref['items']
        targets=[t for r in ref['items'] for t in r['targets']]
        assert any(s.sources.resolve(t['target'])['unit_id']=='103' for t in targets)


def test_collection_tree_depth_parent_and_stable_paging(tmp_path,generation):
    with session(tmp_path,generation,{**PROFILE,'page_size':1},documents=['d','other']) as s:
        root=s.sources.root
        first=s.sources.execute(tool('browse',target=root,relation='self',view='tree',depth=2,cursor=None),'tree1')
        rows=first['items'];cursor=first['next_cursor'];n=1
        while cursor:
            n+=1
            page=s.sources.execute(tool('browse',target=root,relation='self',view='tree',depth=2,cursor=cursor),f'tree{n}')
            rows+=page['items'];cursor=page['next_cursor']
        assert [r['depth'] for r in rows]==[1,2,2]
        doc=next(r['target'] for r in rows if r['target'].startswith('D'))
        parent=s.sources.execute(tool('browse',target=doc,relation='parent',view='children',depth=1,cursor=None),'parent')
        assert parent['resolved_location']['focus'].startswith('F')
        assert rows[-1]['breadcrumb'][0]==root


def test_plain_catalogue_does_not_require_or_call_model(tmp_path,generation):
    app=create_app(tmp_path,generation,contracts_root=ROOT,provider=object())
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json={'question':'전체 문서 목록'})
        assert r.status_code==200,r.text
        assert not r.json()['answer']['claims'] and '모의승인규정' in r.json()['answer']['text']
        assert r.json()['answer']['provider_receipt']['physical_attempts']==0


def test_default_genos_service_dispatches_v2_profile_and_http(tmp_path,generation,monkeypatch):
    import importlib,sys
    from semantic_runtime.legal_agent import domain
    from semantic_runtime.legal_agent.transport import GenosTransport
    monkeypatch.syspath_prepend(str(ROOT))
    sys.modules.pop('service',None)
    service=importlib.import_module('service')
    monkeypatch.setenv('GENOS_GENERATION',str(generation))
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'service-runtime'))
    monkeypatch.delenv('GENOS_RAG_IMPLEMENTATION',raising=False)
    monkeypatch.setenv('LEGAL_AGENT_PROFILE','fixture-profile.json')
    monkeypatch.setenv('LEGAL_AGENT_PROFILE_SHA256','f'*64)
    load=domain.load_bound
    monkeypatch.setattr(domain,'load_bound',lambda root,b:PROFILE if b['path']=='fixture-profile.json' else load(root,b))
    transport=Transport()
    monkeypatch.setattr(GenosTransport,'from_environment',classmethod(lambda cls,b:transport))
    monkeypatch.setattr(service,'_provider',lambda *a:object())
    with TestClient(service.application()) as c:
        r=c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert r.status_code==200,r.text
        assert r.json()['assembly']['term_agent']['implementation']=='legal-agent-tools-v2'
        assert transport.calls
    service._APP=None


def test_filtered_metadata_does_not_silently_expand_to_all_documents(tmp_path,generation):
    app=create_app(tmp_path,generation,contracts_root=ROOT,provider=object())
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json={'question':'"존재하지않음" 관련 문서 목록'})
        assert r.status_code==200,r.text
        assert '모의승인규정' not in r.json()['answer']['text']
        assert not r.json()['answer']['claims']


def test_two_concurrent_requests_have_separate_journals(tmp_path,generation):
    from concurrent.futures import ThreadPoolExecutor
    app=app_for(tmp_path,generation)
    with TestClient(app) as c:
        def request(_):return c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(request,range(2)))
        assert all(r.status_code==200 for r in results),[r.text for r in results]
        assert len({r.json()['run_id'] for r in results})==2
    assert len(list((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite')))==2


def test_v2_release_package_contains_policy_manifests_and_journal(tmp_path,generation):
    import shutil
    from semantic_runtime.control import prepare
    from semantic_runtime.contracts import Contracts,sha
    # All authorization/validation values here are synthetic fixtures under tmp_path.
    for rel in ('service.py','06_TOOLS/serve.sh','00_SYSTEM/PIPELINE.json'):
        dest=tmp_path/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
    pointer=tmp_path/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    pointer.parent.mkdir(parents=True,exist_ok=True)
    pointer.write_text(json.dumps({'generation':0,'release_id':'synthetic-bootstrap'}))
    auth=tmp_path/'auth.json';auth.write_text(json.dumps({'quality_gate_override':True,'synthetic':True}))
    validation=tmp_path/'validation.json';validation.write_text(json.dumps({'structural_checks_passed':True,'synthetic':True}))
    manifest=prepare(tmp_path,ROOT,generation,'synthetic-v2',auth,validation)
    release=json.loads(manifest.read_text()); code=tmp_path/release['code_root']
    assert (code/'00_SYSTEM/LEGAL_AGENT/profile-tools-v2.json').is_file()
    assert (code/'02_BACKEND/semantic_runtime/legal_agent/journal-v2.sql').is_file()
    contracts=Contracts(code)
    for entry in contracts.pipeline['engines'].values():
        assert sha(code/entry['manifest'])==entry['sha256']
        for rel,expected in json.loads((code/entry['manifest']).read_text())['files'].items():
            assert sha(code/rel)==expected
    app=create_app(tmp_path/'packaged-run',generation,contracts_root=code,provider=object())
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json={'question':'전체 문서 목록','use_llm':False})
        assert r.status_code==200,r.text

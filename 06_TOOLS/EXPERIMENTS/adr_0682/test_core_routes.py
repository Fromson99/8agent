"""Independent small source/revision contracts; no model-quality inference."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import core_evidence_route as core
from semantic_runtime.legal_agent.corrected_memory import STAGES, MemoryError, encoded, digest
from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases


@pytest.fixture
def routes(tmp_path):
    p = {'user_id': 'u', 'team_id': 't', 'document_ids': ['a', 'b', 'c'], 'authenticated': True}
    raw = {('a','0'): {'text': '모의 탐색 중 제외한 원문 A', 'unit_id': 'a1'},
           ('b','0'): {'text': '모의 핵심 기준 원문 B', 'unit_id': 'b1'},
           ('c','0'): {'text': '모의 필수 예외 원문 C', 'unit_id': 'c1'}}
    store = SimpleNamespace(source=lambda d,b: raw[(d,str(b))])
    executor = SimpleNamespace(pipeline=SimpleNamespace(store=store), binding={'generation': 'g', 'store_sha256': 'h', 'unit_index_sha256': 'i'},
                               model=SimpleNamespace(pipeline=SimpleNamespace(term_agent=SimpleNamespace(transport=SimpleNamespace(binding={'trust_zone': 'internal'})))))
    cases = ShortcutCases(tmp_path/'cases-v4.sqlite', executor, None, flags={'core_evidence_route': True})
    executor.shortcut = cases.shortcut
    intake = cases.shortcut.intake({'question': '모의 기준', 'session_id': 's', 'request_id': 'r', 'document_ids': p['document_ids']}, p)
    investigation = cases.shortcut.connect(intake['id'], p)
    cases.active_case = investigation['id']; cases.original_session = 's'; cases.internal_session = investigation['id']
    cases.identity(cases.internal_session, p)
    source_values = []
    evidence = []
    for did in ('a', 'b', 'c'):
        value = raw[(did,'0')]
        span = {'block_id': '0', 'start_cp': 0, 'end_cp': len(value['text']), 'text': value['text']}
        source_values.append({'source_id': 'src:'+did, 'document_id': did, 'unit_id': did+'root', 'document_name': '모의 '+did,
                              'text': value['text'], 'adopted_spans': [span]})
        evidence.append({'source_id': 'src:'+did, 'spans': [span], 'evidence_id': 'E'+did})
    def accept(goal='g1', selected=('b','c'), revision=1, facts=None, task='모의 기준', ready=True):
        state = {'task': task, 'facts': facts or [], 'document_ids': p['document_ids'], 'source_category': 'all', 'queries': ['모의']}
        existing = cases.db.execute('SELECT 1 FROM goal WHERE id=?', (goal,)).fetchone()
        if existing:
            cases.db.execute('UPDATE goal SET state=?,revision=?,status=?,pending=? WHERE id=?',
                             (encoded(state), revision, 'READY' if ready else 'PENDING', None if ready else 'ASSESS', goal))
        else:
            ordinal = cases.db.execute('SELECT count(*)+1 FROM goal').fetchone()[0]
            cases.db.execute('INSERT INTO goal VALUES(?,?,?,?,?,?,?)', (goal, cases.internal_session, ordinal, encoded(state), revision, 'READY' if ready else 'PENDING', None))
        cases.db.execute("UPDATE route SET status='RETIRED' WHERE goal=?", (goal,))
        nodes = {}
        for stage in STAGES:
            payload = {'stage': stage}
            if stage=='READ': payload={'originals': source_values, 'evidence': evidence}
            if stage=='SELECT': payload={'final_ids': ['src:'+x for x in selected], 'selected_originals': [x for x in source_values if x['document_id'] in selected]}
            cur=cases.db.execute('INSERT INTO node(goal,stage,revision,payload,hash) VALUES(?,?,?,?,?)', (goal, stage, revision, encoded(payload), digest(payload)))
            nodes[stage]=cur.lastrowid
            cases.db.execute('INSERT OR REPLACE INTO head VALUES(?,?,?)', (goal, stage, cur.lastrowid))
        payload={'state': state, 'nodes': nodes, 'judgment_refs': {'SELECT': {'run_id': 'synthetic-run', 'payload_hash': digest(cases.parts(goal)['SELECT']['payload'])}}}
        route=cases.db.execute('INSERT INTO route(goal,revision,status,payload,hash) VALUES(?,?,?,?,?)', (goal, revision, 'ACTIVE', encoded(payload), digest(payload))).lastrowid
        return {'goal_id': goal, 'revision': revision, 'route_id': route, 'status': 'READY'}
    result=accept()
    yield SimpleNamespace(cases=cases, p=p, accept=accept, result=result, raw=raw, host=executor)
    cases.close()


def page(r):
    entries=r.cases.shortcut.search(r.p)['pages']
    assert len(entries)==1
    return entries[0]


def test_backtrace_keeps_b_c_and_drops_exploration_a(routes):
    r=routes;core.finalize(r.cases,r.result,r.p);value=page(r)
    path=value['core_evidence_route']
    assert [t['document_id'] for t in path['targets']]==['b','c']
    assert not any('a'==t['document_id'] for t in path['targets'])
    assert [t['read_unit_ids'] for t in path['targets']]==[['b1'],['c1']]
    assert value['claims']==value['procedures']==[]
    assert path['legal_claim_reuse'] is False


def test_shared_wiki_head_and_idempotent_finalization(routes):
    r=routes;a=core.finalize(r.cases,r.result,r.p);b=core.finalize(r.cases,r.result,r.p)
    assert a==b and page(r)['revision']==1
    assert r.cases.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==1


def test_condition_change_hides_old_path_before_new_answer(routes):
    r=routes;core.finalize(r.cases,r.result,r.p)
    updated=r.accept(selected=('c',),revision=2,facts=[{'name':'유형','value':'변경'}],ready=False)
    assert r.cases.shortcut.search(r.p)['pages']==[]
    assert core.lookup(r.host,json.loads(r.cases.db.execute('SELECT state FROM goal').fetchone()[0]),r.p) is None
    with pytest.raises(MemoryError):core.finalize(r.cases,updated,r.p)
    assert r.cases.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==1


def test_followup_replaces_core_and_preserves_immutable_prior(routes):
    r=routes;core.finalize(r.cases,r.result,r.p);old=deepcopy(page(r))
    next_result=r.accept(selected=('c',),revision=2,facts=[{'name':'유형','value':'변경'}])
    core.finalize(r.cases,next_result,r.p);new=page(r)
    assert new['revision']==2 and new['core_evidence_route']['goal_revision']==2
    assert [t['document_id'] for t in new['core_evidence_route']['targets']]==['c']
    assert json.loads(r.cases.db.execute('SELECT payload FROM sw_knowledge WHERE unit=? AND revision=1',(old['unit_id'],)).fetchone()[0])['core_evidence_route']==old['core_evidence_route']
    with pytest.raises(MemoryError):r.cases.shortcut.current(old['unit_id'],1,r.p)


def test_restore_rederives_restored_core_at_new_revision(routes):
    r=routes;core.finalize(r.cases,r.result,r.p)
    core.finalize(r.cases,r.accept(selected=('c',),revision=2),r.p)
    core.finalize(r.cases,r.accept(selected=('b',),revision=3),r.p)
    new=page(r)
    assert new['revision']==3 and [t['document_id'] for t in new['core_evidence_route']['targets']]==['b']


def test_unpublished_pending_route_has_no_unit(routes):
    r=routes;pending=r.accept(ready=False)
    with pytest.raises(MemoryError):core.finalize(r.cases,pending,r.p)
    assert r.cases.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0


@pytest.mark.parametrize('change',['owner','team','documents'])
def test_scope_narrowing_hides_core(routes,change):
    r=routes;core.finalize(r.cases,r.result,r.p);value=page(r)
    other={**r.p,change if change!='documents' else 'document_ids': 'other' if change!='documents' else ['b']}
    if change=='owner':other={**r.p,'user_id':'other'}
    if change=='team':other={**r.p,'team_id':'other'}
    with pytest.raises(MemoryError):r.cases.shortcut.current(value['unit_id'],1,other)


def test_branch_conditions_are_not_combined(routes):
    r=routes;core.finalize(r.cases,r.result,r.p)
    changed=r.accept(goal='g2',selected=('c',),facts=[{'name':'유형','value':'別'}])
    core.finalize(r.cases,changed,r.p)
    state=json.loads(r.cases.db.execute("SELECT state FROM goal WHERE id='g1'").fetchone()[0])
    path=core.lookup(r.host,state,r.p)
    assert path['goal_id']=='g1' and [t['document_id'] for t in path['targets']]==['b','c']


@pytest.mark.parametrize('binding',['generation','store_sha256','unit_index_sha256'])
def test_changed_source_binding_never_reuses(routes,binding):
    r=routes;core.finalize(r.cases,r.result,r.p);state=json.loads(r.cases.db.execute('SELECT state FROM goal').fetchone()[0])
    r.host.binding[binding]='changed'
    assert core.lookup(r.host,state,r.p) is None


def test_external_scope_does_not_reuse_private_case(routes):
    r=routes;core.finalize(r.cases,r.result,r.p);state=json.loads(r.cases.db.execute('SELECT state FROM goal').fetchone()[0])
    r.host.model.pipeline.term_agent.transport.binding['trust_zone']='external'
    assert core.lookup(r.host,state,r.p) is None


def test_revoked_source_hides_core(routes):
    r=routes;core.finalize(r.cases,r.result,r.p);value=page(r)
    r.cases.shortcut.revoke_source(value['members'][0]['ref'],r.p)
    assert r.cases.shortcut.search(r.p)['pages']==[]


def test_presentation_only_turn_keeps_sources_and_updates_route_head(routes):
    r=routes;core.finalize(r.cases,r.result,r.p)
    second=r.accept(revision=1);core.finalize(r.cases,second,r.p)
    value=page(r)
    assert value['core_evidence_route']['goal_revision']==1 and value['revision']==2
    assert [t['document_id'] for t in value['core_evidence_route']['targets']]==['b','c']


def test_original_corruption_cannot_be_finalized(routes):
    r=routes;r.raw[('b','0')]['text']='바뀐 원문'
    with pytest.raises(MemoryError,match='span'):core.finalize(r.cases,r.result,r.p)
    assert r.cases.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0


def test_shortcut_wiki_off_disables_reuse(routes):
    r=routes;core.finalize(r.cases,r.result,r.p)
    from semantic_runtime.ad_store import SCHEMA
    r.cases.db.executescript(SCHEMA)
    r.cases.db.execute("INSERT INTO ad_feature VALUES('t',1,0,1,'test')")
    state=json.loads(r.cases.db.execute('SELECT state FROM goal').fetchone()[0])
    assert core.lookup(r.host,state,r.p) is None

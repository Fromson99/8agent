import copy
import json
import sqlite3
import time
import pytest
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import MemoryError, Conflict, digest
from semantic_runtime.legal_agent.reuse_policy import condition, evaluate, execute_procedure
from lawrag.pipeline.legal_wiki_compiler import compile_snapshots, run_batch, rebuild
from lawrag.pipeline.shortcut_operations import backup, restore, migrate

P={'user_id':'alice','team_id':'legal','tenant_id':'org','authenticated':True,'document_ids':['law']}
B={'model':'scripted-contract-model','policy_hash':'test','prompt_hash':'test','trust_zone':'internal'}

@pytest.fixture
def repo(tmp_path):
    r=ShortcutRepository(tmp_path/'cases-v4.sqlite')
    yield r
    r.close()

def receive(repo,text='두 쟁점 질문',session='s1',request='r1',principal=P,case=None):
    body={'question':text,'session_id':session,'request_id':request,'document_ids':['law'],'public_question':True}
    i=repo.intake(body,principal);c=repo.connect(i['id'],principal,investigation_id=case)
    return i,c

def source(repo):
    return repo.source(P,{'document_id':'law','document_name':'테스트규정','generation':'g1','coordinate':'art1','text':'공개 모의 규정 본문','version':'1'})

def normalized_proposal(snapshot, *, claims=False, facts=False):
    e=next(e for e in snapshot['events'] if e['kind']=='UTTERANCE_RECEIVED')
    members=[{'unit':'u1','ref':e['id'],'start':0,'stop':len(e['payload']['text']),'role':'CONTEXT','reason':'쟁점 출처'}]
    for s in snapshot['sources']:members.append({'unit':'u1','ref':s['id'],'start':0,'stop':len(s['payload']['text']),'role':'SOURCE','reason':'원문'})
    if facts:
        for f in snapshot['facts']:members.append({'unit':'u1','ref':f['id'],'role':'CONDITION','reason':'판단 전제'})
    return {'units':[{'id':'u1','topic':'주제','question':'자격에 따른 적용','completeness':'BOUNDED' if claims else 'OPEN','unresolved':[] if claims else ['자격 미확인'],'jurisdiction':'KR','applicable_time':'UNKNOWN'}],
        'members':members,'claims':[{'unit':'u1','id':'c1','statement':'자격이 충족되면 적용','condition':{'op':'eq','field':'qualified','value':True},'exceptions_checked':True,
                                     'evidence_refs':[snapshot['sources'][0]['id']],'rationale':'모의 규정','unresolved':[]}] if claims else [],
        'procedures':[],'relations':[],'unassigned_spans':[],'conflicts':[],
        'completeness_checks':[{'unit':'u1','required_facts':claims,'sources':bool(snapshot['sources']),'exceptions':claims,'corrections':True}]}

def proposal(snapshot, *, claims=False, facts=False):
    from lawrag.pipeline.wiki_proposal import offered
    p=normalized_proposal(snapshot,claims=claims,facts=facts)
    segments,_,_=offered([snapshot]);members=[]
    for m in p['members']:
        for key,segment in segments.items():
            if segment['ref']==m['ref']:
                members.append({'unit':m['unit'],'segment_id':key,'role':m['role'],'reason':m['reason']})
    p['members']=members
    for c in p['claims']:
        c['condition'].update(unit=None,args=[])
        c['document_name']=snapshot['sources'][0]['payload']['document_name']
        c['quote']=snapshot['sources'][0]['payload']['text']
    return p

def build(repo,case,*,claims=False,facts=False):
    s=repo.snapshot(case['id'],P)
    b=compile_snapshots(repo,P,[s],model=lambda *_:proposal(s,claims=claims,facts=facts),binding=B,publish=True)
    return b['units'][0]

def test_c01_intake_idempotence_conflict(repo):
    body={'question':'분류 전','session_id':'s','request_id':'r','document_ids':['law']}
    first=repo.intake(body,P)
    assert repo.intake(body,P)==first
    assert repo.db.execute('SELECT count(*) FROM sw_event').fetchone()[0]==1
    with pytest.raises(Conflict):repo.intake({**body,'question':'다른 본문'},P)

def test_c02_unclassified_survives_restart(repo):
    i=repo.intake({'question':'분류가 실패해도 보존','session_id':'s','request_id':'r'},P)
    repo.db.execute("UPDATE sw_intake SET status='FAILED' WHERE id=?",(i['id'],))
    other=ShortcutRepository(repo.path)
    try:assert other.event(i['event'],P)['payload']['text']=='분류가 실패해도 보존'
    finally:other.close()

def test_c03_explicit_cross_session(repo):
    a,case=receive(repo)
    b,again=receive(repo,session='s2',case=case['id'])
    assert again['id']==case['id']
    assert repo.event(a['event'],P)['session']=='s1'
    assert repo.event(b['event'],P)['session']=='s2'

def test_c04_similar_cases_independent(repo):
    a,one=receive(repo)
    b,two=receive(repo,session='s2')
    assert one['id']!=two['id']
    f=repo.fact(one['id'],P,expected_revision=one['revision'],event=a['event'],subject='B',predicate='months',value={'kind':'duration','value':8,'unit':'month'})
    with pytest.raises(MemoryError):repo.fact(two['id'],P,expected_revision=two['revision'],event=b['event'],subject='B',predicate='months',value={'kind':'duration','value':27,'unit':'month'},fact_id=f['id'])

def test_c05_exact_span_multiple_issues(repo):
    i,c=receive(repo,text='자격과 기간')
    one=repo.issue(c['id'],P,'자격');two=repo.issue(c['id'],P,'기간')
    repo.assign(i['event'],one,P,0,2,reason='자격 질문')
    repo.assign(i['event'],two,P,4,6,reason='기간 질문')
    with pytest.raises(MemoryError):repo.assign(i['event'],two,P,0,2)
    with pytest.raises(MemoryError):repo.assign(i['event'],two,P,0,90,reason='불가능')

def test_c06_cas_and_late_results(repo):
    i,c=receive(repo)
    repo.advance(c['id'],P,c['revision'],'CORRECTION',{'text':'8개월'})
    with pytest.raises(Conflict):repo.advance(c['id'],P,c['revision'],'ANSWER',{})

def test_c07_fact_restore_append_only(repo):
    i,c=receive(repo)
    f=repo.fact(c['id'],P,expected_revision=1,event=i['event'],subject='B',predicate='holding',value={'kind':'duration','value':18,'unit':'month'})
    repo.fact(c['id'],P,expected_revision=2,event=i['event'],subject='B',predicate='holding',value={'kind':'duration','value':8,'unit':'month'},fact_id=f['id'])
    r=repo.fact(c['id'],P,expected_revision=3,event=i['event'],subject='B',predicate='holding',value={'kind':'unknown'},fact_id=f['id'],restore_revision=1)
    assert r['revision']==3
    assert json.loads(repo.db.execute('SELECT value FROM sw_fact WHERE id=? AND revision=3',(f['id'],)).fetchone()[0])['value']==18
    with pytest.raises(sqlite3.IntegrityError):repo.db.execute('DELETE FROM sw_fact')

def test_c08_link_retraction_preserves_history(repo):
    i,a=receive(repo);_,b=receive(repo,session='b')
    e=repo.advance(a['id'],P,a['revision'],'LINK_PROPOSED',{})
    rel=repo.relation(a['id'],b['id'],P,kind='SAME_TOPIC',reason='같은 주제',event=e)
    repo.relation(a['id'],b['id'],P,kind='LINK_RETRACTED',reason='연결 정정',event=e,relation_id=rel)
    assert repo.db.execute('SELECT count(*) FROM sw_relation WHERE id=?',(rel,)).fetchone()[0]==2
    assert repo.db.execute('SELECT count(*) FROM sw_investigation').fetchone()[0]==2

def test_c09_compile_race_rejected(repo):
    i,c=receive(repo);s=repo.snapshot(c['id'],P)
    def model(*_):
        repo.advance(c['id'],P,c['revision'],'CORRECTION',{})
        return proposal(s)
    with pytest.raises(Conflict):compile_snapshots(repo,P,[s],model=model,binding=B,publish=True)
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0

def test_c10_current_source_revocation(repo):
    i,c=receive(repo);ref=source(repo);u=build(repo,c,claims=True)
    assert repo.current(u['unit_id'],u['revision'],P)
    repo.revoke_source(ref,P)
    with pytest.raises(MemoryError):repo.current(u['unit_id'],u['revision'],P)
    assert repo.search(P)['pages']==[]

def test_c11_confirmation_not_verification(repo):
    i,c=receive(repo);source(repo);u=build(repo,c,claims=True)
    outcome=evaluate(repo,**{'unit':u['unit_id'],'revision':u['revision']},principal=P,request='r',facts={'qualified':{'kind':'boolean','value':True}},source_check=lambda m:True,flags={'hint':True,'judgment':True})
    assert outcome['mode']=='HINT' and not outcome['adopted_claims']
    repo.verification(u['unit_id'],u['revision'],P,kind='SOURCE',result='FAIL',policy='title-check',verifier='test',evidence=['wrong document name'],expires=time.time()+60)
    assert evaluate(repo,u['unit_id'],u['revision'],P,request='r2',facts={},source_check=lambda m:True,flags={'judgment':True})['mode']=='NONE'

def test_c12_legacy_missing_reason_not_promoted(repo,tmp_path):
    old=tmp_path/'legacy.sqlite'
    with sqlite3.connect(old) as db:
        db.executescript("PRAGMA user_version=3; CREATE TABLE session(id,owner,team); CREATE TABLE goal(id,session,state); CREATE TABLE event(id,goal,utterance); INSERT INTO session VALUES('s','alice','legal');")
        db.execute('INSERT INTO goal VALUES(?,?,?)',('g','s',json.dumps({'task':'이전 기록','document_ids':['law']})))
        db.execute('INSERT INTO event VALUES(?,?,?)',(1,'g','원발언'))
    a=migrate(old,repo.path,kind='v3');b=migrate(old,repo.path,kind='v3')
    assert a==b and a['reuse']=='LEGACY_UNBOUND'
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0

def test_c13_typed_tool_contract(repo):
    from semantic_runtime.legal_agent.reuse_policy import validate_procedure
    catalogue={'read':{'read_only':True,'schema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id'],'additionalProperties':False}}}
    p={'steps':[{'id':'a','tool':'read','contract_hash':digest(catalogue['read']['schema']),'arguments':{'id':{'literal':'law'}},'purpose':'원문','result_check':'exists'}],
       'stop_rules':['missing'],'reentry':'PLAN','preconditions':{'op':'eq','field':'allowed','value':True}}
    calls=[]
    assert execute_procedure(p,inputs={'allowed':{'kind':'boolean','value':True}},catalogue=catalogue,execute=lambda t,a:calls.append(a) or {'ok':True},verify_result=lambda c,r:True,current_check=lambda:True)['status']=='COMPLETE'
    assert len(calls)==1
    for mutation in ({'tool':'delete'},{'contract_hash':'old'},{'after':['a']}):
        bad=copy.deepcopy(p);bad['steps'][0].update(mutation)
        with pytest.raises(MemoryError):validate_procedure(bad,catalogue)

def test_c14_artifact_commit_and_missing_bytes(repo):
    i,c=receive(repo);ref=repo.trace(c['id'],P,kind='TOOL',payload={'tool':'read','status':'FAILED'},documents=['law'])
    row=repo.db.execute('SELECT artifact FROM sw_trace WHERE id=?',(ref,)).fetchone()
    assert json.loads(repo.read_artifact(row[0],P))['status']=='FAILED'
    path=repo.artifacts/repo.db.execute('SELECT relative_path FROM sw_artifact WHERE id=?',(row[0],)).fetchone()[0]
    path.unlink()
    with pytest.raises(OSError):repo.snapshot(c['id'],P)

def test_c15_projection_rebuild_authority(repo,tmp_path):
    _,c=receive(repo);build(repo,c)
    a=rebuild(repo,P,tmp_path/'wikis')
    pointer=next((tmp_path/'wikis').glob('*/CURRENT.json'));directory=pointer.parent/json.loads(pointer.read_text())['build']
    (directory/'index.md').unlink()
    b=rebuild(repo,P,tmp_path/'wikis')
    assert a['hash']==b['hash'] and a['build']!=b['build']

def test_c16_long_history_exact_lookup(repo):
    i,c=receive(repo)
    first=None
    for n in range(120):
        e=repo.advance(c['id'],P,n+1,'NOTE',{'text':str(n)})
        if first is None:first=e
    page=repo.history(c['id'],P,limit=10)
    assert len(page['events'])==10 and page['next']
    assert repo.event(first,P)['payload']['text']=='0'

def test_c17_scope_denial_all_surfaces(repo):
    i,c=receive(repo);source(repo);u=build(repo,c);a=repo.artifact(b'secret',P,documents=['law'])
    for other in ({**P,'user_id':'bob'},{**P,'team_id':'other'},{**P,'tenant_id':'other'},{**P,'document_ids':[]}):
        for read in (lambda:repo.investigation(c['id'],other),lambda:repo.event(i['event'],other),lambda:repo.current(u['unit_id'],u['revision'],other),lambda:repo.read_artifact(a,other)):
            with pytest.raises(MemoryError):read()
    with pytest.raises(MemoryError):repo.cases({**P,'authenticated':False})

def test_c18_backup_restore(repo,tmp_path):
    _,c=receive(repo);repo.trace(c['id'],P,kind='TOOL',payload={'ok':True},documents=['law'])
    m=backup(repo,tmp_path/'backup');result=restore(tmp_path/'backup',tmp_path/'restored')
    assert result['restored']
    other=ShortcutRepository(tmp_path/'restored'/'cases-v4.sqlite')
    try: assert other.snapshot(c['id'],P)['traces']
    finally: other.close()
    (tmp_path/'backup'/'cases-v4.sqlite').write_bytes(b'corrupt')
    with pytest.raises(MemoryError):restore(tmp_path/'backup',tmp_path/'bad-restore')

def test_c19_retry_quarantine_cursor(repo):
    receive(repo)
    for _ in range(3):
        job=repo.lease('wiki');assert job
        repo.finish(job,error='MODEL_UNAVAILABLE')
        repo.db.execute('UPDATE sw_queue SET next_attempt=0')
    assert repo.lease('wiki') is None
    assert repo.status()['queue']['QUARANTINED']==1
    assert repo.status()['cursors']['wiki']==0

def test_c20_missing_model_preserves_records(repo):
    _,c=receive(repo)
    result=run_batch(repo,principal_for_scope=lambda _:P,model=None,binding={},batch_size=1)
    assert result['results'][0]['status']=='FAILED'
    assert repo.snapshot(c['id'],P)['events']
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0

@pytest.mark.parametrize('expr,facts,expected',[
 ({'op':'eq','field':'x','value':True},{},None),
 ({'op':'eq','field':'x','value':True},{'x':{'kind':'number','value':1}},False),
 ({'op':'duration_lt','field':'x','value':24,'unit':'month'},{'x':{'kind':'duration','value':8,'unit':'month'}},True),
 ({'op':'duration_lt','field':'x','value':24,'unit':'month'},{'x':{'kind':'duration','value':27,'unit':'month'}},False),
 ({'op':'duration_lt','field':'x','value':24,'unit':'month'},{'x':{'kind':'duration','value':1,'unit':'year'}},None),
])
def test_unknown_and_typed_conditions(expr,facts,expected):assert condition(expr,facts) is expected

def test_memberless_or_fabricated_reference_rejected(repo):
    _,c=receive(repo);s=repo.snapshot(c['id'],P)
    p=proposal(s);p['members'][0]['segment_id']='unoffered'
    with pytest.raises(MemoryError):compile_snapshots(repo,P,[s],model=lambda *_:p,binding=B,publish=True)
    p=proposal(s);p['members']=[]
    with pytest.raises(MemoryError):compile_snapshots(repo,P,[s],model=lambda *_:p,binding=B,publish=True)

def test_private_input_never_calls_external(repo):
    i=repo.intake({'question':'private','session_id':'private','request_id':'p','document_ids':['law']},P)
    c=repo.connect(i['id'],P);calls=[]
    with pytest.raises(MemoryError):compile_snapshots(repo,P,[repo.snapshot(c['id'],P)],model=lambda *_:calls.append(1),binding={**B,'trust_zone':'external','public_export_authorized':True})
    assert not calls

def test_judgment_requires_exact_sources_and_typed_conditions(repo):
    _,c=receive(repo);source(repo);u=build(repo,c,claims=True)
    for kind in ['SOURCE','INTERPRETATION']:
        repo.verification(u['unit_id'],u['revision'],P,kind=kind,result='PASS',policy='reviewed-interpretation-v1',verifier='contract test only',evidence=['synthetic reviewed evidence'],expires=time.time()+60)
    accepted=evaluate(repo,u['unit_id'],u['revision'],P,request='j',facts={'qualified':{'kind':'boolean','value':True}},source_check=lambda _:True,flags={'judgment':True})
    assert accepted['mode']=='JUDGMENT'
    for facts,check in [({},lambda _:True),({'qualified':{'kind':'boolean','value':False}},lambda _:True),({'qualified':{'kind':'boolean','value':True}},lambda _:False)]:
        denied=evaluate(repo,u['unit_id'],u['revision'],P,request='denied',facts=facts,source_check=check,flags={'judgment':True})
        assert denied['mode']=='NONE'

def test_fact_correction_does_not_stale_source_only_topic(repo):
    i,c=receive(repo);source(repo);u=build(repo,c,claims=True)
    repo.fact(c['id'],P,expected_revision=c['revision'],event=i['event'],subject='B',predicate='holding',value={'kind':'duration','value':8,'unit':'month'})
    assert repo.current(u['unit_id'],u['revision'],P)

def test_fact_dependent_topic_is_stale(repo):
    i,c=receive(repo);source(repo)
    f=repo.fact(c['id'],P,expected_revision=1,event=i['event'],subject='B',predicate='holding',value={'kind':'duration','value':8,'unit':'month'})
    u=build(repo,c,claims=True,facts=True)
    repo.fact(c['id'],P,expected_revision=2,event=i['event'],subject='B',predicate='holding',value={'kind':'duration','value':27,'unit':'month'},fact_id=f['id'])
    with pytest.raises(MemoryError):repo.current(u['unit_id'],u['revision'],P)

def test_server_segments_preserve_offsets_and_unassigned(repo):
    from lawrag.pipeline.wiki_proposal import offered,normalize
    _,c=receive(repo,text='첫 쟁점. 둘째 쟁점. 아직 미배정.')
    snapshot=repo.snapshot(c['id'],P);segments,_,_=offered([snapshot]);selected=next(k for k,v in segments.items() if v['start']==0)
    p={'members':[{'unit':'u1','segment_id':selected,'role':'CONTEXT','reason':'선택'}],'unassigned_spans':[],'procedures':[]}
    value=normalize(p,segments,{})
    assert value['members'][0]['stop']==6
    assert value['unassigned_spans']
    assert all(m['reason']=='MODEL_DID_NOT_ASSIGN' for m in value['unassigned_spans'])

def test_draft_publish_retire_not_judgment(repo):
    _,c=receive(repo);s=repo.snapshot(c['id'],P)
    b=compile_snapshots(repo,P,[s],model=lambda *_:proposal(s),binding=B,publish=False);u=b['units'][0]
    assert not repo.search(P)['pages']
    repo.publish(u['unit_id'],u['revision'],P,expected_head=1)
    assert repo.search(P)['pages']
    repo.retire(u['unit_id'],u['revision'],P,reason='수정 필요',disputed=True)
    assert not repo.search(P)['pages']

def test_worker_scope_cannot_take_other_scope(repo):
    _,c=receive(repo)
    bob={**P,'user_id':'bob'}
    assert repo.lease('wiki',scope=repo.scope(bob)) is None
    assert repo.status()['queue']['PENDING']==1

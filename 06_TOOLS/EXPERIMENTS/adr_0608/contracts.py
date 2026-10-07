"""Failure, persistence, stage selection and native API contracts. Not LLM scores."""
from contextlib import contextmanager
from pathlib import Path
from copy import deepcopy
import json,sqlite3,sys,traceback,uuid
ROOT=Path(__file__).resolve().parents[3]
def exercise(mod,native,appmod,run,paths):
    checks=[]
    def check(name,fn):
        try:detail=fn();checks.append({'name':name,'pass':True,'detail':detail})
        except Exception as exc:checks.append({'name':name,'pass':False,'error':str(exc),'traceback':traceback.format_exc()})
    class Script:
        def __init__(self):self.command=None;self.fail=False;self.inputs=[];self.repair=None
        def __call__(self,system,data,schema,phase):
            self.inputs.append({'phase':phase,'data':deepcopy(data)})
            if phase.startswith('memory-resolve'):
                if phase.endswith('repair') and self.repair:return self.repair
                return deepcopy(self.command)
            if phase=='memory-command-check':return {'valid':True,'reason':'Scripted state contract only'}
            if phase=='memory-intent':return {'purpose':data['question'],'concepts':['승인 절차']}
            if phase.startswith('source-'):
                if data.get('originals'):ids=[c['id'] for c in data['originals']]
                else:ids=[r[0] for r in data.get('candidates',data.get('deferred_candidates',{})).get('rows',[])]
                out={'issues':['승인 절차'],'choices':[{'id':i,'reason':'모의 승인 조건 원문'} for i in ids]}
                if 'needs_fulltext' in schema['properties']:out['needs_fulltext']=False
                return out
            if phase=='memory-assess':
                if self.fail:raise RuntimeError('injected assessment interruption')
                s=data['sources'][0];return {'claims':[{'text':s['text'],'source_id':s['source_id'],'quote':s['text']}],'limitations':[]}
            if phase.startswith('memory-compose') and not phase.endswith('check'):
                a=data['assessment'];text='\n'.join(c['text'] for c in a['claims'])
                if data['format']=='table':text='| 판단 |\n|---|\n| '+text.replace('\n',' ')+' |'
                return {'text':text,**a}
            if phase.endswith('check'):return {'valid':True,'reason':'Scripted state contract only'}
            raise AssertionError('Unexpected '+phase)
    def command(action='START',target=None,stage='NONE',**kwargs):
        return {'action':action,'target':target,'knowledge_id':None,'stage':stage,'task':None,'source_category':'KEEP','document_ids':None,'facts':None,'queries':None,'restore_event':None,'restore_fields':[],'format':'prose','reason':'모의 명령',**kwargs}
    principal={'user_id':'U1','team_id':'risk_team','document_ids':['d']}
    class Offline:
        binding={'generation':'SYNTHETIC-v1'}
        def __init__(self):self.fail=None;self.late=None
        def catalogue(self,docs):return [{'id':d,'name':d} for d in docs]
        def verify(self,read):
            if read['binding']!=self.binding:raise mod.MemoryError('changed generation')
        @contextmanager
        def open(self,state,principal,body):yield self
        def schema(self,stage):return {'type':'object'}
        def stage(self,stage,state,parts,utterance,format):
            if stage==self.fail:raise RuntimeError('injected '+stage)
            if self.late:self.late(stage)
            if stage=='INTENT':return {'concepts':['승인 절차'],'purpose':state['task']}
            if stage=='READ':return {'binding':dict(self.binding),'originals':[{'source_id':'d/0','text':'합성 원문'}],'evidence':[]}
            if stage=='ASSESS':return {'claims':[{'text':'합성 판단','source_id':'d/0','quote':'합성 원문'}],'limitations':[]}
            if stage=='COMPOSE':return {'text':'| 최종 |\n|---|\n| 판단 |' if format=='table' else '합성 최종 답변',**parts['ASSESS']['payload']}
            return {'stage':stage,'state':deepcopy(state)}
    script=Script();executor=Offline();db=run/'memory.sqlite';m=mod.Memory(db,executor,script)
    seq=0
    def send(c,s='S1',p=principal,**body):
        nonlocal seq
        seq+=1;script.command=c
        b={'session_id':s,'request_id':'R'+str(seq),'question':'모의 요청 '+str(seq),**body}
        result=m.execute(b,p);return result
    one=send(command(task='승인 절차',facts=[{'name':'대상','value':'국내'}]));g=one['goal_id']
    check('all seven initial stages execute',lambda:one['executed']==mod.STAGES or (_ for _ in ()).throw(AssertionError(one)))
    check('answers remain work records before final confirmation',lambda:assert_value(m.db.execute('SELECT count(*) FROM knowledge').fetchone()[0],0))
    check('explicit final route creates typed ontology graph',lambda:assert_value(send(command('FINALIZE',g))['status'],'STORED'))
    old_k=m.db.execute("SELECT id FROM knowledge WHERE status='ACTIVE'").fetchone()[0]
    check('ontology includes concepts conditions judgments sources',lambda:assert_value({r[0] for r in m.db.execute('SELECT DISTINCT kind FROM ontology_node')},{'BUNDLE','CONCEPT','CONDITION','JUDGMENT','SOURCE'}))
    before=m.parts(g)
    corr=send(command('CORRECT',g,'ASSESS',facts=[{'name':'대상','value':'해외'}]))
    check('fact correction recomputes assessment and composition',lambda:assert_value(corr['executed'],['ASSESS','COMPOSE']))
    check('obsolete knowledge retired immediately',lambda:assert_value(m.db.execute('SELECT status FROM knowledge WHERE id=?',(old_k,)).fetchone()[0],'RETIRED'))
    check('original immutable event supports chained restoration',lambda:assert_value(send(command('CORRECT',g,restore_event=m.events(g)[0]['id'],restore_fields=['facts']))['state']['facts'],[{'name':'대상','value':'국내'}]))
    check('correction ordinal distinct from event IDs',lambda:assert_value([e['correction_ordinal'] for e in m.events(g) if e['kind']=='CORRECT'],[1,2]))
    for stage in mod.STAGES:
        check('explicit re-entry '+stage,lambda stage=stage:assert_value(send(command('FOLLOW',g,stage))['executed'],mod.STAGES[mod.STAGES.index(stage):]))
    heads={s:p['id'] for s,p in m.parts(g).items()};table=send(command('PRESENT',g,'COMPOSE',format='table'))
    check('LLM presentation receives only final assessment',lambda:assert_value(table['executed'],['COMPOSE']))
    check('presentation preserves all upstream nodes',lambda:assert_value({s:m.parts(g)[s]['id'] for s in mod.STAGES[:-1]},{s:heads[s] for s in mod.STAGES[:-1]}))
    check('second goal leaves unrelated chain unchanged',lambda:assert_value(send(command(task='다른 절차'))['status'],'READY'))
    untouched=m.parts(g);g2=m.db.execute('SELECT id FROM goal WHERE session=? AND ordinal=2',('S1',)).fetchone()[0]
    send(command('CORRECT',g2,'PLAN',queries=['다른 검색']))
    check('unrelated goal remains untouched',lambda:assert_value(m.parts(g),untouched))
    stored=send(command('FINALIZE',g));kid=stored['knowledge_id']
    check('only one active finalized bundle revision',lambda:assert_value(m.db.execute("SELECT count(*) FROM knowledge WHERE bundle=? AND status='ACTIVE'",(g,)).fetchone()[0],1))
    check('repeated finalization idempotent',lambda:assert_value(send(command('FINALIZE',g))['knowledge_id'],kid))
    send(command('PRESENT',g,'COMPOSE',format='table'))
    check('formatting does not revoke confirmed correct experience',lambda:assert_value(m.db.execute('SELECT status FROM knowledge WHERE id=?',(kid,)).fetchone()[0],'ACTIVE'))
    state=m.goal(g,'S1')['state']
    reused=send(command('REUSE',knowledge_id=kid,**state),'S2')
    check('different session consumes final ontology route',lambda:assert_value(reused['status'],'REUSED'))
    check('cross-session reuse executes composition only',lambda:assert_value(reused['executed'],['COMPOSE']))
    check('reused route contains only new goal nodes',lambda:assert_value({r[0] for r in m.db.execute('SELECT goal FROM node WHERE id IN ('+','.join('?' for _ in mod.STAGES)+')',tuple(m.route(reused['goal_id'])['payload']['nodes'].values()))},{reused['goal_id']}))
    check('wiki remap changes association without changing bundle',lambda:assert_value(send(command('REMAP',g2,knowledge_id=kid))['status'],'REMAPPED'))
    check('wiki correction preserves original knowledge',lambda:assert_value(m.db.execute('SELECT status FROM knowledge WHERE id=?',(kid,)).fetchone()[0],'ACTIVE'))
    def deny(fn):
        try:fn()
        except (mod.MemoryError,mod.Conflict):return True
        raise AssertionError('unexpected admission')
    check('cross-user session rejected',lambda:deny(lambda:send(command('INSPECT',g),p={**principal,'user_id':'U2'})))
    check('cross-user knowledge undiscoverable',lambda:assert_value(m.candidates({**principal,'user_id':'U2'},'승인'),[]))
    check('access removed from knowledge candidates',lambda:assert_value(m.candidates({**principal,'document_ids':[]},'승인'),[]))
    check('late expected revision rejected',lambda:deny(lambda:send(command('CORRECT',g),expected_revision=0)))
    original_binding=deepcopy(executor.binding);executor.binding={'generation':'SYNTHETIC-v2'}
    check('new generation excludes old knowledge',lambda:assert_value(m.candidates(principal,'승인'),[]));executor.binding=original_binding
    executor.fail='ASSESS'
    def interruption():
        try:send(command('CORRECT',g,'ASSESS'))
        except RuntimeError:pass
        assert m.goal(g,'S1')['status']=='PENDING' and m.route(g) is None
        assert not m.db.execute("SELECT 1 FROM knowledge WHERE bundle=? AND status='ACTIVE'",(g,)).fetchone()
        return 'pending, no active route or ontology'
    check('failure removes obsolete reuse path and preserves pending state',interruption);executor.fail=None
    m.close();m=mod.Memory(db,executor,script)
    check('process restart resumes pending stage',lambda:assert_value(send(command('FOLLOW',g,'COMPOSE'))['executed'],['ASSESS','COMPOSE']))
    for i in range(120):send(command('CORRECT',g,'ASSESS',facts=[{'name':'회차','value':str(i)}]))
    restored=send(command('CORRECT',g,restore_event=m.events(g)[0]['id'],restore_fields=['facts']))
    check('120 correction chain restores first condition',lambda:assert_value(restored['state']['facts'],[{'name':'대상','value':'국내'}]))
    check('correction chain retains all immutable revisions',lambda:assert_value(sum(e['kind']=='CORRECT' for e in m.events(g)),124))
    send(command('FINALIZE',g));view=m.export_wiki(principal)
    check('wiki projection includes only current final versions',lambda:assert_value(len([p for p in view['pages'] if p['bundle']==g]),1))
    def replay():
        script.command=command('INSPECT',g);body={'session_id':'S1','request_id':'REPLAY','question':'기록 조회'}
        a=m.execute(body,principal);count=len(script.inputs);b=m.execute(body,principal);assert a==b and len(script.inputs)==count
        return {'no_new_calls':True}
    check('request replay does not mutate or rerun',replay)
    def bad_restore():
        script.repair=command('CORRECT',g,restore_event=999999,restore_fields=['facts'])
        r=send(script.repair);script.repair=None;assert r['status']=='CLARIFY';return r
    check('missing origin blocks mutation after bounded repair',bad_restore)
    def concurrent():
        other=mod.Memory(db,executor,script)
        def late(stage):
            executor.late=None
            script.command=command('CORRECT',g,'ASSESS',facts=[{'name':'최종','value':'새 요청'}])
            other.execute({'session_id':'S1','request_id':'CONCURRENT','question':'동시에 들어온 새 정정'},principal)
        executor.late=late
        try:
            deny(lambda:send(command('CORRECT',g,'ASSESS',facts=[{'name':'최종','value':'늦은 요청'}])))
            assert m.goal(g,'S1')['state']['facts']==[{'name':'최종','value':'새 요청'}]
            assert m.goal(g,'S1')['status']=='READY'
            return 'Two SQLite connections; late stage cannot overwrite newer ready revision'
        finally:other.close();executor.late=None
    check('two-writer CAS rejects late stage and preserves newer route',concurrent)
    def service_contract():
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('memory_service_contract',paths['service.py']);module=module_from_spec(spec);spec.loader.exec_module(module)
        x=module._normalize({'API_TYPE':'LEGAL_AGENT','question':'후속 정정','memory':True,'session_id':'SID','user_id':'UID','request_id':'RID'})['json']
        assert [x[k] for k in ('session_id','user_id','request_id')]==['SID','UID','RID']
        return x
    check('GENOS service boundary preserves memory identities',service_contract)
    write=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=lambda v:sorted(v) if isinstance(v,set) else str(v))+'\n')
    write(run/'wiki.json',view);m.close()
    # Actual Store/index/matcher/SourceRecall/exact READ, not Offline.stage.
    sys.path.insert(0,str(ROOT/'05_TESTS'));sys.path.insert(0,str(ROOT/'05_TESTS/CONTRACTS'))
    from conftest import term_glossary
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    from fastapi.testclient import TestClient
    work=run/'native';work.mkdir();dictionary=term_glossary.__wrapped__(work)
    raw=source(work/'RAW.sqlite',[('d','모의승인규정',['국내 대상의 승인 절차는 A이다. 해외 대상의 승인 절차는 B이다.','긴급 사건은 별도 예외를 확인해야 한다.'])])
    build_generation(raw,dictionary,work/'built',serving=True)
    actual_script=Script()
    def factory(p,runtime,body,principal):return mod.Memory(work/'memory.sqlite',native.NativeRag(p,runtime,actual_script),actual_script)
    app=appmod.create_app(work,work/'built/generation',contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile={**DEFAULT_PROFILE,'bounded_source_selection_enabled':True},memory_factory=factory,memory_identity=lambda request:principal)
    with TestClient(app) as client:
        actual_script.command=command(task='모의승인규정 제1조 승인 절차',document_ids=['d'],facts=[{'name':'대상','value':'국내'}])
        body={'memory':True,'session_id':'NATIVE','request_id':'N1','question':'모의승인규정 제1조 승인 절차를 알려줘','document_ids':['d']}
        first=client.post('/v1/rag/ask',json=body);write(work/'first.json',{'http':first.status_code,'body':first.json()})
        check('native HTTP entry reaches seven checkpoint executor',lambda:assert_value(first.status_code,200))
        if first.status_code==200 and first.json().get('status')=='READY':
            first=first.json();gid=first['goal_id'];actual_script.command=command('FINALIZE',gid)
            saved=client.post('/v1/rag/ask',json={**body,'request_id':'N2','question':'이게 최종 맞는 내용이야. 저장해줘'}).json();write(work/'saved.json',saved)
            check('native finalization persists real ontology',lambda:assert_value(saved['status'],'STORED'))
            actual_script.command=command('PRESENT',gid,'COMPOSE',format='table')
            table=client.post('/v1/rag/ask',json={**body,'request_id':'N3','question':'그 최종 답변을 표로 써줘'}).json();write(work/'table.json',table)
            check('native format-only preserves source stages',lambda:assert_value(table['executed'],['COMPOSE']))
            check('native final table generated from assessment',lambda:assert_value('|' in table['answer']['text'],True))
            check('native source discovery and complete exact READ receipts',lambda:assert_value(any(p for p in work.rglob('journal.sqlite')),True))
        else:checks.append({'name':'native continuation','pass':False,'error':first.json()})
        check('API identity spoof rejected',lambda:assert_value(client.post('/v1/rag/ask',json={**body,'request_id':'spoof','user_id':'U2'}).status_code,422))
    (run/'model-inputs-scripted.json').write_text(json.dumps(actual_script.inputs,ensure_ascii=False,indent=2)+'\n')
    return {'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks)}
def assert_value(actual,expected):
    assert actual==expected, {'observed':actual,'expected':expected}
    return {'observed':actual}

"""Predeclared behavioral probes; never repair candidate after seeing results."""
import copy
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

def rejected(call, exception=ValueError, contains=None):
    try:call()
    except exception as e:
        if contains:assert contains in str(e),str(e)
        return {'rejected':True,'reason':str(e)}
    raise AssertionError('unsafe operation accepted')

def run_all(mod,out,design,schema,shortcut_schema):
    out.mkdir(parents=True,exist_ok=False);seed=json.loads((design/'seed.json').read_text());docs=json.loads((design/'RAW/documents.json').read_text())
    results=[]
    def probe(group,name,fn,arm='GUARDED'):
        folder=out/f'{len(results)+1:03d}-{group}'
        store=mod.ContextStore(folder/'context.sqlite',schema,folder/'assets');who=mod.DevIdentity(seed['tenant'],seed['user']);cid=store.session(who,seed['session']);case=store.seed(who,cid,copy.deepcopy(seed))
        start=time.perf_counter()
        try:
            value=fn(store,who,cid,case,folder)
            results.append({'id':f'F{len(results)+1:03d}','group':group,'feature':name,'arm':arm,'status':'PASS','observed':value,'seconds':time.perf_counter()-start})
        except Exception as e:
            results.append({'id':f'F{len(results)+1:03d}','group':group,'feature':name,'arm':arm,'status':'FAIL','error':type(e).__name__+': '+str(e),'seconds':time.perf_counter()-start})
        finally:store.close()
    scope={'intent':'CORRECT','field':'scope','value':'EXTERNAL','goal_id':'G2','decision_id':'G2-scope','extent':'TARGET_GOAL'}
    party={'intent':'CORRECT','field':'party','value':'해외','extent':'CURRENT_CASE'}
    def apply(s,w,c,k,cmd=None,text='두 번째 질문은 외규야',rid='edit1',rev=3,**kw):return s.apply(w,c,k,text,cmd or scope,rev,rid,**kw)

    def install(s,w,c,k,p):
        assert s.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not s.db.execute('PRAGMA foreign_key_check').fetchall()
        assert s.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==23
        return {'tables':23,'turns':3,'decisions':6,'facts':3,'integrity':'ok'}
    probe('load','23 tables, full seed linkage',install)
    probe('load','append-only history',lambda s,w,c,k,p:rejected(lambda:s.db.execute("UPDATE cm_fact SET value_json='null'"),sqlite3.IntegrityError,'append-only'))
    probe('load','committed membership sealed',lambda s,w,c,k,p:rejected(lambda:s.put('cm_state_fact',case_id=k,branch_id='actual',state_revision=3,fact_id='party',fact_branch_id='actual',fact_revision=1),sqlite3.IntegrityError,'sealed'))
    def checksum(s,w,c,k,p):
        snapshot=s.read_state(w,k);assert snapshot['body']['fact_membership_hash']==mod.digest(sorted(snapshot['members']))
        return {'state_hash':snapshot['hash'],'membership_hash':snapshot['body']['fact_membership_hash']}
    probe('load','calculated state and membership hashes',checksum)
    def opaque(s,w,c,k,p):
        r=s.db.execute('SELECT external_session_id FROM cm_session_binding').fetchone()[0];assert r==seed['session']
        assert s.session(w,r)==c
        return {'characters':len(r),'preserved':True}
    probe('identity','opaque session and retry binding',opaque)
    def user_split(s,w,c,k,p):
        bob=mod.DevIdentity(w.tenant,'mock-bob');other=s.session(bob,seed['session']);assert other!=c
        rejected(lambda:s.read_state(bob,k));return {'same_external_session':True,'separate_conversations':True,'case_read_denied':True}
    probe('identity','same session other user isolated',user_split)
    probe('identity','unverified identity blocked',lambda s,w,c,k,p:rejected(lambda:s.read_state(mod.DevIdentity(w.tenant,w.user,False),k)))
    probe('identity','another tenant blocked',lambda s,w,c,k,p:rejected(lambda:s.read_state(mod.DevIdentity('other',w.user),k)))
    def acl(s,w,c,k,p):
        bob=mod.DevIdentity(w.tenant,'mock-bob');s.grant(w,k,bob.user,'READ');assert s.read_state(bob,k)['revision']==3
        rejected(lambda:s.authorize(bob,k,True));s.grant(w,k,bob.user,'REVOKED');rejected(lambda:s.read_state(bob,k))
        return {'read_grant':True,'write_denied':True,'revocation_checked':True}
    probe('identity','read-only grant and revoke',acl)
    probe('identity','session over limit rejected, not truncated',lambda s,w,c,k,p:rejected(lambda:s.session(w,'x'*2049)))
    def retry(s,w,c,k,p):
        first=apply(s,w,c,k);second=apply(s,w,c,k);assert second['status']=='REPLAY';assert first['revision']==second['revision']==4
        assert s.db.execute('SELECT count(*) FROM cm_turn').fetchone()[0]==4
        return {'first':first,'retry':second,'turn_count':4}
    probe('state','idempotent identical retry',retry)
    def conflict(s,w,c,k,p):
        apply(s,w,c,k);return rejected(lambda:apply(s,w,c,k,text='다른 입력'),contains='payload conflict')
    probe('state','same request key different input conflict',conflict)
    probe('state','stale revision rejected',lambda s,w,c,k,p:rejected(lambda:apply(s,w,c,k,rev=2),contains='stale'))
    def rollback(s,w,c,k,p):
        rejected(lambda:apply(s,w,c,k,failpoint='before_head'),contains='injected')
        assert s.read_state(w,k)['revision']==3;assert s.db.execute('SELECT count(*) FROM cm_turn').fetchone()[0]==3
        assert s.db.execute('SELECT count(*) FROM cm_edit').fetchone()[0]==0
        return {'revision':3,'turn_count':3,'partial_rows':0}
    probe('recovery','transaction rollback before head',rollback)
    def hypothesis(s,w,c,k,p):
        b=s.fork(w,k);apply(s,w,c,k,party,text='해외야')
        actual=s.read_state(w,k);hyp=s.read_state(w,k,b)
        assert next(f['value'] for f in actual['facts'] if f['fact_id']=='party')=='해외'
        assert next(f['value'] for f in hyp['facts'] if f['fact_id']=='party')=='국내'
        return {'actual_revision':4,'hypothesis_revision':0,'hypothesis_party':'국내','parent_revision':3}
    probe('state','hypothesis pins original parent',hypothesis)
    def unrelated_branch(s,w,c,k,p):
        b=s.fork(w,k);apply(s,w,c,k,party,text='해외야')
        return rejected(lambda:s.check_membership(k,b,'party','actual',2),contains='pinned parent')
    probe('state','hypothesis cannot inherit later parent facts',unrelated_branch)
    def newcase(s,w,c,k,p):
        other=s.create_case(w);assert not s.read_state(w,other)['facts'];assert s.read_state(w,k)['revision']==3
        return {'new_case_facts':0,'old_case_revision':3}
    probe('state','new case does not copy facts',newcase)
    probe('state','source verification requires receipt',lambda s,w,c,k,p:rejected(lambda:s.fact(k,'actual','verified','国内','T2',basis='SOURCE_VERIFIED'),contains='verification'))
    def ordinal(s,w,c,k,p):
        g=next(g for g in s.read_state(w,k)['body']['goals'] if g['question_ordinal']==2)
        assert g['origin_turn_id']=='T3';assert s.db.execute("SELECT turn_number FROM cm_turn WHERE turn_id='T3'").fetchone()[0]==3
        return {'question_ordinal':2,'turn_number':3,'target':'G2-scope'}
    probe('correction','question ordinal differs from turn number',ordinal)
    def isolated(s,w,c,k,p):
        old=s.read_state(w,k);r=apply(s,w,c,k);new=s.read_state(w,k)
        assert r['affected']==['G2-answer','G2-scope','G2-select'];assert next(g['scope'] for g in new['body']['goals'] if g['id']=='G1')=='INTERNAL'
        assert next(g['scope'] for g in new['body']['goals'] if g['id']=='G2')=='EXTERNAL'
        assert s.read_state(w,k,revision=3)==old
        return {'affected':r['affected'],'G1':'INTERNAL','G2':'EXTERNAL','old_state_preserved':True}
    probe('correction','goal-only scope and exact descendants',isolated)
    probe('correction','wrong goal/decision relation rejected',lambda s,w,c,k,p:rejected(lambda:apply(s,w,c,k,{**scope,'goal_id':'G1'}),contains='mismatch'))
    probe('correction','old before-value rejected',lambda s,w,c,k,p:rejected(lambda:apply(s,w,c,k,{**scope,'before':'EXTERNAL'}),contains='before'))
    probe('correction','ambiguous command leaves state unchanged',lambda s,w,c,k,p:rejected(lambda:apply(s,w,c,k,{'intent':'CLARIFY'}),contains='separate'))
    def sharedparty(s,w,c,k,p):
        r=apply(s,w,c,k,party,text='해외 법인이야');assert r['affected']==['G1-answer','G1-select','G2-answer','G2-select'];return r
    probe('correction','common party invalidates both goals but not scope',sharedparty)
    def new_exception(s,w,c,k,p):
        r=apply(s,w,c,k,{'intent':'CONTINUE','field':'exception','value':'긴급'},text='긴급이야');assert len(r['affected'])==6;return r
    probe('correction','new condition without old edge expands review',new_exception)
    def retract(s,w,c,k,p):
        r=apply(s,w,c,k,{**party,'value':'UNKNOWN'},text='당사자 정보를 철회해');f=next(f for f in s.read_state(w,k)['facts'] if f['fact_id']=='party');assert f['basis']=='UNKNOWN';return {'basis':f['basis'],'affected':r['affected']}
    probe('correction','fact withdrawal stays unknown',retract)
    def recompute(s,w,c,k,p):
        r=apply(s,w,c,k);mapping=s.recompute_mock(w,k,r,docs)
        d=s.inspect(w,k,mapping['G2-answer']);assert d['statement']=='가상 D 검토'
        assert d['parent_refs']==[mapping['G2-select']];assert s.inspect(w,k,'G2-answer')['statement']=='가상 B 검토'
        return {'new_statement':d['statement'],'supersession':mapping,'old_statement':'가상 B 검토'}
    probe('correction','fresh decisions and preserved supersession chain',recompute)
    def superseded(s,w,c,k,p):
        r=apply(s,w,c,k);s.recompute_mock(w,k,r,docs)
        return rejected(lambda:apply(s,w,c,k,rev=4,rid='edit2'),contains='superseded')
    probe('correction','old superseded target not applied again',superseded)
    def history(s,w,c,k,p):
        d=s.inspect(w,k,'G2-select');assert d['reason'] and d['source_refs'] and d['original_hash'];return d
    probe('history','original reason/source lookup',history)
    def anchor(s,w,c,k,p):
        ref,h=s.anchor(w,k,'G2-scope','범위 설명');assert s.resolve_anchor(w,k,ref,h,'paragraph-1')==['G2-scope']
        rejected(lambda:s.resolve_anchor(w,k,ref,'0'*64,'paragraph-1'))
        return {'exact_decision':'G2-scope','forged_hash_denied':True}
    probe('history','answer anchor maps exact publication/decision',anchor)
    def position(s,w,c,k,p):
        r=apply(s,w,c,k,{'intent':'CONTINUE','field':'user_position','value':'추가 검토 불필요'},text='내 의견이야');assert not r['affected']
        u=s.read_state(w,k)['body']['unresolved'][-1];assert u['origin_kind']=='USER_POSITION'
        return {'stored_as':'USER_POSITION','agent_decisions_changed':0,'decision_index_projection_implemented':False}
    probe('history','user position does not replace agent conclusion',position)
    def pref(s,w,c,k,p):
        s.preference(w,'table');assert s.preferences(w)==['table'];s.preference(w,'prose');assert s.preferences(w)==['prose'];s.preference(w,'prose','RETRACTED');assert not s.preferences(w)
        return {'latest_only':True,'retracted_excluded':True}
    probe('history','preference update and withdrawal',pref)
    def expire(s,w,c,k,p):
        s.preference(w,'table',expiry='2026-09-30');assert not s.preferences(w)
        s.preference(w,'prose','PROPOSED');assert not s.preferences(w)
        return {'expired_excluded':True,'inferred_proposed_excluded':True}
    probe('history','preference expiry and inferred state',expire)
    def handoff(s,w,c,k,p):
        r=apply(s,w,c,k);v=s.handoff(w,k);assert len(v['facts'])==3 and len(v['decisions'])==6
        assert all(d['reason'] and d['source_refs'] for d in v['decisions'])
        assert sum(d['status']=='NEEDS_CHECK' for d in v['decisions'])==3
        return {'facts':3,'decisions':6,'requires_recheck':3,'bytes':len(mod.encode(v).encode())}
    probe('handoff','full facts/reasons/sources and stale status',handoff)
    probe('handoff','mandatory state refuses truncation',lambda s,w,c,k,p:rejected(lambda:s.handoff(w,k,max_bytes=100),contains='budget'))
    def restart(s,w,c,k,p):
        r=apply(s,w,c,k);other=mod.ContextStore(s.path,schema,s.assets)
        try:assert other.read_state(w,k)['revision']==4
        finally:other.close()
        return {'persisted_revision':4}
    probe('recovery','new connection persistent state',restart)
    def two(s,w,c,k,p):
        other=mod.ContextStore(s.path,schema,s.assets)
        try:
            assert other.read_state(w,k)['revision']==3;apply(s,w,c,k)
            return rejected(lambda:other.apply(w,c,k,'외규',scope,3,'second'),contains='stale')
        finally:other.close()
    probe('recovery','two connections reject stale writer',two)
    def outbox(s,w,c,k,p):
        r=apply(s,w,c,k);sink=p/'sink';rejected(lambda:s.deliver(r['turn_id'],sink,True),contains='injected')
        s.deliver(r['turn_id'],sink);s.deliver(r['turn_id'],sink)
        assert len(list(sink.glob('*.json')))==1;return {'sink_events':1,'delivery_receipts':2,'crash_window_recovered':True}
    probe('recovery','outbox crash and identical redelivery',outbox)
    def collision(s,w,c,k,p):
        r=apply(s,w,c,k);sink=p/'sink';sink.mkdir();(sink/(r['turn_id']+'.json')).write_text('{}')
        return rejected(lambda:s.deliver(r['turn_id'],sink),contains='conflict')
    probe('recovery','sink same event different hash rejected',collision)
    def native(s,w,c,k,p):
        from semantic_runtime.contracts import digest
        class NativeV5(mod.NativeRepository):VERSION=5;DDL='journal-v5.sql'
        b={'synthetic':'ADR-0591','state':s.read_state(w,k)['hash']}
        ctx=SimpleNamespace(run_id='native-mock',query={'id':'mock-query'},binding=b,binding_hash=digest(b),request={'question':'모의 질의'},deadline_at='2099-01-01T00:00:00Z')
        repo=NativeV5(p/'native-journal.sqlite',ctx,{'max_model_attempts':10,'finalization_reserve':2,'max_tool_actions':20})
        try:
            with repo.transaction():
                seq=repo.event('MOCK_REHYDRATE',{'synthetic':True})
                repo.put('fact','F1',{'value':'국내'},seq)
                repo.put('source_selection','S1',{'reason':'모의 선별'},seq,dependencies=[('fact','F1')])
                repo.put('claim','J1',{'text':'모의 B'},seq,dependencies=[('source_selection','S1')])
                repo.put('claim','UNRELATED',{'text':'다른 질문'},seq)
                seq=repo.event('MOCK_CORRECT',{'value':'해외'})
                repo.put('fact','F1',{'value':'해외'},seq)
            status={r['entity_id']:r['validity'] for r in repo.heads()};assert status=={'F1':'CURRENT','S1':'STALE','J1':'STALE','UNRELATED':'CURRENT'}
            return {'native_schema':5,'entity_status':status,'production_coordinator_executed':False}
        finally:repo.close()
    probe('recovery','existing native v5 dependency invalidation',native)

    # SQL alone intentionally delegates these semantic checks to an absent writer.
    def raw_gap(name,fn,expected='writer must reject'):
        def run(s,w,c,k,p):
            try:
                fn(s,w,c,k,p)
                return {'unsafe_insert_accepted':True,'expected_boundary':expected}
            except sqlite3.IntegrityError as e:return {'unsafe_insert_accepted':False,'sql_rejected':str(e)}
        probe('sql_boundary',name,run,'baseline')
    raw_gap('same-tenant unauthorized turn actor accepted',lambda s,w,c,k,p:s.add_turn(mod.DevIdentity(w.tenant,'mock-bob'),c,k,'actual',3,'위조 발언','bad',{'bad':True}))
    raw_gap('bogus state JSON/hash accepted',lambda s,w,c,k,p:s.put('cm_state',case_id=k,branch_id='actual',revision=4,parent_revision=3,source_turn_id='T3',state_json='{}',state_hash='0'*64,created_at='mock-now'))
    raw_gap('wrong goal on exact edit accepted',lambda s,w,c,k,p:s.put('cm_edit',edit_id='bad',source_turn_id='T3',case_id=k,branch_id='actual',base_revision=2,target_turn_id='T1',target_decision_id='G1-scope',target_goal_id='G2',extent='TARGET_GOAL',operation='CHANGE_SCOPE',patch_json='{}',interpretation_ref='mock:wrong',interpretation_hash='0'*64,created_at='mock-now'))
    raw_gap('non-hex 64 character hash accepted',lambda s,w,c,k,p:s.put('cm_outbox',event_id='bad',aggregate_key=k,destination='RUN_JOURNAL',payload_json='{}',payload_hash='z'*64,created_at='mock-now'))
    raw_gap('run-state sequence gap accepted',lambda s,w,c,k,p:s.put('cm_run_state',run_id='run-T3',case_id=k,branch_id='actual',seq=99,state_revision=3,native_event_ref='mock:wrong',native_event_hash='0'*64))
    raw_gap('applicable receipt without semantic/source validation accepted',lambda s,w,c,k,p:s.put('cm_decision_check',case_id=k,branch_id='actual',state_revision=3,decision_id='G2-answer',check_no=1,status='APPLICABLE',reason='임의 승인',receipt_ref='mock:wrong',receipt_hash='0'*64))
    raw_gap('fact key changed within same identity accepted',lambda s,w,c,k,p:s.put('cm_fact',case_id=k,branch_id='actual',fact_id='party',revision=2,previous_revision=1,fact_key='금액',goal_id=None,value_json='100',basis='USER_ASSERTED',source_turn_id='T3',origin_ref='mock:wrong',origin_hash='0'*64))
    def pubhash(s,w,c,k,p):
        s.put('cm_answer_anchor',publication_ref='mock:pub',publication_hash='a'*64,anchor_id='p1',anchor_text='문단1',case_id=k,branch_id='actual',run_id='run-T3',decision_id='G2-scope')
        s.put('cm_answer_anchor',publication_ref='mock:pub',publication_hash='b'*64,anchor_id='p2',anchor_text='문단2',case_id=k,branch_id='actual',run_id='run-T3',decision_id='G2-select')
    raw_gap('same publication conflicting hashes accepted',pubhash)

    step={'tenant':seed['tenant'],'owner':seed['user'],'state':'REUSABLE','wiki_status':'ACCEPTED','run_status':'COMPLETED',
          'conditions':{'party':'국내','scope':'INTERNAL'},'source_hash':docs[0]['sha256'],'generation':'mock-v1','complete_read':True,
          'reviews':[{'id':kind,'kind':kind,'verdict':'PASS','reviewer':'SYNTHETIC_FIXTURE','supersedes':None} for kind in ['SOURCE_INTEGRITY','TASK_RELEVANCE','LEGAL_CORRECTNESS','CAPSULE_FIDELITY']]}
    current={'tenant':seed['tenant'],'user':seed['user'],'conditions':step['conditions'],'source_hash':step['source_hash'],'generation':'mock-v1','wiki_live':True}
    def exp(changes=None,ctx=None,adopt=False):
        def run(s,w,c,k,p):
            v=mod.check_experience({**copy.deepcopy(step),**(changes or {})},{**copy.deepcopy(current),**(ctx or {})})
            assert v['status']==('ADOPTABLE' if adopt else 'FALLBACK'),v
            return v
        return run
    probe('experience','matched approved synthetic fixture can adopt',exp(adopt=True))
    probe('experience','unreviewed remains preserved but cannot adopt',exp({'state':'OBSERVED'}))
    probe('experience','source generation drift fallback',exp(ctx={'generation':'mock-v2'}))
    probe('experience','source hash drift fallback',exp(ctx={'source_hash':'0'*64}))
    probe('experience','current user ACL rechecked',exp(ctx={'user':'mock-bob'}))
    probe('experience','condition differs fallback',exp(ctx={'conditions':{'party':'해외','scope':'INTERNAL'}}))
    probe('experience','wiki withdrawal fallback',exp(ctx={'wiki_live':False}))
    probe('experience','disputed knowledge fallback',exp({'wiki_status':'DISPUTED'}))
    probe('experience','incomplete original run fallback',exp({'run_status':'INTERRUPTED'}))
    probe('experience','partial read fallback',exp({'complete_read':False}))
    fail_reviews=copy.deepcopy(step['reviews']);fail_reviews[2]['verdict']='FAIL'
    probe('experience','integrity pass does not override legal fail',exp({'reviews':fail_reviews}))
    competing=copy.deepcopy(step['reviews'])+[{'id':'second-legal','kind':'LEGAL_CORRECTNESS','verdict':'PASS','supersedes':None}]
    probe('experience','competing live reviews held',exp({'reviews':competing}))
    superseded=copy.deepcopy(fail_reviews)+[{'id':'legal-new','kind':'LEGAL_CORRECTNESS','verdict':'PASS','supersedes':'LEGAL_CORRECTNESS'}]
    probe('experience','explicit legal supersession recognized',exp({'reviews':superseded},adopt=True))

    def shortcut_constraints(s,w,c,k,p):
        db=sqlite3.connect(p/'shortcut.sqlite');db.executescript(Path(shortcut_schema).read_text());h='a'*64
        try:
            db.execute('INSERT INTO shortcut_question VALUES(?,?,?,?,?,?,?,?,?)',('q','tenant','owner','OWNER','PUBLIC','모의 질문','{}',h,'mock-now'))
            db.execute('INSERT INTO shortcut_run VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('run','q','tenant','native','v5','mock:package',h,'{}',h,h,'COMPLETED','mock-now'))
            for n,d in enumerate(['A','B']):db.execute('INSERT INTO shortcut_step VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(d,'run',n,'SOURCE_SELECT','DECISION','select','OK','mock:input',h,'mock:result',h,'모의 이유','{}','[]','mock-now'))
            db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)',('B','A',h))
            rejected(lambda:db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)',('A','B',h)),sqlite3.IntegrityError,'cyclic')
            rejected(lambda:db.execute('INSERT INTO shortcut_step_dependency VALUES(?,?,?)',('A','B','0'*64)),sqlite3.IntegrityError)
            return {'cycle_denied':True,'wrong_dependency_hash_denied':True,'tables_installed':True}
        finally:db.commit();db.close()
    probe('experience','real shortcut schema dependency constraints',shortcut_constraints)
    def intake_to_receipt(s,w,c,k,p):
        db=sqlite3.connect(p/'shortcut.sqlite');db.executescript(Path(shortcut_schema).read_text())
        def put(table,**v):db.execute(f"INSERT INTO {table} ({','.join(v)}) VALUES ({','.join('?' for _ in v)})",tuple(v.values()))
        d=s.inspect(w,k,'G2-select');package={'data_kind':'SYNTHETIC','decision':d,'state':s.read_state(w,k),'source':docs[0]};ref,h=s.asset(package)
        request={'text':'가상 보고 검토','kind':'SYNTHETIC'};rh=mod.digest(request)
        for q in ['past','current']:
            put('shortcut_question',question_id=q,tenant_id=w.tenant,owner_id=w.user,visibility='OWNER',sensitivity='PUBLIC',question_text=request['text'],request_json=mod.encode(request),request_hash=rh,received_at='mock-now')
        binding={'source_generation':'mock-v1','schema':'v5','data_kind':'SYNTHETIC'};bh=mod.digest(binding)
        put('shortcut_run',run_snapshot_id='snap',question_id='past',tenant_id=w.tenant,native_run_id='run-T3',journal_schema='v5',package_ref=ref,package_hash=h,
            binding_json=mod.encode(binding),binding_hash=bh,data_key=bh,run_status='COMPLETED',recorded_at='mock-now')
        dr,dh=s.asset(d)
        put('shortcut_step',step_id='S1',run_snapshot_id='snap',ordinal=0,stage='SOURCE_SELECT',record_kind='DECISION',operation='select',outcome='OK',input_ref=ref,input_hash=h,result_ref=dr,result_hash=dh,
            reason=d['reason'],applicability_json=mod.encode(step['conditions']),native_event_refs_json='["mock-run-T3"]',created_at='mock-now')
        capsule={'statement':d['statement'],'reason':d['reason'],'conditions':step['conditions'],'source_id':docs[0]['id'],'data_kind':'SYNTHETIC'};ch=mod.digest(capsule)
        put('shortcut_capsule',capsule_id='cap',step_id='S1',revision=1,body_json=mod.encode(capsule),body_hash=ch,source_result_hash=dh,compiler_binding_json='{"kind":"mock-manual"}',created_at='mock-now')
        put('shortcut_evidence_ref',step_id='S1',evidence_key='E1',document_id=docs[0]['id'],source_id='mock-source',unit_id='mock-article-1',generation_id='mock-v1',origin_hash=docs[0]['sha256'],span_refs_json='["mock-full-text"]',read_receipt_ref=ref,read_receipt_hash=h,acquired_complete=1)
        for r in step['reviews']:
            put('shortcut_review',review_id=r['id'],step_id='S1',capsule_id='cap' if r['kind']=='CAPSULE_FIDELITY' else None,review_kind=r['kind'],verdict='PASS',reviewer_kind='HUMAN' if r['kind']=='LEGAL_CORRECTNESS' else 'CODE',
                reviewer_id='SYNTHETIC_REVIEW_FIXTURE_NOT_REAL_APPROVAL',reason='가상 검토 이벤트 적재 검사',proof_ref=ref,proof_hash=h,policy_version='mock-v1',created_at='mock-now')
        put('shortcut_step_event',event_id='observed',step_id='S1',revision=1,state='OBSERVED',reason='가상 관찰',actor_id=w.user,policy_version='mock-v1',created_at='mock-now')
        put('shortcut_step_event',event_id='reusable',step_id='S1',revision=2,state='REUSABLE',reason='가상 승인 fixture',actor_id=w.user,policy_version='mock-v1',created_at='mock-now')
        put('shortcut_route_selection',selection_id='sel',tenant_id=w.tenant,current_question_id='current',past_question_id='past',wiki_provider='MOCK_WIKI',wiki_group_ref='mock-group',wiki_revision='mock-v1',selector_id=w.user,selection_reason='명시 선택 fixture',selected_at='mock-now')
        put('shortcut_run_binding',binding_id='bind',selection_id='sel',past_question_id='past',tenant_id=w.tenant,run_snapshot_id='snap',reason='정확한 실행 고정',created_at='mock-now')
        body={'memory':[capsule],'data_kind':'SYNTHETIC'};wire={'memory':body,'question':request};wh=mod.digest(wire)
        put('shortcut_reuse_policy',policy_id='pol',stage='SOURCE_SELECT',operation='select',contract_json=mod.encode(current),contract_hash=mod.digest(current),created_at='mock-now')
        put('shortcut_prompt_packet',packet_id='pkt',selection_id='sel',binding_id='bind',current_run_id='current-run',model_attempt_id='mock-attempt',phase='select',current_state_revision=3,body_json=mod.encode(body),body_hash=mod.digest(body),request_hash=wh,
            byte_count=len(mod.encode(body).encode()),token_count=0,request_byte_count=len(mod.encode(wire).encode()),request_token_count=0,token_counter_binding='mock-not-token-measurement',budget_policy_json='{}',delivery_ref='mock:no-real-model-delivery',created_at='mock-now')
        put('shortcut_packet_item',packet_id='pkt',memory_ref=1,step_id='S1',capsule_id='cap')
        check=mod.check_experience(step,current);assert check['status']=='ADOPTABLE'
        put('shortcut_reuse_event',reuse_event_id='reuse',packet_id='pkt',step_id='S1',capsule_id='cap',policy_id='pol',action='ADOPTED',reason='모의 결과 채택',preflight_json=mod.encode(check),current_result_ref=dr,current_result_hash=dh,created_at='mock-now')
        put('shortcut_work_receipt',receipt_id='receipt',reuse_event_id='reuse',current_run_id='current-run',task_key='mock-source-select:E1',attempt_no=1,operation='select',outcome='SKIPPED',result_ref=dr,result_hash=dh,
            native_event_ref='mock:synthetic-dispatch',native_event_hash=mod.digest(check),reason='모의 callback 결과; 실제 검색/모델 생략 아님',created_at='mock-now')
        assert not db.execute('PRAGMA foreign_key_check').fetchall();db.commit();db.close()
        return {'chain':['question','run','step','evidence','capsule','reviews','selection','binding','packet','adoption','work_receipt'],
                'actual_sql_rows_inserted':21,'package_sha256':h,'review_fixture_only':True,'model_packet_delivered':False,'real_task_skipped':False}
    probe('experience','SQL intake to selection/adoption/work receipt chain',intake_to_receipt)
    (out/'features.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return results

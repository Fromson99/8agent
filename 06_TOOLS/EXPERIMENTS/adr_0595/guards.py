"""Adversarial state/transaction contracts. Scripted outputs, zero network/model calls."""
import copy
import json
from pathlib import Path

def exercise(mod, docs, root):
    checks=[]
    class Script:
        def __init__(self):
            self.command=None;self.check=None;self.reject_text=False;self.bad_facts=False
            self.bad_sources=False;self.bad_procedure=False;self.calls=[]
            self.check_queue=[];self.repaired_command=None
        def __call__(self,system,data,schema,phase):
            self.calls.append({'phase':phase,'data':copy.deepcopy(data)})
            if phase in ('resolve','command-repair'):return copy.deepcopy(self.repaired_command if phase=='command-repair' and self.repaired_command else self.command)
            if phase=='command-verify':return copy.deepcopy(self.check_queue.pop(0) if self.check_queue else self.check or {'valid':True,'requires_origin':False,'origin_turn':None,'required_stage':self.command['stage'],'reason':'scripted contract fixture'})
            if phase=='select':return {'selected':[r['id'] for r in data['read']],'reason':'all provided synthetic units'}
            if phase=='assess':
                c=data['config'];p={('INTERNAL','DOMESTIC'):'B',('INTERNAL','FOREIGN'):'A',('EXTERNAL','DOMESTIC'):'D',('EXTERNAL','FOREIGN'):'C'}[(c['scope'],c['party'])]
                return {'procedure':p,'needs_check':c['urgent'],'reason':'synthetic fixture only','source_ids':[r['id'] for r in data['sources']]}
            if phase.endswith('-verify'):
                return {'consistent':not self.reject_text,'contradictions':['scripted text contradicts locked facts'] if self.reject_text else [],'reason':'scripted semantic verification fixture'}
            f=copy.deepcopy(data['locked_facts']);ids=[r.get('id',mod.ChainStore.identity(r)) for r in data['sources']]
            if self.bad_facts:f['urgent']=True if f['urgent'] is not True else False
            if self.bad_procedure:f['procedure']='C' if f['procedure']!='C' else 'B'
            if self.bad_sources:ids.append('UNREAD/main')
            u='긴급 여부 미확인' if f['urgent'] is None else '긴급 사건이며 예외 확인 필요' if f['urgent'] else '긴급하지 않으며 예외 확인 불필요'
            return {'text':f"합성 {'내규' if f['scope']=='INTERNAL' else '외규'}의 {'국내' if f['party']=='DOMESTIC' else '해외'} 법인 {f['procedure']} 절차. {u}.",'procedure':f['procedure'],'facts':f,'source_ids':ids}
    def command(stage='NONE',action='FOLLOW',**extra):
        c={'action':action,'goal':'G1','stage':stage,'scope':'KEEP','party':'KEEP','task':'KEEP','urgent':'KEEP','query_mode':'KEEP','format':'prose','original_refs':[],'reason':'scripted synthetic command','restore_turn':None,'restore_fields':[]};c.update(extra);return c
    def record(name,fn):
        try:detail=fn();checks.append({'name':name,'pass':True,'detail':detail})
        except Exception as e:checks.append({'name':name,'pass':False,'error_type':type(e).__name__,'error':str(e)})
    counter=0
    def seeded():
        nonlocal counter
        counter+=1;s=Script();store=mod.ChainStore(root/f'guard-{counter:02d}',docs,s,history=True)
        s.command=command('INTENT','START',scope='INTERNAL',party='DOMESTIC',task='PROCEDURE')
        first=store.process({'goal':'G1','utterance':'모의 내규 국내 법인 절차'})
        assert first['status']=='READY'
        return store,s,first
    for stage in mod.STAGES:
        def explicit(stage=stage):
            store,s,first=seeded()
            try:
                s.command=command(stage)
                o=store.process({'goal':'G1','utterance':stage+'부터 다시 검토'})
                assert o['executed']==mod.STAGES[mod.STAGES.index(stage):]
                before=first['heads'];after=o['heads']
                assert all(before[k]==after[k] for k in mod.STAGES[:mod.STAGES.index(stage)])
                return {'executed':o['executed']}
            finally:store.close()
        record('explicit FOLLOW re-entry '+stage,explicit)
    def missing_origin():
        store,s,first=seeded()
        try:
            store.history=False
            s.command=command('INTENT','CORRECT',restore_turn=999,restore_fields=['scope'])
            s.check={'valid':False,'requires_origin':True,'origin_turn':None,'required_stage':'INTENT','reason':'missing original'}
            o=store.process({'goal':'G1','utterance':'최초 조건 복원'})
            assert o['status']=='CLARIFY' and store.goal('G1')['revision']==first['revision']
            assert store.current_route('G1')['id']==first['route_id'] and o['answer'] is None
            return {'status':o['status'],'unchanged_revision':first['revision']}
        finally:store.close()
    record('missing original cannot mutate or answer',missing_origin)
    def grounded_origin():
        store,s,first=seeded()
        try:
            s.command=command('PLAN','CORRECT',scope='EXTERNAL');store.process({'goal':'G1','utterance':'외규로 변경'})
            s.command=command('PLAN','CORRECT',scope='EXTERNAL',restore_turn=1,restore_fields=['scope'],original_refs=[1])
            s.check={'valid':True,'requires_origin':True,'origin_turn':1,'required_stage':'PLAN','reason':'restore original'}
            o=store.process({'goal':'G1','utterance':'최초 범위 복원'})
            assert o['config']['scope']=='INTERNAL' and o['answer']['procedure']=='B'
            return {'scope':o['config']['scope'],'original_refs':o['command']['original_refs']}
        finally:store.close()
    record('restore ignores invented command value and uses immutable origin',grounded_origin)
    def pending_rewind():
        store,s,first=seeded()
        try:
            s.command=command('SELECT','CORRECT',urgent='TRUE')
            try:store.process({'goal':'G1','utterance':'긴급 조건 적용','fault':'ASSESS'})
            except mod.GuardError:pass
            assert store.goal('G1')['pending']=='ASSESS' and store.current_route('G1') is None
            s.command=command('PLAN','CORRECT',query_mode='ALL')
            o=store.process({'goal':'G1','utterance':'검색 계획부터 다시 검토'})
            assert o['executed']==mod.STAGES[1:]
            return {'executed':o['executed']}
        finally:store.close()
    record('pending earlier re-entry is not replaced by resume stage',pending_rewind)
    def foreign_ref():
        store,s,first=seeded()
        try:
            store.db.execute("INSERT INTO turn(id,goal,utterance) VALUES(100,'G2','foreign goal')")
            s.command=command('PLAN','CORRECT',scope='EXTERNAL',original_refs=[100])
            try:store.process({'goal':'G1','utterance':'외규 수정'})
            except mod.GuardError:pass
            else:raise AssertionError('foreign-goal ref accepted')
            assert store.goal('G1')['revision']==first['revision']
            return 'foreign refs rejected before mutation'
        finally:store.close()
    record('foreign goal provenance rejected',foreign_ref)
    def present_edit():
        store,s,first=seeded()
        try:
            s.command=command('COMPOSE','PRESENT',scope='EXTERNAL')
            o=store.process({'goal':'G1','utterance':'외규로 바꾸고 표로 작성'})
            assert o['executed'][0]=='PLAN' and o['answer']['procedure']=='D'
            return {'executed':o['executed']}
        finally:store.close()
    record('PRESENT cannot bypass upstream edits',present_edit)
    def envelopes():
        store,s,first=seeded()
        try:
            s.command=command('NONE','INSPECT');a=store.process({'goal':'G1','utterance':'현재 판단 조회'})
            b=store.process({'goal':'G1','utterance':'현재 경로 재사용','action':'reuse'})
            for o in [a,b]:
                assert o['assessment']==first['assessment'] and o['route_id']==first['route_id']
                assert o['retrieval']['present']==sorted(o['answer']['source_ids']) and o['route_goal']=='G1'
            return [a['status'],b['status']]
        finally:store.close()
    record('INSPECT REUSE complete route envelopes',envelopes)
    def nullable():
        store,s,first=seeded()
        try:
            assert first['config']['urgent'] is None and first['assessment']['needs_check'] is None
            results=[]
            for value,expected in [('FALSE',False),('TRUE',True),('UNKNOWN',None)]:
                s.command=command('SELECT','CORRECT',urgent=value);o=store.process({'goal':'G1','utterance':value})
                assert o['config']['urgent'] is expected and o['assessment']['needs_check'] is expected and o['answer']['facts']['urgent'] is expected
                results.append(expected)
            return results
        finally:store.close()
    record('unknown false true remain distinct',nullable)
    for attr in ['bad_facts','bad_sources','bad_procedure','reject_text']:
        def rejected(attr=attr):
            store,s,first=seeded()
            try:
                setattr(s,attr,True);s.command=command('COMPOSE')
                try:store.process({'goal':'G1','utterance':'답변 다시 작성'})
                except mod.GuardError:pass
                else:raise AssertionError('invalid answer published')
                assert store.current_route('G1') is None and store.goal('G1')['pending']=='COMPOSE'
                rows=[json.loads(r[0]) for r in store.db.execute("SELECT payload FROM receipt WHERE kind='ANSWER_CONTRACT' AND turn_id=2")]
                assert len(rows)==2 and all(not r['accepted'] for r in rows)
                setattr(s,attr,False);o=store.process({'goal':'G1','utterance':'중단 답변 이어서 처리'})
                assert o['status']=='READY' and o['executed']==['COMPOSE']
                return {'rejected_attempts':len(rows),'resumed':o['executed']}
            finally:store.close()
        record('invalid answer blocks publication and bounded resume: '+attr,rejected)
    def two_goals():
        store,s,first=seeded()
        try:
            s.command=command('INTENT','START',goal='G2',scope='EXTERNAL',party='FOREIGN',task='PROCEDURE')
            second=store.process({'goal':'G2','utterance':'외규 해외 법인'})
            s.command=command('NONE','INSPECT');o=store.process({'goal':'G1','utterance':'첫 질문 현재 판단'})
            assert o['route_goal']=='G1' and o['route_id']==first['route_id']!=second['route_id']
            assert all(x.startswith('MOCK-INTERNAL/') for x in o['retrieval']['present'])
            return {'consumed_goal':o['route_goal'],'last_other_goal':'G2'}
        finally:store.close()
    record('final inspect retrieval is actual G1 route despite later G2 execution',two_goals)
    def stale_guard():
        store,s,first=seeded()
        try:
            try:store.publish_guard('G1',first['revision']-1)
            except mod.GuardError:pass
            else:raise AssertionError('stale publish accepted')
            store.db.execute('UPDATE route SET manifest=? WHERE id=?',(json.dumps({'nodes':[999],'config':first['config'],'hash':'wrong'}),first['route_id']))
            try:store.publish_guard('G1',first['revision'])
            except mod.GuardError:pass
            else:raise AssertionError('corrupt route accepted')
            return 'stale and corrupt manifest blocked'
        finally:store.close()
    record('stale revision and manifest corruption rejected',stale_guard)
    def native_failure():
        original=mod.NativeRepository
        class Broken(original):
            def put(self,*args,**kwargs):raise mod.GuardError('scripted native write failure')
        mod.NativeRepository=Broken;script=Script();store=None
        try:
            store=mod.ChainStore(root/'native-failure',docs,script)
            script.command=command('INTENT','START',scope='INTERNAL',party='DOMESTIC',task='PROCEDURE')
            try:store.process({'goal':'G1','utterance':'native write fixture'})
            except mod.GuardError:pass
            else:raise AssertionError('failed native write accepted')
            assert store.db.execute('SELECT COUNT(*) FROM node').fetchone()[0]==0
            assert store.db.execute('SELECT COUNT(*) FROM head').fetchone()[0]==0
            assert store.current_route('G1') is None
            return 'chain node/head rollback confirmed'
        finally:
            if store:store.close()
            mod.NativeRepository=original
    record('native write failure rolls back chain node/head',native_failure)
    def command_repair():
        store,s,first=seeded()
        try:
            s.command=command('ASSESS');s.repaired_command=command('COMPOSE')
            s.check_queue=[{'valid':False,'requires_origin':False,'origin_turn':None,'required_stage':'COMPOSE','reason':'keep and explain is composition only'},{'valid':True,'requires_origin':False,'origin_turn':None,'required_stage':'COMPOSE','reason':'repaired'}]
            o=store.process({'goal':'G1','utterance':'조건과 결론 유지하고 근거 설명'})
            assert o['executed']==['COMPOSE']
            assert sum(c['phase']=='command-repair' for c in s.calls)==1
            return {'executed':o['executed'],'command_repairs':1}
        finally:store.close()
    record('invalid command repaired once without upstream mutation',command_repair)
    def direct_equivalence():
        store,s,first=seeded()
        try:
            s.command=command('PLAN','CORRECT',scope='EXTERNAL',restore_turn=1,restore_fields=['scope'],original_refs=[1])
            s.check={'valid':True,'requires_origin':False,'origin_turn':None,'required_stage':'PLAN','reason':'explicit user value applies'}
            o=store.process({'goal':'G1','utterance':'외규를 명시적으로 적용'})
            assert o['config']['scope']=='EXTERNAL' and o['command']['restore_turn'] is None
            assert o['command']['restore_fields']==[] and o['answer']['procedure']=='D'
            return 'explicit value, rather than irrelevant original metadata, is authoritative'
        finally:store.close()
    record('explicit values normalize irrelevant restore metadata',direct_equivalence)
    return {'schema_version':'adversarial-contract-v1','kind':'scripted synthetic, no live model calls','checks':checks,'passed':sum(x['pass'] for x in checks),'total':len(checks)}

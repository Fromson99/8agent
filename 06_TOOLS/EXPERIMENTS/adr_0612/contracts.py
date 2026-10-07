"""Focused model-free state/authority contracts; no fabricated model scores."""
import importlib.util,json,sys,copy,traceback
from pathlib import Path
from contextlib import contextmanager
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'));sys.dont_write_bytecode=True
A=R/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery'
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
B=R/'02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/snapshot/02_BACKEND/semantic_runtime/legal_agent'
methods=load('semantic_runtime.legal_agent.memory_methods',B/'memory_methods.py');mod=load('semantic_runtime.legal_agent.corrected_memory',B/'corrected_memory.py')
class Fake:
 binding={'generation':'CONTRACT-SYNTHETIC'}
 def catalogue(self,ids):return [{'id':i,'name':i} for i in ids]
 def verify(self,read):assert read['binding']==self.binding
 @contextmanager
 def open(self,*args):yield self
 def schema(self,s):return {'type':'object'}
 def stage(self,s,state,parts,*args):
  if s=='READ':return {'binding':self.binding,'originals':[{'source_id':'public/1','text':'공개 모의 원문'}]}
  if s=='INTENT':return {'purpose':state['task'],'concepts':['보고 의무']}
  if s=='ASSESS':return {'claims':[{'text':'보고 대상별 적용 검토','source_id':'public/1','quote':'공개 모의 원문'}],'limitations':[]}
  if s=='COMPOSE':return {'text':'현재 판단',**parts['ASSESS']['payload']}
  return {'stage':s}
class Wire:
 command=None
 def __call__(self,system,data,schema,phase):
  if phase.startswith('memory-resolve'):return copy.deepcopy(self.command)
  if phase.endswith('check'):return {'valid':True,'reason':'contract stub, not a model'}
  raise AssertionError(phase)
def command(method,**kwargs):
 return {'method_id':method,'document_scope_mode':'KEEP','target':None,'knowledge_id':None,'stage':'NONE','task':None,'source_category':'KEEP','document_ids':None,'facts':None,'queries':None,'restore_event':None,'restore_fields':[],'format':'prose','reason':'contract stub',**kwargs}
def main():
 out=A/'artifacts/contracts';assert not out.exists();out.mkdir();wire=Wire();m=mod.Memory(out/'memory.sqlite',Fake(),wire);checks=[];seq=0;principal={'user_id':'U','team_id':'cm_public','document_ids':['d']}
 def send(c,session='S'):
  nonlocal seq
  seq+=1;wire.command=c;return m.execute({'session_id':session,'request_id':'C'+str(seq),'question':'계약용 모의 요청 '+str(seq)},principal)
 def check(name,fn):
  try:fn();checks.append({'name':name,'pass':True})
  except Exception as e:checks.append({'name':name,'pass':False,'error':str(e),'traceback':traceback.format_exc()})
 def eq(a,b):assert a==b,(a,b)
 one=send(command('CASE_START',task='보고 위임 판단',facts=[{'name':'대상','value':'전체'}]));gid=one['goal_id'];origin=m.events(gid)[0]['id']
 check('initial seven stages',lambda:eq(one['executed'],mod.STAGES))
 check('unconfirmed route not published',lambda:eq(m.db.execute('select count(*) from knowledge').fetchone()[0],0))
 for value in ('주주총회','이사회','감사'):
  result=send(command('FACT_UPDATE',target=gid,stage='INTENT',facts=[{'name':'대상','value':value}]))
  check('fact method overrides excessive stage '+value,lambda:eq(result['executed'],['ASSESS','COMPOSE']))
 restored=send(command('STATE_RESTORE',target=gid,restore_event=origin,restore_fields=['facts']))
 check('chained original restoration',lambda:eq(restored['state']['facts'],one['state']['facts']))
 saved=send(command('EXPERIENCE_CONFIRM',target=gid));kid=saved['knowledge_id']
 def active():return m.db.execute('select status from knowledge where id=?',(kid,)).fetchone()[0]
 check('confirmed bundle active',lambda:eq(active(),'ACTIVE'))
 before=(m.goal(gid,'S'),m.route(gid),m.parts(gid),m.events(gid));history=send(command('HISTORY_EXPLAIN',target=gid))
 check('history is read only',lambda:eq((m.goal(gid,'S'),m.route(gid),m.parts(gid),m.events(gid)),before))
 check('history preserves approved experience',lambda:eq(active(),'ACTIVE'))
 check('history event IDs are exact',lambda:eq([e['event_id'] for e in history['history']],[e['id'] for e in m.events(gid)]))
 check('history includes four actual corrections',lambda:eq(sum(e['correction_ordinal'] is not None for e in history['history']),4))
 check('history names restored origin',lambda:eq(history['history'][-1]['restore_event'],origin))
 check('history answer includes all event references',lambda:eq(all('['+str(e['id'])+']' in history['answer']['text'] for e in m.events(gid)),True))
 oldheads={s:n['id'] for s,n in m.parts(gid).items()};table=send(command('ANSWER_PRESENT',target=gid,format='table'))
 check('presentation compose only',lambda:eq(table['executed'],['COMPOSE']))
 check('presentation preserves approved experience',lambda:eq(active(),'ACTIVE'))
 check('presentation keeps upstream IDs',lambda:eq({s:n['id'] for s,n in m.parts(gid).items() if s!='COMPOSE'},{s:n for s,n in oldheads.items() if s!='COMPOSE'}))
 for label,c in [('presentation facts',command('ANSWER_PRESENT',target=gid,facts=[{'name':'대상','value':'임의'}])),('explain queries',command('HISTORY_EXPLAIN',target=gid,queries=['숨겨진 수정'])),('unknown method',command('UNREGISTERED',target=gid)),('fake purpose change',command('PURPOSE_REVISE',target=gid)),('unknown original',command('STATE_RESTORE',target=gid,restore_event=99999,restore_fields=['facts']))]:
  before=m.goal(gid,'S');denied=send(c)
  check('reject '+label,lambda:eq(denied['status'],'CLARIFY'));check('no mutation '+label,lambda:eq(m.goal(gid,'S'),before))
 state=m.goal(gid,'S')['state'];reuse=send(command('EXPERIENCE_REUSE',knowledge_id=kid,document_scope_mode='EXPLICIT',**state),'NEW')
 check('reuse after explanation and table',lambda:eq(reuse['status'],'REUSED'))
 check('reuse binds nodes to new goal',lambda:eq({m.db.execute('select goal from node where id=?',(n,)).fetchone()[0] for n in m.route(reuse['goal_id'])['payload']['nodes'].values()},{reuse['goal_id']}))
 send(command('RESEARCH_REENTER',target=gid,stage='COMPOSE'))
 check('no-change compose preserves knowledge independent of action label',lambda:eq(active(),'ACTIVE'))
 corrected=send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'이사회'}]))
 check('real correction retires previous knowledge',lambda:eq(active(),'RETIRED'))
 check('retired experience excluded',lambda:eq([k['id'] for k in m.candidates(principal,'보고')],[]))
 for stage in ('PLAN','READ','SELECT'):
  result=send(command('RESEARCH_REENTER',target=gid,stage=stage));check('explicit '+stage+' reentry',lambda:eq(result['executed'],mod.STAGES[mod.STAGES.index(stage):]))
 # New source authority and finite-output contracts.
 ctx={'goals':[],'allowed_documents':[{'id':'d'},{'id':'d2'}]}
 normalized=methods.normalize(command('CASE_START',document_scope_mode='AUTHORIZED'),ctx)
 check('authorized source universe is host owned',lambda:eq(normalized['document_ids'],None))
 def bad_scope():
  try:methods.normalize(command('CASE_START',document_scope_mode='AUTHORIZED',document_ids=['d']),ctx)
  except ValueError:return
  raise AssertionError('model narrowed authorized universe')
 check('authorized mode cannot hide narrowing',bad_scope)
 def overlong():
  from jsonschema import validate,ValidationError
  c=methods.normalize(command('CASE_START',queries=['x']*5),ctx)
  try:validate(c,mod.COMMAND)
  except ValidationError:return
  raise AssertionError('overlong query array admitted')
 check('five queries rejected before state mutation',overlong)
 from format_recovery import generate
 from lawrag.research.experiment_client import ExperimentFormatError
 class Cut:
  def __init__(self,n):self.n=n;self.calls=0
  def generate(self,*a,**kw):
   self.calls+=1
   if self.calls<=self.n:raise ExperimentFormatError('Incomplete or blocked OpenRouter response',response={'body_json':{'choices':[{'finish_reason':'length'}]}})
   return {'ok':True}
 c=Cut(1);receipts=[];result=generate(c,'system',{}, {},'contract',receipts.append)
 check('one truncated output repaired',lambda:eq((result,c.calls,len(receipts)),({'ok':True},2,1)))
 def bounded():
  c=Cut(9)
  try:generate(c,'system',{}, {},'contract',lambda v:None)
  except ExperimentFormatError:eq(c.calls,2);return
  raise AssertionError('unbounded format retry')
 check('format repair stops after second failure',bounded)
 # Compile the native source module too; no external invocation.
 compile((B/'memory_rag.py').read_text(),str(B/'memory_rag.py'),'exec')
 m.close();r={'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,'external_calls':0};(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False));assert r['passed']==r['total']
if __name__=='__main__':main()

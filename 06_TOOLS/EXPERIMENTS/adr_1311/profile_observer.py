"""Bounded diagnostic instrumentation; timers are nested-exclusive, samples are estimates."""
from common import *
from sql_observer import Observer
import time,threading,collections,re,sys,importlib,functools,cProfile,pstats
from contextlib import contextmanager

class DetailedSQL(Observer):
 def __init__(self,*a):
  super().__init__(*a);self.queries={};self.query_stats=collections.defaultdict(lambda: {'calls':0,'exclusive_seconds':0.0,'rows':0})
 def timed(self,db,operation,function,*args,**kwargs):
  cursor=getattr(function,'__self__',None)
  if operation in ('execute','executemany','executescript') and args and isinstance(args[0],str):
   sql=args[0];shape=re.sub(r"'(?:[^']|'')*'",'?',sql);shape=re.sub(r'\b\d+\b','?',shape);shape=' '.join(shape.split())
   qid=hashlib.sha256(shape.encode()).hexdigest()[:20]
   if qid not in self.queries:
    if len(self.queries)>=2500:raise RuntimeError('SQL shape diagnostic bound exceeded')
    frame=sys._getframe(1);sites=[]
    while frame and len(sites)<6:
     filename=frame.f_code.co_filename
     if 'semantic_runtime' in filename:sites.append([filename.split('/code/')[-1],frame.f_code.co_firstlineno,frame.f_code.co_name])
     frame=frame.f_back
    self.queries[qid]={'shape':shape,'caller':sites}
   cursor._diag_qid=qid
  qid=getattr(cursor,'_diag_qid','unattributed')
  stack=getattr(self.local,'stack',None)
  if stack is None:stack=self.local.stack=[]
  frame=[time.perf_counter(),0.0];stack.append(frame);key=(self.phase,db._ob_kind,operation);rows=0
  try:
   value=function(*args,**kwargs)
   if operation=='fetchone':rows=int(value is not None)
   elif operation in ('fetchall','fetchmany'):rows=len(value)
   elif operation=='next':rows=1
   return value
  finally:
   elapsed=time.perf_counter()-frame[0];stack.pop()
   if stack:stack[-1][1]+=elapsed
   exclusive=max(0.0,elapsed-frame[1]);row=self.rows[key];row['api_calls']+=1;row['api_seconds']+=exclusive;row['returned_rows']+=rows
   row=self.query_stats[(self.phase,db._ob_kind,qid)];row['calls']+=operation in ('execute','executemany','executescript');row['exclusive_seconds']+=exclusive;row['rows']+=rows
 def report(self):
  return {**super().report(),'sql_shapes':self.queries,'query_stats':[dict(phase=k[0],database=k[1],query_id=k[2],**v) for k,v in sorted(self.query_stats.items())],'query_bind_values_recorded':False}

class Profiler:
 def __init__(self,out,deep=False):
  self.out=out;self.deep=deep;self.cp=cProfile.Profile() if deep else None;self.active=False;self.worker=None;self.stacks={};self.stats=collections.defaultdict(lambda:{'calls':0,'inclusive_seconds':0.,'exclusive_seconds':0.,'cpu_seconds':0.});self.long=[];self.samples=collections.Counter();self.done=threading.Event();self.installed=[];self.sampling_cpu=0.
 @contextmanager
 def span(self,name):
  if not self.active:yield;return
  tid=threading.get_ident();stack=self.stacks.setdefault(tid,[]);start=time.perf_counter();cpu=time.thread_time();frame=[name,start,0.];stack.append(frame)
  try:yield
  finally:
   elapsed=time.perf_counter()-start;stack.pop()
   if stack:stack[-1][2]+=elapsed
   r=self.stats[name];r['calls']+=1;r['inclusive_seconds']+=elapsed;r['exclusive_seconds']+=max(0.,elapsed-frame[2]);r['cpu_seconds']+=time.thread_time()-cpu
   if elapsed>=.1 and len(self.long)<10000:self.long.append({'name':name,'start':start,'seconds':elapsed,'parent':stack[-1][0] if stack else None})
 def wrap(self,owner,name,label):
  if not hasattr(owner,name):return
  original=getattr(owner,name)
  @functools.wraps(original)
  def measured(*a,**k):
   with self.span(label):return original(*a,**k)
  setattr(owner,name,measured);self.installed.append(label)
 def install(self):
  pkg='semantic_runtime.'
  targets={
   'pipeline':{'Pipeline':['initialize','prepare','run']},
   'storage':{'Store':['__init__','check_unchanged','source','sources','source_lengths','section']},
   'contracts':{'Contracts':['validate','validate_port']},
   'legal_agent.law_navigation':{'Investigation':['view','save','execute','build_view','execute_tool','validate','request_decision','bounded_result','read_records','prepare_read_details','reference_overview','inspect_references','coverage_gate','run']},
   'legal_agent.bounded_source_session':{'BoundedSourceSession':['prepare_navigation_context','prepare_source_recall','structured','catalogue_pages','investigate']},
   'legal_agent.source_tools':{'SourceSession':['read','verify','execute','source_card']},
   'legal_agent.source_recall':{'SourceRecall':['prepare','discover']},
   'legal_agent.definition_entry':{None:['matches','verified','acquire_initial']},
   'legal_agent.repository':{'WorkRepository':['event','save_view','evidence','put','head']},
   'legal_agent.read_judgment':{None:['normalize_review','validate_review','context']},
   'legal_agent.completion_execution':{'CompletionExecution':['completion_stage','finish_assessment']},
   'legal_agent.unified_rag':{'UnifiedExecution':['stage']},
   'legal_agent.gateway':{'ModelGateway':['request','generate']},
   'legal_agent.connection_scope':{None:['offer_choices']},
  }
  for mod,owners in targets.items():
   module=importlib.import_module(pkg+mod)
   for cls,names in owners.items():
    owner=getattr(module,cls,None) if cls else module
    if owner is None:continue
    for name in names:self.wrap(owner,name,mod+'.'+(cls+'.' if cls else '')+name)
 def bind_app(self,app):
  route=next(r for r in app.routes if getattr(r,'path',None)=='/v1/rag/ask');old=route.dependant.call
  @functools.wraps(old)
  def ask(*a,**k):
   self.worker=threading.get_ident()
   if self.cp:self.cp.enable()
   try:
    with self.span('request.worker'):return old(*a,**k)
   finally:
    if self.cp:self.cp.disable()
    self.worker=None
  route.dependant.call=ask
 def start(self):
  self.active=True;self.started=time.perf_counter();self.thread=threading.Thread(target=self.sample,daemon=True);self.thread.start()
 def sample(self):
  last=time.perf_counter();cpu=time.thread_time()
  while not self.done.wait(.02):
   now=time.perf_counter();dt=now-last;last=now;frame=sys._current_frames().get(self.worker)
   if not frame:continue
   chain=[]
   while frame and len(chain)<80:
    c=frame.f_code;name=c.co_filename
    if '/code/' in name:name=name.split('/code/')[-1]
    elif '/site-packages/' in name:name=name.split('/site-packages/')[-1]
    elif '/lib/python' in name:name=name[name.find('/lib/python'):]
    chain.append((name,c.co_firstlineno,c.co_name));frame=frame.f_back
   if len(self.samples)>15000:raise RuntimeError('Sample stack bound exceeded')
   self.samples[tuple(chain)]+=dt
  self.sampling_cpu=time.thread_time()-cpu
 def stop(self):
  if self.done.is_set():return
  self.done.set();self.active=False
  if hasattr(self,'thread'):self.thread.join(3)
  self.finished=time.perf_counter()
 def write(self):
  put(self.out/'function-timings.json',{'installed':self.installed,'functions':dict(self.stats),'long_spans':self.long,'boundary':'Inclusive function times overlap; exclusive subtracts only installed child timers. Samples are estimates, not per-call measurements.','deep_profile':self.deep})
  write_raw_json(self.out/'sample-stacks.json.gz',{'interval_seconds':.02,'sampled_seconds':sum(self.samples.values()),'sampler_thread_cpu_seconds':self.sampling_cpu,'stacks':[{'stack':list(k),'seconds':v} for k,v in self.samples.most_common()]})
  if self.cp:
   self.cp.dump_stats(str(self.out/'worker.pstats'));stats=pstats.Stats(self.cp);rows=[]
   for (file,line,name),(cc,nc,tt,ct,callers) in stats.stats.items():
    rows.append({'file':file,'line':line,'function':name,'primitive_calls':cc,'calls':nc,'self_seconds':tt,'cumulative_seconds':ct})
   write_raw_json(self.out/'cprofile-functions.json.gz',sorted(rows,key=lambda r:r['cumulative_seconds'],reverse=True))

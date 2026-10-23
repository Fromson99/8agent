"""Read-only observational wrappers; preserve return values and exceptions."""
import json,functools,time

def install(out):
 from semantic_runtime.legal_agent import law_navigation as nav,law_candidates as lc
 path=out/'scope-trace.jsonl';seq=0
 def record(kind,data):
  nonlocal seq
  seq+=1
  with path.open('a') as s:s.write(json.dumps({'seq':seq,'time':time.time(),'kind':kind,'data':data},ensure_ascii=False)+'\n')
 def wrap(cls,name,project):
  original=getattr(cls,name)
  @functools.wraps(original)
  def call(self,*args,**kwargs):
   result=original(self,*args,**kwargs)
   record(name,project(self,args,kwargs,result))
   return result
  setattr(cls,name,call)
 def state(i):
  return {'location':i.location(),'groups':[{k:g.get(k) for k in ('id','source_id','hit','offer','status','matched_coordinates','previews')} for g in i.p['groups'].values()]}
 wrap(nav.Investigation,'article_menu',lambda i,a,k,r:{'law':a[0],'menu':r})
 wrap(nav.Investigation,'add_reads',lambda i,a,k,r:state(i))
 wrap(nav.Investigation,'reference_overview',lambda i,a,k,r:{**state(i),'delivered_spans':getattr(i.s,'investigation_delivered_spans',{}),'result':r})
 wrap(nav.Investigation,'execute_tool',lambda i,a,k,r:{'decision':a[0],**state(i)})
 original=lc.parent_offer
 @functools.wraps(original)
 def parent(session,hit):
  result=original(session,hit);record('parent_offer',{'hit':hit,'offer':result});return result
 lc.parent_offer=parent

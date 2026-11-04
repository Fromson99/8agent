"""Request-bound, typed handoff state shared by routing, tools and answer stages."""
from copy import deepcopy
import hashlib,json

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class WorkState:
    VERSION='navigation-work-state-v1'
    def __init__(self,question,manifest,authorized,effective=None,filters=None,bindings=None):
        self.question=question;self.generation=manifest['generation_id'];self.store_hash=manifest['store_sha256']
        self.authorized=sorted(set(authorized));self.effective=sorted(set(self.authorized if effective is None else effective))
        if not set(self.effective)<=set(self.authorized):raise ValueError('work scope outside authorization')
        self.filters=deepcopy(filters or {});self.bindings=deepcopy(bindings or []);self.entities={};self.events=[]
    def put(self,kind,identity,record):
        # Type is part of the key: document=leave and term=leave never collide.
        key=kind+':'+identity;self.entities[key]={'key':key,'type':kind,'identity':identity,**deepcopy(record)};return key
    def event(self,tool,args,result,status='OK',error=None):
        entry={'id':'event:'+str(len(self.events)+1),'tool':tool,'args':deepcopy(args),'status':status,'result':deepcopy(result),'error':error}
        entry['result_sha256']=digest(result);self.events.append(entry);return entry['id']
    @staticmethod
    def page(rows,offset=0,limit=12):
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=32:raise ValueError('invalid work page bounds')
        return {'items':deepcopy(rows[offset:offset+limit]),'total':len(rows),'offset':offset,'next_offset':offset+limit if offset+limit<len(rows) else None}
    def entities_page(self,kind=None,offset=0):
        return self.page([v for k,v in sorted(self.entities.items()) if kind is None or v['type']==kind],offset)
    def result_page(self,event_id,offset=0):
        e=next((e for e in self.events if e['id']==event_id),None)
        if e is None:raise ValueError('unknown work event')
        value=e['result'];rows=value.get('items') if isinstance(value,dict) else None
        if isinstance(rows,list):return {'event_id':event_id,'result_sha256':e['result_sha256'],'metadata':{k:v for k,v in value.items() if k!='items'},**self.page(rows,offset)}
        if offset:raise ValueError('scalar tool result has no next page')
        return {'event_id':event_id,'result_sha256':e['result_sha256'],'value':deepcopy(value),'next_offset':None}
    def scope(self):
        # Prompts get counts and a hash; the id lists live in the snapshot and the document entities.
        return {'authorized_count':len(self.authorized),'effective_count':len(self.effective),'effective_sha256':digest(self.effective),'narrowed':self.effective!=self.authorized,'effective_document_ids':self.effective if len(self.effective)<=12 else self.effective[:12]+['... +%d more (WORK_PAGE entities)'%(len(self.effective)-12)],'filters':deepcopy(self.filters)}
    def header(self):
        return {'schema_version':self.VERSION,'question':self.question,'generation_id':self.generation,'source_store_sha256':self.store_hash,'scope':self.scope(),'expression_bindings':deepcopy(self.bindings),'entity_count':len(self.entities),'event_count':len(self.events),'history_access':'WORK_PAGE events or TOOL_RESULT event_id; server retains exact results'}
    def snapshot(self,include_results=True):
        # Tool results are already the trace; the handoff snapshot can carry hashes only.
        events=deepcopy(self.events) if include_results else [{k:v for k,v in e.items() if k!='result'} for e in self.events]
        return {**self.header(),'scope':{**self.scope(),'authorized_document_ids':self.authorized,'effective_document_ids':self.effective},'entities':deepcopy(self.entities),'events':events,'results_included':include_results}

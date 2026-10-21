from pathlib import Path
from types import SimpleNamespace as NS
import json,sys,os,time,resource,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0829-comparison-main-qualification';D=A/'artifacts/design'
arm=sys.argv[1];f=json.loads((D/'freeze.json').read_text());base=json.loads((D/'baseline.json').read_text())['manifest'];code=R/(f['code_root'] if arm=='connected' else base['code_root'])
sys.dont_write_bytecode=True;sys.path[:0]=[str(code/'02_BACKEND'),str(R/'02_BACKEND')]
from workflow.presentation import packets
assert Path(sys.modules['workflow.presentation'].__file__).is_relative_to(code)
try:from workflow.risk_team_compare_workflow.task_board import checked,sources_for_issue,partial_items
except ModuleNotFoundError:checked=sources_for_issue=partial_items=None
sources=[{'evidence_id':'Ei','side':'internal','spans':[{'text':'신규 모의 의무 원문'}]},
         {'evidence_id':'Ee','side':'external','spans':[{'text':'신규 모의 외부 원문'}]}]
def side(status,source):
 return {'status':status,'text':'' if status=='MISSING' else source['spans'][0]['text'],
 'citations':[] if status=='MISSING' else [{'evidence':source['evidence_id'],'quote':source['spans'][0]['text']}],
 'dependencies':[],'scope_sufficient':status=='CONFIRMED','missing':'' if status=='CONFIRMED' else '미확인'}
def rejected(value,locs):
 if checked is None:raise NotImplementedError('baseline lacks field/task validator')
 try:checked(value,sources,['obligation'],locs)
 except ValueError:return True
 return False
def fields(c):
 row={'field':'obligation','internal':side(c['internal'],sources[1] if c['wrong_side'] else sources[0]),
      'external':side(c['external'],sources[1]),'content_status':c['comparison'],'difference':'문구 관측' if c['comparison']!='UNKNOWN' else '', 'next_tasks':[]}
 invalid=(c['wrong_side'] and c['internal']!='MISSING') or (c['comparison']!='UNKNOWN' and any(c[s] in ('MISSING','CONFLICT') for s in ('internal','external')))
 actual=rejected({'items':[row]},{});return {'passed':actual==invalid,'expected_rejection':invalid,'observed_rejection':actual}
def tasks(c):
 row={'field':'obligation','internal':side('PARTIAL',sources[0]),'external':side('CONFIRMED',sources[1]),'content_status':'UNKNOWN','difference':'','next_tasks':[
  {'side':'internal','operation':c['operation'],'locator_id':None if c['locator']=='none' else 'L', 'query':'공동 담당의 예외 확인',
   'anchor_ids':['Ee' if c['anchor']=='valid' else 'fabricated'],'reason':'신규 유한 계약'}]}
 locs={} if c['locator']=='none' else {'L':{'side':'internal' if c['locator']=='same' else 'external','reference_id':'witnessed-reference'}}
 invalid=c['anchor']=='missing' or c['locator']=='opposite' or (c['locator']=='none' and c['operation'] in ('read_node','locate_provision','search_subtree','follow_reference'))
 actual=rejected({'items':[row]},locs);return {'passed':actual==invalid,'expected_rejection':invalid,'observed_rejection':actual}
def projection(c):
 data=[]
 for n in range(c['irrelevant']+2):
  text=('검토 대상 본문' if n==0 else '공통 예외 및 분모 정의' if n==1 else '무관한 다른 업무 항목'+str(n))
  data.append({'evidence_id':'E'+str(n),'source_id':'annex','document_id':'doc','side':c['side'],
    'metadata':{'document_name':'새 모의 별표'},'text':text,'version_verified':True,'citation_names':[],
    'spans':[{'block_id':str(n),'start_cp':0,'end_cp':len(text),'text':text}]})
 native=type('Native',(),{'__module__':'semantic_runtime.workflow_bridge'})()
 port=NS(services=native,session=NS(tools=NS(sources={'annex':{'id':'annex','blocks':[{'block_id':str(n),'text':e['text']} for n,e in enumerate(data)]}})))
 ctx=NS(rag=NS(evidence=lambda:data,port=port),request={'question':'공동 담당과 예외를 비교','as_of':None},repo=NS(work=NS(budget=lambda:{}),save=lambda _:None),context=NS(deadline_at='fixed'),model=NS(services=NS(profile={'max_context_chars':14000})))
 result={'side':c['side'],'status':'completed','evidence_ids':[e['evidence_id'] for e in data],'bundle':{'claims':[
  {'evidence_ids':['E0','E1'],'parent_issue_refs':['need']},{'evidence_ids':[e['evidence_id'] for e in data[2:]],'parent_issue_refs':['unrelated']}]}}
 state={'scope':{},'gaps':[],'task_board':{'schema_version':'comparison-research-v1'},'rag_results':{} if c['historical'] else {c['side']:result},'rag_valid_results':{c['side']:[result]}}
 emitted=packets(ctx,state,'ITEMS',ids=['E0','E1']);ids={e['evidence_id'] for _,es in emitted for e in es}
 scoped={e['evidence_id'] for e in sources_for_issue(ctx,state,'need')} if sources_for_issue else None
 return {'passed':ids=={'E0','E1'} and scoped==ids and all(not e['source_complete'] for _,es in emitted for e in es),
   'provided_span_count':len(data),'presented_span_ids':sorted(ids),'issue_scoped_ids':sorted(scoped) if scoped is not None else None,'exception_retained':'E1' in ids,
   'retrieval_executed':False,'fixed_inventory_source':'synthetic immutable provided spans, common article-root doc/0','canonical_root_count':1}
def partial(c):
 if partial_items is None:raise NotImplementedError('baseline lacks per-side partial validation')
 field=c['field'];bad=c['invalid_side'];good='external' if bad=='internal' else 'internal'
 row={'field':field,'internal':side('CONFIRMED',sources[0]),'external':side('CONFIRMED',sources[1]),'content_status':'MATCH','difference':'동일 관측','next_tasks':[]}
 row[good]=side(c['good_status'],sources[0 if good=='internal' else 1])
 if c['fault']=='wrong_side':row[bad]['citations']=side('CONFIRMED',sources[1 if bad=='internal' else 0])['citations']
 elif c['fault']=='unread_quote':row[bad]['citations'][0]['quote']='제시되지 않은 위조 문구'
 elif c['fault']=='missing_prose':row[bad].update(status='MISSING',text='확인 불가라는 설명',citations=[],scope_sufficient=False,missing='원문 부족')
 elif c['fault']=='scope':row[bad]['scope_sufficient']=False
 else:row['difference']=''
 value,errors=partial_items({'items':[row]},sources,[field],{})
 got=value['items'][0];expected_bad=got[bad]['status']=='MISSING' and not got[bad]['citations'] if c['fault']!='comparison' else got[bad]==row[bad]
 return {'passed':bool(errors) and got[good]==row[good] and expected_bad and got['content_status']=='UNKNOWN' and not got['difference'], 'errors':errors,'observed':got,'original_proposal_accepted':False}
def resume(c):
 from semantic_runtime.legal_agent import workflow_execution as wx
 from semantic_runtime.legal_agent.errors import ContractError
 from semantic_runtime.contracts import digest
 import sqlite3
 if not hasattr(wx,'recover_abandoned_request'):raise NotImplementedError('control lacks abandoned child recovery')
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
 db.execute('CREATE TABLE workflow_call(call_id TEXT,kind TEXT,status TEXT,error_json TEXT,result_json TEXT,input_json TEXT)')
 body={'request_id':'call','session_id':'workflow:parent:internal','question':'내규: q'};principal={'document_ids':['d']}
 old={'status':c['old_status'],'input_hash':digest({'body':body,'principal':principal}) if c['fingerprint'] else 'changed'}
 if c['call_status']!='absent':db.execute('INSERT INTO workflow_call VALUES(?,?,?,?,?,?)',('call','rag',c['call_status'],None,None,json.dumps({'operation':'ask_rag','side':'internal','args':{'question':'q'}})))
 events=[];work=NS(db=db,event=lambda *a:events.append(a));ctx=NS(run_id='parent');cases=NS(owner_held=c['owner'],model_resource=NS(body=body),request_key=lambda *a:'key')
 from contextlib import nullcontext
 expected='False' if not c['parent'] or c['old_status']!='RUNNING' else 'True' if c['owner'] and c['fingerprint'] and c['call_status']=='PREPARED' else 'ERROR'
 with wx.child_execution(work,ctx,'call',['d']) if c['parent'] else nullcontext():
  try:actual=str(wx.recover_abandoned_request(cases,body,principal,old))
  except ContractError:actual='ERROR'
 db.close()
 return {'passed':actual==expected and len(events)==int(expected=='True'),'expected':expected,'observed':actual,'recovery_events':len(events)}
def publication(c):
 from workflow.risk_team_compare_workflow import task_board
 if not hasattr(task_board,'unreviewed_sources'):raise NotImplementedError('control lacks preserved original publication')
 ident='E-'+c['side'];good={'side':c['side'],'status':'completed','evidence_ids':[ident],'bundle':{'side':c['side'],'evidence_ids':[ident],'claims':[{'evidence_ids':[ident]}]}}
 state={'rag_results':{c['side']:{**good,'status':c['status']}},'rag_valid_results':{c['side']:[good] if c['historical'] else []},'context_evidence':['X'+str(n) for n in range(c['context_count'])]}
 by={i:{'evidence_id':i,'side':c['side'],'text':'fixed original '+i} for i in [ident,*state['context_evidence']]}
 expected=[ident] if (c['status']!='failed' or c['historical']) and not c['reviewed'] else []
 actual=[e['evidence_id'] for e in task_board.unreviewed_sources(state,by,{ident} if c['reviewed'] else set())]
 return {'passed':actual==expected,'expected':expected,'observed':actual,'unrelated_context_not_published':not (set(actual)&set(state['context_evidence']))}
start=time.monotonic();out=[]
for c in json.loads((D/'cases.json').read_text()):
 try:observed={'fields':fields,'tasks':tasks,'packets':projection,'partial':partial,'resume':resume,'publication':publication}[c['family']](c)
 except Exception as e:observed={'passed':False,'error_type':type(e).__name__,'error':str(e)}
 out.append({'case_id':c['case_id'],'family':c['family'],**observed})
value={'arm':arm,'code_root':str(code.relative_to(R)),'cases':out,'passed':sum(r['passed'] for r in out),'total':len(out),'elapsed_seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_calls':0,'retrieval_calls':0}
p=A/'artifacts'/('matrix-'+arm+'.json');p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k!='cases'},ensure_ascii=False))

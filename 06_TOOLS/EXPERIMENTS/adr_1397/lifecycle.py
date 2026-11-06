"""Experiment-only authoring and publication using existing product contracts."""
from common import *
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,sqlite3,time,httpx

class Lifecycle:
 def __init__(self,code,base,data,metadata,documents):
  from semantic_runtime.ontology_work.repository import Repository
  from semantic_runtime.ontology_work.store import LocalFolderStore
  from semantic_runtime.ontology_work import runtime
  self.code,self.base,self.data,self.metadata,self.documents=code,base,data,metadata,list(documents)
  self.out=base/'knowledge';self.out.mkdir()
  self.repo=Repository(lambda:sqlite3.connect(self.out/'work.sqlite'));self.repo.initialize()
  self.store=LocalFolderStore(self.out/'objects');self.reader=None;self.ready_for_use=False
  self.compiled=None;self.w=None;self.domain=None;self.author_calls=[]
  self.endpoint=SimpleNamespace(headers={},url=lambda path:'https://authoring-experiment.invalid'+path)
  # The same authenticated read port is used on original arrival AND revalidation.
  # No validator or semantic state is replaced by this local connection injection.
  runtime.repository=lambda:self.repo

 def author_post(self,kw,client,active,admission):
  if admission:return httpx.Response(429,json={'error':'Synthetic no-send admission boundary'})
  if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('UNKNOWN forbids further authoring sends')
  response=client.chat_completions(kw['json_body'],phase=active[-1],timeout_seconds=min(180,max(1,kw['deadline']-time.monotonic())))
  return httpx.Response(response['status_code'],json=response['body_json'])

 def _generate(self,active,raw):
  from semantic_runtime.ontology_work import authoring_model
  from semantic_runtime import genos
  def generate(prompt,context,schema):
   stage=context.get('operation','NORMALIZE' if 'raw' in context else 'WIKI_PROPOSE')
   n=len(self.author_calls)+1;row={'number':n,'stage':stage,'status':'STARTED'};self.author_calls.append(row)
   raw(self.out/'canonical'/f'{n:03}.json.gz',{'prompt':prompt,'context':context,'schema':schema})
   active.append('AUTHOR:'+stage)
   try:
    with patch.object(genos,'from_env',lambda kind:(self.endpoint,'qwen/qwen3.8-27b')),patch.object(genos,'advertised_model',lambda *a:'qwen/qwen3.8-27b'):
     value,receipt=authoring_model.generate(self.store,prompt,context,schema)
    raw(self.out/'canonical'/f'{n:03}-output.json.gz',value);row['status']='RECEIVED';return value,receipt
   except Exception as exc:row.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));raise
   finally:active.pop();put(self.out/'generations.json',self.author_calls)
  return generate

 def _parts_and_originals(self,turn):
  from semantic_runtime.legal_agent.shortcut_store import selected_store
  from semantic_runtime.legal_agent import journal_storage
  from semantic_runtime.legal_agent.ontology_compiler import content_hash
  path=selected_store(self.base/'runtime');db=journal_storage.connect(path,isolation_level=None)
  try:
   from semantic_runtime.contracts import digest
   route=db.execute('SELECT payload,hash FROM route WHERE goal=? AND revision=?',(turn['goal_id'],turn['revision'])).fetchone()
   stored=json.loads(route['payload']);assert digest(stored)==route['hash']
   parts={}
   for stage,node in stored['nodes'].items():
    row=db.execute('SELECT payload,hash FROM node WHERE id=? AND goal=?',(node,turn['goal_id'])).fetchone()
    parts[stage]=json.loads(row['payload']);assert digest(parts[stage])==row['hash']
   goal=stored['state']
  finally:db.close()
  if not parts['ASSESS'].get('claims') or parts['ASSESS'].get('source_excerpt_reply'):raise RuntimeError('No supported first-turn judgment to accumulate')
  evidence={e['evidence_id']:e for e in parts['READ'].get('evidence',[])+parts['SELECT'].get('selected_evidence',[])}
  allowed_blocks={}
  for e in evidence.values():
   assert e['document_id'] in self.documents
   allowed_blocks.setdefault(e['document_id'],set()).update(str(p['block_id']) for p in e['spans'])
  originals=[]
  with sqlite3.connect('file:'+str(self.data/'store.sqlite')+'?mode=ro',uri=True) as source:
   for did,blocks in allowed_blocks.items():
    version=source.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
    units=set()
    for bid in blocks:
     row=source.execute('SELECT unit_id FROM source_block WHERE document_id=? AND block_id=?',(did,bid)).fetchone()
     if row and row[0] is not None:units.add(str(row[0]))
    for uid in sorted(units):
     rows=source.execute('SELECT block_id,text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(did,uid)).fetchall()
     if not rows or not {str(b) for b,_ in rows}<=blocks:continue
     text='\n'.join(t for _,t in rows)
     originals.append({'id':'S'+str(len(originals)+1),'anchor':{'document_id':did,'version':version,'unit_id':uid,'content_sha256':content_hash(text),'label':'확보된 원문 '+uid},'text':text})
  if not originals or len(originals)>32:raise RuntimeError('No bounded complete own-body originals from actual acquired evidence')
  return parts,goal,originals

 def build_and_review(self,first_turn,client,active,raw):
  from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
  from semantic_runtime.ontology_work.wiki_workspace import Workspace
  from semantic_runtime.ontology_work.wiki_projection import compile_selection
  from semantic_runtime.ontology_work import wiki_contracts as wc
  from semantic_runtime.ontology_work.configuration import source_reader
  from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
  from semantic_runtime.full_glossary import Glossary
  from semantic_runtime.full_glossary_connections import ConnectionReader
  from semantic_runtime.contracts import digest
  parts,state,originals=self._parts_and_originals(first_turn)
  raw(self.out/'actual-first-judgment.json.gz',{'parts':parts,'state':state,'originals':originals})
  g=self.metadata['glossary'];self.reader=Glossary(self.data/g['bundle'],self.data/g['dictionary'],self.data/g['cache'],manifest_sha256=g['manifest_sha256'],connection_factory=ConnectionReader)
  glossary=GlossaryBinding(self.reader,snapshot=self.metadata['generation_id'])
  source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(self.data/'store.sqlite')}},self.documents)
  for s in originals:assert source(s['anchor'])==s['text']
  args=dict(actor='codex-ADR1397-isolated-reviewer',source_reader=source,generate=self._generate(active,raw),namespace='ADR1397-only',source_snapshot=self.metadata['generation_id'],acl_ref=digest(self.documents),document_ids=self.documents,glossary=glossary,producer_binding=read(DES/'candidate-repaired.json')['pin']['revision_sha256'])
  self.w=Workspace(self.repo,self.store,can_publish=True,**args);self.domain=DomainWorkflow(self.repo,self.store,**args);self.domain.can_publish_workspace=True
  self.repo.workspace_scopes={wc.scope_key(self.w.scope())}
  profile=self.domain.save_profile(read(self.code/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(self.code/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
  self.domain.review_profile(profile['bundle_id'],profile['revision'],profile['work_hash'],True,'Existing schema profile for isolated test, no legal knowledge approval')
  actual={'question':state['task'],'claims':parts['ASSESS']['claims'],'judgment_reasons':parts['ASSESS'].get('issue_assessments',[])}
  imported=self.w.import_payload(actual,event_id='accepted-first-assessment',run_id=first_turn['run_id'],format_description='Exact accepted actual Qwen claims/reasons; no answer key or management metadata')
  proposal=self.w.propose(change_id='actual-first-judgment',raw_ids=[imported['bundle_id']],originals=originals,query='정기총회 소집 시기')
  raw(self.out/'proposal.json.gz',proposal);self.w.apply(**proposal)
  statements=self.w.list_items(kind='STATEMENT',limit=128)['items'];ids=[x['bundle_id'] for x in statements];self.statement_ids=ids
  put(self.out/'statements.json',[self.w.item(i) for i in ids])
  purpose='정기총회 소집 시기를 원문과 실제 판단으로 검토하고 후속 질문에서 재사용'
  self.compiled=compile_selection(self.domain,self.w,statement_ids=ids,purpose=purpose,profile_id=profile['bundle_id'],profile_work_hash=profile['work_hash'])
  document=self.domain.load(self.compiled['bundle_id']);raw(self.out/'compiled.json.gz',document)
  put(self.out/'review-needed.json',{'compiled':self.compiled,'purpose':purpose,'originals':originals,'review_gate':'Inspect exact original support, statement preservation, no invented facts/claims. Isolated test only; never approve unresolved or contradicted content for operational use.'})
  print('EXPERIMENTAL_REVIEW_REQUIRED',str(self.out/'review-needed.json'),flush=True)
  deadline=time.monotonic()+600;gate=self.out/'experimental-review.json'
  while not gate.exists() and time.monotonic()<deadline:
   if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('UNKNOWN forbids publication')
   time.sleep(0.5)
  if not gate.exists():raise RuntimeError('Isolated review not provided in time')
  decision=read(gate)
  assert (decision['bundle_id'],decision['revision'],decision['work_hash'])==(self.compiled['bundle_id'],self.compiled['revision'],self.compiled['work_hash'])
  if decision['approve'] is not True:raise RuntimeError('Isolated knowledge review rejected; no publication')
  self.domain.review(self.compiled['bundle_id'],self.compiled['revision'],self.compiled['work_hash'],True,decision['reason'])
  self.stage=self.domain.stage_publication(self.compiled['bundle_id'],self.compiled['revision'],self.compiled['work_hash'],0)
  verified=self.domain.verify_publication(self.stage['publication_id'])
  activated=self.domain.activate_publication(self.stage['publication_id'],0,verified)
  put(self.out/'publication.json',{'stage':self.stage,'verified':verified,'activated':activated,'not_operational_approval':True})
  self.ready_for_use=True

 def used(self,turn):
  value=read(self.base/('turn-'+str(turn['step']['number']))/'response.json.gz')['body']
  uses=[u for b in value.get('assembly',{}).get('term_agent',{}).get('review_explanation',{}).get('ontology',{}).get('bundles',[]) for u in b.get('claim_uses',[])]
  put(self.out/'actual-usage.json',{'turn':turn['step']['number'],'uses':uses,'delivered_is_not_adoption':True})
  return bool(uses)

 def compare_conflict(self,client,active,raw):
  from semantic_runtime.ontology_work.wiki_projection import compare_judgment
  previous=self.w.load(self.compiled['bundle_id']);head=self.repo.head(self.compiled['bundle_id'])
  payload={'counterclaim':read(DES/'criteria.json')['scripted_counterclaim'],'origin':'EXPLICIT_EXPERIMENT_COUNTERCLAIM_NOT_AN_ACTUAL_QWEN_MISTAKE'}
  item=self.w.import_payload(payload,event_id='explicit-conflict-probe',run_id='ADR1397-conflict',format_description='Predeclared scripted counterclaim; actual Qwen must compare with originals; not an organic model error')
  result=compare_judgment(self.w,self.w,bundle_id=previous['bundle_id'],revision=previous['revision'],work_hash=previous['work_hash'],raw_id=item['bundle_id'])
  after=self.w.load(previous['bundle_id'])
  assert self.repo.head(previous['bundle_id'])==head
  put(self.out/'conflict.json',{'saved':result,'review_state':after['review_state'],'active_preserved':True,'graph_preserved':after['proposal']['graph']==previous['proposal']['graph'],'observation_count_before':len(previous['observation_ledger']),'observation_count_after':len(after['observation_ledger']),'scripted_input_actual_model_comparison':True})

 def withdraw(self):
  head=self.repo.head(self.compiled['bundle_id']);target=self.statement_ids[0];statement=self.w.item(target)
  expected={target:{'revision':statement['revision'],'work_hash':statement['work_hash']}}
  result=self.w.apply(change_id='withdraw-experimental-knowledge',expected=expected,
      operations=[{'op':'RETRACT','target':target,'value':{'reason':'사전 계획한 실험용 게시 철회, 원문은 보존'}}])
  after=self.repo.head(self.compiled['bundle_id']);assert after['publication_id'] is None
  put(self.out/'withdrawal.json',{'before':head,'after':after,'same_originals':True,'workspace_change':result})

 def close(self):
  if self.reader:self.reader.close()

"""Bounded term agent in the serving pipeline; provider injected by host."""
import json
from pathlib import Path
import threading
import time
import uuid
from jsonschema import Draft202012Validator
from . import term_tools as agent
from .contracts import sha
from .term_index import cached_serving_index
from . import observability as obs

log = obs.get_logger('term-index')

DEFAULTS={'max_rounds':3,'max_calls':9,'wall_seconds':1800,'search_limit':3,'max_repairs':1}

class TermAgent:
    def __init__(self,pipeline,config):
        self.pipeline=pipeline;self.config=config;self.index=None;self.lock=threading.Lock()
    def get_index(self):
        with self.lock:
            if self.index is None:
                binding=self.pipeline.store.manifest.get('navigation') or self.config.get('index')
                if not binding:raise ValueError('term-agent requires a version-bound navigation index')
                root=self.pipeline.store.path if self.pipeline.store.manifest.get('navigation') else self.pipeline.contracts.root
                path=(root/binding['path']).resolve();path.relative_to(root)
                with obs.step(log, 'index.open'):
                    self.index=cached_serving_index(path,self.pipeline.store,
                        expected_manifest_sha256=binding['manifest_sha256'])
            return self.index
    def get_fulltext(self):
        """Optional morpheme ranking index bound in config; None when not configured."""
        # Bound to one navigation index: generations sharing a source store and generation ID
        # still differ by index, and one without this build has no full-text ranking.
        # A published generation owns its derived fulltext binding. The profile
        # binding remains a fallback for older, frozen local generations.
        generation_binding=self.pipeline.store.manifest.get('fulltext')
        binding=generation_binding if generation_binding is not None else self.config.get('fulltext')
        index=self.get_index()
        if not binding:return None
        if binding.get('navigation_index_sha256')!=index.manifest['index_sha256']:
            if generation_binding is not None:
                raise ValueError('generation fulltext/navigation binding mismatch')
            return None
        with self.lock:
            if getattr(self,'fulltext',None) is None:
                from .fulltext import cached_open_bound
                self.fulltext=cached_open_bound(self.pipeline.store.path,binding,index.manifest)
            return self.fulltext
    def retrieve(self,plan,use_llm):
        p=self.pipeline;config={**DEFAULTS,**self.config.get('limits',{})};index=self.get_index();scope=plan['scope']['document_version_ids'];tools=index.tools(scope);question=plan['question'];seen=[];searched=[];attempted=[];outcomes=[];trace=[];receipts=[];repairs=0;calls=0;start=time.monotonic();final=agent.failure_output();status='STOP';failure=None
        def call(role,prompt,data,schema):
            nonlocal calls
            if calls>=config['max_calls'] or time.monotonic()-start>=config['wall_seconds']:raise ValueError('term-agent execution budget exhausted')
            if p.provider is None:raise ValueError('LLM provider is not configured')
            calls+=1;value,receipt=p.provider.call('term-agent-'+role,prompt,data,schema);receipts.append(receipt);Draft202012Validator(schema).validate(value);return value
        try:
            literal=tools.initial_menu(question)
            if use_llm:
                plan_value=call('plan',agent.PLAN_SYSTEM,{'question':question,'literal_term_candidates':literal},agent.PLAN_SCHEMA);seeds,missing=tools.resolve(plan_value['seed_labels'])
            else:plan_value={'questions_to_check':[],'seed_labels':[]};seeds=[x['id'] for x in literal[:4]];missing=[]
            if not seeds:seeds=[x['id'] for x in literal[:4]]
            next_terms=seeds;next_navigation=[];nav_menu=[];latest=None;action='SEARCH'
            if not seeds:status='NO_RESOLVED_TERM';final=agent.failure_output();final['open_questions'][0]['text']='질문에 연결할 용어를 찾지 못했습니다.'
            else:
                for round_no in range(1,config['max_rounds']+1):
                    step={'round':round_no,'action':action,'before_evidence_ids':list(seen),'term_ids':next_terms};trace.append(step)
                    if action=='SEARCH':
                        results=tools.search(next_terms,scope,config['search_limit'],exclude_ids=seen);step['search_results']=results;searched=list(dict.fromkeys(searched+next_terms));seen=list(dict.fromkeys(seen+[r['id'] for r in results]))
                    elif action=='NAVIGATE':
                        opened,rows=tools.navigate(next_navigation,nav_menu,seen,scope);step['navigation_results']=rows;outcomes+=rows;attempted+=next_navigation;seen=list(dict.fromkeys(seen+opened))
                    if round_no==1:
                        opened,rows=tools.prefetch(seen,searched,question,scope);step['bounded_prefetch']={'opened_ids':opened,'results':rows};outcomes+=rows;attempted+=[x['id'] for x in rows];seen=list(dict.fromkeys(seen+opened))
                    step['after_evidence_ids']=list(seen)
                    if not use_llm:status='SOURCE_ONLY';final=agent.failure_output();final['evidence_ids']=seen;break
                    frontier=tools.frontier(seen,searched,question);nav_menu=tools.navigation_menu(seen,searched,question,scope,attempted);term_ids=[t['id'] for t in frontier['terms']];nav_ids=[x['id'] for x in nav_menu]
                    data={'question':question,'questions_to_check':plan_value['questions_to_check'],'round':round_no,'remaining_rounds':config['max_rounds']-round_no,'last_action':action,'searched_terms':[tools.term_card(t) for t in searched],'documents':tools.evidence(seen),'term_menu':frontier,'navigation_menu':nav_menu,'scoped_definition_results':[x['definition'] for x in outcomes if x['action']=='LOOKUP_DEFINITION'],'navigation_outcomes':[{k:v for k,v in x.items() if k!='definition'} for x in outcomes],'previous_review':latest,'scope_note':'Only selected document versions; glossary and relationship candidates are unreviewed source hints.'}
                    schema=agent.review_schema(seen,term_ids,nav_ids);raw=call('review',agent.REVIEW_SYSTEM,data,schema)
                    try:review=agent.validate_review(raw,seen,term_ids,nav_ids)
                    except ValueError as exc:
                        if repairs>=config['max_repairs']:raise
                        repairs+=1;step['state_repair']={'invalid_output':raw,'validation_error':str(exc)};raw=call('repair',agent.REVIEW_SYSTEM,{**data,'invalid_draft':raw,'state_contract_error':str(exc)},schema);review=agent.validate_review(raw,seen,term_ids,nav_ids)
                    latest=review;final=review;step['review']=review;next_terms=review['next_term_ids'];next_navigation=review['next_navigation_ids'];action=agent.route_review(review,round_no,config['max_rounds']);step['controller_action']=action
                    if action=='REPLAN_SEARCH':
                        repl=call('replan',agent.REPLAN_SYSTEM,{'question':question,'missing':review['open_questions'],'term_menu':frontier,'previous_terms':[tools.term_card(t) for t in searched]},agent.PLAN_SCHEMA);next_terms,unknown=tools.resolve(repl['seed_labels']);next_terms=next_terms or seeds;step['replan']={'output':repl,'unresolved_labels':unknown};action='SEARCH'
                    elif action=='COUNTER_SEARCH':next_terms=seeds;action='SEARCH'
                    elif action=='ASK_USER':
                        final={**review,'next_action':'ASK_USER','question_for_user':review['question_for_user'] or ' '.join(g['text'] for g in review['open_questions'] if g['kind']=='USER_FACT')}
                    elif action=='STOP_UNRESOLVED':action='STOP';final={**review,'next_action':'STOP'}
                    status=action
                    if action in ['FINISH','ASK_USER','STOP']:break
            selected=final['evidence_ids']
        except Exception as exc:
            status='EXECUTION_FAILURE';failure={'type':type(exc).__name__,'message':str(exc),'failed_draft':final};final=agent.failure_output();selected=[]
        try:
            candidates=[]
            for sid in seen:
                s=tools.sources[sid];section=p.store.source_scope(s['document_id'],s['block_id']);candidates.append({**s,'ancestors':section['ancestors'],'routes':['term_agent'],'score':0})
            return {'candidates':candidates,'routes':{'term_agent':len(candidates)},'vector_status':'NOT_USED','generation_id':p.store.manifest['generation_id'],'term_agent':{'status':status,'final':final,'selected_ids':selected,'trace':trace,'calls':calls,'provider_receipts':receipts,'failure':failure,'elapsed_seconds':time.monotonic()-start,'quality_certified':False,'index_manifest':index.manifest,'use_llm':use_llm}}
        finally:tools.db.close()

def assemble(p,plan,selection):
    state=selection['term_agent'];contexts=[]
    for s in selection['selected']:
        contexts.append({'id':s['id'],'document_id':s['document_id'],'block_id':s['block_id'],'unit_id':s['unit_id'],'text':s['text'],'document_name':s['document_name'],'ancestors':s['ancestors'],'reasons':['TERM_AGENT_SELECTED_ARTICLE'],'evidence_ids':[],'source_artifact_sha256':s['source_artifact_sha256'],'blocks':s['blocks']})
    return {'context':contexts,'unresolved':[],'data_status':p.store.manifest['data_status'],'term_agent':state}

def answer(p,plan,assembly):
    state=assembly['term_agent'];final=state['final'];contexts={c['id']:c for c in assembly['context']};claims=[];texts=[]
    if state['use_llm']:
        for i,f in enumerate(final['findings']):
            if not set(f['source_ids'])<=contexts.keys():raise ValueError('agent claim source not selected')
            claims.append({'id':'claim:'+str(i),'text':f['text'],'source_ids':f['source_ids']});texts.append(f['text'])
        unresolved=[g['text'] for g in final['open_questions']]
        if final['question_for_user']:unresolved.append(final['question_for_user'])
        if not claims and not unresolved:unresolved=['확인한 근거가 없어 답변을 확정하지 못했습니다.']
    else:
        texts=[c['document_name']+'\n'+c['text'] for c in contexts.values()];unresolved=['원문 조회 모드: LLM 판단을 수행하지 않았습니다.']
        if state['status']=='METADATA_ONLY':unresolved=['모델 미사용: 용어·구조 시작점만 조회했습니다. 원문 탐색과 근거 채택은 수행하지 않았습니다.']
    receipt=p.provider.record_local({'agent_status':state['status'],'provider_receipts':state['provider_receipts'],'source_ids':list(contexts),'source_verification':'article identity and original source text; semantic entailment not certified'})
    result={'schema_version':'term-runtime-v1','id':'answer:'+uuid.uuid4().hex,'scope':plan['scope'],
            'query_id':plan['id'],'generation_id':p.store.manifest['generation_id'],
            'source_store_sha256':p.store.manifest['store_sha256'],'text':'\n\n'.join(texts+unresolved),
            'claims':claims,'unresolved':[{'reason':t} for t in unresolved],'provider_receipt':receipt}
    navigation = state.get('navigation_output')
    if navigation and state.get('implementation') == 'document-navigation-v1':
        result['text'] = navigation['text']
        result['unresolved'] = [{'reason': x} for x in navigation['unresolved']]
    if state.get('reference_terms'):
        result['text'] = '\n\n'.join(x for x in (result['text'], reference_note(state['reference_terms'])) if x)
    p.contracts.validate(result,'urn:8-agent:term-runtime-v1','Answer');return result

REFERENCE_SOURCE_NAMES={'econedu':'경제교육 경제용어사전','nts':'국세청 세무용어사전','bok':'한국은행 경제금융용어',
                        'kofia':'금융투자협회 용어집','krx':'한국거래소 용어사전'}

def reference_note(rows):
    """Orphan glossary headwords: the source definition as a labelled note, never a claim."""
    lines=['참고 용어 설명 (공개 용어사전 설명이며 선택한 문서의 근거가 아닙니다)']
    for r in rows:
        name=REFERENCE_SOURCE_NAMES.get(r['source'],r['source'])
        lines.append('- '+r['label']+' ('+name+'): '+r['definition']+(' …' if r['definition_truncated'] else ''))
        lines.append('  선택한 문서 범위에는 이 용어를 직접 다루는 조문이 없습니다.')
    return '\n'.join(lines)

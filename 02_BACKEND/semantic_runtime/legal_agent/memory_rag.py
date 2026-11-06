"""Seven durable checkpoints over the existing Pipeline, SourceRecall and READ.

No alternate source search, copied legal answer or private-data export policy.
Model invocation and authenticated principal must be injected by the host.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from .schema_preparation import validate
from .corrected_memory import MemoryError, Reenter, encoded, digest, object_schema, array
from .source_recall import SourceRecall
from .source_selection import originals, select_sources
from . import investigation_contracts as ic
from . import completion_contracts as cc
from .completion_execution import CompletionExecution
from .errors import ContractError
from . import output_contract as output
from .. import query_latency as latency

CLAIM=object_schema({'text':{'type':'string'},'source_id':{'type':'string'},'quote':{'type':'string'}})
CLAIM['properties']['evidence']=array(object_schema({'source_id':{'type':'string'},'quote':{'type':'string','minLength':1}}))
ASSESS=object_schema({'claims':array(CLAIM),'limitations':array({'type':'string'})})
ASSESS['properties']['claims']['maxItems']=12
ASSESS['properties']['limitations']['maxItems']=8
ANSWER=object_schema({'text':{'type':'string'},'claims':array(CLAIM),'limitations':array({'type':'string'})})
INTENT=object_schema({'purpose':{'type':'string'},'concepts':array({'type':'string'})})


class SourceInvestigationIncomplete(MemoryError):
    code='SOURCE_INVESTIGATION_INCOMPLETE'
    failure_stage='SELECT'

    def __init__(self,result):
        from .investigation_diagnostics import selection_report
        self.diagnostics=result.get('diagnostics') or selection_report(result)
        causes=', '.join(self.diagnostics['cause_codes']) or 'CAUSE_NOT_RECORDED'
        super().__init__('source investigation incomplete: '+str(result.get('next_action'))+'; causes='+causes)

def evidence_schema(base, sources):
    """The model may cite only current source IDs, never a facts/context label."""
    schema=deepcopy(base)
    ids=list(dict.fromkeys(s['source_id'] for s in sources))
    if not ids:raise MemoryError('no current originals for supported claims')
    schema['properties']['claims']['minItems']=1
    schema['properties']['claims']['items']['properties']['source_id']['enum']=ids
    schema['properties']['claims']['items']['properties']['evidence']=array(object_schema({'source_id':{'type':'string','enum':ids},'quote':{'type':'string','minLength':1}}))
    return schema



class NativeRag:
    def __init__(self,pipeline,runtime,invoke):
        self.pipeline=pipeline;self.runtime=runtime;self.invoke=invoke
        self.binding={'generation':pipeline.store.manifest['generation_id'],
            'store_sha256':pipeline.store.manifest['store_sha256'],
            'configuration':digest(pipeline.term_agent.config),
            'unit_index_sha256':getattr(pipeline.term_agent,'unit_fulltext',None).manifest['index_sha256'] if getattr(pipeline.term_agent,'unit_fulltext',None) else None}
    def catalogue(self,documents):
        known={r['document_id']:r['name'] for r in self.pipeline.store.db.execute('SELECT document_id,name FROM document')}
        if set(documents)-set(known):raise MemoryError('principal includes unknown documents')
        return [{'id':d,'name':known[d]} for d in documents]
    def question(self,state):
        # The current state is the question. Earlier failed instructions never enter retrieval.
        text=state['task']
        if state['facts']:text+='\n현재 사실: '+encoded(state['facts'])
        return text
    def retrieval_question(self,state):
        """Search typed task/fact values; JSON labels belong to model context."""
        values=[state['task']]
        values.extend(fact['value'] for fact in state['facts']
                      if fact['value'] is not None and fact['value'].strip())
        return '\n'.join(dict.fromkeys(values))
    def documents(self,state,principal):
        docs=state['document_ids']
        if not docs or not set(docs)<=set(principal['document_ids']):raise MemoryError('current document scope inaccessible')
        if state['source_category']!='ALL':
            from ..folder_navigation import load_origin_projection,bind_catalogue
            from types import SimpleNamespace
            projection=load_origin_projection(self.pipeline.contracts.root,self.pipeline.term_agent.config,self.pipeline.store)
            catalogue=bind_catalogue(SimpleNamespace(),self.pipeline.store,projection).document_catalogue
            docs=[d for d in docs if catalogue[d]['category']==state['source_category']]
            if not docs:raise MemoryError('category has no accessible documents')
        return docs
    @contextmanager
    def open(self,state,principal,body):
        p=self.pipeline;question=self.retrieval_question(state);docs=self.documents(state,principal)
        query=p.plan(question,docs)
        request={'question':question,'document_ids':docs,'use_llm':False}
        with p.term_agent.open_session(request,query=query,runtime=self.runtime) as session:
            session.work.event('MEMORY_REQUEST_BINDING',{'request_id':body['request_id'],'session_id':body['session_id'],'user_id':principal['user_id'],'team_id':principal['team_id']})
            execution=NativeExecution(self,session,state,principal)
            yield execution
            session.check_sources_unchanged()
    @latency.timed('law.evidence.verify')
    def verify(self,read):
        if read['binding']!=self.binding:raise MemoryError('cached source generation changed')
        for e in read['evidence']:
            if e['generation_id']!=self.binding['generation']:raise MemoryError('foreign cached generation')
            for span in e['spans']:
                raw=self.pipeline.store.source(e['document_id'],span['block_id'])
                if raw['source_artifact_sha256']!=e['source_artifact_hash'] or raw['text'][span['start_cp']:span['end_cp']]!=span['text'] or hashlib.sha256(raw['text'].encode()).hexdigest()!=span['block_hash']:
                    raise MemoryError('cached evidence changed')

class NativeExecution(CompletionExecution):
    @staticmethod
    def completion_limits(parts, limitations):
        values=list(dict.fromkeys(list(limitations)+parts.get('SELECT',{}).get('payload',{}).get('completion_limitations',[])))
        return values if len(values)<=8 else values[:7]+['\n'.join(values[7:])]
    def __init__(self,host,session,state,principal):
        self.host=host;self.s=session;self.state=state;self.principal=principal
    def selected_originals(self,parts):
        from .unit_reading import selected_originals
        selected=parts['SELECT']['payload']
        if selected.get('selected_evidence') is not None:
            self.host.verify({'binding':parts['READ']['payload']['binding'],'evidence':selected['selected_evidence']})
        return selected_originals(parts)

    @property
    def control(self):
        return getattr(getattr(self.s,'sources',None),'profile',{}).get('candidate_navigation',{}).get('investigation_control',False)
    @property
    def completion(self):
        return cc.enabled(self.s.sources.profile)
    def schema(self,stage):
        from .source_handoff import enabled as source_mode,schema as source_schema
        if stage=='SELECT' and source_mode():return source_schema()
        if stage=='INTENT':
            value=ic.intent_schema(INTENT) if self.control else INTENT
            if self.completion:
                value=deepcopy(value)
                if cc.version(self.s.sources.profile) in (cc.V5,cc.V6,cc.V7,cc.V8):
                    from .completion_v5 import intent_schema
                    value=intent_schema(value)
                value['properties'].update(completion_contract={'const':cc.version(self.s.sources.profile)},request_text={'type':'string'},request_hash={'type':'string'})
                value['required'] += ['completion_contract','request_text','request_hash']
            return value
        if stage=='ASSESS':
            if not self.control:return ASSESS
            value=ic.assess_schema(ASSESS,getattr(self,'issues',[{'id':'Q1'}]),getattr(self,'saved_material_ids',[]))
            value['properties'].update(answer_coverage={'type':'string'},semantic_quality_certified={'type':'boolean'})
            return cc.internal_schema(value,'ASSESS') if self.completion else value
        if stage=='COMPOSE':return cc.internal_schema(ANSWER,'COMPOSE') if self.completion else ANSWER
        return {'type':'object'}
    def invoke(self,system,data,schema,phase,*,timeout=None):
        # Actual source/selection payloads are receipted in the native work journal.
        with latency.span('model.input_journal',phase=phase):
            self.s.work.event('MEMORY_MODEL_INPUT',{'phase':phase,'input_sha256':digest(data),'data':data})
        import inspect
        options={'timeout':timeout} if timeout is not None and 'timeout' in inspect.signature(self.host.invoke).parameters else {}
        out=self.host.invoke(system,data,schema,phase,**options)
        with latency.span('model.output_validate',phase=phase):
            validate(out,schema,owner=self.s)
        with latency.span('model.output_journal',phase=phase):
            self.s.work.event('MEMORY_MODEL_OUTPUT',{'phase':phase,'output':out})
        return out
    def verify_claims(self,claims,sources):
        by_id={s['source_id']:s for s in sources}
        if not claims:raise MemoryError('judgment contains no supported claims')
        for i,claim in enumerate(claims):
            if claim.get('span_receipts'):
                cc.verify_span_claim(claim, sources)
            for extra in claim.get('evidence',[]):
                self.verify_claims([{'text':claim['text'],**extra}],sources)
            if claim['source_id'] not in by_id:
                raise MemoryError(f'unsupported claim[{i}]: source_id {claim["source_id"]!r} is not an offered original. Allowed: {list(by_id)}. current_facts is user context, not a legal source; cite the legal rule for its application to the facts.')
            if not claim['quote'].strip() or claim['quote'] not in by_id[claim['source_id']]['text'] or not claim['text'].strip():
                raise MemoryError(f'unsupported claim[{i}]: quote must be an exact nonempty substring of the offered original {claim["source_id"]}; factual context cannot be quoted as legislation')
    def stage(self,stage,state,parts,utterance,format):
        with latency.span('law.native.'+stage, phase=stage, pressure=True):
            return self._stage(stage,state,parts,utterance,format)

    def _stage(self,stage,state,parts,utterance,format):
        data={'question':self.host.question(state),'current_facts':state['facts'],
              'dialogue':deepcopy(getattr(self,'guidance_dialogue',[]))}
        chain=parts.get('SELECT',{}).get('payload',{}).get('investigation_chain')
        if chain:data['investigation_chain']=chain
        if self.completion and stage in ('INTENT','ASSESS','COMPOSE'):
            result=self.completion_stage(stage,state,parts,utterance,format,data)
            self.s.work.event('MEMORY_STAGE_COMPLETE',{'stage':stage,'payload':result})
            return result
        if stage=='INTENT':
            wire=self.schema('INTENT')
            def check_intent(value):
                output.validate_shape(value,wire)
                if self.control and len({i['id'] for i in value['issues']})!=len(value['issues']):
                    raise output.OutputContractError('duplicate issue ID',[output.issue('DUPLICATE_ISSUE_ID','/issues')],category='DECISION_CONFLICT')
            result=output.bounded_decision(self.s.work,'request-intent',data,wire,
                lambda payload,attempt:self.invoke('현재 목적의 개념명을 추출한다. 조건·과거 오답을 개념으로 승인하지 않는다. purpose는 수행 목적이며 concepts는 검색용 개념명이다. issues가 요구되면 원문 질문을 대상·요구별로 나누어 Q1부터 순서대로 기록한다. 원문 요구나 명시 범위를 삭제하지 않는다. JSON만 출력한다.',payload,wire,'memory-intent' if not attempt else 'memory-intent-repair'),check_intent)
        elif stage=='PLAN':
            result={'query':self.s.context.query,'queries':state['queries'] or [state['task']],
                'law_names':[self.s.sources.matcher.documents[d['id']] for d in self.s.sources.matcher.document_starts(self.host.question(state),self.s.sources.scope)],'binding':self.host.binding}
        elif stage=='RECALL':
            self.s.sources.recall_query_plan={k:parts['PLAN']['payload'][k] for k in ('law_names','queries')}
            extra=getattr(self.s.sources,'additional_recall_queries',[])
            if extra:self.s.sources.recall_query_plan['queries']=list(dict.fromkeys(self.s.sources.recall_query_plan['queries']+extra))
            selected,receipt=SourceRecall(self.s.sources).discover()
            result={'selected_for_read':selected,'discovery':receipt,'corpus_ids':sorted(self.s.sources.tools.sources),'binding':self.host.binding}
        elif stage=='READ':
            recall=parts['RECALL']['payload'];r=SourceRecall(self.s.sources)
            r.discover=lambda:(recall['selected_for_read'],recall['discovery'])
            record=r.prepare();record['evidence']=self.s.work.evidence()
            source_map=originals(record)
            if not source_map and not record.get('law_navigation'):raise MemoryError('no complete originals acquired')
            result={'record':record,'originals':list(source_map.values()),'evidence':record['evidence'],'binding':self.host.binding}
            self.host.verify(result)
        elif stage=='SELECT':
            read=parts['READ']['payload'];self.host.verify(read)
            if self.control:
                self.issues=parts['INTENT']['payload'].get('issues',[{'id':'Q1','question':self.host.question(state)}])
                self.s.sources.investigation_issues=self.issues
            progress=getattr(self,'selection_progress',None)
            evidence=list(getattr(self,'selection_progress_evidence',[]))
            prior_route=False
            if self.control and not progress:
                # Only a user re-entry reaches SELECT without this request's own checkpoint.
                progress=deepcopy(parts.get('SELECT',{}).get('payload',{}).get('investigation_state'))
                prior_route=bool(progress)
                if progress and getattr(self,'assessment_gaps',None):progress['assessment_gaps']=deepcopy(self.assessment_gaps)
            self.s.sources.investigation_prior_route=prior_route
            self.s.sources.investigation_hints=getattr(self,'investigation_hints',None)
            self.s.sources.guidance_dialogue=deepcopy(getattr(self,'guidance_dialogue',[]))
            self.s.sources.continuation_request=deepcopy(getattr(self,'continuation_request',None))
            if progress:
                records=list(progress.get('working',{}).get('unit_reads',[]))
                records+=list(progress.get('batch',{}).get('selected',{}).values())
                records+=list((progress.get('previous') or {}).get('_selected_units',{}).values())
                records+=list(progress.get('selected',{}).values())+list(progress.get('contexts',{}).values())+list(progress.get('material_history',{}).values())
                evidence.extend(e for r in records for e in r['evidence']
                                if not prior_route or e['document_id'] in set(self.s.sources.scope))
            if evidence:
                evidence=list({e['evidence_id']:e for e in evidence}.values())
                self.host.verify({'binding':read['binding'],'evidence':evidence})
                self.s.work.record_observation({'tool':'selection_progress_restore','args':{'binding':digest(read['binding'])}},
                    {'status':'REUSED'},evidence,verify=self.s.sources.source.verify)
            record={**read['record'],'query_plan':{k:parts['PLAN']['payload'][k] for k in ('law_names','queries')},
                    'current_request':utterance}
            if record.get('unit_read_contract')=='unit-read-v1':
                from .unit_reading import read_state
                read_state(self.s.sources,getattr(self,'selection_read_state',{}))
                self.s.sources._unit_read_checkpoint=getattr(self,'save_selection_evidence',None)
            def select(system,data,schema,phase,timeout):
                from copy import deepcopy
                wire=deepcopy(schema)
                legacy=not self.control and not phase.startswith(('source-law-','source-reference-'))
                if legacy and 'choices' in wire.get('properties',{}):
                    item=wire['properties']['choices']['items']
                    item['properties'].pop('status',None)
                    item['required']=[k for k in item['required'] if k!='status']
                raw=self.invoke(system,data,wire,phase,timeout=timeout)
                if legacy:
                    for item in raw.get('choices',[]):item.setdefault('status','ADOPT')
                if phase.startswith('source-reference-') or phase.startswith('source-law-') or phase=='source-reason-decision-review':
                    return raw  # Group coverage and READ scopes are validated by navigation.
                # Schema enforces offered IDs and the original physical choice budget.
                # Preserve MAIN's stricter selector; only this audited adapter coalesces.
                seen={};choices=[]
                for item in raw['choices']:
                    if item['id'] in seen:
                        if seen[item['id']]!=item:
                            from .output_contract import DecisionConflict,issue
                            raise DecisionConflict('conflicting decisions for the same offered source',
                                [issue('CONFLICTING_SOURCE_CHOICES','/choices')])
                    else:
                        choices.append(item);seen[item['id']]=item
                if len(choices)!=len(raw['choices']):
                    self.s.work.event('MEMORY_SELECTION_COALESCED',{'phase':phase,'raw':raw,'executed_choices':choices})
                return {**raw,'choices':choices}
            seconds=max(1,self.s.context.remaining()-30) if record.get('law_navigation') else 240
            result=select_sources(self.host.question(state),record,select,remaining_seconds=seconds, session=self.s.sources,
                checkpoint=progress,
                on_checkpoint=getattr(self,'save_selection_progress',None))
            if result.get('terminal')=='SOURCE_HANDOFF':return result
            from .guided_navigation import waiting, enabled as guided_navigation_enabled, BOUNDED_STOPS as GUIDED_BOUNDED_STOPS
            if waiting(result) or (guided_navigation_enabled(self.s.sources.profile) and
                    result.get('stop_reason') in ('MODEL_DECISION_UNRESOLVED',)+GUIDED_BOUNDED_STOPS):
                return result
            if result.get('status')=='pending' and not result.get('needs_fulltext'):
                failure=SourceInvestigationIncomplete(result)
                self.s.work.event('SOURCE_INVESTIGATION_INCOMPLETE',failure.diagnostics)
                if self.completion:
                    from .errors import InvestigationPending
                    raise InvestigationPending('질문에 필요한 원문 조사가 완료되지 않았습니다.',
                        diagnostics={**failure.diagnostics,'resume_available':False,'stop_reason':result.get('stop_reason')})
                raise failure
            if result.get('needs_fulltext') or (not result['final_ids'] and read['record'].get('discovery_mode')=='structure'):
                if result.get('law_navigation'):
                    self.s.sources.law_search_queries=result['search_queries']
                    self.s.work.event('MEMORY_FULLTEXT_REENTRY',{'reason':'law navigation requested a new fulltext expression','selection':result})
                    raise Reenter('RECALL','law navigation requested additional originals',result)
                prior=set(getattr(self.s.sources,'recall_query_plan',parts['PLAN']['payload']).get('queries',[]))
                fresh=[q for q in result.get('search_queries',[]) if q.strip() and q not in prior]
                if read['record'].get('discovery_mode')=='fulltext' and not fresh:
                    raise MemoryError('source investigation incomplete: new search requires a changed query')
                if getattr(self.s.sources,'force_fulltext_recall',False) and not fresh:
                    raise MemoryError('source investigation remains unresolved: unchanged search is not repeated')
                self.s.sources.additional_recall_queries=list(dict.fromkeys(getattr(self.s.sources,'additional_recall_queries',[])+fresh))
                self.s.sources.force_fulltext_recall=True
                self.s.work.event('MEMORY_FULLTEXT_REENTRY',{'reason':result.get('fallback_reason'),'selection':result})
                raise Reenter('RECALL','source selection requested additional originals',result)
            if not result['final_ids']:raise MemoryError('no relevant source selected; current question is pending')
        elif stage=='ASSESS':
            read=parts['READ']['payload'];self.host.verify(read)
            selected=parts['SELECT']['payload']['final_ids'];sources=[s for s in self.selected_originals(parts) if s['source_id'] in selected]
            selection=parts['SELECT']['payload']
            data['investigation_limitations']=selection.get('completion_limitations',[])
            if self.control:
                self.issues=selection.get('issues',[{'id':'Q1','question':data['question']}])
                self.saved_material_ids=[r['material_id'] for r in selection.get('saved_inventory',[])]
                data.update(issues=self.issues,saved_inventory=selection.get('saved_inventory',[]),
                    reference_navigation={k:v for k,v in selection.get('reference_navigation',{}).items() if k in ('pending','groups','unresolved','limits')},
                    reentry_budget=getattr(self,'reentry_counters',{}),
                    evidence_rule='saved_inventory is metadata, not quote evidence; reinspection must deliver original text before adoption',
                    issue_assessment_origin='MODEL_ASSESSMENT; semantic_quality_certified=false')
            assessment_schema=evidence_schema(ASSESS,sources)
            if self.control:assessment_schema=ic.assess_schema(assessment_schema,self.issues,self.saved_material_ids)
            def check_assessment(value):
                output.validate_shape(value,assessment_schema)
                if self.control:
                    try:ic.validate_assessment(value,self.issues,self.saved_material_ids)
                    except ContractError as exc:
                        raise output.OutputContractError(str(exc),[output.issue('ASSESSMENT_FIELDS_CONFLICT')],category='DECISION_CONFLICT') from exc
                try:
                    if value['claims']:self.verify_claims(value['claims'],sources)
                    elif not self.control:raise MemoryError('judgment contains no supported claims')
                except MemoryError as exc:
                    raise output.OutputContractError(str(exc),[output.issue('CLAIM_EVIDENCE_INVALID','/claims')],category='EVIDENCE_CONTRACT_INVALID') from exc
            result=output.bounded_decision(self.s.work,'assessment',{**data,'current_request':utterance,'sources':sources,'repair_feedback':None},assessment_schema,
                lambda payload,attempt:self.invoke(('쟁점별 status와 핵심 gaps를 기록한다. 저장되었지만 미채택한 자료를 원문 없음으로 표현하지 않는다. 보완 가능한 원문 부족은 NEEDS_INVESTIGATION, 사용자 사실 부족은 LIMITED_ANSWER와 조건부 법률 판단이다. 더 조사할 필요가 없으면 ANSWER 또는 LIMITED_ANSWER다. 무관한 미해결 연결을 일반 경고로 반복하지 않는다. 사용자가 항·호를 한정하지 않은 질문을 현재 제공된 한 항으로 임의 제한하지 않는다. 해당 규칙에 관한 다른 항의 추가 요건·예외·조건부 분기가 미열람이면 MISSING_SCOPE 또는 MISSING_SOURCE gap으로 원문 조사를 재개한다. 원문에서 확인한 조건부 추가 요건은 사건 사실이 없어도 조건과 함께 설명한다. 요구 사항을 답변 범위 밖으로 돌려 limitations에만 넣은 상태를 COVERED나 ANSWER로 표시하지 않는다. ' if self.control else '')+'현재 목적·사실과 제공된 원문으로만 판단한다. current_request는 이번 사용자의 원문 요청이다. 요약 question보다 이번 요청의 판단 범위·제외 범위·미확인 사항을 우선 보존한다. 특정 금지의 대상에서 제외됨이나 필요조건 하나의 충족을 전체 행위의 허용·적법성·충분조건으로 역추론하지 않는다. 판단 범위 밖이거나 미확인인 요건은 충족됐다고 쓰지 말고 claims의 결론 자체를 제한하고 limitations에도 명시한다. current_facts는 사용자가 제공한 판단 전제이며 법령 출처가 아니다. claims에는 원문 규칙과 그 규칙을 현재 사실에 적용한 판단을 기록한다. 사실만 진술하는 별도 claim이나 current_facts라는 출처를 만들지 않는다. source_id는 sources에 제공된 ID 중에서만 고른다. 원칙과 단서, 위임된 세칙의 예외를 함께 검토한다. claims의 text는 판단, source_id는 실제 원문 ID, quote는 해당 원문에서 한 글자도 바꾸지 않고 그대로 복사한 인용이다. 현재 사실에 없는 자격이나 기간은 확정하지 말고 조건부 결론과 limitations에 남긴다. 과거 정답은 사용하지 않는다. repair_feedback이 있으면 지적된 잘못을 원문으로 수정한다. JSON만 출력한다.',payload,assessment_schema,'memory-assess' if not attempt else 'memory-assess-repair'),check_assessment)
            self.s.work.event('MEMORY_SEMANTIC_REVIEW_SKIPPED',{'stage':stage,'policy':'disabled','payload_sha256':digest(result),'quality_certified':False})

            if self.control:
                actionable=[g for g in result['gaps'] if g['kind']!='MISSING_FACT']
                count=getattr(self,'reentry_counters',{}).get('ASSESS_GAP_REENTRY',0)
                limit=self.s.sources.profile['candidate_navigation']['assessment_reentry_limit']
                if result['disposition']=='NEEDS_INVESTIGATION' and actionable and count<limit:
                    raise Reenter('SELECT','assessment requires additional delivered evidence',{'reentry_kind':'ASSESS_GAP_REENTRY','gaps':actionable,'assessment':result,'investigation_state':selection['investigation_state']})
                if result['disposition']=='NEEDS_INVESTIGATION':
                    if not result['claims']:raise MemoryError('assessment budget exhausted without supported claims')
                    result['disposition']='LIMITED_ANSWER'
                keys=set();gaps=[]
                for g in result['gaps']:
                    key=digest([g['issue_id'],g['kind'],g['material_id']])
                    if key not in keys:gaps.append(g);keys.add(key)
                result.update(gaps=gaps,answer_coverage=ic.coverage(result),semantic_quality_certified=False)
                result['limitations']=list(dict.fromkeys(result['limitations']+[g['reason'] for g in gaps]))
            result['limitations']=self.completion_limits(parts,result['limitations'])
        else:
            assessment=parts['ASSESS']['payload'];read=parts['READ']['payload'];self.host.verify(read)
            sources=[s for s in self.selected_originals(parts) if s['source_id'] in parts['SELECT']['payload']['final_ids']]
            display_data={**data,'state_authority':'current_facts is the current case state; historical events are not alternative facts','response_purpose':'current legal answer only; history is served by HISTORY_EXPLAIN'}
            wire=evidence_schema(ANSWER,sources)
            def check_composition(value):
                output.validate_shape(value,wire)
                try:
                    self.verify_claims(value['claims'],sources)
                    if value['claims']!=assessment['claims'] or value['limitations']!=assessment['limitations']:raise MemoryError('composer changed judgment')
                    if not value['text'].strip():raise MemoryError('empty answer')
                except MemoryError as exc:
                    raise output.OutputContractError(str(exc),[output.issue('COMPOSITION_JUDGMENT_CONFLICT')],category='DECISION_CONFLICT') from exc
            from .answer_stream import current_sink
            result=output.bounded_decision(self.s.work,'composition',{**display_data,'utterance':utterance,'format':format,'assessment':assessment,'sources':sources,'repair':None},wire,
                lambda payload,attempt:self.invoke('현재 판단·조건·출처를 유지해 최종 답변을 작성한다. assessment.limitations의 판단 범위와 미확인 사항을 본문에도 빠짐없이 반영한다. 제한된 결론을 전체 행위의 허용으로 확대하지 않는다. table이면 Markdown 표로 쓴다. claims는 assessment.claims를 그대로 복사한다. 원문 인용과 판단을 바꾸지 않는다. 현재 사용자 표현 요청을 반영하되 추가 조건을 만들지 않는다. 이번 응답은 현재 판단만 설명한다. 정정 횟수·과거 조사 경위·과거 상태를 추측해 쓰지 않는다. 이력 설명은 별도 HISTORY_EXPLAIN에서 처리된다. 일반 규칙의 대상별 설명과 현재 사건의 사실 단정을 구분한다. 원문에 있는 규칙·단서·조건부 분기를 설명하는 것은 사건 사실을 추가하는 행위가 아니다. JSON만 출력한다.',payload,wire,'memory-compose' if not attempt else 'memory-compose-repair'),check_composition,
                can_repair=lambda:not (current_sink() and getattr(current_sink(),'started',False)))
            self.s.work.event('FINAL_REVIEW_SKIPPED',{'stage':stage,'policy':'disabled','payload_sha256':digest(result),'claim_review_status':'UNREVIEWED','quality_certified':False})
        self.s.work.event('MEMORY_STAGE_COMPLETE',{'stage':stage,'payload_sha256':digest(result)})
        return result

"""Current-source rebind for optional wiki hints, procedures and reviewed claims."""
import json
from .unified_rag import UnifiedExecution
from .reuse_policy import evaluate, execute_procedure
from .corrected_memory import MemoryError, digest

READ_SCHEMA={'type':'object','properties':{'document_id':{'type':'string'},'unit_id':{'type':'string'}},'required':['document_id','unit_id'],'additionalProperties':False}
CATALOGUE={'read_durable_unit':{'read_only':True,'schema':READ_SCHEMA}}


class WikiExecution(UnifiedExecution):
    def invoke(self,system,data,schema,phase,*,timeout=None):
        from . import wiki_recall
        if phase=='memory-intent' and wiki_recall.enabled(self.host):
            values=wiki_recall.offer(self.host,self.principal,self.host.question(self.state),self.s.sources.scope,self.s.work.event)
            data,schema=wiki_recall.augment(data,schema,values)
            result=super().invoke(system+(wiki_recall.PROMPT if values else ''),data,schema,phase,timeout=timeout)
            ids=result.pop('history_ids',[])
            if values:wiki_recall.choose(self.host,ids,self.s.work.event)
            return result
        if self.host.shortcut_flags.get('core_evidence_route') or self.host.shortcut_flags.get('basis_live'):
            # Core routes replace replaying every historical exploration choice.
            return super().invoke(system,data,schema,phase,timeout=timeout)
        memory=getattr(self.host,'procedure',None)
        reusable=(phase=='memory-intent' or phase.startswith('source-'))
        if memory is None or not reusable:return super().invoke(system,data,schema,phase,timeout=timeout)
        # The complete current menu, prompt and schema bind cached choices.
        # IDs are never reused against a changed menu, including reference scopes.
        contract={'system':system,'data':data,'schema':schema}
        prior,deviation=memory.lookup(phase,self.state['task'],contract)
        unexpected=getattr(self,'procedure_deviation',None)
        if prior is not None and unexpected is None:
            from jsonschema import validate
            validate(prior,schema)
            self.s.work.event('MEMORY_MODEL_REPLAY',{'phase':phase,'output':prior,
                                                  'input_sha256':digest(contract)})
            return prior
        if unexpected or (deviation and deviation['status']=='DEVIATION'):
            data={**data,'procedure_deviation':unexpected or deviation,
                  'instruction':'Stored procedure expectation changed. Judge current input only; explain the current choice.'}
        result=super().invoke(system,data,schema,phase,timeout=timeout)
        memory.save(phase,self.state['task'],contract,result,decision='MODEL_ON_DISCOVERY_OR_DEVIATION')
        self.procedure_deviation=None
        return result

    def current_source(self, member):
        repo=self.host.shortcut
        row=repo.db.execute('SELECT payload FROM sw_source WHERE id=?',(member['ref'],)).fetchone()
        if not row:return False
        source=json.loads(row[0]);store=self.host.pipeline.store
        return (source['document_id'] in self.principal['document_ids'] and
                source['generation']==store.manifest['generation_id'] and
                source['version']==store.manifest['store_sha256'])

    def plans(self):
        repo=self.host.shortcut
        if not self.principal.get('authenticated') or self.host.shortcut_flags.get('basis_live'):return []
        # Use this goal's effective facts only. Predicates in another branch of
        # the same investigation cannot supply an unstated current precondition.
        import re
        facts={}
        for item in self.state.get('facts',[]):
            raw=item['value'];value={'kind':'string','value':raw}
            match=re.fullmatch(r'(\d+)\s*(개월|년|일)',raw)
            if match:value={'kind':'duration','value':int(match[1]),'unit':{'개월':'month','년':'year','일':'day'}[match[2]]}
            facts[item['name']]=value
        plans=[]
        # Common source routes are resolved directly in RECALL. They must not
        # consume the bounded menu for private procedures and reviewed claims.
        for unit in repo.search(self.principal,limit=8,include_common=False)['pages']:
            if unit.get('core_evidence_route'):continue
            flags=dict(self.host.shortcut_flags)
            # A semantic topic match alone cannot license reusing a conclusion.
            if unit['question'].strip()!=self.state['task'].strip():flags['judgment']=False
            receipt=evaluate(repo,unit['unit_id'],unit['revision'],self.principal,request=self.s.context.run_id,
                             facts=facts,source_check=self.current_source,catalogue=CATALOGUE,flags=flags)
            if receipt['mode']!='NONE':plans.append((unit,receipt,facts))
        return plans

    def stage(self,stage,state,parts,utterance,format):
        if stage=='SELECT' and self.host.shortcut_flags.get('core_evidence_route') and parts.get('SELECT'):
            # A new READ after a user replan must not revive FINISH from an
            # older selection. Actual in-request recovery still has its own
            # selection_progress and retains the existing checkpoint protocol.
            old=self.host.shortcut.db.execute('SELECT parent FROM node WHERE id=?',(parts['SELECT']['id'],)).fetchone()
            if old and old['parent']!=parts['READ']['id']:
                previous=dict(parts['SELECT']['payload'])
                from .workflow_execution import has_reentry
                if not has_reentry():previous.pop('investigation_state',None)
                parts={**parts,'SELECT':{**parts['SELECT'],'payload':previous}}
                self.s.work.event('CORE_ROUTE_CURRENT_SELECTION',{'reason':'current READ replaces older completed selection',
                    'read_node':parts['READ']['id']})
        if stage=='RECALL' and self.host.shortcut_flags.get('core_evidence_route') and not self.host.shortcut_flags.get('basis_live'):
            from .core_evidence_route import lookup
            path=lookup(self.host,state,self.principal,question=utterance)
            from . import wiki_recall
            if not path and wiki_recall.enabled(self.host) and getattr(self.host,'wiki_recall_selected',[]):
                path=wiki_recall.selected_route(self.host,self.principal,state,self.s.work.event)
            if path and not (getattr(self.s.sources,'law_search_queries',None) or getattr(self.s.sources,'force_fulltext_recall',False)):
                self.s.sources.core_evidence_route=path
        plans=self.plans() if stage in ('PLAN','ASSESS') and not self.host.shortcut_flags.get('bounded_recall') else []
        if stage=='PLAN':
            for unit,receipt,facts in plans:
                if receipt['mode'] not in ('PROCEDURE','JUDGMENT'):continue
                for procedure in unit['procedures']:
                    def execute(tool,args):
                        if tool!='read_durable_unit' or args['document_id'] not in self.s.sources.scope:raise MemoryError('unapproved procedure tool')
                        node=self.s.sources.source.node(args['document_id'],args['unit_id'])
                        return self.s.sources.source.execute({'tool':'read_node','args':{'node':node,'cursor':None},'reason':'verified wiki procedure: current source re-read'})
                    outcome=execute_procedure(procedure,inputs=facts,catalogue=CATALOGUE,execute=execute,
                        verify_result=lambda check,r:check=='complete_source' and r.get('status')=='OK' and r.get('coverage',{}).get('complete') is True,
                        current_check=lambda:self.host.shortcut.current(unit['unit_id'],unit['revision'],self.principal) is not None)
                    self.s.work.event('WIKI_PROCEDURE_USED',{'unit':unit['unit_id'],'revision':unit['revision'],'outcome':outcome})
        if stage=='ASSESS' and not self.control:
            originals=[s for s in self.selected_originals(parts) if s['source_id'] in parts['SELECT']['payload']['final_ids']]
            for unit,receipt,facts in plans:
                if receipt['mode']!='JUDGMENT':continue
                claims=[]
                for claim in unit['claims']:
                    if not claim.get('quote'):break
                    candidates=[]
                    for ref in claim['evidence_refs']:
                        source=json.loads(self.host.shortcut.db.execute('SELECT payload FROM sw_source WHERE id=?',(ref,)).fetchone()[0])
                        candidates += [s for s in originals if s['document_id']==source['document_id'] and
                                       (s.get('unit_id') or s['source_id'])==source['coordinate'] and claim['quote'] in s['text']]
                    if len(candidates)!=1:break
                    claims.append({'text':claim['statement'],'source_id':candidates[0]['source_id'],'quote':claim['quote']})
                if len(claims)==len(unit['claims']) and claims:
                    self.host.shortcut.current(unit['unit_id'],unit['revision'],self.principal)
                    self.verify_claims(claims,originals)
                    self.domain_choice=self.host.domain.select(stage,state,self.s)
                    payload={'claims':claims,'limitations':self.completion_limits(parts,unit['unresolved'])}
                    self.record(stage,payload,origin={'unit_id':unit['unit_id'],'revision':unit['revision'],'hash':unit['hash']})
                    self.s.work.event('WIKI_JUDGMENT_USED',{'unit_id':unit['unit_id'],'revision':unit['revision'],'hash':unit['hash']})
                    return payload
        result=super().stage(stage,state,parts,utterance,format)
        memory=getattr(self.host,'procedure',None)
        if memory and not self.host.shortcut_flags.get('core_evidence_route') and stage in ('PLAN','RECALL','READ'):
            if stage=='PLAN':actual={k:result[k] for k in ('queries','law_names','binding')}
            elif stage=='RECALL':actual={'selected_for_read':result['selected_for_read'],
                                        'discovery':result['discovery'],'binding':result['binding']}
            else:actual={'originals':[{'document_id':s['document_id'],'unit_id':s.get('unit_id'),
                          'text_hash':digest(s['text'])} for s in result['originals']],
                         'binding':result['binding']}
            deviation=memory.observe(stage,state['task'],actual)
            if deviation:self.procedure_deviation=deviation
        return result

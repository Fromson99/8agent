"""Current-source rebind for optional wiki hints, procedures and reviewed claims."""
import json
from .unified_rag import UnifiedExecution
from .reuse_policy import evaluate, execute_procedure
from .corrected_memory import MemoryError, digest

READ_SCHEMA={'type':'object','properties':{'document_id':{'type':'string'},'unit_id':{'type':'string'}},'required':['document_id','unit_id'],'additionalProperties':False}
CATALOGUE={'read_durable_unit':{'read_only':True,'schema':READ_SCHEMA}}


class WikiExecution(UnifiedExecution):
    def invoke(self,system,data,schema,phase,*,timeout=None):
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
        if not self.principal.get('authenticated'):return []
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
        for unit in repo.search(self.principal,limit=8)['pages']:
            flags=dict(self.host.shortcut_flags)
            # A semantic topic match alone cannot license reusing a conclusion.
            if unit['question'].strip()!=self.state['task'].strip():flags['judgment']=False
            receipt=evaluate(repo,unit['unit_id'],unit['revision'],self.principal,request=self.s.context.run_id,
                             facts=facts,source_check=self.current_source,catalogue=CATALOGUE,flags=flags)
            if receipt['mode']!='NONE':plans.append((unit,receipt,facts))
        return plans

    def stage(self,stage,state,parts,utterance,format):
        plans=self.plans() if stage in ('PLAN','ASSESS') else []
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
        if memory and stage in ('PLAN','RECALL','READ'):
            if stage=='PLAN':actual={k:result[k] for k in ('queries','law_names','binding')}
            elif stage=='RECALL':actual={'selected_for_read':result['selected_for_read'],
                                        'discovery':result['discovery'],'binding':result['binding']}
            else:actual={'originals':[{'document_id':s['document_id'],'unit_id':s.get('unit_id'),
                          'text_hash':digest(s['text'])} for s in result['originals']],
                         'binding':result['binding']}
            deviation=memory.observe(stage,state['task'],actual)
            if deviation:self.procedure_deviation=deviation
        return result

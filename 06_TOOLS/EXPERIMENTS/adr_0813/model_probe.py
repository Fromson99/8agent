"""Frozen fictional COMPARE probe through the real workflow/gateway journals.

Importing this module never loads credentials or sends a model request. The CLI
requires root's freeze receipt. Source fixtures are explicitly synthetic; this
is not a full corpus/API/GENOS or legal accuracy qualification.
"""
from copy import deepcopy
from importlib import import_module, util
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib
import json
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison'
DESIGN=ADR/'artifacts/design'
AS_OF='2026-10-01'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def put(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def modules():
    return NS(**{key:import_module(name) for key,name in {
        'bridge':'semantic_runtime.workflow_bridge','work':'semantic_runtime.legal_agent.repository',
        'source':'semantic_runtime.legal_agent.source_tools','errors':'semantic_runtime.legal_agent.errors',
        'model_contract':'semantic_runtime.legal_agent.model_contract',
        'local':'semantic_runtime.legal_agent.local_gemma','output':'semantic_runtime.legal_agent.output_contract',
        'repo':'workflow.repository','model':'workflow.adapters.model',
        'contracts':'workflow.risk_team_compare_workflow.contracts',
        'basis':'workflow.risk_team_compare_workflow.basis','compare':'workflow.risk_team_compare_workflow.compare',
        'workflow':'workflow.contracts'}.items()})


def ordered_keys(value,path='$'):
    rows=[]
    if isinstance(value,dict):
        rows.append({'path':path,'keys':list(value)})
        for key,item in value.items():rows.extend(ordered_keys(item,path+'.'+key))
    elif isinstance(value,list):
        for n,item in enumerate(value):rows.extend(ordered_keys(item,path+'['+str(n)+']'))
    return rows


def order_receipt(body):
    schema=((body.get('response_format') or {}).get('json_schema') or {}).get('schema')
    prompts=[]
    for index,message in enumerate(body.get('messages',[])):
        try:value=json.loads(message.get('content',''))
        except (ValueError,TypeError):continue
        prompts.append({'message':index,'keys':ordered_keys(value)})
    return {'schema_keys':ordered_keys(schema),'prompt_keys':prompts,
            'ordered_payload_sha256':hashlib.sha256(json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}


def model_binding(policy):
    return {'provider':'openrouter','model':policy['model'],'adapter_version':'adr0813-common-client-single-send-v1',
        'endpoint_identity':hashlib.sha256(policy['endpoint'].encode()).hexdigest(),
        'trust_zone':'external','max_input_bytes':2_000_000}


class Transport:
    """One physical send; semantic correction belongs only to ModelAdapter."""
    def __init__(self,binding,sender):
        self.binding=deepcopy(binding);self.sender=sender;self.calls=[];self.expected=None
    def validate_authorization(self,context):
        expected=self.expected
        if expected is None or any(context.binding.get(k)!=v for k,v in expected.items()):
            raise modules().errors.ContractError('synthetic fixture authorization changed')
        if context.binding.get('model')!=self.binding or context.binding.get('export_allowed') is not True:
            raise modules().errors.ContractError('synthetic model/export binding changed')
        if context.query['scope']['document_version_ids']!=expected['document_ids']:
            raise modules().errors.ContractError('synthetic source scope changed')
    def send_once(self,*,body,ticket):
        m=modules()
        if len(self.calls)>=2:raise m.errors.BudgetExhausted('frozen physical call limit per case')
        if body.get('model')!=self.binding['model'] or body.get('stream') is not False:
            raise m.errors.ContractError('probe request model/stream binding changed')
        call={'attempt_id':ticket['attempt_id'],'request':deepcopy(body),'request_order':order_receipt(body)}
        self.calls.append(call)
        started=time.monotonic()
        try:
            result=self.sender(body,ticket)
            call['response']=deepcopy(result)
            if isinstance(result.get('body_json'),dict):
                try:
                    content=m.model_contract.structured_content(result['body_json'],require_complete=True)
                    call['response_order']=ordered_keys(m.output.strict_json(content))
                except Exception as exc:
                    # Diagnostics never become a second validation/repair owner.
                    # The unmodified envelope always reaches the real gateway.
                    call['order_diagnostic_error']={'type':type(exc).__name__,'message':str(exc)}
            return result
        except BaseException as exc:
            call['error']={'type':type(exc).__name__,'message':str(exc)}
            raise
        finally:
            call['elapsed_seconds']=time.monotonic()-started
            if hasattr(self.sender,'last_wire_order'):
                call['provider_request_order']=deepcopy(self.sender.last_wire_order)


class FixtureStore:
    def __init__(self,path,case):
        self.db=sqlite3.connect(path);self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE IF NOT EXISTS document(document_id TEXT PRIMARY KEY,json TEXT);'
            'CREATE TABLE IF NOT EXISTS source_block(document_id TEXT,block_id TEXT,text TEXT,source_artifact_sha256 TEXT,PRIMARY KEY(document_id,block_id));')
        self.native={};self.originals=[];m=modules()
        self.generation='synthetic-'+digest(case)
        for side,title in (('internal','모의내규'),('external','모의외규')):
            text=case[side];artifact=m.work.text_hash(text);did='fictional-'+side;sid='source-'+side
            metadata={'document_metadata':{'document_title':title},
                      'workflow_version':{'verified':True,'valid_from':AS_OF,'valid_to':AS_OF},
                      'synthetic':True,'fixture_sha256':digest(case)}
            row=self.db.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone()
            if row is None:
                self.db.execute('INSERT INTO document VALUES(?,?)',(did,json.dumps(metadata,ensure_ascii=False)))
                self.db.execute('INSERT INTO source_block VALUES(?,?,?,?)',(did,'1',text,artifact));self.db.commit()
            else:
                if json.loads(row[0])!=metadata or dict(self.db.execute('SELECT * FROM source_block WHERE document_id=?',(did,)).fetchone())!={
                        'document_id':did,'block_id':'1','text':text,'source_artifact_sha256':artifact}:
                    raise m.errors.ContractError('frozen synthetic source changed')
            span={'block_id':'1','start_cp':0,'end_cp':len(text),'text':text,'block_hash':artifact,'span_hash':artifact}
            origin={'source_id':sid,'document_id':did,'unit_id':sid+'-unit','generation_id':self.generation,
                    'source_artifact_hash':artifact,'role':'normative','temporal_status':'unknown',
                    'metadata':{'document_name':title,'heading':'제1조','read_location':'제1조'}}
            self.originals.append(m.source.canonical_evidence(origin,[span]))
            self.native[sid]={'id':sid,'document_id':did,'blocks':[{'block_id':'1','text':text}]}
    def sources(self,did,ids):
        return [dict(self.db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(did,bid)).fetchone()) for bid in ids]
    def close(self):self.db.close()


class Stack:
    def __init__(self,directory,case,profile,transport,*,code_binding):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.case={k:case[k] for k in ('id','question','internal','external')}
        self.profile=deepcopy(profile);self.profile.update(model_binding=transport.binding,max_transport_retries=0,max_output_tokens=4000)
        self.transport=transport;self.code_binding=deepcopy(code_binding);self.m=modules()
        self.request={'workflow_id':'risk_team_compare_workflow','workflow_version':None,
            'question':case['question'],'as_of':AS_OF,'use_llm':True,'session_id':'adr0813-synthetic',
            'request_id':case['id'],'document_ids':['fictional-external','fictional-internal'],
            'principal':{'user_id':'experiment','team_id':'synthetic'},'return_to':None}
        self.store=FixtureStore(self.directory/'sources.sqlite',self.case)
        self.binding={'generation_id':self.store.generation,'export_allowed':True,'model':deepcopy(transport.binding),
            'document_ids':self.request['document_ids'],'fixture_sha256':digest(self.case),
            'scope_kind':'FICTIONAL_FIXED_INPUT','code':self.code_binding,'profile_sha256':digest(self.profile)}
        transport.expected={k:deepcopy(self.binding[k]) for k in ('generation_id','document_ids','fixture_sha256','scope_kind','code','profile_sha256')}
        self.pipeline=NS(term_agent=NS(profile=self.profile,transport=transport))
        self.services=self.m.bridge.Services(self.pipeline,self.directory,{'scope':'fictional comparison-stage probe'})
        self.run_id=uuid.uuid5(uuid.NAMESPACE_URL,digest(self.binding)+case['id']).hex
        self.open()
    def open(self):
        journal=self.directory/'journal.sqlite'
        self.context=self.services.context(self.request,self.binding,self.run_id,journal)
        self.work=self.services.journal(journal,self.context)
        self.repo=self.m.repo.Repository(self.work,self.request,self.binding)
        session=NS(repo=self.work,store=self.store,context=self.context,
            scope=self.request['document_ids'],tools=NS(sources=self.store.native),
            navigator=NS(m=NS(document_catalogue={did:{'category':did.removeprefix('fictional-')} for did in self.request['document_ids']})))
        session.verify=lambda evidence:self.m.source.SourceSession.verify(session,evidence)
        self.port=self.m.bridge.SourcePort(session);self.port.services=self.services
        if not self.work.evidence():
            self.work.record_observation({'tool':'synthetic_originals','args':{'fixture_sha256':digest(self.case)}},
                {'status':'OK','source_kind':'FICTIONAL_FIXED_INPUT'},self.store.originals,verify=session.verify)
        def evidence():
            values=self.port.evidence()
            for item in values:session.verify(item)
            return values
        self.ctx=NS(request=self.request,context=self.context,repo=self.repo,
            rag=NS(port=self.port,evidence=evidence),model=self.m.model.ModelAdapter(self.repo,self.services,self.context))
        self.state=self.repo.state()['checkpoint']
        if self.state['stage']=='INTAKE':
            values=evidence();by_side={item['side']:item for item in values}
            citations=[{'evidence':by_side[side]['evidence_id'],'quote':by_side[side]['text']} for side in ('internal','external')]
            pair={'pair_id':'comparison-1','issue_id':'numeric-issue','internal':[citations[0]['evidence']],
                'external':[citations[1]['evidence']],
                'applicability':{'status':'MATCH','reason':'명시적 모의 대상·기준일의 입력 조건','as_of':AS_OF,'citations':citations},
                'basis_relation':'DIRECT','basis_path':[{'from_evidence':citations[0]['evidence'],
                    'to_evidence':citations[1]['evidence'],'citation':citations[0]}],
                'comparison_eligibility':True,'reason':'모의 문서의 명시 참조','content_difference':'','content_citations':citations}
            self.state.update(stage='COMPARE',scope={'issues':[{'id':'numeric-issue','label':self.case['question'],'numeric':True}],
                'missing_user_facts':[]},basis={'pairs':[pair],'gaps':[],'summary':'모의 문서 입력 관계'},
                rag_results={},context_evidence=[e['evidence_id'] for e in values])
            self.m.basis.validate(self.state['basis'],values,self.state['scope']['issues'],AS_OF)
            self.repo.save(self.state)
    def run(self):return self.m.compare.compare(self.ctx,self.state)
    def reopen(self):
        self.work.close();self.open()
    def close(self):
        self.work.close();self.store.close()
    def report(self):
        errors={}
        for row in self.work.db.execute("SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID'"):
            item=json.loads(row[0]);errors.setdefault(item['attempt_id'],[]).append(item)
        attempts=[]
        for row in self.work.db.execute('SELECT a.*,v.body_json FROM model_attempt a JOIN model_view v USING(view_id) ORDER BY a.created_seq'):
            row=dict(row);view=json.loads(row['body_json']);call=self.repo.call(view['workflow_call_id'])
            raw=json.loads(row['response_json'] or 'null')
            try:proposal=self.m.output.strict_json(self.m.model_contract.structured_content(raw['body_json'],require_complete=True)) if raw else None
            except Exception:proposal=None
            attempts.append({'attempt_id':row['attempt_id'],'provider_status':row['status'],
                'workflow_call_id':view['workflow_call_id'],'workflow_call_status':call['status'],
                'canonical_accepted':call['status']=='COMPLETE' and not errors.get(row['attempt_id']),
                'validation_errors':errors.get(row['attempt_id'],[]),'repair':view.get('repair'),
                'source_binding':digest(view.get('sources',[])),
                'catalogue_hash':view.get('citation_catalogue_hash'),'raw_order':ordered_keys(proposal),
                'raw_verdict':(proposal or {}).get('rows',[{}])[0].get('verdict') if (proposal or {}).get('rows') else None,
                'input_tokens':row['input_tokens'],'output_tokens':row['output_tokens']})
        return {'attempts':attempts,'initial_valid':attempts[0]['canonical_accepted'] if attempts else None,
            'final_model_valid':attempts[-1]['canonical_accepted'] if attempts else None,
            'physical_calls':len(self.transport.calls),'budget':self.work.budget(),
            'deadline_at':self.work.run()['deadline_at'],'comparison':deepcopy(self.state.get('comparison')),
            'scope':'actual comparison adapter/gateway/journal with fictional originals; no full retrieval/service certification'}


class AuditedSender:
    def __init__(self,client,client_module,case_id):
        self.client,self.client_module,self.case_id=client,client_module,case_id
        self.last_wire_order=None
    def __call__(self,body,ticket):
        m=modules();payload=m.local.provider_request(body)
        try:raw=self.client.chat_completions(payload,phase='compare-'+self.case_id,timeout_seconds=min(180,ticket['remaining_seconds']))
        except self.client_module.ExperimentFormatError as exc:
            if exc.response:
                try:m.model_contract.structured_content(exc.response['body_json'],require_complete=True)
                except m.errors.ProposalError as error:error.response=exc.response;raise
            error=m.errors.ProposalError(str(exc));error.response=exc.response;raise error from exc
        except self.client_module.ExperimentProviderError as exc:
            status=(exc.response or {}).get('status_code',0)
            if 200<=status<300:raise m.errors.ContractError('experiment provider/model policy rejected successful HTTP response') from exc
            raise m.errors.TransportError('experiment provider rejected request',retryable=False,unknown=status>=500,response=exc.response) from exc
        except self.client_module.ExperimentTransportError as exc:
            raise m.errors.TransportError('experiment transport outcome',retryable=False,unknown=exc.unknown) from exc
        except self.client_module.ExperimentCallError as exc:
            raise m.errors.BudgetExhausted(str(exc)) from exc
        finally:
            # The common client saves its exact final wire payload after adding
            # policy fields. Keep this separately from the gateway's input order.
            path=self.client.output/f'call-{self.client.calls:03d}-compare-{self.case_id}'/'request.json'
            try:self.last_wire_order=order_receipt(read(path))
            except (OSError,ValueError,TypeError) as exc:
                self.last_wire_order={'diagnostic_error':type(exc).__name__}
        if raw['body_json'].get('model')!=self.client.model or raw['body_json'].get('provider')!='Parasail':
            raise m.errors.ContractError('actual model/provider mismatch')
        raw['acceptance']='ACCEPTED';return raw


def main():
    arm=sys.argv[1] if len(sys.argv)>1 else 'connected'
    criteria=read(DESIGN/'criteria.json');spec=criteria['model_probe']
    if arm not in spec['arms']:raise ValueError('arm is outside the frozen model probe')
    freeze=read(DESIGN/'freeze.json')
    for name,expected in freeze['files'].items():
        if sha(ROOT/name)!=expected:raise ValueError('frozen input changed: '+name)
    code=ROOT/freeze['code_root'];sys.dont_write_bytecode=True
    sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND')]
    m=modules()
    for name,module in vars(m).items():
        if not Path(module.__file__).resolve().is_relative_to(code):raise ValueError('runtime import escaped candidate: '+name)
    output=ADR/'artifacts/model-real-stack'/arm;output.mkdir(parents=True,exist_ok=False)
    path=ROOT/'02_BACKEND/lawrag/research/experiment_client.py'
    if sha(path)!=freeze['files'][str(path.relative_to(ROOT))]:raise ValueError('common ExperimentClient changed')
    loader=util.spec_from_file_location('bound_experiment_client_0813',path)
    client_module=util.module_from_spec(loader);loader.loader.exec_module(client_module)
    client=client_module.ExperimentClient(ROOT,output/'raw',max_calls=spec['max_calls_per_arm'],
        max_output_tokens=spec['max_output_tokens'],max_repairs=0)
    profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    cases=read(DESIGN/'model-cases.json')
    if [c['id'] for c in cases]!=spec['case_ids']:raise ValueError('case order changed')
    binding=model_binding(read(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'))
    reports=[]
    for case in cases:
        sender=AuditedSender(client,client_module,case['id']);transport=Transport(binding,sender)
        stack=Stack(output/case['id'],case,profile,transport,code_binding=freeze['candidate'])
        started=time.monotonic();result=None;failure=None
        try:result=stack.run()
        except Exception as exc:failure={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
        before=len(transport.calls);deadline=stack.work.run()['deadline_at'];budget=stack.work.budget()
        first=stack.report();replay=None;replay_failure=None
        stack.reopen()
        try:replay=stack.run()
        except Exception as exc:replay_failure={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
        report={**first,'case_id':case['id'],'failure':failure,'replay_failure':replay_failure,
            'reopen_no_additional_calls':len(transport.calls)==before,
            'reopen_same_deadline':stack.work.run()['deadline_at']==deadline,
            'reopen_same_budget':stack.work.budget()==budget,'reopen_same_result':replay==result,
            'elapsed_seconds':time.monotonic()-started,
            'orders':[{'attempt_id':call['attempt_id'],'request_order':call['request_order'],
                       'provider_request_order':call.get('provider_request_order'),
                       'response_order':call.get('response_order'),'elapsed_seconds':call['elapsed_seconds']} for call in transport.calls]}
        # Expected verdict is evaluator-only and is never included in product case/binding/input.
        verdict=((result or {}).get('rows') or [{}])[0].get('verdict')
        report.update(expected=case['expected'],verdict=verdict,correct=first['final_model_valid'] is True and verdict==case['expected'])
        stack.close();reports.append(report);put(output/(case['id']+'-result.json'),report)
        put(output/'result.json',{'arm':arm,'results':reports,'model_calls':client.calls,'usage':client.usage,
            'quality_certified':False,'causal_order_effect_claim':False,'scope':spec['scope']})
        print(json.dumps({k:report[k] for k in ('case_id','initial_valid','final_model_valid','physical_calls','verdict','correct','reopen_no_additional_calls')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()

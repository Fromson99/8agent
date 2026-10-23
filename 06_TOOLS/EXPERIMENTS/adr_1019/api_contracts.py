"""Actual candidate /v1/rag/ask with tiny synthetic originals and scripted responses."""
from common import *
import sys, os, sqlite3, inspect, pytest
from contextlib import contextmanager
from copy import deepcopy

meta=read(DES/'candidate.json');S=ROOT/meta['path']/'snapshot';C=S/meta['selected_code_relative']
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),AD_WORKER_ENABLED='0',GENOS_RESIDENT_DATA='off')
sys.path[:0]=[str(C/'02_BACKEND'),str(S/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag,lawrag.pipeline
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
from conftest import term_glossary
sys.path.insert(0,str(Path(__file__).parent))
from test_main50_request_repair import tree
from test_source_span_norm import SpanTransport,proposal
from test_bounded_source_main import settings
from test_legal_agent_double_harness import wire
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.errors import ContractError
from lawrag.legal_knowledge.adapters.oracle import ddl
from lawrag.legal_knowledge.adapters.repository import Repository
from lawrag.legal_knowledge.adapters.existing import ExistingReferences
from lawrag.legal_knowledge.application import Service,ref
from e2e import LabDB

class Transport(SpanTransport):
    knowledge_delivery_enabled=True
    knowledge_required_items=True
    knowledge_use_first_prompt=True
    knowledge_reuse_mode='CLOSED_EVIDENCE'
    def __init__(self,mode):
        super().__init__(False,False);self.mode=mode
    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            assert len(view['required_review_items'])==2
            if self.mode=='invalid':return wire({'claims':[],'issue_assessments':[],'gaps':[]})
            if self.mode=='repair' and not phase.endswith('repair'):
                return wire({'claims':[],'issue_assessments':[],'gaps':[]})
            opts=view['evidence_options'];sid=next(o['id'] for o in opts if '승인 후 보고한다.' in o['text'])
            v=proposal('승인 후 보고한다.','OBLIGATION',[sid],sid);v.pop('disposition')
            if self.mode!='omitted':
                a,b=view['required_review_items']
                v['required_review']=[{'item_id':a['item_id'],'action':'EXPLAIN','claim_ids':['C1'],'reason':'보고 원문과 설명을 연결했다.'},
                    {'item_id':b['item_id'],'action':'UNKNOWN','claim_ids':[],'reason':'예외 적용 판단은 확인하지 못했다.'}]
            return wire(v)
        return super().send_once(body=body,ticket=ticket)

def run():
    directory=ART/(sys.argv[1] if len(sys.argv)>1 else 'api-contracts-001');assert not directory.exists()
    directory.mkdir();fixture=directory/'fixture';fixture.mkdir()
    gen,idx=tree.__wrapped__(fixture,term_glossary.__wrapped__(fixture));checks=[]
    for mode in ['valid','omitted','repair','invalid']:
        d=directory/mode;d.mkdir();dbpath=d/'knowledge.sqlite'
        db=LabDB(dbpath);db.raw.executescript(ddl({n:n for n in ('lk_record','lk_head','lk_lookup')}));db.raw.close()
        holder={};who={'authenticated':True,'tenant_id':'synthetic','team_id':'test_team','user_id':'curator',
            'document_ids':['d'],'knowledge_roles':['read','edit','publish']}
        @contextmanager
        def factory():
            db=LabDB(dbpath)
            try:yield Service(Repository(db),ExistingReferences(holder['app'].state.pipeline.store))
            finally:db.raw.close()
        t=Transport(mode)
        profile={**settings(),'max_model_attempts':24,'max_read_chars':10000,
            'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
                'completion_policy_version':cc.V8,'compact_input':True}}
        app=create_app(d,gen,contracts_root=C,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
            legal_agent_profile=profile,legal_agent_transport=t,runtime_root=d/'runtime',knowledge_factory=factory,
            knowledge_identity=lambda _:dict(who),memory_identity=lambda _:dict(who))
        holder['app']=app;app.state.pipeline.term_agent.unit_fulltext=idx
        app.state.pipeline.contracts.pipeline['legal_knowledge'].update(management_enabled=True,consumer_mode='consume')
        store=app.state.pipeline.store
        binding={'generation':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],
                 'unit_index_sha256':idx.manifest['index_sha256']}
        with TestClient(app) as api:
            def command(op,args,key):
                r=api.post('/v1/legal-knowledge/commands',json={'schema_version':'legal-knowledge-v1','operation':op,
                    'operation_id':mode+':'+key,'arguments':args},headers={'X-Knowledge-Request':'1'})
                assert r.status_code==200,r.text
                return r.json()
            definition=deepcopy(read(DES/'method-templates.json')[0]['definition'])
            definition.update(title='모의승인규정 제1조',description='합성 원문에 연결한 필수 검토',lookup_terms=['승인'],
                source_refs=[{'document_id':'d','version':'d','locator':'5','content_hash':text_hash(store.source('d','5')['text'])}])
            definition['content']={'purpose':'모의 원문 검토','requested_outputs':['검토 결과'],'inputs':[],
                'evidence_needs':['모의승인규정 제1조'],'steps':[
                    {'id':'report','label':'승인 후 보고 의무를 확인한다.','capability':'READ_SOURCE','after':[]},
                    {'id':'exception','label':'예외 적용을 확인한다.','capability':'READ_SOURCE','after':[]}],'policies':[]}
            obj=command('save_draft',{'object_id':None,'expected_revision':0,'definition':definition},'save')
            build=command('prepare_publication',{'refs':[ref(obj)],'source_binding':binding,'review_note':'합성 계약 검사'},'build')
            command('publish',{'build_id':build['id'],'build_hash':build['content_hash'],'expected_revision':0},'publish')
            body={'question':'모의승인규정 제1조 승인 기준은?','session_id':mode,'request_id':'r1'}
            response=api.post('/v1/rag/ask',json=body);out=response.json()
            put(d/'response.json',{'http_status':response.status_code,'body':out,'phases':t.phases})
            assert response.status_code==200,(mode,response.text,t.phases)
            review=out['assembly']['term_agent']['legal_knowledge']['required_review']
            assert len(review['rows'])==2
            assert [r['status'] for r in review['rows']]==(['UNKNOWN','UNKNOWN'] if mode in ('omitted','invalid') else ['EXPLAINED','UNKNOWN'])
            assert out['answer']['text'].count('원문별 필수 확인 사항')==1
            for item in review['rows']:assert out['answer']['text'].count('등록 메모: '+item['note'])==1
            count=len(t.phases);again=api.post('/v1/rag/ask',json=body)
            assert again.status_code==200 and again.json()['answer']==out['answer'] and count==len(t.phases)
            checks.append(mode+': API publication, required rows exactly once, explicit missing, duplicate idempotent')
            journal=next((d/'runtime/legal-agent/runs').glob('*/'+out['run_id']+'/journal.sqlite'))
            from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
            from semantic_runtime.legal_agent.unified_publication import validate_saved
            repo=UnifiedRepository(journal)
            try:
                validate_saved(repo,out)
                bad=deepcopy(out);bad['answer']['text']=bad['answer']['text'].split('원문별 필수 확인 사항')[0]
                try:validate_saved(repo,bad)
                except ContractError:pass
                else:raise AssertionError('mandatory display removal accepted')
                assert len([p for p in t.phases if p.startswith('memory-assess')])==(2 if mode in ('repair','invalid') else 1)
            finally:repo.close()
            checks.append(mode+': publication mutation rejected and assessment repair budget bounded')
        store.close()
    put(directory/'result.json',{'status':'PASS','checks':checks,'model_calls':0,'synthetic_transport':True,
        'code_root':str(C.relative_to(ROOT)),'pipeline_sha256':sha(C/'00_SYSTEM/PIPELINE.json')})
    print('API CONTRACT PASS',len(checks),flush=True)
if __name__=='__main__':run()

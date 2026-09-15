"""Fictional data: executable downstream acceptance, not legal/RAG quality gold."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.contracts import digest,sha,write
from semantic_runtime.pipeline import Pipeline,evaluate
from semantic_runtime.provider import Haiku
from semantic_runtime.storage import publish,Store


def fixture(root,output):
    output.mkdir(parents=True)
    texts=['제1조(적용범위) 이 예시규정은 신규상장 전 주식 취득에 적용한다.',
           '예시회사가 제3자배정으로 취득한 주식은 상장일부터 6개월간 의무보유한다. 다만, 제2조제1호에 해당하면 제외한다.',
           '제2조(예외)', '1. 전문투자자가 취득한 경우.', '2. 별도로 정한 다른 예외.', '제53조 예시회사의 시설 관리에 관한 내용이다.']
    source_sha=digest(texts);db=sqlite3.connect(output/'source.sqlite')
    db.executescript('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT,json TEXT); CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT); CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);')
    db.execute('INSERT INTO document VALUES (?,?,?,?)',('example','검증용 가상 규정',source_sha,'{}'))
    parents=[None,'0',None,'2','2',None];spans=[[0,2],[1,2],[2,5],[3,4],[4,5],[5,6]]
    for i,t in enumerate(texts):
        u={'id':i,'block':i,'parent':parents[i],'span':spans[i],'family':'kr_article' if parents[i] is None else 'kr_paragraph',
           'title':t if parents[i] is None else str(i),'surface':f'제{i}조' if parents[i] is None else str(i)}
        db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',('example',str(i),parents[i],json.dumps(u,ensure_ascii=False)))
        db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',('example',str(i),str(i),t,source_sha,'{}'))
    db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',('example','6',None,'미분류원문 연결 확인',source_sha,'{}'))
    db.commit();db.close()
    ev=[{'id':f'evidence:{i}','document_version_id':'example','structural_unit_id':str(i),'block_id':str(i),
         'source_artifact_sha256':source_sha,'start':0,'end':len(t),'quote':t,'quote_sha256':hashlib.sha256(t.encode()).hexdigest()} for i,t in enumerate(texts)]
    concept={'id':'concept:company','label':'예시회사','concept_type':'ENTITY','aliases':[],'definition_rule_ids':[],'evidence_ids':['evidence:1','evidence:5']}
    investor={'id':'concept:investor','label':'전문투자자','concept_type':'ENTITY','aliases':[],'definition_rule_ids':[],'evidence_ids':['evidence:3']}
    clauses=[]
    for ident,block in [('base',1),('condition',3),('effect',1),('exception',3)]:
        clauses.append({'id':'clause:'+ident,'clause_type':'STATE','polarity':'POSITIVE','role_bindings':[
            {'role':'ACTOR','concept_id':'concept:investor' if block==3 else 'concept:company','mention_ids':[],'resolution':'RESOLVED','unresolved_reason':None,'evidence_ids':[f'evidence:{block}']}],
            'evidence_ids':[f'evidence:{block}']})
    def rule(ident,block,consequence,antecedent):
        return {'id':'rule:'+ident,'rule_type':'NORM','applicability':{'operator':'TRUE','evidence_ids':[f'evidence:{block}']},'antecedent':antecedent,
                'consequent_clause_ids':['clause:'+consequence],'modality':'OBLIGATION','valid_from':None,'valid_until':None,'evidence_ids':[f'evidence:{block}']}
    rules=[rule('base',1,'base',{'operator':'UNKNOWN','reason':'상장 전 취득 사실은 질문에서 확인해야 함','evidence_ids':['evidence:0']}),
           rule('exception',3,'exception',{'operator':'CLAUSE','clause_id':'clause:condition'})]
    relation={'id':'relation:dependency','predicate':'DEPENDS_ON_REQUIREMENTS_OF','source':{'type':'Proviso','id':'proviso:base'},
              'target':{'type':'Rule','id':'rule:exception'},'resolution':'RESOLVED','target_locator':None,'unresolved_reason':None,'evidence_ids':['evidence:1']}
    proviso={'id':'proviso:base','attached_rule_id':'rule:base','condition':{'operator':'CLAUSE','clause_id':'clause:condition'},
             'outcome_clause_ids':['clause:effect'],'effect_type':'EXEMPTION','completion_type':'EXTERNAL',
             'dependency_relation_ids':['relation:dependency'],'evidence_ids':['evidence:1']}
    scope={'source_set_sha256':source_sha,'authority_generation':'synthetic-example','document_version_ids':['example'],'jurisdiction':'EXAMPLE','as_of':None}
    legal=json.loads((root/'00_SYSTEM/LEGAL_SCHEMA.json').read_text())['normative_schema']
    bundle={'schema_version':'legal-semantic-v2','schema_sha256':legal['sha256'],'record_kind':'CANONICAL_BUNDLE','id':'canonical:example',
            'scope':scope,'generation_id':'example-v1','payload':{'concepts':[concept,investor],'mentions':[],'clauses':clauses,'rules':rules,'provisos':[proviso],
            'relations':[relation],'evidence':ev,'crosswalk':[]},'source_observation_ids':['observation:synthetic'],
            'review_receipts':[{'id':'receipt:synthetic-shape-only','sha256':digest('synthetic fixture, not legal approval')}]}
    write(output/'bundle.json',bundle)
    return output/'source.sqlite',output/'bundle.json'


def run(root,code_root,output,live=False):
    test_root=output/'test-root';(test_root/'00_SYSTEM').mkdir(parents=True)
    shutil.copytree(root/'00_SYSTEM/SCHEMAS',test_root/'00_SYSTEM/SCHEMAS')
    shutil.copyfile(root/'00_SYSTEM/LEGAL_SCHEMA.json',test_root/'00_SYSTEM/LEGAL_SCHEMA.json')
    shutil.copyfile(code_root/'00_SYSTEM/PIPELINE.json',test_root/'00_SYSTEM/PIPELINE.json')
    for p in (code_root/'00_SYSTEM/SCHEMAS').glob('*.json'):shutil.copyfile(p,test_root/'00_SYSTEM/SCHEMAS'/p.name)
    shutil.copytree(code_root/'02_BACKEND/ENGINES/semantic_runtime',test_root/'02_BACKEND/ENGINES/semantic_runtime')
    shutil.copytree(code_root/'02_BACKEND/semantic_runtime',test_root/'02_BACKEND/semantic_runtime')
    source,bundle=fixture(root,output/'fixture')
    generation=output/'example-generation'
    publish(test_root,source,[bundle],generation,data_status='EXAMPLE',export_allowed=True)
    store=Store(generation);provider=Haiku(root,output/'provider',True);pipe=Pipeline(test_root,store,provider)
    checks={};plan=pipe.plan('제3자배정 주식 의무보유 기간과 예외를 알려줘')
    selected={'selected':[{'id':'C1','document_id':'example','block_id':'1','unit_id':'1'}]}
    assembled=pipe.assemble(plan,selected)
    ids={x['block_id'] for x in assembled['context']}
    checks['base_proviso_external_condition_present']={'1','3'}<=ids
    checks['reference_item_only_not_sibling']='4' not in ids
    checks['shared_concept_does_not_expand_unrelated_article']='5' not in ids
    checks['ancestor_scope_included']='0' in ids
    checks['explicit_relation_path_recorded']=any(x['predicate']=='DEPENDS_ON_REQUIREMENTS_OF' for x in assembled['relationship_paths'])
    checks['unknown_rule_condition_preserved']=assembled['condition_assessments'][0]['antecedent'] is None
    checks['false_and_unknown']=evaluate({'operator':'ALL','operands':[{'operator':'CLAUSE','clause_id':'a'},{'operator':'CLAUSE','clause_id':'b'}]},{'a':False}) is False
    checks['true_or_unknown']=evaluate({'operator':'ANY','operands':[{'operator':'CLAUSE','clause_id':'a'},{'operator':'CLAUSE','clause_id':'b'}]},{'a':True}) is True
    checks['not_unknown']=evaluate({'operator':'NOT','operand':{'operator':'CLAUSE','clause_id':'missing'}},{}) is None
    unstructured=pipe.retrieve(pipe.plan('미분류원문'))
    checks['raw_block_without_unit_retrievable']=any(x['block_id']=='6' for x in unstructured['candidates'])
    raw_assembly=pipe.assemble(plan,{'selected':[{'document_id':'example','block_id':'6','unit_id':None}]})
    checks['raw_block_scope_unknown_explicit']=any(x.startswith('SOURCE_WITHOUT_STRUCTURAL_UNIT') for x in raw_assembly['unresolved'])
    checks['template_is_validated_artifact']=pipe.template['record_kind']=='ASSEMBLY_TEMPLATE'
    try:
        pipe.assemble(plan,selected,{'clause:condition':True});checks['unscoped_fact_rejected']=False
    except ValueError:checks['unscoped_fact_rejected']=True
    confirmed=pipe.assemble(plan,selected,{'canonical:example/clause:condition':True})
    checks['namespaced_condition_fact']=any(x.get('proviso_id')=='proviso:base' and x['condition'] is True for x in confirmed['condition_assessments'])
    class BadProvider:
        def select(self,*args):return {'selected_ids':['UNKNOWN_ID']},{'id':'fake'}
        def answer(self,*args):return {'text':'unsupported','claims':[{'text':'unsupported','citations':[{'source_id':assembled['context'][0]['id'],'quote':'THIS IS NOT IN THE SOURCE'}]}]},{}
    pipe.provider=BadProvider()
    try:
        pipe.select(plan,pipe.retrieve(plan));checks['unknown_llm_candidate_rejected']=False
    except ValueError:checks['unknown_llm_candidate_rejected']=True
    try:
        pipe.answer(plan,assembled);checks['wrong_llm_quote_rejected']=False
    except ValueError:checks['wrong_llm_quote_rejected']=True
    pipe.provider=provider
    source_run=pipe.run('제3자배정 주식 의무보유',use_llm=False)
    checks['configured_pipeline_runs_without_legacy']=source_run['answer']['record_kind']=='ANSWER'
    app=create_app(test_root,generation,contracts_root=test_root,provider=provider)
    with TestClient(app) as client:
        checks['health_latest_runtime']=client.get('/health').json()['runtime']=='semantic-runtime-v2'
        checks['exact_item_api']=len(client.get('/v1/rag/section',params={'doc_id':'example','node':'3'}).json()['blocks'])==1
        checks['missing_item_no_article_fallback']=client.get('/v1/rag/section',params={'doc_id':'example','node':'999'}).status_code==404
        checks['old_main_api_removed']=client.get('/v1/rag/switches').status_code==410
        response=client.post('/v1/rag/ask',json={'question':'제3자배정 주식 의무보유','use_llm':False})
        checks['ask_api']=response.status_code==200
        if response.status_code!=200:raise ValueError(response.text)
        result=response.json();feedback=client.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'MISSING_EVIDENCE','reason':'예시 검증'})
        checks['feedback_round_trip']=feedback.status_code==200 and feedback.json()['proposal']['status']=='PROPOSED'
        checks['feedback_not_auto_admitted']=json.loads((generation/'manifest.json').read_text())['data_status']=='EXAMPLE'
        checks['unknown_document_rejected']=client.post('/v1/rag/ask',json={'question':'질문','document_ids':['missing'],'use_llm':False}).status_code==422
    live_runs=[]
    if live:
        for question in ['제3자배정으로 취득한 주식의 의무보유 기간과 예외는?', '전문투자자가 취득했다면 예시규정에서 무엇을 더 확인해야 하나?']:
            r=pipe.run(question,use_llm=True);live_runs.append(r)
        write(output/'live-runs.json',live_runs)
        checks['haiku_actual_calls']=len(live_runs)==2 and all(x['selection']['method']=='haiku' for x in live_runs)
        checks['haiku_cited_claims']=all(x['answer']['claims'] for x in live_runs)
    write(output/'source-run.json',source_run);write(output/'assembly-check.json',assembled)
    report={'structural_checks_passed':all(checks.values()),'checks':checks,'passed':sum(checks.values()),'total':len(checks),
            'live_questions':len(live_runs),'quality_certified':False,'data':'fictional examples, not legal quality gold',
            'code_root':str(code_root),'example_generation':str(generation)}
    write(output/'report.json',report);store.close();return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['root','code-root','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--live',action='store_true');a=p.parse_args()
    r=run(a.root,a.code_root,a.output,a.live);print(json.dumps(r,ensure_ascii=False,indent=2))
    raise SystemExit(0 if r['structural_checks_passed'] else 1)

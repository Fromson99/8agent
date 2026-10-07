"""Explicit frozen candidate runner; never imported by a serving registry."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
sys.dont_write_bytecode=True
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0621-unit-read-canonical-boundaries'
DESIGN=ADR/'artifacts/design'
RUN=ADR/'artifacts/run-001'

def read(p):return json.loads(Path(p).read_text())
def put(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def pin(arm):
    m=read(ADR/'실험/manifest.json');assert m['design']['criteria_frozen_before_run']
    for p,h in m['design']['frozen_inputs'].items():assert sha(ROOT/p)==h,p
    cm=read(ROOT/'02_BACKEND/lawrag/research/candidates/adr_0621'/arm/'candidate.json')
    rev=cm['revisions'][-1]
    for f in rev['files']:assert sha(ROOT/f['frozen_path'])==f['snapshot_sha256'],f['target_path']
    code=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0621'/arm/'revisions'/rev['revision_id']/'snapshot'
    sys.path.insert(0,str(code/'02_BACKEND'))
    return code

class NoModel:
    binding={'provider':'offline','model':'synthetic-resource-setup','adapter_version':'disabled-v1',
        'endpoint_identity':'none','trust_zone':'internal','max_input_bytes':2000000}
    def validate_model(self):return {'verified':False,'mode':'RESOURCE_SETUP_ONLY'}
    def send_once(self,**kw):raise AssertionError('resource setup cannot call a model')

def build_index():
    pin('adaptive-unit')
    from semantic_runtime.unit_fulltext import build
    b=read(DESIGN/'source-binding.json');generation=ROOT/b['generation']
    result=build(generation,generation/'navigation',RUN/'unit-index',document_ids=b['scope_document_ids'],workers=4)
    put(RUN/'index-build.json',result)

def case_run(cid,arm):
    code=pin(arm)
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.obligation_repository import ObligationRepository as ToolsRepository
    from semantic_runtime.legal_agent.workflow_tiers_tools import TiersTools as ExplorationTools
    from semantic_runtime.legal_agent.source_recall import SourceRecall
    from semantic_runtime.legal_agent.source_selection import select_sources,originals
    from semantic_runtime.legal_agent import tools_policy, workflow_tiers_policy
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.contracts import digest
    from lawrag.research.experiment_client import ExperimentClient
    from jsonschema import validate
    logging.getLogger('semantic_runtime').setLevel(logging.ERROR)
    b=read(DESIGN/'source-binding.json');case=next(c for c in read(DESIGN/'inputs.json') if c['case_id']==cid)
    out=RUN/cid/arm;out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();store=Store(ROOT/b['generation']);repo=None;client=None
    result={'case_id':cid,'arm':arm,'question':case['question'],'error':None,'answer_quality_measured':False}
    try:
        assert sha(ROOT/'08_DEPLOYMENT/CONFIG/legal-source-export.json')==b['source_authorization_sha256']
        external=LocalGemmaTransport(code,ROOT);docs=b['scope_document_ids']
        assert set(docs)<=set(external.public_scope)
        profile=workflow_tiers_policy.profile({**workflow_tiers_policy.DEFAULT_PROFILE,'model_binding':NoModel.binding,
            'wall_seconds':600,'max_tool_actions':1024,'max_context_chars':120000},require_model=True)
        pipeline=Pipeline(code,store,implementation=workflow_tiers_policy.IMPLEMENTATION,legal_agent_profile=profile,legal_agent_transport=NoModel())
        if arm=='bounded-unit':
            from semantic_runtime.unit_fulltext import UnitFulltextIndex
            idx=UnitFulltextIndex(ROOT/'04_EXPERIMENTS/ADR/ADR-0620-unit-fulltext-adaptive-read/artifacts/run-001/unit-index',pipeline.term_agent.get_index().manifest)
            pipeline.term_agent.unit_fulltext=idx
        request={'question':case['question'],'document_ids':docs,'use_llm':True,'public_question':True}
        query=pipeline.plan(case['question'],docs)
        auth=external.authorize(query,request,store.manifest,public_question=True)
        with ServingDocumentAgent(pipeline,pipeline.term_agent.config).resources(docs) as (index,tools,glossary,matcher):
            binding={'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],
                'export_allowed':False,'scope':query['scope'],'model':NoModel.binding,
                'domain_sha256':digest(tools_policy.DOMAIN),'profile_sha256':digest(profile),
                'pipeline_sha256':sha(code/'00_SYSTEM/PIPELINE.json'),'index_sha256':index.manifest['index_sha256'],
                'glossary':glossary.binding,'external_authorization':auth}
            context=RequestContext.create(query,request,binding,600)
            repo=ToolsRepository(out/'journal.sqlite',context,profile)
            s=ExplorationTools(store,tools,glossary,matcher,repo,context,profile)
            s.recall_query_plan={'queries':case['queries'],'law_names':[]}
            recall=SourceRecall(s).prepare();recall.update(evidence=repo.evidence(),query_plan=s.recall_query_plan)
            put(out/'recall.json',recall)
            client=ExperimentClient(ROOT,out/'provider',max_calls=2,max_repairs=0,max_output_tokens=6400,schema_in_prompt=True)
            inputs=[]
            def invoke(system,data,schema,phase,timeout):
                external.authorize(query,request,store.manifest,public_question=True)
                inputs.append({'phase':phase,'system':system,'data':data,'schema':schema})
                value=client.generate(system,data,schema,phase=phase)
                validate(value,schema)
                put(out/('model-input-'+str(len(inputs))+'.json'),inputs[-1])
                put(out/('model-output-'+str(len(inputs))+'.json'),value)
                return value
            kwargs={'session':s} if arm=='bounded-unit' else {}
            selected=select_sources(case['question'],recall,invoke,remaining_seconds=240,max_fulltext_chars=80000,**kwargs)
            put(out/'selection.json',selected)
            result.update(corpus_ids=sorted(tools.sources),discovered_ids=recall['discovered'],
                read_ids=recall.get('selection_complete',recall['read_complete']),selected_ids=selected['final_ids'],
                actual_presented_ids=list(dict.fromkeys(selected.get('label_to_source',{}).values())),
                status=selected['status'],needs_search=selected.get('needs_fulltext',False),
                initial_unit_count=len(recall.get('unit_reads',[])),article_complete_count=len(recall['read_complete']),
                read_scopes=selected.get('read_scopes',[]),selected_originals=selected.get('selected_originals',[]),
                selector_seconds=selected['seconds'],source_chars=recall['source_chars'],
                selector_excerpts=selected['actual_selector_excerpts'])
    except BaseException as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)}
        (out/'error.txt').write_text(traceback.format_exc())
    finally:
        result.update(seconds=time.monotonic()-start,usage=client.usage if client else [],model_calls=client.calls if client else 0)
        put(out/'result.json',result)
        if repo:repo.close()
        store.close()
    print(json.dumps({k:result.get(k) for k in ('case_id','arm','status','error','model_calls','seconds')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build-index',action='store_true');p.add_argument('--case');p.add_argument('--arm',choices=['bounded-unit']);a=p.parse_args()
    if a.build_index:raise SystemExit('Reuse ADR0620 index; rebuilding is outside this run')
    else:case_run(a.case,a.arm)

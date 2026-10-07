"""Frozen public-source node-path prefetch probe; no product MAIN imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0586-node-bound-path-prefetch'
CANDIDATE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0586/path-prefetch'


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')


def pin():
    manifest=read(ADR/'실험/manifest.json')
    if manifest['design']['criteria_frozen_before_run'] is not True:
        raise ValueError('design was not frozen before model call')
    for raw,expected in manifest['design']['frozen_inputs'].items():
        if sha(ROOT/raw)!=expected:raise ValueError('frozen input drift: '+raw)
    revision=read(CANDIDATE/'candidate.json')['revisions'][-1]
    for entry in revision['files']:
        if sha(ROOT/entry['frozen_path'])!=entry['snapshot_sha256']:
            raise ValueError('candidate revision drift')
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    import semantic_runtime.legal_agent as package
    folder=CANDIDATE/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/semantic_runtime/legal_agent'
    package.__path__.insert(0,str(folder))
    from semantic_runtime.legal_agent import exploration_tools,path_shortcut,unit_access
    for module in (exploration_tools,path_shortcut,unit_access):
        if not Path(module.__file__).is_relative_to(folder):
            raise ValueError('candidate module escaped frozen revision: '+module.__name__)
    return exploration_tools,path_shortcut,unit_access


class NoModel:
    binding={'provider':'offline','model':'no-model-resource-setup','adapter_version':'disabled-v1',
             'endpoint_identity':'none','trust_zone':'internal','max_input_bytes':2000000}
    def validate_model(self):return {'verified':False,'mode':'RESOURCE_SETUP_ONLY'}
    def send_once(self,**kwargs):raise AssertionError('resource setup must not call a model')


def run_case(case, *, preflight=False):
    exploration_tools,path_shortcut,unit_access=pin()
    from lawrag.research.experiment_client import ExperimentClient
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.tools_repository import ToolsRepository
    from semantic_runtime.legal_agent import tools_policy
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.contracts import digest
    design=read(ADR/'artifacts/design/cases.json')
    did=design['document_id'];out=ADR/'artifacts'/('preflight-001' if preflight else 'run-001')/case['case_id']
    out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();store=repo=memory=client=None
    row={'case_id':case['case_id'],'question':case['question'],'preflight':preflight,
         'model':'qwen/qwen3.8-27b','error':None}
    try:
        store=Store(ROOT/design['data_generation'])
        transport=LocalGemmaTransport(ROOT,ROOT)
        if transport.binding['model']!=row['model']:raise ValueError('Qwen3.8 transport unavailable')
        settings=tools_policy.profile({**tools_policy.DEFAULT_PROFILE,
            'model_binding':NoModel.binding,'wall_seconds':300,'max_tool_actions':24,
            'max_context_chars':60000},require_model=True)
        runtime=ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-qwen38-public-20260930-r1/code'
        pipeline=Pipeline(runtime,store,implementation=tools_policy.IMPLEMENTATION,
                          legal_agent_profile=settings,legal_agent_transport=NoModel())
        request={'question':case['question'],'document_ids':[did],'use_llm':True}
        query=pipeline.plan(case['question'],[did])
        auth=transport.authorize(query,request,store.manifest,public_question=True)
        row['authorization']={'grant_sha256':auth['grant_sha256'],
                              'policy_sha256':auth['policy_sha256'],'scope_document_ids':auth['scope_document_ids']}
        agent=ServingDocumentAgent(pipeline,pipeline.term_agent.config)
        with agent.resources([did]) as (index,tools,glossary,matcher):
            binding={'generation_id':store.manifest['generation_id'],
                'store_sha256':store.manifest['store_sha256'],'export_allowed':False,
                'scope':query['scope'],'model':NoModel.binding,
                'domain_sha256':digest(tools_policy.DOMAIN),
                'profile_sha256':digest(settings),'pipeline_sha256':sha(runtime/'00_SYSTEM/PIPELINE.json'),
                'index_sha256':index.manifest['index_sha256'],'glossary':glossary.binding,
                'external_authorization':auth}
            context=RequestContext.create(query,request,binding,300)
            repo=ToolsRepository(out/'journal.sqlite',context,settings)
            sources=exploration_tools.ExplorationTools(store,tools,glossary,matcher,repo,context,settings)
            memory=path_shortcut.PathMemory(out/'memory.sqlite')
            observations=[]
            for seed_case,seed in design['seed_runs'].items():
                path=ROOT/seed['path']
                if sha(path)!=seed['sha256']:raise ValueError('seed run changed')
                proposed=memory.observe(store=store,trace=read(path),trace_hash=seed['sha256'],
                    document_id=did,article_unit_id=design['article_unit_id'])
                gold=next(item for item in design['cases'] if item['seed_case_id']==seed_case)
                observations.extend(memory.verify_probe(x,gold['required_block_ids']) for x in proposed)
            row['seed_observation_ids']=observations
            overview=path_shortcut.article_overview(store,matcher.units,did,design['article_unit_id'],
                                                     excerpt_chars=48,max_chars=900)
            row['article_overview']=overview
            plan=memory.compile(store=store,question=case['question'],document_id=did,
                focus_unit_id=case['focus_unit_id'],allowed_document_ids=[did],
                allowed_status=('VERIFIED_PROBE',),max_hops=2,max_nodes=4,max_chars=2500)
            row['path_plan']=plan
            if plan['status']!='HIT':raise ValueError('node path did not match the variant question')
            expected={case['focus_unit_id']}|{x['unit_id'] for x in plan['targets']}
            row['read_units']=sorted(expected,key=int)
            if len(expected)>4:raise ValueError('prefetch exceeded unit budget')
            evidence_ids=[];receipts=[]
            read_started=time.monotonic()
            for uid in row['read_units']:
                handle=sources.handle('U',{'document_id':did,'unit_id':uid})
                action={'tool':'read','args':{'target':handle,'extent':'exact','cursor':None},
                        'reason':'버전 결속 경로의 정확 단위 사전 읽기'}
                result=sources.execute(action,'path-prefetch-'+uid)
                receipts.append({'unit_id':uid,'status':result['status'],
                                 'coverage':result.get('coverage'),'evidence_ids':result.get('evidence_ids',[])})
                if result['status'] not in ('OK','REUSED') or not result.get('coverage',{}).get('complete'):
                    raise ValueError('prefetch READ failed: '+uid)
                evidence_ids.extend(result['evidence_ids'])
            row['prefetch_seconds']=round(time.monotonic()-read_started,3)
            row['read_receipts']=receipts
            block_map={}
            for eid in evidence_ids:
                evidence=repo.evidence(eid)
                sources.source.verify(evidence)
                if evidence['document_id']!=did:raise ValueError('prefetch evidence escaped document')
                for span in evidence['spans']:
                    bid=str(span['block_id']);block_map[bid]=span['text']
            row['evidence_blocks']=[{'block_id':bid,'text':block_map[bid]}
                                    for bid in sorted(block_map,key=int)]
            row['read_chars']=sum(len(x['text']) for x in row['evidence_blocks'])
            row['overview_chars']=sum(len(x['preview']) for x in overview['child_index'])
            row['required_blocks_present']=set(case['required_block_ids'])<=set(block_map)
            if not row['required_blocks_present']:raise ValueError('required blocks missing after prefetch')
            if not preflight:
                client=ExperimentClient(ROOT,out/'calls',max_calls=1,max_output_tokens=3000,
                                        schema_in_prompt=True,max_repairs=0)
                schema={'type':'object','additionalProperties':False,'properties':{
                    'sufficient':{'type':'boolean'},'answer':{'type':'string'},
                    'cited_block_ids':{'type':'array','items':{'type':'string'}},
                    'next_scope':{'type':'string','enum':['NONE','NEIGHBORS','ARTICLE','SEARCH']},
                    'reason':{'type':'string'}},
                    'required':['sufficient','answer','cited_block_ids','next_scope','reason']}
                guide=[{'observation_id':oid,'status':'VERIFIED_PROBE',
                        'role':'navigation_hint_not_evidence'} for oid in plan['observation_ids']]
                transport.authorize(query,request,store.manifest,public_question=True)
                answer=client.generate(
                    '현재 질문에 대해 evidence_blocks의 정확 원문만 법률 근거로 쓴다. '
                    'article_overview는 조의 자식 목록 미리보기이며 인용 근거가 아니다. '
                    'past_path는 과거 탐색 힌트일 뿐 답변이나 법률 정답이 아니다. '
                    '읽은 원문으로 충분하면 sufficient=true, next_scope=NONE으로 답하고 '
                    '사용한 block_id만 인용한다. 부족하면 sufficient=false와 필요한 다음 범위를 표시한다. '
                    '질문에 없는 사실·규정을 가정하지 않는다.',
                    {'question':case['question'],'article_overview':overview,
                     'past_path':guide,'evidence_blocks':row['evidence_blocks']},
                    schema,phase='path-prefetch-answer')
                if set(answer['cited_block_ids'])-set(block_map):
                    raise ValueError('model cited an unread block')
                row['answer']=answer;row['model_calls']=client.calls
                row['required_blocks_cited']=set(case['required_block_ids'])<=set(answer['cited_block_ids'])
                row['fast_path_complete']=bool(answer['sufficient'] and answer['next_scope']=='NONE'
                                               and row['required_blocks_cited'])
            row['tool_budget']=repo.budget()
            glossary.check_unchanged()
    except Exception as exc:
        row['error']={'type':type(exc).__name__,'message':str(exc),
                      'traceback':traceback.format_exc()}
    finally:
        if memory is not None:memory.close()
        if repo is not None:repo.close()
        if store is not None:store.close()
        row['seconds']=round(time.monotonic()-started,3)
        row['usage']=client.usage if client else []
        write(out/'result.json',row)
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    case=next(x for x in read(ADR/'artifacts/design/cases.json')['cases']
              if x['case_id']==args.case)
    row=run_case(case,preflight=args.preflight)
    print(json.dumps({k:row.get(k) for k in ('case_id','preflight','path_plan','read_units',
        'read_chars','overview_chars','model_calls','fast_path_complete','seconds','error')},
        ensure_ascii=False),flush=True)
    if row['error']:raise SystemExit(1)


if __name__=='__main__':main()

"""Frozen public-source unit expansion probe with actual Qwen3.8 decisions."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0582-unit-expansion-real-public-cases'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0582/real-expansion'
DOCUMENT = '00f033fddcef6be2'


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')


def pin():
    manifest = read(ADR/'실험/manifest.json')
    if manifest['design']['criteria_frozen_before_run'] is not True:
        raise ValueError('experiment design is not frozen')
    for path, expected in manifest['design']['frozen_inputs'].items():
        if sha(ROOT/path) != expected: raise ValueError('frozen input changed: '+path)
    revision = read(CANDIDATE/'candidate.json')['revisions'][-1]
    for entry in revision['files']:
        if sha(ROOT/entry['frozen_path']) != entry['snapshot_sha256']:
            raise ValueError('candidate revision drift: '+entry['frozen_path'])
    sys.path.insert(0, str(ROOT/'02_BACKEND'))
    import semantic_runtime.legal_agent as package
    candidate = CANDIDATE/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/semantic_runtime/legal_agent'
    package.__path__.insert(0, str(candidate))
    from semantic_runtime.legal_agent import exploration_tools, source_recall, source_selection, unit_access, unit_expansion
    for module in (exploration_tools, source_recall, source_selection, unit_access, unit_expansion):
        if not Path(module.__file__).is_relative_to(candidate):
            raise ValueError('research module was not loaded from frozen candidate: '+module.__name__)
    return exploration_tools, source_recall, source_selection, unit_access, unit_expansion


class NoModel:
    binding = {'provider':'offline','model':'no-model-resource-setup','adapter_version':'disabled-v1',
               'endpoint_identity':'none','trust_zone':'internal','max_input_bytes':2000000}
    def validate_model(self): return {'verified':False,'mode':'RESOURCE_SETUP_ONLY'}
    def send_once(self, **kwargs): raise AssertionError('resource setup must not call a model')


def run_case(case, preflight=False):
    exploration_tools, source_recall, source_selection, unit_access, unit_expansion = pin()
    from lawrag.research.experiment_client import ExperimentClient
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.tools_repository import ToolsRepository
    from semantic_runtime.legal_agent import tools_policy
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.contracts import digest
    out = ADR/'artifacts'/('preflight-002' if preflight else 'run-001')/case['case_id']
    out.mkdir(parents=True, exist_ok=False)
    started=time.monotonic();store=repo=None;client=None
    row={'case_id':case['case_id'],'question':case['question'],'error':None,
         'model':'qwen/qwen3.8-27b','preflight':preflight}
    try:
        config=read(ADR/'artifacts/design/cases.json')
        store=Store(ROOT/config['generation'])
        transport=LocalGemmaTransport(ROOT,ROOT)
        assert transport.binding['model']=='qwen/qwen3.8-27b'
        assert DOCUMENT in transport.public_scope
        settings=tools_policy.profile({**tools_policy.DEFAULT_PROFILE,
            'model_binding':NoModel.binding,'wall_seconds':300,'max_tool_actions':32,
            'max_context_chars':60000},require_model=True)
        runtime=ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-repair-20260929-r1/code'
        pipeline=Pipeline(runtime,store,implementation=tools_policy.IMPLEMENTATION,
            legal_agent_profile=settings,legal_agent_transport=NoModel())
        request={'question':case['question'],'document_ids':[DOCUMENT],'use_llm':True}
        query=pipeline.plan(case['question'],[DOCUMENT])
        auth=transport.authorize(query,request,store.manifest,public_question=True)
        row['authorization']={'grant_sha256':auth['grant_sha256'],
            'policy_sha256':auth['policy_sha256'],'scope_document_ids':auth['scope_document_ids']}
        agent=ServingDocumentAgent(pipeline,pipeline.term_agent.config)
        with agent.resources([DOCUMENT]) as (index,tools,glossary,matcher):
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
            sid_candidates=matcher._unit_sources(DOCUMENT,config['article_unit_id'])
            if len(sid_candidates)!=1: raise ValueError('article does not map to one source')
            sid=sid_candidates[0]
            uid,basis=unit_access.choose_unit(store,matcher.units,DOCUMENT,
                config['article_unit_id'],case['question'])
            row['initial_unit_id']=uid;row['initial_basis']=basis;row['source_id']=sid
            if uid!=case['expected_initial_unit_id']:
                raise ValueError('first unit differs from frozen expectation')
            target=sources.handle('U',{'document_id':DOCUMENT,'unit_id':uid})
            first=sources.execute({'tool':'read','args':{'target':target,'extent':'exact','cursor':None},
                'reason':'고정 공개 질문의 첫 구조 단위 확인'},'initial-unit-read')
            if first['status'] not in ('OK','REUSED') or not first.get('coverage',{}).get('complete'):
                raise ValueError('first exact READ did not complete')
            evidence=repo.evidence()
            record={'evidence':evidence,'read_complete':[], 'unit_complete':[sid],
                'selection_complete':[sid], 'article_unread_remainder':[sid],
                'selection_evidence_ids':{sid:first['evidence_ids']},
                'read_extent_by_source':{sid:'exact'},
                'unit_choices':[{'source_id':sid,'unit_id':uid,'basis':basis['basis']}],
                'selected_for_read':[sid],
                'routes':{sid:[{'kind':'fulltext','query':case['question'],'rank':1,'branch':'fixed_public_case'}]},
                'query_plan':{'queries':[case['question']],'law_names':[]},
                'packets':source_recall.evidence_packets(case['question'],evidence),
                'read_partial':[], 'limits':[], 'discovery_mode':'fulltext'}
            row['first_read_chars']=len(source_selection.originals(record)[sid]['text'])
            row['first_evidence_ids']=first['evidence_ids']
            if preflight:
                row['preflight_status']='SOURCE_READ_COMPLETE'
            else:
                client=ExperimentClient(ROOT,out/'calls',max_calls=6,
                    max_output_tokens=6400,schema_in_prompt=True,max_repairs=0)
                def invoke(system,data,schema,phase,timeout):
                    transport.authorize(query,request,store.manifest,public_question=True)
                    return client.generate(system,data,schema,phase=phase)
                selected=source_selection.select_sources(case['question'],record,invoke,
                    remaining_seconds=240)
                expansion=selected.get('expansion_request')
                row['selector_decisions']=selected['decisions']
                row['expansion_request']=expansion
                row['expansion_rejected']=selected.get('expansion_rejected')
                receipt=None
                if expansion and expansion['scope'] in ('NEIGHBORS','PARENT','ARTICLE'):
                    working=deepcopy(record)
                    working['final_ids']=list(selected['final_ids'])
                    receipt=unit_expansion.execute_local_expansion(
                        sources,working,expansion,case['question'])
                    if receipt['status']=='COMPLETE':
                        selected=source_selection.review_expanded(case['question'],working,
                            selected,expansion,invoke,remaining_seconds=120)
                        record=working
                elif expansion and expansion['scope']=='SEARCH':
                    working=deepcopy(record)
                    working['final_ids']=list(selected['final_ids'])
                    receipt=unit_expansion.execute_search_expansion(
                        sources,working,expansion,case['question'])
                    if receipt['status']=='COMPLETE':
                        selected=source_selection.select_sources(case['question'],working,invoke,
                            remaining_seconds=120,allow_expansion=False)
                        record=working
                row['expansion_receipt']=receipt
                row['final_ids']=selected['final_ids']
                row['final_decisions']=selected['decisions']
                original=source_selection.originals(record)
                final=[original[s] for s in selected['final_ids']]
                row['final_evidence_ids']={s:record['selection_evidence_ids'][s]
                                           for s in selected['final_ids']}
                row['final_texts']=[{'source_id':s['source_id'],'read_extent':s['read_extent'],
                    'text':s['text']} for s in final]
                block_ids={str(span['block_id']) for e in record['evidence']
                           if e['evidence_id'] in {eid for ids in row['final_evidence_ids'].values() for eid in ids}
                           for span in e['spans']}
                row['final_block_ids']=sorted(block_ids,key=int)
                row['required_blocks_present']=set(case['required_block_ids'])<=block_ids
                answer_schema={'type':'object','additionalProperties':False,'properties':{
                    'answer':{'type':'string'},'cited_block_ids':{'type':'array','items':{'type':'string'}},
                    'insufficient':{'type':'boolean'}},
                    'required':['answer','cited_block_ids','insufficient']}
                row['answer']=invoke('제공된 공개 규정 원문만 사용해 질문에 답한다. 보이지 않는 조항은 추측하지 않는다. '
                    '인용한 block_id만 cited_block_ids에 쓴다. 필요한 정의가 빠졌으면 insufficient=true다.',
                    {'question':case['question'],'sources':row['final_texts'],
                     'evidence_blocks':[{ 'block_id':str(span['block_id']), 'text':span['text']}
                        for e in record['evidence'] if e['evidence_id'] in
                        {eid for ids in row['final_evidence_ids'].values() for eid in ids}
                        for span in e['spans']]},answer_schema,'grounded-answer',120)
                row['model_calls']=client.calls
            row['tool_budget']=repo.budget()
            glossary.check_unchanged()
    except Exception as exc:
        row['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        if repo is not None: repo.close()
        if store is not None: store.close()
        row['seconds']=round(time.monotonic()-started,3)
        row['usage']=client.usage if client else []
        write(out/'result.json',row)
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    cases=read(ADR/'artifacts/design/cases.json')['cases']
    case=next(c for c in cases if c['case_id']==args.case)
    row=run_case(case,args.preflight)
    print(json.dumps({k:row.get(k) for k in ('case_id','preflight','initial_unit_id',
        'expansion_request','final_block_ids','required_blocks_present','model_calls','seconds','error')},
        ensure_ascii=False),flush=True)
    if row['error']: raise SystemExit(1)


if __name__=='__main__': main()

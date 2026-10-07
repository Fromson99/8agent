"""Paired hard-10 source-first probe. Gold answers are never loaded here."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0481-reviewed-links-hard10'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0481/hard10-reviewed-links'
MODEL='gemini-3.1-flash-lite'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')

def pin():
    design=read(ADR/'artifacts/frozen-design.json')
    for raw,value in design['file_hashes'].items():
        if sha(ROOT/raw)!=value:raise RuntimeError('Frozen input changed: '+raw)
    candidate=read(CAND/'candidate.json')
    rev=next(r for r in candidate['revisions'] if r['revision_id']=='rev-001')
    for row in rev['files']:
        if sha(ROOT/row['frozen_path'])!=row['snapshot_sha256']:
            raise RuntimeError('Frozen candidate changed')
    frozen=CAND/'revisions/rev-001/snapshot/02_BACKEND'
    sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.path.insert(0,str(frozen))
    import lawrag.research
    lawrag.research.__path__.insert(0,str(frozen/'lawrag/research'))
    return design,frozen

class GeminiSingleSendAdapter:
    """Translate one source-first JSON-schema request into one audited Gemini call."""
    def __init__(self,client):
        self.client=client
        self.binding={'provider':'gemini-experiment','model':client.model,
          'adapter_version':'gemini-single-send-v1',
          'endpoint_identity':hashlib.sha256(b'https://generativelanguage.googleapis.com/v1beta').hexdigest(),
          'trust_zone':'external','max_input_bytes':2_000_000}
    @property
    def physical_calls(self):return self.client.calls
    def validate_model(self):return {'verified':True,'model':self.client.model,'mode':'policy-pinned-experiment-client'}
    def send_once(self,*,body,ticket):
        from lawrag.research.experiment_client import ExperimentCallError
        from semantic_runtime.legal_agent.errors import BudgetExhausted,ProposalError,TransportError
        schema=body['response_format']['json_schema']['schema']
        system='\n\n'.join(m['content'] for m in body['messages'] if m['role']=='system')
        data={'messages':[m for m in body['messages'] if m['role']!='system']}
        phase='product-'+ticket['attempt_id'][-12:]
        try:
            value=self.client.generate(system,data,schema,phase=phase)
        except ExperimentCallError as exc:
            if str(exc)=='model_call_budget_exhausted':raise BudgetExhausted(str(exc)) from exc
            raise TransportError('Gemini audited call failed',retryable=False,unknown=True) from exc
        except Exception as exc:
            err=ProposalError('Gemini structured output failed local validation');err.response=None
            raise err from exc
        usage=self.client.usage[-1] if self.client.usage else {}
        mapped={'prompt_tokens':usage.get('input_tokens'),'completion_tokens':usage.get('output_tokens'),
                'total_tokens':usage.get('total_tokens')}
        payload={'model':self.client.model,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value,ensure_ascii=False)}}],
                 'usage':mapped}
        return {'status_code':200,'body_json':payload,'body_text':None,
                'body_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}

def preload_reviewed(session,source_ids):
    session.nav.bootstrap(session.context.query['question'])
    receipts=[]
    for sid in source_ids:
        card=session.nav.card(sid,'reviewed_relation')
        cursor=None
        while True:
            result=session.nav.read(card['card'],cursor,route='reviewed_relation')
            receipts.append({'source_id':sid,'card':card['card'],'status':result['status'],
                             'evidence_ids':result['evidence_ids'],'next_cursor':result['next_cursor']})
            cursor=result['next_cursor']
            if cursor is None:break
    return receipts

def run_one(case,arm,index,fixture,design,frozen):
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.domain import DEFAULT_PROFILE,profile
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.repository import WorkRepository
    from semantic_runtime.legal_agent.source_tools import SourceSession
    from semantic_runtime.legal_agent.source_first_protocol import DOMAIN,NAVIGATION,FEEDBACK_POLICY,LINKED_CONTEXT_POLICY
    from semantic_runtime.legal_agent.source_first_gateway import SourceFirstGateway
    from semantic_runtime.legal_agent.source_first_session import SourceFirstSession
    from semantic_runtime.contracts import digest
    from lawrag.research.experiment_client import GeminiExperimentClient
    out=ADR/'artifacts/run-001'/case['case_id']/arm
    out.mkdir(parents=True,exist_ok=False)
    client=GeminiExperimentClient(ROOT,out/'calls',max_calls=14,max_output_tokens=2800)
    wire=GeminiSingleSendAdapter(client);settings=profile({**DEFAULT_PROFILE,'model_binding':wire.binding},require_model=True)
    store=repo=session=None;started=time.monotonic()
    output={'case_id':case['case_id'],'arm':arm,'model':MODEL,'main_wiring':'unchanged','error':None,
            'reviewed_relation_source_ids':case['reviewed_relation_source_ids'],'reviewed_read_receipts':[]}
    try:
        store=Store(ROOT/fixture['generation'])
        p=Pipeline(ROOT,store,implementation='legal-agent-v1',legal_agent_profile=settings,legal_agent_transport=wire)
        query=p.plan(case['question'],fixture['public_scope_document_ids'])
        request={'question':case['question'],'document_ids':fixture['public_scope_document_ids'],'use_llm':True}
        source_agent=ServingDocumentAgent(p,p.term_agent.config)
        with source_agent.resources(query['scope']['document_version_ids']) as (index_db,tools,glossary,matcher):
            binding={'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],
              'source_export_allowed':store.manifest['export_allowed'],'export_allowed':True,
              'authorization_sha256':digest({'policy':'gemini-experiments-v1','scope':'public'}),
              'scope':query['scope'],'model':wire.binding,'domain_sha256':digest(DOMAIN),
              'profile_sha256':digest(settings),'navigation_policy':NAVIGATION,
              'feedback_policy_sha256':digest(FEEDBACK_POLICY),'linked_context_policy_sha256':digest(LINKED_CONTEXT_POLICY),
              'index_sha256':index_db.manifest['index_sha256'],'glossary':glossary.binding,
              'fulltext_sha256':matcher.fulltext.manifest['fulltext_sha256']}
            context=RequestContext.create(query,request,binding,settings['wall_seconds'])
            repo=WorkRepository(out/'journal.sqlite',context,settings)
            sources=SourceSession(store,tools,glossary,matcher,repo,context,settings)
            gateway=SourceFirstGateway(repo,context,settings,DOMAIN,wire)
            session=SourceFirstSession(context,repo,sources,gateway,settings,store.manifest['data_status'])
            session.check_sources_unchanged=glossary.check_unchanged
            if arm=='reviewed-links':
                output['reviewed_read_receipts']=preload_reviewed(session,case['reviewed_relation_source_ids'])
            retrieval=session.investigate()
            selected=session.select({'request':request,'query':query,'retrieval':retrieval})
            assembled={'request':request,'query':query,'retrieval':retrieval,'selection':selected,'assembly':session.assemble()}
            for _ in range(settings['max_cycles']+1):
                result,control=session.answer_and_review(assembled)
                if control['decision']=='FINAL':break
                if control['decision']=='RESEARCH':
                    retrieval=session.investigate();selected=session.select({'retrieval':retrieval})
                    assembled={'request':request,'query':query,'retrieval':retrieval,'selection':selected,'assembly':session.assemble()}
            else:raise RuntimeError('Controller did not reach FINAL')
            output.update(result=result,control=control);glossary.check_unchanged()
    except Exception as exc:
        output['error']={'type':type(exc).__name__,'message':str(exc)}
        if repo is not None:repo.fail(getattr(exc,'code',type(exc).__name__))
    finally:
        if repo is not None:
            evidence=repo.evidence();by_e={e['evidence_id']:e['source_id'] for e in evidence}
            presented={by_e[r[0]] for r in repo.db.execute('SELECT DISTINCT evidence_id FROM presentation') if r[0] in by_e}
            selected_sources={by_e[i] for i in getattr(session,'selected',set()) if i in by_e}
            claims=repo.heads('claim',current=True)
            answer_sources={by_e[i] for c in claims for i in c['payload']['evidence_ids'] if i in by_e}
            output['stages']={'discovered':sorted(getattr(session.nav,'by_source',{})),
              'read':sorted({e['source_id'] for e in evidence}),'presented':sorted(presented),
              'selected':sorted(selected_sources),'answer':sorted(answer_sources)}
            output.update(budget=repo.budget(),journal_run=repo.run())
            write(out/'trace.json',{'cards':list(session.nav.cards.values()),'evidence':evidence,
              'selected_evidence_ids':sorted(session.selected),'packed':session.packed,
              'observations':repo.observations(10000),'limitations':session.limitations})
            session.close();repo.close()
        if store is not None:store.close()
        output.update(physical_calls=client.calls,usage=client.usage,seconds=round(time.monotonic()-started,3))
        write(out/'result.json',output)
    return output

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    design,frozen=pin();fixture=read(ADR/'product-cases.json')
    if not args.execute:
        print(json.dumps({'preflight':'pass','network_calls':0,'cases':len(fixture['cases']),'arms':design['arms'],'model':MODEL}));return
    runroot=ADR/'artifacts/run-001'
    if runroot.exists():raise RuntimeError('run-001 exists; never overwrite or repeat')
    runroot.mkdir(parents=True)
    summary={'schema_version':'hard10-paired-results-v1','model':MODEL,'cases':{},'started_at':time.time()}
    for i,case in enumerate(fixture['cases']):
        order=['baseline','reviewed-links'] if i%2==0 else ['reviewed-links','baseline']
        summary['cases'][case['case_id']]={}
        for arm in order:
            result=run_one(case,arm,i,fixture,design,frozen)
            summary['cases'][case['case_id']][arm]=result
            write(runroot/'results.partial.json',summary)
            print(json.dumps({'case':case['case_id'],'arm':arm,'calls':result['physical_calls'],
                              'error':result['error'],'seconds':result['seconds']},ensure_ascii=False),flush=True)
    summary['finished_at']=time.time();write(runroot/'results.json',summary)
    print(json.dumps({'complete':True,'case_count':len(summary['cases'])},ensure_ascii=False))

if __name__=='__main__':main()

from common import *
import sqlite3,time,types,httpx,traceback,resource
from unittest.mock import patch
os.environ.update(MALLOC_ARENA_MAX='1',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.environ.pop('DP',None)
case='conflict'
out=ART/'replay';out.mkdir(exist_ok=False)
C=ROOT/read(DES/'candidate.json')['code_root']
from pinned_imports import install
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.ontology_work.repository import Repository
from semantic_runtime.ontology_work.store import LocalFolderStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
from semantic_runtime.ontology_work.wiki_workspace import Workspace
from semantic_runtime.ontology_work.wiki_projection import compare_judgment
from semantic_runtime.ontology_work import wiki_contracts as wc,authoring_model
from semantic_runtime.ontology_work.configuration import source_reader
from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
from semantic_runtime.ontology_work.observations import envelope
from semantic_runtime.full_glossary import Glossary
from semantic_runtime.full_glossary_connections import ConnectionReader
from semantic_runtime.contracts import digest
from semantic_runtime import genos
from lawrag.core import request_deadline as dt
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from resource_guard import Guard
guard=Guard(out);guard.start()
b=read(DES/'baseline.json');data=ROOT/b['release']['data_path'];meta=read(data/'manifest.json');g=meta['glossary']
reader=Glossary(data/g['bundle'],data/g['dictionary'],data/g['cache'],manifest_sha256=g['manifest_sha256'],connection_factory=ConnectionReader)
glossary=GlossaryBinding(reader,snapshot=meta['generation_id'])
base_dir=ART/'sandbox-repository'
repo=Repository(lambda:sqlite3.connect(base_dir/'work.sqlite'));store=LocalFolderStore(base_dir/'objects')
documents=read(DES/'source-scope.json')['public']
source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(data/'store.sqlite')}},documents)
args=dict(actor='codex-isolated-experiment-reviewer',source_reader=source,generate=None,namespace='ADR1371-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=read(DES/'candidate.json')['pin']['revision_sha256'])
w=Workspace(repo,store,can_publish=True,**args)
repo.workspace_scopes={wc.scope_key(w.scope())}
parent=read(DES/'parent-knowledge.json')
target=read(DES/'followups.json')[case];origin=read(ROOT/target['path'])
for key in target['pointer']:origin=origin[key]
assert origin==target['payload'] and sha(ROOT/target['path'])==target['sha256']
record=envelope(origin,namespace=w.namespace,run_id=target['run_id'],event_id=target['path']+str(target['pointer']),sequence=0,source_snapshot=w.source_snapshot,producer_binding=target['sha256'],acl_ref=w.acl_ref,document_ids=documents,format_description='Exact earlier public Qwen statement, possible error; independently verify original text',origin='ARCHIVED_MODEL_OUTPUT')
r=w.ingest(record);assert w.ingest(record)['work_hash']==r['work_hash']
previous=w.load(parent['bundle_id']);assert previous['revision']==2
P=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1374*/artifacts/followup-conflict/canonical'))
calls=[]
def recorded(prompt,context,schema):
    n=len(calls)+1
    assert n<=2
    incoming=read(P/f'{n:03}.json.gz')
    assert prompt==incoming['prompt'] and schema==incoming['schema']
    def substantive(d):
        return {k:v for k,v in d.items() if k!='call_budget'}
    assert substantive(context)==substantive(incoming['context'])
    value=read(P/f'{n:03}-output.json.gz')
    calls.append({'stage':context.get('operation','NORMALIZE'),'source':str((P/f'{n:03}-output.json.gz').relative_to(ROOT)),'hash':sha(P/f'{n:03}-output.json.gz')})
    return value, {'mode':'recorded-proposal-only','physical_calls':0,'origin':calls[-1]['hash']}
w.generate=recorded
try:
    args={'bundle_id':parent['bundle_id'],'revision':previous['revision'],'work_hash':previous['work_hash'],'raw_id':r['bundle_id']}
    saved=compare_judgment(w,w,**args)
    current=w.load(parent['bundle_id'])
    assert compare_judgment(w,w,**args)['reused'] and len(calls)==2
    assert current['review_state']=='REVIEW_CONFLICT' and current['revision']==3
    assert current['proposal']['graph']==previous['proposal']['graph'] and current['comparison_history'][:-1]==previous['comparison_history']
    rows=current['proposal']['comparisons'];new,=[z for z in rows if z['relation']=='NEW']
    assert new['verdict']=='SUPPORTED' and new['node_ids']==[] and new['basis']
    assert any(z['relation']=='CONTRADICTION' and z['verdict']=='CONTRADICTED' and z['node_ids'] for z in rows)
    put(out/'result.json',{'physical_calls':0,'same_model_input_and_schema_except_clock':True,'replayed':calls,'saved':saved,'unchanged_graph':True,'original_comparisons_preserved':True,'review_state':current['review_state'],'comparisons':rows})
    print('Recorded proposals accepted, review conflict, new independent reference has no forced node.')
finally:
    guard.done.set();guard.thread.join(timeout=2);reader.close()

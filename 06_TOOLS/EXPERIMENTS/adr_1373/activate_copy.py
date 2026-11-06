from common import *
import sqlite3,time,types,httpx,traceback,resource
from unittest.mock import patch
os.environ.update(MALLOC_ARENA_MAX='1',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.environ.pop('DP',None)

out=ART/'sandbox-repository'
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

b=read(DES/'baseline.json');data=ROOT/b['release']['data_path'];meta=read(data/'manifest.json');g=meta['glossary']
reader=Glossary(data/g['bundle'],data/g['dictionary'],data/g['cache'],manifest_sha256=g['manifest_sha256'],connection_factory=ConnectionReader)
glossary=GlossaryBinding(reader,snapshot=meta['generation_id'])
base_dir=out
repo=Repository(lambda:sqlite3.connect(base_dir/'work.sqlite'));store=LocalFolderStore(base_dir/'objects')
documents=read(DES/'source-scope.json')['public']
source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(data/'store.sqlite')}},documents)
args=dict(actor='codex-isolated-experiment-reviewer',source_reader=source,generate=None,namespace='ADR1371-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=read(DES/'candidate.json')['pin']['revision_sha256'])
w=Workspace(repo,store,can_publish=True,**args)
repo.workspace_scopes={wc.scope_key(w.scope())}
parent=read(DES/'parent-knowledge.json')
gate=read(ART/'isolated-review-decision.json')
assert gate['scope']=='isolated-reuse-only' and gate['approved_revision'] in (1,2)
bid=parent['bundle_id'];d=w.load(bid)
assert d['revision']==gate['approved_revision'] and d['work_hash']==gate['work_hash']
assert d['review_state']!='REVIEW_CONFLICT' and d['status']=='DRAFT'
w.can_publish_workspace=True
w.review(bid,d['revision'],d['work_hash'],True,gate['reason'])
stage=w.stage_publication(bid,d['revision'],d['work_hash'],0)
pid=stage['publication_id'];receipt=w.verify_publication(pid);w.activate_publication(pid,0,receipt)
head=repo.head(bid);assert head['publication_id']==pid and repo.current_publications([{'bundle_id':bid,'publication_id':pid,'package_sha256':receipt['binding']['package_hash']}],set(documents))[pid]
published=repo.publication(pid,documents)
assert published['context']['assembly_package']['revision']==d['revision']
put(ART/'publication-verified.json',{'active':True,'bundle_id':bid,'revision':d['revision'],'work_hash':d['work_hash'],'publication_id':pid,'stage':stage,'receipt':receipt,'package_sha256':published['context']['assembly_package']['package_sha256'],'test_only':True,'scope':w.scope(),'selected_main_or_gold_modified':False})
reader.close()
print('Activated test-only revision',d['revision'],pid)

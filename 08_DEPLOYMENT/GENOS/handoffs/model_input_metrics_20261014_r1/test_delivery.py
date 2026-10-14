"""Actual shipped installers and service.service boot, synthetic data/models only."""
import gzip,hashlib,importlib.util,json,os,subprocess,sys,zipfile
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_unit_fulltext_adaptive_read import tree as source_tree
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
R1=OUT.with_name('rag_focused_rules_20261013_r1')/'GENOS_RAG_FOCUSED_RULES_20261013_R1_RUN.txt'
R2=OUT.with_name('rag_focused_rules_20261013_r2')/'GENOS_RAG_FOCUSED_RULES_20261013_R2_RUN.txt'
R3=OUT.with_name('rag_focused_rules_20261013_r3')/'GENOS_RAG_FOCUSED_RULES_20261013_R3_RUN.txt'
RN=OUT/'GENOS_MODEL_INPUT_METRICS_20261014_R1_RUN.txt'
spec=importlib.util.spec_from_file_location('r3_installer_test',OUT/'apply_patch.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

@pytest.fixture
def tree(tmp_path_factory,term_glossary):
 return source_tree.__wrapped__(tmp_path_factory.mktemp('metrics-synthetic-api-data'),term_glossary)

@pytest.mark.parametrize('basis,display,budget_enabled,prior_ad,prior_success,prior_guidance',[
 ('query_latency_20261007_r3',False,False,True,False,False),
 ('query_latency_20261007_r4',True,True,True,True,False),
 ('query_latency_20261007_r3',False,False,True,False,True),
 ('query_latency_20261007_r4',True,True,True,True,True)])
def test_real_service_boot_upgrade_repeat_tamper_undo_and_gate(tmp_path,structured_generation,tree,basis,display,budget_enabled,prior_ad,prior_success,prior_guidance):
 source=OUT.with_name(basis);hand=json.loads((source/'HANDOFF.json').read_bytes());root=tmp_path/'DEV';root.mkdir()
 with zipfile.ZipFile(source/(hand['version']+'.zip')) as z:z.extractall(root)
 generation=structured_generation
 generation_files={str(p.relative_to(generation)):hashlib.sha256(p.read_bytes()).hexdigest() for p in generation.rglob('*') if p.is_file()}
 env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
  'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_GENERATION':str(generation),
  'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
  'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6','GENOS_LLM_MODEL':'synthetic-no-network-model',
  'GENOS_BASE_URL':'https://synthetic-genos.invalid','GENOS_LLM_SERVING_ID':'1','GENOS_LLM_KEY':'synthetic-test-key',
  'SEMANTIC_LLM_BACKEND':'genos','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
 env.update(METRICS_TEST_GENERATION=str(tree[0]),METRICS_TEST_UNIT_INDEX=str(tree[1].path))
 for k in ('LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256','GENOS_LLM_URL','GENOS_PATCH_DEV'):env.pop(k,None)
 transcript=[]
 def run(argv,success=True):
  r=subprocess.run(argv,cwd=root,env=env,text=True,capture_output=True,timeout=90)
  transcript.append({'argv':argv,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
  # Always save evidence even if a later assertion fails.
  (OUT/('TEST_'+basis+('_display' if display else '')+('_budget' if budget_enabled else '')+('_ad' if prior_ad else '')+('_success' if prior_success else '')+('_guidance' if prior_guidance else '')+'.json.gz')).write_bytes(gzip.compress(json.dumps(transcript,ensure_ascii=False).encode(),mtime=0))
  assert (r.returncode==0)==success,r.stdout+r.stderr
  return r
 rollback=OUT.with_name('db_log_rollback_20261007_r3')/'GENOS_DB_LOG_ROLLBACK_20261007_R3_RUN.txt'
 run(['bash',str(rollback),'apply'])
 if display:
  script=OUT.with_name('rag_progress_graph_20261008_r5')/'GENOS_RAG_PROGRESS_GRAPH_20261008_R5_RUN.txt'
  run(['bash',str(script),'apply'])
 run(['bash',str(R1),'apply'])
 run(['bash',str(R2),'apply'])
 run(['bash',str(R3),'apply'])
 run(['bash',str(OUT.with_name('rag_narrative_stream_20261013_r2')/'GENOS_RAG_NARRATIVE_STREAM_20261013_R2_RUN.txt'),'apply'])
 run(['bash',str(OUT.with_name('model_stream_fix_20261013_r1')/'GENOS_MODEL_STREAM_FIX_20261013_R1_RUN.txt'),'apply'])
 if budget_enabled:
  budget_dir=OUT.with_name('investigation_budget_20261007_r1')
  budget_spec=importlib.util.spec_from_file_location('verified_budget_installer',budget_dir/'install_budget.py')
  budget_installer=importlib.util.module_from_spec(budget_spec);budget_spec.loader.exec_module(budget_installer)
  _,_,budget_changes,_=budget_installer.prepare(root,json.loads((budget_dir/'PATCH_SPEC.json').read_bytes()))
  for name,raw in budget_changes.items():(root/name).write_bytes(raw)
  env.update(GENOS_RAG_MAX_MODEL_ATTEMPTS='60',GENOS_RAG_MAX_TOOL_ACTIONS='2048',GENOS_RAG_WALL_SECONDS='3600',GENOS_RAG_SEARCH_ROUNDS='12',GENOS_RAG_ASSESSMENT_REENTRY_LIMIT='0')
 if prior_ad:
  run(['bash',str(OUT.with_name('ad_request_logs_20261013_r2')/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt'),'apply'])
 if prior_success:
  run(['bash',str(OUT.with_name('successful_shortcut_20261013_r1')/'GENOS_SUCCESSFUL_SHORTCUT_20261013_R1_RUN.txt'),'apply'])
 run(['bash',str(OUT.with_name('assessment_gap_action_20261013_r2')/'GENOS_ASSESSMENT_GAP_ACTION_20261013_R2_RUN.txt'),'apply'])
 if prior_guidance:
  run(['bash',str(OUT.with_name('public_failure_guidance_20261014_r1')/'GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1_RUN.txt'),'apply'])
 before_manifest=(root/'CODE_MANIFEST.json').read_bytes();before=json.loads(before_manifest)
 before_files={row['path']:(root/row['path']).read_bytes() for row in before['files']}
 # Exercise the real endpoint-model validation with a synthetic /models response;
 # prohibit every real socket and any inference request.
 boot='''import asyncio,json,os,socket,sys,httpx
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('unexpected network access'))
model_requests=[]
def advertised_model(request):
 assert request.url.host=='synthetic-genos.invalid',str(request.url)
 assert request.method=='GET' and request.url.path.endswith('/models'),str(request.url)
 model_requests.append(str(request.url))
 return httpx.Response(200,json={'data':[{'id':'synthetic-no-network-model'}]})
original_client=httpx.AsyncClient
class LocalClient(original_client):
 def __init__(self,*args,**kwargs):
  if 'transport' not in kwargs:kwargs['transport']=httpx.MockTransport(advertised_model)
  super().__init__(*args,**kwargs)
httpx.AsyncClient=LocalClient
import service
reply=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}))
print('SERVICE_BOOT_RESULT '+json.dumps(reply,ensure_ascii=False))
expected=int(sys.argv[1]);assert reply['status']==expected,reply
if expected==503:
 assert reply['body']['code']=='RUNTIME_BOOTSTRAP_ERROR' and reply['body']['error_type']=='ContractError'
 assert not model_requests
else:
 p=service._APP.state.pipeline.term_agent.profile
 assert p['request_entry_policy']=='fused-title-v1'
 assert p['candidate_navigation']['completion_policy_version']=='investigation-completion-v8'
 assert service._BINDING['mode']=='genos-generation'
 if os.environ.get('GENOS_RAG_MAX_MODEL_ATTEMPTS')=='60':
  assert p['max_model_attempts']==60 and p['max_tool_actions']==2048 and p['wall_seconds']==3600
  assert p['candidate_navigation']['search_rounds']==12 and p['candidate_navigation']['assessment_reentry_limit']==0
 assert len(model_requests)==1,model_requests
 print('SERVICE_PROFILE_BOOTSTRAP PASS; mocked model discovery=1; real network/inference calls=0')
'''
 run([str(ROOT/'.venv/bin/python'),'-c',boot,'200'])
 run(['bash',str(RN),'check']);run(['bash',str(RN),'apply']);run(['bash',str(RN),'apply']);run(['bash',str(RN),'verify'])
 r=run([str(ROOT/'.venv/bin/python'),'-c',boot,'200']);assert 'SERVICE_PROFILE_BOOTSTRAP PASS' in r.stdout
 if budget_enabled:
  after=json.loads((root/'CODE_MANIFEST.json').read_bytes())
  assert after['investigation_budget_settings']==before['investigation_budget_settings']
  for op in json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))['budget_policy']['operations']:
   assert (root/'service.py').read_text().count(op['after'])==1
 run([str(ROOT/'.venv/bin/python'),str(OUT/'installed_runner.py'),str(root),str(ROOT/'05_TESTS/CONTRACTS/test_model_input_metrics.py'),str(ROOT/'05_TESTS/CONTRACTS/test_final_failure_logging.py')])
 backup=next((root/'TRANSFER/model-input-metrics-r1').glob('backup-*'))
 changed=json.loads((backup/'receipt.json').read_bytes())['files']
 allowed={'CODE_MANIFEST.json','00_SYSTEM/PIPELINE.json'} | set(json.loads((OUT/'SOURCE_BINDING.json').read_text())['source_files'])
 allowed|={entry['manifest'] for entry in json.loads(before_files['00_SYSTEM/PIPELINE.json'])['engines'].values()}
 assert {r['path'] for r in changed}<=allowed
 assert all((root/n).read_bytes()==raw for n,raw in before_files.items() if n not in allowed)
 run(['git','init','-q',str(root)])
 manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
 run(['git','add','-f','--','CODE_MANIFEST.json',*[r['path'] for r in manifest['files']]])
 run(['git','-c','user.name=Synthetic validation','-c','user.email=validation@example.invalid','commit','-qm','R3 scoped fulltext fixture'])
 r=run(['bash',str(RN),'gate',str(backup),'--generation',str(generation)])
 assert 'GENOS_RELEASE_GATE PASS' in r.stdout
 target=root/'02_BACKEND/semantic_runtime/request_report.py';saved=target.read_bytes()
 target.write_bytes(saved+b'\n# unknown change\n')
 run(['bash',str(RN),'verify'],success=False);run(['bash',str(RN),'undo',str(backup)],success=False)
 assert target.read_bytes()==saved+b'\n# unknown change\n';target.write_bytes(saved)
 run(['bash',str(RN),'undo',str(backup)])
 assert (root/'CODE_MANIFEST.json').read_bytes()==before_manifest
 assert all((root/n).read_bytes()==raw for n,raw in before_files.items())
 assert (root/'02_BACKEND/semantic_runtime/legal_agent/model_contract.py').exists() == prior_ad
 assert (root/'02_BACKEND/semantic_runtime/legal_agent/model_stream.py').exists()
 assert {str(p.relative_to(generation)):hashlib.sha256(p.read_bytes()).hexdigest() for p in generation.rglob('*') if p.is_file()}==generation_files

"""Finite host protocol truth table; actual bounded adapter/journal, no model."""
from pathlib import Path
import gzip,itertools,json,sys,tempfile
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]);out=Path(sys.argv[2])
sys.dont_write_bytecode=True
sys.path[:0]=[str(code/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(R/'02_BACKEND')]
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(code)
from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
from semantic_runtime.legal_agent import output_contract as oc
import importlib
for name in ('lawrag','lawrag.pipeline','lawrag.core','lawrag.core.structure'):
 module=importlib.import_module(name);module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
from test_legal_agent_double_harness import work,PROFILE,wire
from types import SimpleNamespace
from copy import deepcopy
criteria=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0783-length-recovery-path-integrity/artifacts/design/criteria.json').read_text())['matrix']
schema={'type':'object','properties':{'ok':{'const':True}},'required':['ok'],'additionalProperties':False}
rows=[]
with tempfile.TemporaryDirectory(prefix='length-contracts-') as td:
 for ceiling,initial,first,second,usage in itertools.product(*(criteria[k] for k in ('ceiling','initial','first','second','usage'))):
  n=len(rows);folder=Path(td)/str(n);folder.mkdir();fixture=work.__wrapped__(folder);repo=next(fixture);calls=[]
  class Transport:
   binding=PROFILE['model_binding']
   def send_once(self,*,body,ticket):
    calls.append(deepcopy(body));reason=first if len(calls)==1 else second
    response=wire({'ok':True});response['body_json']['choices'][0]['finish_reason']=reason
    if reason=='length':response['body_json']['choices'][0]['message']['content']='{"ok":'
    if usage:response['body_json']['usage']={'completion_tokens':body['max_tokens']}
    return response
  s=object.__new__(BoundedSourceSession);s.work=repo;s.context=repo.context;s.selection_views={}
  s.profile={**PROFILE,'max_output_tokens':6400,'candidate_navigation':{'completion_contract':True,'length_recovery_max_tokens':ceiling}}
  s.gateway=SimpleNamespace(domain={},transport=Transport())
  data={'question':'synthetic','sources':[]};phase='source-law-navigation-2'
  def invoke(payload,attempt):return s.structured('unchanged system',payload,schema,phase+('-repair' if attempt else ''),60,initial)
  def run():return oc.bounded_decision(repo,'law-navigation',data,schema,invoke,lambda v:oc.validate_shape(v,schema))
  success=False;error=None
  try:success=run()=={'ok':True}
  except oc.OutputContractError as exc:error=oc.diagnostics(exc)
  retry=first=='length' and (ceiling==0 or ceiling>initial)
  expected_success=first=='stop' or retry and second=='stop'
  expected_caps=[initial]+([max(initial,ceiling)] if retry else [])
  before=len(calls)
  try:run()
  except oc.OutputContractError:pass
  checks=[success==expected_success,[c['max_tokens'] for c in calls]==expected_caps,len(calls)==before,
   repo.budget()['model_reserved']==len(calls),not repo.heads('finding'),
   all(c['response_format']==calls[0]['response_format'] for c in calls),
   all(c['messages'][0]==calls[0]['messages'][0] for c in calls)]
  rows.append({'ceiling':ceiling,'initial':initial,'first':first,'second':second,'usage':usage,
    'success':success,'caps':[c['max_tokens'] for c in calls],'expected_success':expected_success,
    'expected_caps':expected_caps,'checks':checks,'contract_correct':all(checks),'error':error})
  try:next(fixture)
  except StopIteration:pass
assert len(rows)==criteria['expected_total'],len(rows)
# Independent finite namespace contract: checkout names do not grant or deny
# dependency permissions. Actual dependency components still enforce exclusion.
import importlib.util
spec=importlib.util.spec_from_file_location('qualification_host',code/'02_BACKEND/PIPELINE/engine_host.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
paths=['plain','research','nested/research/checkout','research/project/research','researcher','my-research','한글/research/검사','a/b/c']
deps=['02_BACKEND/runtime.py','02_BACKEND/research/private.py','02_BACKEND/lawrag/research/private.py','02_BACKEND/researcher/runtime.py']
with tempfile.TemporaryDirectory(prefix='namespace-contract-') as td:
 for index,(folder,dep,maturity) in enumerate(itertools.product(paths,deps,['TOOL','RELEASED'])):
  root=Path(td)/str(index)/folder;(root/'00_SYSTEM/SCHEMAS').mkdir(parents=True)
  (root/'00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json').write_bytes((R/'00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json').read_bytes())
  m=json.loads((code/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json').read_text())
  source=root/dep;source.parent.mkdir(parents=True,exist_ok=True);source.write_text('VALUE = 1\n')
  m.update(inputs={},outputs={},maturity=maturity,files={dep:host.sha(source)},entrypoint={'path':dep,'function':'run'})
  target=root/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json';target.parent.mkdir(parents=True);target.write_text(json.dumps(m))
  config={'engines':{m['id']:{'manifest':str(target.relative_to(root)),'sha256':host.sha(target)}}}
  accepted=False
  try:host.engine(config,m['id'],'tool',root);accepted=True
  except host.ContractError:pass
  expected='research' not in Path(dep).parts
  rows.append({'family':'engine_namespace','checkout':folder,'dependency':dep,'maturity':maturity,'accepted':accepted,'expected':expected,'contract_correct':accepted==expected})
# Resolve symlinks before classifying actual dependencies.
with tempfile.TemporaryDirectory(prefix='resolved-dependency-') as td:
 for index,(folder,target_kind,maturity) in enumerate(itertools.product(['checkout','research/checkout'],['runtime','research'],['TOOL','RELEASED'])):
  root=Path(td)/str(index)/folder;(root/'00_SYSTEM/SCHEMAS').mkdir(parents=True)
  (root/'00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json').write_bytes((R/'00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json').read_bytes())
  dep='02_BACKEND/'+target_kind+'/target.py';source=root/dep;source.parent.mkdir(parents=True);source.write_text('VALUE = 1\n')
  alias=root/'02_BACKEND/alias.py';alias.symlink_to(source)
  m=json.loads((code/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json').read_text());m.update(inputs={},outputs={},maturity=maturity,files={'02_BACKEND/alias.py':host.sha(alias)},entrypoint={'path':'02_BACKEND/alias.py','function':'run'})
  target=root/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json';target.parent.mkdir(parents=True);target.write_text(json.dumps(m))
  config={'engines':{m['id']:{'manifest':str(target.relative_to(root)),'sha256':host.sha(target)}}};accepted=False
  try:host.engine(config,m['id'],'tool',root);accepted=True
  except host.ContractError:pass
  expected=target_kind=='runtime';rows.append({'family':'resolved_dependency','checkout':folder,'target':dep,'maturity':maturity,'accepted':accepted,'expected':expected,'contract_correct':accepted==expected})
assert len(rows)==264

out.write_bytes(gzip.compress(json.dumps({'code_root':str(code),'cases':rows},ensure_ascii=False).encode(),mtime=0))
print(json.dumps({'code_root':str(code),'cases':len(rows),'passed':sum(r['contract_correct'] for r in rows)}))

from pathlib import Path
import json,hashlib,sys,shutil,ast
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract';ART=A/'artifacts';D=Path(__file__).parent;OLDADR=R/'04_EXPERIMENTS/ADR/ADR-1121-ontology-semantic-compilation'
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
of=read(OLDADR/'artifacts/freeze.json');OLD=R/of['code_root'];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
criteria=read(OLDADR/'artifacts/criteria.json');criteria.update(hypothesis='Explicit exception-to-target direction and path-rich structural feedback let the same source/judgment proposal become a compilable semantic plan; compare the same original set downstream.',build='Start from the preserved failed1121 proposal with original28/judgment3 and exact structural diagnostics. At most2 new calls (proposal correction + one repair). No offline gold/critique. No automatic semantic reversal.',predecessor='1121 110checks passed;2buildcalls failed, answerpair not run. Both failures retained.')
put(ART/'criteria.json',criteria)
for n in ('baseline.json','composition.json','cases.json','build-input.json','prefix.json'):shutil.copyfile(OLDADR/'artifacts'/n,ART/n)
previous=OLDADR/'artifacts/build/raw/call-002-semantic-repair/output.json';put(ART/'previous-proposal.json',{'path':str(previous.relative_to(R)),'sha256':sha(previous),'proposal':read(previous),'failure':'exception target on wrong node role'})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['success'],failure_criteria='Any integrity failure or failed build; downstream no semantic replacement',criteria_frozen_before_run=True)
for a in m['design']['arms']:a.update(changes=criteria['arms'][a['id']],controls='Same660files/currentMAIN107, original snapshot, replayprefix, schemas/model/budget; semantic graph only differs')
m['runs'][0].update(selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(R)));put(A/'실험/manifest.json',m)
present=[n for n in of['files'] if (R/n).is_file()];C=ac.snapshot(A,'semantic-r1',present,experiment_id=m['experiment_id'],arm_id='semantic',run_ids=['run-001']);S=C/'snapshot'
for n,h in of['files'].items():
 assert sha(OLD/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
p=S/'02_BACKEND/semantic_runtime/legal_agent/ontology_semantics.py';s=p.read_text()
s=s.replace("'exception_targets':arr(REF,16)","'exception_targets':{**arr(REF,16),'description':'Only an EXCEPTION node may use this field: IDs of EFFECT/CALCULATION/CONDITION nodes that THIS exception modifies. EFFECT must have []. Never list an exception on its normal effect.'}")
s=s.replace("exception_targets는 예외가 바꾸는 효과 노드 ID이며 의존과 구분한다.","exception_targets는 현재 EXCEPTION 노드가 변경하는 EFFECT/CALCULATION/CONDITION 노드 ID다. EXCEPTION 이외 역할은 반드시 빈 배열이다. 정상 효과가 자기에게 붙는 예외를 가리키는 역방향 목록이 아니다. 예: E(정상효과)의 exception_targets=[], X(예외)의 exception_targets=[E]. 역할이나 원문 의미를 바꾸어 형식을 맞추지 않는다. dependencies는 효과가 실제로 요구하는 선행 조건과 산정 입력을 가리킨다.")
s=s.replace("raise ContractError('exception target on wrong node role')", "raise ContractError('nodes['+n['id']+'].exception_targets='+repr(n['exception_targets'])+' on kind='+n['kind']+': only EXCEPTION may list the EFFECT/CALCULATION/CONDITION it modifies; the normal effect must not list its exceptions. Preserve original legal meaning and correct the direction explicitly.')")
p.write_text(s)
for n in ('common.py','live.py','build.py','check.py','test_semantics.py','test_direct.py','test_projection.py','source_audit.py','wire_audit.py','report.py','finish.py','coordinate.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1121'/n).read_text().replace('ADR-1121-ontology-semantic-compilation','ADR-1124-ontology-explicit-exception-contract').replace('adr_1121','adr_1124').replace('ADR-1121-experiment-v1','ADR-1124-experiment-v1').replace("'ADR-1121'","'ADR-1124'")
 (D/n).write_text(s)
p=D/'build.py';s=p.read_text();s=s.replace('from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentCallError','from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,_schema_for_api')
s=s.replace("put(out/'input.json',prompt_input);started=", "previous=read(ART/'previous-proposal.json');assert sha(ROOT/previous['path'])==previous['sha256']\ntry:sem.validate(previous['proposal'],data['originals'],data['judgments'])\nexcept ContractError as error:prompt_input.update(previous_proposal=previous['proposal'],structural_errors=[str(error)],repair_instruction='명시된 역할·방향 계약에 맞춰 수정한다. 원문·의미를 자동 추정하지 않는다.')\nput(out/'input.json',prompt_input);started=")
old="   p=client.generate(sem.PROMPT,prompt_input,sem.SCHEMA,phase='semantic-proposal' if not attempt else 'semantic-repair')"
new="""   phase='semantic-proposal' if not attempt else 'semantic-repair'
   payload={'model':client.model,'messages':[{'role':'system','content':sem.PROMPT},{'role':'user','content':json.dumps(prompt_input,ensure_ascii=False)}],'temperature':0,'stream':False,'response_format':{'type':'json_schema','json_schema':{'name':'ontology_semantics','strict':True,'schema':_schema_for_api(sem.SCHEMA)}}}
   raw=client.chat_completions(payload,phase=phase,timeout_seconds=600)
   try:p=json.loads(raw['body_json']['choices'][0]['message']['content'])
   except (ValueError,KeyError,IndexError) as e:raise ExperimentFormatError('Incomplete JSON',response=raw) from e
   put(out/'raw'/f'call-{client.calls:03d}-{phase}'/'output.json',p)"""
assert old in s;s=s.replace(old,new).replace('except (ContractError,ExperimentFormatError,ExperimentCallError) as e:','except (ContractError,ExperimentFormatError) as e:');p.write_text(s)
# Add checks for actionable role diagnostics; retain all prior tests.
p=D/'test_semantics.py';p.write_text(p.read_text()+'''\n\ndef test_exception_error_identifies_node_and_direction():
    b,f=fixture();b['proposal']['nodes'][0]['exception_targets']=['X']
    with pytest.raises(ContractError,match=r"nodes\\[C\\]\\.exception_targets=.*kind=EFFECT"):
        sem.validate(b['proposal'],b['originals'],b['judgments'])
''')
for p in list(D.glob('*.py'))+list(S.rglob('*.py')):ast.parse(p.read_text())
print(S)

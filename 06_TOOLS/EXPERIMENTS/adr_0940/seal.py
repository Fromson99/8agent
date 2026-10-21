from pathlib import Path
import json,hashlib,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0940/modified'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for command in ('freeze','validate'):
 p=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';names=read(D/'working-before.json')
for name,h in names.items():assert sha(code/name)==h
candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':'modified','arm_id':'modified','experiment_id':'ADR-0940-experiment-v1','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
put(D/'modified-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':names,'candidate':candidate,'release_id':'adr0940-modified','generation':90})
m=read(A/'실험/manifest.json');m['design']['arms'][0]['derived_from']=[]
m['design']['arms'][0]['controls']+=' Selected immutable release binding is an observational control, not a new implementation derived from qualified.'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate])
m['questions']=[]
for i,case in enumerate(read(D/'cases.json'),1):
 name=f'질문-{i:03d}-{case["id"]}.md';p=A/'실험'/name
 p.write_text('# 프롬프트 비용 짝비교\n\n## 1. 실행 메타\n\n사전 동결 run-001, baseline/modified 각1회. 알려진 사례.\n\n## 2. 사용자 질문 원문\n\n'+case['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n승인된 법률 정답 없음. 원문 확보·프롬프트 비용 검사.\n\n## 4. 제품 입력을 구성한 원값\n\n고정 binding과 호출 원문 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/run-001/retrieval-ledger.json\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n각 arm/case raw 및 wire의 원래 요청/응답.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ncalls.json/generations.json 및 canonical 기록.\n\n## 7. 채점 호출과 반복 판정\n\n채점 모델0회. 기계 계측과 원문 기반 수동 확인.\n\n## 8. 사례 최종 판정\n\n실행 후 기록.\n')
 m['questions'].append({'case_id':case['id'],'file':name,'sha256':sha(p)})
put(A/'실험/manifest.json',m)
files={}
for arm in ('baseline','modified'):
 b=read(D/(arm+'-binding.json'))
 for n,h in b['serving_files'].items():
  p=R/b['code_root']/n;assert sha(p)==h;files[str(p.relative_to(R))]=h
base=read(D/'baseline.json')['manifest']
paths=[*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/resource_guard.py',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
paths += [R/base['data_path']/n for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Both code bindings and 4-run schedule frozen. MAIN90 unchanged.')

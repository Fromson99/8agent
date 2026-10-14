"""Preserve the failed package preflight; no model result is invented."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def suite(p):
 cs=list(E.parse(p).iter('testcase'));bad=[c for c in cs if c.find('failure') is not None or c.find('error') is not None]
 return {'tests':len(cs),'passed':len(cs)-len(bad),'failures':[c.get('name') for c in bad],'path':str(p.relative_to(R)),'sha256':sha(p)}
m=read(A/'실험/manifest.json');s={a:suite(A/'artifacts/contracts'/(a+'.xml')) for a in ('pre-review','repaired')}
result={'strict_success':False,'reason':'Candidate service preflight missed a pinned document-alias projection; actual model cases were not started.',
 'new_contract_development':suite(A/'artifacts/dev-contracts-3.xml'),'same_code_regression':s,
 'new_regressions':sorted(set(s['repaired']['failures'])-set(s['pre-review']['failures'])),
 'model_calls':0,'model_cases_executed':0,'main_changed':False,'genos_deployed':False,
 'preflight':{a:read(A/'artifacts/setup-check'/a/'venture-exercise/result.json') for a in ('baseline','repaired')},
 'limitations':['Four aggregate failures occur in both arms: one historical knowledge fixture, three mutable workspace activation receipt failures.',
 '37 development repair/recovery contracts passed before concurrent workspace activation changed.',
 'No measured legal response, latency, retrieval or generalization result; follow-up requires a new ADR.']}
put(A/'artifacts/run-001/result.json',result)
m['results'].update(status='complete',by_arm={a:{'status':'complete','package_preflight_passed':a=='baseline','model_calls':0,'model_cases_executed':0,'model_cases_not_executed':3} for a in ('baseline','repaired')},
 comparisons=[],judge_disagreements=None,usage={'model_calls':0},latency={'not_measured_reason':'Stopped before product requests'},error_taxonomy=['candidate_projection_missing','shared_workspace_receipt_changed','historical_knowledge_fixture'])
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
reason='No product retrieval was executed: candidate package preflight failed before model calls; synthetic contract tests do not measure corpus recall.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason)
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=reason)
for q in m['questions']:
 p=A/'실험'/q['file'];s0=p.read_text()
 for old,new in {'## 2. 제품 요청':'## 2. 사용자 질문 원문','## 3. 기준답변':'## 3. 기준답변 — 채점 전용, 제품 입력 비공개','## 4. 제품 입력의 원값':'## 4. 제품 입력을 구성한 원값','## 5. 제품 모델 호출':'## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출':'## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출':'## 7. 채점 호출과 반복 판정','## 8. 최종 판정':'## 8. 사례 최종 판정'}.items():s0=s0.replace(old,new)
 s0=s0.replace('## 5. 제품 모델 호출','### 회수·탈락 단계 원장 — run·arm별\n'+reason+'\n\n## 5. 제품 모델 호출',1)
 s0+='\n제품 요청 미실행: 양 arm 모델0회. 후보의 기동 실패로 실제 질문3건 모두 실행하지 않았다. artifacts/run-001/result.json 및 setup-check 오류 원문을 보존한다.\n'
 p.write_text(s0);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
sections=[
 ('결정 요약','패키지 기동 기준 실패로 이번 후보의 MAIN 승격을 기각한다. 판단 루프 보완 구현은 보존하고, 빠진 약칭 projection을 포함하는 후속 ADR에서 검증한다. 작업 코드·선택 MAIN45·GENOS는 변경하지 않았다.'),
 ('문제와 변경 전 구조','검토 R1 의존 해시, R2 대상 생략 시 부족 충돌, R3 공유 근거 쟁점 누락, R4 라운드 전체 행동/근거로 서로 다른 부족을 종료하는 문제를 고쳤다.'),
 ('가설과 사전 판정 기준','artifacts/design/criteria.json에 선점 후·후보 수정 전 동결했다. 신규 계약 통과, 새 회귀0, 코드/원문/권한/상태 검증 및 실제 기동이 필수다. 법률 의미 상세 채점은 절대 통과 기준이 아니다.'),
 ('실험 설계','기준 MAIN45와 repaired 공개3사례 비교 계획이다. 합성 회귀는 동일한 수정 전 작업 코드와 후보를 대조한다. 부모 ADR0688/integrated의 완료된 조사 경로를 보존했다. 모델 실행 전 기동에서 중단했으며 사례 교체/재실행하지 않았다.'),
 ('데이터·모델·재현성','모델0회. 고정 데이터셋은 공개 법령 질문3건이며 실제 비공개 질문을 반출하지 않았다. 후보 reviewed/rev-001과 실행기·fixture·원문 세대의 해시는 artifacts/design/freeze.json에 있다. Qwen3.8/Parasail FP8/reasoning none/fallback없음 정책을 유지한다.'),
 ('결과','개발 계약37개 통과. 동결 후 합성 회귀는 수정 전131/135, 후보146/150으로 같은4개 실패이며 새 회귀0이다. 후보 실제 앱 기동은 약칭 projection 미포함으로 실패했다. MAIN45 앱 기동은 성공했고 양쪽 모델 호출0이다.'),
 ('사례별 오류 분석','동일한4실패 중1개는 이전 knowledge_id를 기대하는 역사적 fixture다. 3개는 다른 작업이 WORKSPACE 활성화를 r5로 바꾸는 동안 해당 receipt를 찾지 못한 오류다. frozen 후보 pin 우회는 하지 않았다. 최초 fixture 생성기가 병행 factorized-audit 코드를 참조한14개 설정 실패도 보존한다.'),
 ('비용·지연·회수 규모','모델 호출·비용0, 실제 질의 지연·검색 회수는 미측정. 실행을 하지 않은3질문을 성공이나 오답으로 집계하지 않는다. 단계별 회수 원장은 제품 검색 미실행으로 해당 없음이다.'),
 ('해석','구현의 합성 기능 증거는 얻었으나 동일 패키지의 실제 서비스 연결 요건을 충족하지 못했다. 누락된 파일은 법령명 약칭 metadata이며 법률 근거 본문은 아니다. 그 파일을 빼거나 검증을 생략하지 않고 후속에 포함한다.'),
 ('한계와 일반화 가능 범위','In-sample 알려진 사례의 실제 모델 결과도 없으므로 품질 개선이나 현장 성능은 주장하지 않는다. 후속은 완전한 의존 묶음과 고정 workspace receipt에서 동일 계약 및 분리된 공개 holdout을 검증해야 한다.'),
 ('운영 결정·롤백 조건','연구 후보만 변경했다. 제품 통합과 포인터 변경이 없으므로 운영 rollback은 불필요하다. 이전 후보·실패 로그·완료된 부모·원본 generation은 그대로 보존한다.'),
 ('재현 명령','.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0689/run_contracts.py <고정 code root> <계약 파일>. 원 실행기·해시는 freeze.json, 원 출력은 artifacts/contracts 및 setup-check에 있다. 모델 재실행/후속 후보는 새 ADR을 선점한다.')]
fm=f"---\nadr_id: ADR-0689\ntitle: 판단 루프 검토 보완과 패키지 기동 실패 기록\nstatus: Rejected\ndecision_date: 2026-10-08\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 실행하지 않은 공개 질문과 패키지 기동 기록\n\n후보 package preflight 실패로 실제 모델 질문은 모두 미실행, 모델0회다. [결과](../artifacts/run-001/result.json).\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+') — 미실행' for q in m['questions'])+'\n')
raws=[]
for p in list((A/'artifacts/contracts').glob('*.log'))+list(Path('/tmp').glob('adr0689-*.log')):
 target=A/'artifacts/logs'/(p.name+'.gz');target.parent.mkdir(exist_ok=True)
 data=p.read_bytes()
 with gzip.open(target,'wb') as stream:stream.write(data)
 raws.append({'archive':str(target.relative_to(R)),'sha256':sha(target),'raw_sha256':hashlib.sha256(data).hexdigest(),'restore':'gzip -dc archive > original.log'})
put(A/'artifacts/logs/receipts.json',raws)
files=[]
for p in (A/'artifacts').rglob('*'):
 if not p.is_file() or p.name=='manifest.json' or 'pre-review-code' in p.parts or 'fixture-code' in p.parts or 'prepared-generations' in p.parts:continue
 files.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved contract/preflight result; no model requests','contains_raw_prompts_and_outputs':False})
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0689','created_at':m['reservation']['created_at'],'files':files})
print('Package rejected; functional implementation and all failures retained')

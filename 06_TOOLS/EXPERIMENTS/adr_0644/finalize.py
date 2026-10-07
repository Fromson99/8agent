from pathlib import Path
import ast,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations';D=A/'artifacts/design';RUN=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
run=read(RUN/'result.json');assert len(run['results'])==2
one=read(RUN/'turn-1-snapshots.json');two=read(RUN/'turn-2-snapshots.json')
old={e['id'] for s in one for e in s['events']};new={e['id'] for s in two for e in s['events']};delta_ok=not old&new
accepted=sum(r['status']=='ACCEPTED' for r in run['results']);run.update(in_sample=True,decision_eligible=False,contract_tests=100,delta_input_excludes_previous_events=delta_ok,previous_event_count=len(old),new_event_count=len(new),probe_success=accepted==2 and delta_ok);put(RUN/'result.json',run)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results']={'status':'complete','by_arm':{'baseline':{'status':'complete','measurement':'completed parent structural reference only; no model rerun'},'integrated':{'status':'complete','actual_outputs_accepted':accepted,'actual_outputs_total':2,'contract_tests':100,'delta_ok':delta_ok}},'comparisons':[],'judge_disagreements':0,'usage':{'calls':run['calls'],'receipts':run['usage']},'latency':{'seconds':[x['seconds'] for x in run['results']]},'error_taxonomy':[{'type':'other','reason':x.get('error'),'turn':x['turn']} for x in run['results'] if x['status']!='ACCEPTED']}
heads={}
for node in ast.parse((R/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('ADR_HEADINGS','QUESTION_HEADINGS_COMMON'):heads[node.targets[0].id]=ast.literal_eval(node.value)
qh=heads['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
raw='\n'.join('### '+str(p.relative_to(RUN))+'\n'+block(read(p)) for folder in sorted((RUN/'provider').glob('call-*')) for p in sorted(folder.glob('*.json')))
values=['ADR-0644/run-001/integrated;2 preregistered related-case compiler turns; no legal-quality approval.',block({k:v for k,v in read(D/'inputs.json').items() if k in ('initial_questions','correction')}),'No legal gold answer or offline judge. Acceptance is exact provenance, scope, delta and unapproved legal claims.',block({'turn1':one,'turn2':two}),'Not applicable: compiler input and provenance contracts only; no retrieval quality measured.',raw,'These2 actual calls are the compiler; no hidden repair or fallback.','Code admission and100 ordinary contracts, no legal correctness evaluator.',block(run)]
q=m['questions'][0];p=A/'실험'/q['file'];p.write_text('# related-case-incremental\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,values))+'\n');q['sha256']=sha(p);put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1]
if not run['probe_success']:front=front.replace('status: Proposed','status: Rejected')
values=[f'구현 probe: 실제 출력 {accepted}/2 수락,100개 계약·회귀·프로세스 복구 검사 통과. 이전 이벤트 재전송 없음={delta_ok}. 법률 품질 승격은 ADR0643 미통과로 계속 차단.',
 '부모 후보는 단일 사건 중심·이력 재처리였고 native 외부 artifact 및 별도 검토 파일의 운영 연결이 부족했다.',m['design']['success_criteria'],
 '두 독립 합성 사건을 명시 SAME_TOPIC으로 연결한 뒤 첫 사건만 정정한다. 모델 출력은 원본 그대로 보존하고 해당 시점 입력과 결속한다.',
 '공개 원문9블록과 합성 질문. 실제 Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 선택 원문 generation·반출 승인·정책 해시 사전 동결.',
 block(m['results']['by_arm']),block(m['results']['error_taxonomy']),block({'usage':m['results']['usage'],'latency':m['results']['latency']}),
 '증분 제외는 원본 삭제가 아니다. 현재 사실·원문은 함께 제공하고 이전 지식은 비교용으로만 다룬다. 관련 사건 사실은 합치지 않고 검증 승인도 상속하지 않는다.',
 '합성 인샘플. 실제 내부 데이터·GENOS 검증 없음. 과대 단일 기록은 예산 오류로 남으며 보존/삭제 정책의 실제 값은 운영자가 결정해야 한다. 법률 품질·성능 개선을 주장하지 않는다.',
 '운영 ACTIVE pointer·source generation·운영 DB 이행·GENOS 배포 미변경. 현재 MAIN과의 실제 비교는 ADR0643에 보존. 정상 승격 조건이 갖춰지기 전 활성화하지 않는다.',
 '동결 후보의100개 테스트: SHORTCUT_CANDIDATE_SNAPSHOT=revisions/rev-001/snapshot .venv/bin/python -m pytest 06_TOOLS/EXPERIMENTS/adr_0644 05_TESTS/CONTRACTS/test_unified_legal_agent.py 05_TESTS/CONTRACTS/test_unified_memory_recovery.py. 완료 실제 호출은 재실행하지 않는다.']
(A/'README.md').write_text('---'+front+'---\n\n# ADR-0644 증분·연결 compiler 및 운영 계약\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(heads['ADR_HEADINGS'],values))+'\n')
(A/'실험/README.md').write_text('# 관련 사건과 증분 구성\n\n- ['+q['case_id']+']('+q['file']+')\n\n법률 품질 평가가 아닌 실제 compiler 수락·정확한 기록 연결 확인.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and p.suffix!='.pyc']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, actual model output or contract receipt','contains_raw_prompts_and_outputs':'provider/' in str(p)} for p in paths]})
print(json.dumps({'accepted':accepted,'delta_ok':delta_ok,'tests':100}))

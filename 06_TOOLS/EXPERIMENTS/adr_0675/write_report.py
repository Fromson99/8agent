"""Finalize the decision from immutable measured results, before promotion."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0675-investigation-control-binding-closure'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');result=read(A/'artifacts/run-001/result.json');ok=result['strict_success']
assert len(m['questions'])==32 and m['results']['status']=='complete'
m['decision_eligible']=ok;put(A/'실험/manifest.json',m)
path=A/'README.md';front=path.read_text().split('---',2)[1]
front=front.replace('status: Proposed','status: Accepted' if ok else 'status: Rejected').replace('decision_eligible: false','decision_eligible: true' if ok else 'decision_eligible: false').replace('main_wiring: unchanged','main_wiring: promotion-candidate' if ok else 'main_wiring: unchanged')
executed=15
table='| arm | 실제 실행 | 실행 성공 | 독립 채점 정답 | 입력 토큰 | 출력 토큰 | 모델 비용 USD | 요청 p50 / p95 초 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
for arm,row in result['by_arm'].items():
 u=row['usage'];l=row['latency'];table+=f"| {arm} | {executed}/32 | {row['request_success_count']}/{executed} | {row['correct_count']}/{executed} | {u['input_tokens']} | {u['output_tokens']} | {u['cost_usd']:.6f} | {l['request_p50']:.3f} / {l['request_p95']:.3f} |\n"
sections={
 '1. 결정 요약':('Accepted. 동결 통합 후보의 계약·패키지·공개 독립 비교·기존 회귀를 통과했다. 별도 hash 고정 승격 입력으로 로컬 MAIN을 활성화한다. 이 결정 시점의 MAIN은 generation42다.' if ok else 'Rejected. 사전 기준을 충족하지 못했다. 실패·원시 결과를 보존하며 MAIN은 변경하지 않는다.')+'\n\n'+json.dumps(result['checks'],ensure_ascii=False,indent=2),
 '2. 문제와 변경 전 구조':'작업 코드·완료 실험·활성 릴리스의 기능 차이를 파일별로 대조했다. 후보 전체를 덮어쓰지 않고 최신 AD·shortcut/wiki·SQL/NFS·서비스 변경 위에 법령별 탐색과 행동 체인, 정확한 전달·채택 범위, 저장 원문 재열람, 쟁점별 ASSESS 재진입을 통합했다. 앞선 ADR0674의 공개 grant 세대 불일치와 평가 hardlink 준비 순서 오류는 실패 기록으로 보존했다. 이번 후보는 활성 승인 grant와 원문 세대에 결속하며 legacy 선택 wire를 보존한다.',
 '3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n성공 기준: '+m['design']['success_criteria']+'\n\n반증 기준: '+m['design']['failure_criteria']+'\n\n판정 기준·원문·질문·모델·후보·서빙 파일은 실제 호출 전에 freeze.json 및 release-freeze.json으로 동결했다.',
 '4. 실험 설계':'baseline은 generation42 활성 릴리스 그대로다. integrated는 해당 서빙 파일에서 검토된 최신 작업 코드와 완료 기능을 통합한 동결 revision이다. 자연 질문 32건·서로 다른 조문 그룹·8유형에서 각4건을 고정했다. 각 arm/case의 독립 런타임과 동일 원문 세대, 공개145 문서 권한·모델·provider·예산을 동결했다. 실제로 IC01~IC15의15쌍을 각각1회 실행·채점했다. 필수 실행·회귀 조건이 이미 실패해 나머지17쌍은 미실행으로 보존했다. 사용자 기존2질문과 CM6의8건 회귀는 계획에 보존했으나 이 탈락 후보에서 실행하지 않았다. 제품 입력에 golden source·정답·평가 설명을 주입하지 않았다.',
 '5. 데이터·모델·재현성':'Qwen3.8 / qwen/qwen3.8-27b / OpenRouter Parasail FP8 단독 / reasoning none / fallback 없음. 데이터는 term-source-3b667f54bb11d9477888, store SHA cd64bf1301bc68d58741c332748084691b9f57136f827bb782f71b68068c66a2다. 동결 원문 판본을 평가하며 최신 법률 해석 인증은 별도다. 제품·중간 호출과 독립 judge 각1회의 실제 request/response/usage는 질문 문서와 artifacts에 보존한다. 첫 중단 실행은 모델 호출0회이며 재개 전 기록을 별도로 보존했다. 동시 제품 프로세스를2개로 제한한 환경의 실측이며 환경 차이를 숨기지 않는다.',
 '6. 결과':'계획32쌍 중 실제15쌍 실행,17쌍 미실행. 미실행은 오답이나 성공으로 세지 않았다. 아래 실측 분모는15다.\n\n'+table+'\n\n'+json.dumps({k:len(v) for k,v in result['paired_outcomes'].items()},ensure_ascii=False,indent=2),
 '7. 사례별 오류 분석':'실행한 실패는 실측 분모15에 유지하고 미실행17건은 별도 표시했다. IC11의 재열람 DEFER 충돌과 행동 변경 후 preview 근거 잔존, IC12·IC13의 같은 충돌, IC14의 Parasail 응답 중 upstream 연결 중단, IC15의 요청 범위를 임의로 제1항에 제한한 누락을 보존했다. 기준 버전의 계약 오류·시간 초과·실패 응답과 후보의 쟁점·gaps·정확 인용·판단 refs를 질문별 diagnostic 및 native 이벤트에 연결한다. 실패 사례를 성공 사례로 대체하거나 답변을 수정해 채점하지 않았다.\n\n'+json.dumps(result['paired_outcomes'],ensure_ascii=False,indent=2),
 '8. 비용·지연·회수 규모':'입력·출력 토큰, 실제 호출 비용·시간은 위 결과표와 run-001/result.json에 기록했다. 배포 패키지는 정확한265개 서빙 파일과 설정된 모든 엔진 의존성을 확인했다. 기준 source→recall→acquired→presented 단계 좌표는 retrieval-ledger.json으로 전수 기록하고 출력 이후 gold recall을 결합했다. 확보·전달·채택의 완전성은 각 원문 codepoint 범위로 별도 기록하며 의미 품질과 동일시하지 않는다. 준비 과정의 보고서 직렬화 오류는 원래 예외와 이미 저장된 검증 자료를 보존한 상태로 영수증만 수정했고, 제품 재실행이나 모델 호출은 추가하지 않았다.',
 '9. 해석':'쟁점별 충분성은 모델의 현재 판단이다. 전달·채택 범위와 인용 일치는 결정적으로 검증했다. 독립 채점과 paired 회귀 결과를 함께 보고하며 후보의 자체 COVERED 선언을 품질 점수로 사용하지 않았다. 부수 연결의 미해결은 일반 경고로 반복하지 않고 해당 쟁점의 한계로 보존한다.',
 '10. 한계와 일반화 가능 범위':'32개 공개 사례를 동결하고15개만 양 arm에서 실제 실행했다. 성공 응답만 단일 모델 judge로 각1회 채점했으며 통계적 인증이나 법률 전문가 인증이 아니다. 실제 내부 자료와 GENOS 내부 모델·배포는 실행하지 않았다. quality_certified=false를 유지한다. 과거 완료 기록은 변경하지 않으며 전체 계보의 기존 오류는 별도 보고한다. 기존 사용자의 저장 DB를 실험 DB로 대체하지 않았다.',
 '11. 운영 결정·롤백 조건':'승격 조건 통과 시 기존 stable runner의 rag_main_promotion.py prepare/apply --confirm-main으로 exact serving inventory와 source qualification을 고정한다. 활성화 후 신규 프로세스의 service.service에서 실제 질문을 실행하고 release/code/profile/data/search/schema 지문을 대조한다. 실패 시 같은 관리 도구의 rollback --confirm-main 및 작업 파일 백업으로 복구한다. 실제 MAIN 완료 영수증은 이 immutable 실험과 별도 MAIN_RESULT.md에 기록한다. Git main 병합과 GENOS 현장 배포는 별도 상태다.',
 '12. 재현 명령':'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0675/run_case.py --arm baseline 또는 integrated --case IC01…IC32. 동결 hash 검사 및 기존 결과 덮어쓰기 거부를 유지한다. 후속 재실행·후보 수정·재채점은 새 ADR에서 수행한다. 완료 검사: .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0675-investigation-control-binding-closure --final 및 graph.'}
path.write_text('---'+front+'---\n\n# ADR-0675 조사 제어 통합과 독립 MAIN 검증\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in sections.items())+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and p.suffix in ('.json','.txt','.log','.py') and not any(part in ('prepared-generations','runtime','setup-check','main-stage','preflight-symlink-run-001','preflight-symlink-setup-check','preflight-interrupted-run-001','preflight-interrupted-regression','preflight-interrupted-package-001') for part in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact frozen design, product/provider/evaluator/trace/validation artifact'} for p in sorted(files)]})
print('Decision', 'Accepted' if ok else 'Rejected')

"""Finalize only measured, frozen results; semantic errors remain diagnostic."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');v=read(A/'artifacts/run-001/result.json');ok=v['strict_success'];assert len(m['questions'])==32 and m['results']['status']=='complete'
m['decision_eligible']=False;put(A/'실험/manifest.json',m)
f=(A/'README.md').read_text().split('---',2)[1];f=f.replace('status: Proposed','status: Accepted' if ok else 'status: Rejected')
row=v['by_arm']['integrated'];u=row['usage'];l=row['latency'];counts={k:len(x) for k,x in v['semantic_outcomes'].items()}
sections={
'1. 결정 요약':('Accepted development probe. Frozen contract and completion criteria passed; in-sample result is not eligible for MAIN promotion. Independent qualification remains required.' if ok else 'Rejected development probe. Frozen requirements were not met; results and failure traces are retained and MAIN remains unchanged.')+'\n\n'+json.dumps(v['checks'],ensure_ascii=False,indent=2),
'2. 문제와 변경 전 구조':'분석 대상은 활성 generation43 MAIN의265개 서빙 파일과 동일했다. 도구 schema/실행 검증 불일치, 보류 원문 전달 차단, 반복 탐색, 마무리 예약 미사용, gap 모순, 자유 답변 후첨가, 전송 오류와 재개 예산 문제를 기존 7단계에 연결해 수정했다. RETURN_TO는 기존 기능으로 유지하며 과거 선택지·원문 복귀와 이후 판단 보존을 검사했다. 직접 재열람은 명시 요청일 때만 전달하고 자동 채택하지 않는다.',
'3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n성공 기준: '+m['design']['success_criteria']+'\n\n반증 기준: '+m['design']['failure_criteria']+' 사전 design.json/freeze.json을 변경하지 않았다. 의미 오류는 사용자 지시에 따라 별도 진단하되 원문·권한·상태·게시 무결성을 유지한다.',
'4. 실험 설계':'이미 결과를 관찰했던 ADR0677의 32문항과 8회귀를 각 1회 실행하도록 동결했다. 필수 T10 계약 실패를 확인해 신규 배정을 중단하고 진행 중인 요청만 완료했다. 실제 17문항 실행, 나머지 15문항 및 8회귀는 NOT_RUN으로 보존했다. 통합 단일 후보이며 in_sample=true, decision_eligible=false다. 과거 baseline은 계보 참고용이고 같은 조건의 paired A/B를 실행하지 않아 정확도·속도 개선의 인과효과를 주장하지 않는다.',
'5. 데이터·모델·재현성':'동일 공개145문서 범위, 동일 generation, Qwen3.8 qwen/qwen3.8-27b / Parasail FP8 단독 / reasoning none / fallback 없음. 각 요청40call와1800초; retry와repair도 같은물리예산. 공통 ExperimentClient 요청과원응답을 보존하며 gold는 제품입력에 넣지 않았다. GENOS 내부모델 실험이 아니다.',
'6. 결과':f"실행한 개발질문 {row['executed_count']}/32, 실행된 질문 중 응답 {row['request_success_count']}/{row['executed_count']}, 단일 자동평가 정답 {row['correct_count']}/{row['executed_count']}. 회귀 8개는 모두 미실행.\n\n"+json.dumps(counts,ensure_ascii=False,indent=2)+'\n\n'+json.dumps(v['critical_failures'],ensure_ascii=False,indent=2),
'7. 사례별 오류 분석':'GENERALIZATION_ERRORS.json과 질문별 기록에 정답·판단 오류·미답변·미실행을 분리했다. NG13은 누락 시행령을 MISSING_FACT로 제출하면서 COVERED/ANSWER로 표시했고, 한 차례 보정 후에도 모순이 남아 차단됐다. NG11 실제 502는 전송 실패가 아니라 출력 길이 초과 응답을 잘못 분류한 것으로 별도 기록한다. 원결과와 채점은 변경하지 않았다. 모형의 coverage 표시는 의미정답을 인증하지 않는다. 채점오류 가능성도 원문과 독립검토하며 기존점수는 소급변경하지 않는다. 구조계약과 의미정확성의 한계를 구분한다.',
'8. 비용·지연·회수 규모':f"실행된 개발질문 입력토큰 {u['input_tokens']}, 출력토큰 {u['output_tokens']}, 비용 USD {u['cost_usd']:.6f}, 요청 p50 {l['request_p50']:.3f}초 / p95 {l['request_p95']:.3f}초. 회귀·평가자 비용은 각 원시기록에 별도 보존. 회수 단계 전수 원장은 retrieval-ledger.json.gz이며 원시SQLite와 보조파일은 해시·복원 정보와 함께 보존한다.",
'9. 해석':'초기 새 계약 테스트 20개와 실제 268서빙파일·프로필·기존 접근제한을 검사했다. 이후 실제 NG11에서 드러난 T10 오류 분류 경계를 합성 테스트로 재현했고 실패했다. HTTP200/finish_reason=length 출력 중단을 전송 실패로 잘못 변환하므로 사전 필수 기준을 충족하지 못한다. 광범위 구 테스트는 기존 MAIN39실패와 후보39실패가 정확히 같으며 모두통과했다고 보지 않는다. 신규 실제 API 테스트로 정정·표·이력·경험·게시변조·권한철회·동일요청 예산·RETURN_TO를 확인했다. 전송과실제모델의 의미판단은 추가관찰대상이다.',
'10. 한계와 일반화 가능 범위':'계획한 40개는 모두 관찰된 개발·회귀 질문이며 실제 실행은 17개다. 독립성과 성능을 주장할 수 없고 새 ADR의 미관찰 조문 그룹 평가가 필요하다. 실제 GENOS 현장·내부자료·내부모델은 미검증이다. 압축 보조도구가 남은 SQLite WAL 때문에중단된 경우 원본과sidecar를보존하고동결된 제품실행기의미실행질문만이어서실행했다. scheduler-recovery 영수증을참조한다.',
'11. 운영 결정·롤백 조건':'이 ADR만으로 MAIN을 승격하지 않는다. 후속 독립 ADR의 동일코드 검증과 선택적 작업코드통합, hash고정 prepare/apply --confirm-main, 활성포인터와 실제새 service.service 요청 확인이 남는다. 미충족이면 MAIN그대로유지한다. 로컬MAIN, Git병합, GENOS반입·현장배포는각각별도상태다.',
'12. 재현 명령':'WSL /home/jin/8-AGENT의 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0678/run_case.py --arm integrated --case CASE_ID. 완료된 결과덮어쓰기·재실행은허용하지않으며 새비교·수정은새ADR로한다. 최종검사 adr_structure.py validate --final 및 graph를사용한다.'}

(A/'README.md').write_text('---'+f+'---\n\n# ADR-0678 조사·판단·답변 완료 계약 개발 검증\n\n'+'\n\n'.join('## '+k+'\n\n'+x for k,x in sections.items())+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and p.suffix in ('.json','.txt','.log','.py','.gz','.md') and not any(x in ('prepared-generations','runtime','setup-check','main-stage') for x in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design or exact actual product/provider/evaluator/trace artifact'} for p in sorted(files)]})
print('Decision','Accepted' if ok else 'Rejected')

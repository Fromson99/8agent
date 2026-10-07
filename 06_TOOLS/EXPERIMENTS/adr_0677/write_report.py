"""Finalize only measured, frozen results; semantic errors remain diagnostic."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');v=read(A/'artifacts/run-001/result.json');ok=v['strict_success'];assert len(m['questions'])==32 and m['results']['status']=='complete'
m['decision_eligible']=ok;put(A/'실험/manifest.json',m)
f=(A/'README.md').read_text().split('---',2)[1];f=f.replace('status: Proposed','status: Accepted' if ok else 'status: Rejected').replace('decision_eligible: false','decision_eligible: true' if ok else 'decision_eligible: false').replace('main_wiring: unchanged','main_wiring: promotion-candidate' if ok else 'main_wiring: unchanged')
row=v['by_arm']['integrated'];u=row['usage'];l=row['latency'];counts={k:len(x) for k,x in v['semantic_outcomes'].items()}
sections={
'1. 결정 요약':('Accepted. 사전 동결한 실행·원문·권한·상태·배선 기준을 통과했다. 세부 의미 오류는 별도 개선 기록으로 남긴다. 로컬 MAIN 승격과 실제 service.service 실행 영수증은 MAIN_RESULT.md에서 확인한다.' if ok else 'Rejected. 실행·원문·권한·상태·배선 기준에 미충족이 있다. 원시 결과를 보존하고 MAIN은 변경하지 않는다.')+'\n\n'+json.dumps(v['checks'],ensure_ascii=False,indent=2),
'2. 문제와 변경 전 구조':'기존 작업 코드·완료 후보·활성 generation42 릴리스의 차이를 파일별로 검토해 통합했다. 법령별 탐색, 요청 단위 우선 정렬, 정확한 확보·전달·채택 범위, 저장 원문 재열람, 쟁점별 충분성·gaps, 행동·이유 체인, RETURN_TO와 재개, 답변 소비자 및 서비스 지문을 연결했다. 최신 AD·shortcut/wiki·SQL/NFS 수정은 보존한다. ADR0676에서 실제 원문 획득과 저장 원문 재열람의 DEFER 판정을 구분하고, 제어 모드 보정은 행동·대상·근거 전체 계약으로 처리했다. 이 후보의 제품 파일은 그 완료 후보를 그대로 계승한다.',
'3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n성공 기준: '+m['design']['success_criteria']+'\n\n반증 기준: '+m['design']['failure_criteria']+'\n\n2026-10-07 사용자 지시에 따라 모든 세부 의미 정답을 승격 전제에서 제외했다. 이를 과거 실패 기록에 소급 적용하지 않고 새 ADR의 acceptance-policy.json과 freeze.json으로 모델 호출 전에 고정했다. 새로운 품질 우회나 과거 waiver를 재사용하지 않았다.',
'4. 실험 설계':'통합 후보 단일 arm, 독립 사례32개·서로 다른 조문 그룹·8유형 각4개, 알려진 회귀8개를 각각1회 실행했다. NG01~15는 새 질문, IC16~32는 이전에 동결했으나 실제 실행하지 않았던 질문이다. 관찰된 IC01~15 원문 그룹은 제외했다. 활성 generation42는 정확한 기준 연결로 기록하며 baseline 모델 호출은 반복하지 않았다. A/B 품질·비용·지연 개선을 주장하지 않는다. 원문 gold와 채점 설명은 제품 프로세스에서 읽지 않는다.',
'5. 데이터·모델·재현성':'공개 승인145문서 / term-source-3b667f54bb11d9477888 / Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 단독 / reasoning none / 자동 fallback 없음. 실제 요청은 공통 ExperimentClient로 기록했다. 제품 프로세스 동시2개, 각40call/6400outputtoken 예산이다. 분리된 judge는 성공 답변만 원문 기준 각1회 채점한다. 원문 판본은 고정이며 현행 법률 전문가 인증이나 GENOS 내부 데이터 인증은 아니다.',
'6. 결과':f"실제 독립 실행 {row['executed_count']}/32, 성공 응답 {row['request_success_count']}/32. 원문 기반 단일 judge 세부 정답 {row['correct_count']}/32. 의미 점수는 진단이다. 회귀 응답 {sum(x['http_status']==200 for x in v['regressions'])}/8.\n\n"+json.dumps(counts,ensure_ascii=False,indent=2)+'\n\n'+json.dumps(v['critical_failures'],ensure_ascii=False,indent=2),
'7. 사례별 오류 분석':'GENERALIZATION_ERRORS.json에 질문·유형·원문 source_id·판단 이유·gaps·불변 실행 경로를 남겼다. 주체 선택, 조건·예외·하위 단위 누락, 과도한 범위 제한, 미답변을 실제 결과 그대로 구분한다. 의미 오류를 심각한 시스템 오류로 자동 처리하지 않으며, 근거 없는 인용·권한 누출·지문 불일치·상태 손상은 승격을 막는다. 답변 후처리나 재채점으로 기존 점수를 바꾸지 않았다.',
'8. 비용·지연·회수 규모':f"독립 제품 입력토큰 {u['input_tokens']}, 출력토큰 {u['output_tokens']}, 비용 USD {u['cost_usd']:.6f}, 요청 p50 {l['request_p50']:.3f}초 / p95 {l['request_p95']:.3f}초. 회귀와 evaluator 실제 사용량은 각각 원시 기록에 포함한다. 원문 catalogue→recall→acquired→presented의 canonical 전수 원장은 retrieval-ledger.json.gz에 무손실 압축했다. raw provider JSON은 원본 경로·해시를 참조해 문서에 중복 내장하지 않는다. 각 종료 실행의 큰 SQLite 기록은 원본·압축 해시와 복원 정보를 검증한 후 압축하며 완료 이력을 변경하지 않는다.",
'9. 해석':'후보의 COVERED 판정은 현재 모델 판단이며 의미 정답 보증이 아니다. 인용 문자열은 실제 최종 채택 원문에서 검증한다. 일반화 오류는 후속 신규 ADR에서 원인을 분류하고 공통 계약·프롬프트를 수정할 입력이다. 현재 단일 arm 측정으로 활성 baseline보다 더 정확하거나 빠르다고 주장하지 않는다.',
'10. 한계와 일반화 가능 범위':'공개 사례32개와 알려진 회귀8개, 단일 외부 모델·단일 judge·각1회 측정이다. 드문 판단 오류·provider 제한은 기록하고 전문가 품질 인증은 quality_certified=false로 유지한다. 실제 내부 자료·GENOS 현장 모델·배포는 미검증이다. 과거 완료 ADR0674~676의 기각과 중단 결과는 보존한다.',
'11. 운영 결정·롤백 조건':'Accepted 후보만 stable rag_main_promotion.py prepare/apply --confirm-main으로 승격한다. 등록 후보의 검토 파일만 작업 코드에 백업 후 적용하며 다른 변경을 덮어쓰지 않는다. 제품265파일의 작업 코드·검증 단계·선택 릴리스 해시를 맞추고, 새 프로세스의 실제 service.service HEALTH/RAG_SEARCH/RAG_ASK 지문을 확인한다. 코드·프로필·원문 세대·검색 정책·스키마·실행 binding 불일치나 실제 진입점 실패는 관리 rollback과 작업 백업으로 복구한다. Git main 병합과 GENOS 반입·배포는 별도 상태다.',
'12. 재현 명령':'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0677/run_case.py --arm integrated --case NG01…NG15 또는 IC16…IC32. 기존 결과 덮어쓰기와 hash 변경을 거부한다. 새 재실행·후보 변경·재채점은 새 ADR을 선점한다. 최종 검사: .venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization --final 및 graph.'}
(A/'README.md').write_text('---'+f+'---\n\n# ADR-0677 조사 제어 실행 무결성과 일반화\n\n'+'\n\n'.join('## '+k+'\n\n'+x for k,x in sections.items())+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and p.suffix in ('.json','.txt','.log','.py','.gz','.md') and not any(x in ('prepared-generations','runtime','setup-check','main-stage') for x in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design or exact actual product/provider/evaluator/trace artifact'} for p in sorted(files)]})
print('Decision','Accepted' if ok else 'Rejected')

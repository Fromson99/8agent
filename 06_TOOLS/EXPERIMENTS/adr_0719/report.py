"""Finalize measured results without changing frozen criteria or product outputs."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];number=int(Path(__file__).parent.name[-4:]);A=next((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04}-*'));O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success'];failed=[k for k,v in r['checks'].items() if not v]
table='| 신규 공개 3문항 | 원문 근거 응답 | 실제 호출 | 입력 토큰 | 요청 시간 합계 |\n|---|---:|---:|---:|---:|\n'
for a,v in r['primary_comparison'].items():table+=f"| {a} | {v['supported']}/3 | {v['calls']} | {v['input_tokens']:,} | {v['request_seconds']:.1f}초 |\n"
repeat=[x for x in r['by_arm']['repaired']['cases'] if x['case_id'].startswith('S')]
rt='| 사전 고정 반복 | 응답 | 호출 | 입력 토큰 | 시간 |\n|---|---:|---:|---:|---:|\n'
for x in repeat:rt+=f"| {x['case_id']} | {x['supported_response']} | {x['physical_model_attempts']} | {x['usage']['input_tokens']:,} | {x['request_seconds']:.1f}초 |\n"
decision='사전 기준 통과. 동일 코드의 로컬 MAIN 승격 후보로 채택한다. 실제 적용 상태는 MAIN_RESULT.md와 별도 receipt를 따른다.' if ok else 'MAIN50 유지. 실패 기준: '+', '.join(failed)+'. 후속 변경은 별도 ADR에서 검증한다.'
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text()+'\n\n| arm | HTTP | 호출 | 입력 토큰 | 시간 | 원문 근거 응답 |\n|---|---:|---:|---:|---:|---|\n'
 for a,v in r['by_arm'].items():
  c=next((x for x in v['cases'] if x['case_id']==q['case_id']),None)
  if c:s+=f"| {a} | {c['http_status']} | {c['physical_model_attempts']} | {c['usage']['input_tokens']:,} | {c['request_seconds']:.3f}초 | {c['supported_response']} |\n"
 s+='\n'+('사전 고정 동일 질문 반복이며 신규 holdout 수에는 포함하지 않는다.' if q['case_id'].startswith('S') else '출력 전에 선택한 신규 주 원문 사례다.')+' 원시 요청·응답·journal은 raw.tar.gz와 복원 receipt, 원문 확보·전달·채택은 retrieval-ledger.json.gz와 diagnostic.json을 따른다.\n';p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
parts=[('결정 요약',decision),('문제와 변경 전 구조','MAIN50/CM51에서 요청 범위·부족 근거 대상·재조사·조건 구조·최종 조립에 걸친 문제가 관찰됐다. ADR0718은 코드로 지킬 수 있는 경계를 v5로 통합했다. ADR0720은 추가로 동일 결정의 수정 호출 중단 뒤 입력 복원과 새 요청 경계를 보강했다.'),('가설과 사전 판정 기준','artifacts/design/criteria.json을 호출 전에 고정했다. 인용·권한·상태·답변 내용 보존·실제 코드/데이터 binding·물리 호출 장부를 필수로 하고 세부 법률 의미 채점과 지연 관측은 별도다. 사후 기준 완화는 없다.'),('실험 설계','신규 공개 주 원문3건을 MAIN50/후보로 paired 실행하고 후보에만 같은 질문3건을 새 세션으로 반복했다. 순서·총 예산·모델을 사전 고정하고 적응적 재실행은 하지 않았다. 새 코드 변경은 없다.'),('데이터·모델·재현성','같은 불변 generation, 승인 공개65문서, Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 과거에 노출된 원문 ID를 제외하고 primary root를 고정했다. 이 검사는 보조 참조의 미노출이나 사전학습 미노출을 증명하지 않는다. CM 비공개 질문은 보내지 않았다.'),('결과',table+'\n'+rt+'\n[의미 검토](SEMANTIC_REVIEW.md), [측정 결과](artifacts/run-001/result.json)를 함께 본다. 원문이 뒷받침되는 응답 수는 세부 의미 전부 정답 수가 아니다.'),('사례별 오류 분석',json.dumps(r.get('known_critical_state_defect',{}),ensure_ascii=False) if not ok else '신규23개 합성·실제 native 경계 검사를 모두 통과했다. 기존271개 대비 신규 실패0이며 기존15실패는 그대로 기록했다. 실제 모델 출력에서 발견한 판단·표현 오류는 의미 검토에 남겼다.'),('비용·지연·회수 규모','실제 물리 호출·입출력 토큰·비용·요청 시간과 최종 판단 이전 시간을 각각 집계한다. 확보 원문과 실제 모델 전달 및 채택은 구분한다. RSS는 요청 중 프로세스 샘플 최고값으로 공유 캐시를 포함하며 요청 단독 메모리 할당량이 아니다.'),('해석','구조 검증과 정확 인용으로 모델의 법률 의미 판단까지 보증할 수 없다. 조립 단계는 승인된 결론·상세 설명·조건·의무·예외를 보존한다. 대상 일치와 반복 판단 경계는 코드가 확인하고 의미적 충분성은 모델 판단 및 별도 검토에 남는다.'),('한계와 일반화 가능 범위','신규3문항과 사전 반복3건의 제한된 공개 검증이다. 계획의 넓은12문항 반복 매트릭스·CM51 전체·GENOS·통계적 성능 인증을 완료했다고 보지 않는다. 기존15계약 실패와 전역 graph의 과거8오류를 그대로 보존한다. 이번 ADR 및 직접 부모의 검증 결과는 별도 확인한다.'),('운영 결정·롤백 조건',decision+' 통과시 검증한 변경 파일만 백업해 통합하고 같은289서빙 파일의 해시를 확인한다. stable prepare/apply --confirm-main 및 실제 service.service HEALTH/RAG_SEARCH의 선택을 확인한다. quality override는 사용하지 않는다. 심각한 인용·권한·상태·해시·서빙 연결 오류는 MAIN50으로 롤백한다. GENOS와 상주 프로세스 재시작은 별도다.'),('재현 명령',f'06_TOOLS/EXPERIMENTS/adr_{number:04}/run_all.py, audit.py, report.py, archive.py. 완료 기록은 재실행으로 덮어쓰지 않는다. 무손실 압축 원시는 새 빈 디렉터리로 복원하고 receipt의 각 해시를 확인한다.')]
front=f"---\nadr_id: ADR-{number:04}\ntitle: 요청 상태·답변 보존 공개 검증\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-09\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(front+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 공개 분리 검증\n\n'+table+'\n'+rt+'\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':f'ADR-{number:04}','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, exact output and qualification','contains_raw_prompts_and_outputs':p.name in ('result.json','raw.tar.gz')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup'))]})
print('Recorded','Accepted' if ok else 'Rejected',failed)

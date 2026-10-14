"""Record prospective qualification without changing frozen criteria or raw outcomes."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success'];failed=[k for k,v in r['checks'].items() if not v]
table='| 방식 | 원문 근거 포함 응답 | 실제 모델 호출 | 요청 시간 합계 |\n|---|---:|---:|---:|\n'
for a,v in r['by_arm'].items():table+=f"| {a} | {v['supported']}/3 | {v['calls']} | {v['request_seconds']:.1f}초 |\n"
decision=('사전 기준 통과. 동일287서빙 파일을 로컬 MAIN 승격 후보로 채택한다. 실제 적용·선택은 MAIN_RESULT.md와 영수증을 따른다.' if ok else '미통과로 MAIN48 유지. 실패 기준: '+', '.join(failed))
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text()+'\n\n| arm | HTTP | 호출 | 요청 시간 | 원문 근거 포함 응답 |\n|---|---:|---:|---:|---|\n'
 for a,v in r['by_arm'].items():
  c=next(x for x in v['cases'] if x['case_id']==q['case_id'])
  s+=f"| {a} | {c['http_status']} | {c['physical_model_attempts']} | {c['request_seconds']:.3f}초 | {c['supported_response']} |\n"
 s+='\n완전한 답변·사용량은 각 arm/case/result.json, 개별 모델 전송과 원시 입력/출력·journal은 raw.tar.gz 및 raw-archive.json을 따른다. 회수·탈락은 retrieval-ledger.json.gz, 세부 의미 검토는 SEMANTIC_REVIEW.md에 분리했다.\n'
 p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
parts=[('결정 요약',decision),
 ('문제와 변경 전 구조','MAIN48은 새 요청의 앞단 네 호출과 구조 우선 검색을 사용한다. 완료0707은 앞단을 한 호출로 합치고 실제 법령 제목 힌트와 선택형 구조/fulltext를 추가했다.0709의 기본 기동 검사에서 PIPELINE에 이전 profile hash가 남은 것을 발견했다. 앞선 profile 직접 주입 실험은 이 기본 연결을 검사하지 못했다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json): 공개3문항 두 방식6요청, 후보 원문 근거 응답2/3 이상 및 baseline 비열등·개별 응답 회귀0, 성공 인용·권한·상태·실행 hash·표시 경계 보존, 계약 회귀0, 실제 호출 계수. 세부 법률 판단 미스는 별도 진단하고 인용·상태 등 심각한 문제와 구분한다. 소표본 속도 개선은 통과 기준이나 일반 성능 주장으로 쓰지 않는다.'),
 ('실험 설계','완료0707/title-entry에서 PIPELINE의 기본 v6 profile binding hash 한 곳만 바로잡았다. 제품 Python·프롬프트·검색 정책의 바이트는0707과 같다. 기준은 실제 MAIN48이다.0709에서 동결했으나 모델0회로 전부 미실행한 공개3문항을 사용한다. 실제 출력에 맞춘 질문 교체·반복·모델 변경은 없다.'),
 ('데이터·모델·재현성','동일 term-source-8729f978a28924cb8c5b·공개 승인65문서·Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 과거 원시 기록의 조문 ID 제외 감사5242개와 세 신규 주 조문을 결속했다. 기준 원문은 별도 gold.json이며 제품 실행기는 읽지 않는다. 요청마다 새 프로세스/세션을 사용하고 순서를 교대했다. OS 캐시는 비우지 않았다.'),
 ('결과',table+'\n기본 기동·권한·인용·판단·표시·제목 힌트·검색 선택 계약271개 통과. 기존 경험 fixture1개 제외는 유지했다. 동결287파일 패키지와 MAIN48을 비교했다. 처리 성공은 법률 설명의 완전 정답을 뜻하지 않는다.'),
 ('사례별 오류 분석','[의미 검토](SEMANTIC_REVIEW.md)와 질문별 결과를 따른다. 기존0708의 이유/행동 불일치와 중복 재검색 제안 실패는 해결됐다고 주장하지 않는다.0709는 실제 모델0회·기본 설정 hash 실패로 보존했고, 완료 원장의 corpus_total=0 형식 오류 역시 소급 수정하지 않았다. 이번 독립 원장은 실제 양수 corpus와 수행 결과를 기록한다.'),
 ('비용·지연·회수 규모','실제 물리 전송은 실패/재시도를 포함한다. 요청 시간과 모델별 시간을 분리하고 토큰/비용 미보고는0으로 추정하지 않는다. 자료 확보·모델 전달·근거 채택 및 canonical 조문 회수·탈락을 별도 계수했다. 속도 차이에 초기 준비·검색 범위·모델 출력 변동이 모두 포함된다.'),
 ('해석','문장과 실제 제목 사이의 단서를 추가 모델 호출 없이 제공한다. 모델은 위치를 짐작하면 구조 검색, 세부 내용으로 찾을 때 본문 검색을 선택할 수 있다. 제목 힌트는 검색 단서이며 접근권한이나 법적 근거가 아니다. 기존 세션·정정·복구 경로, 중복 검사, 읽기/채택 분리는 유지한다.'),
 ('한계와 일반화 가능 범위','독립 공개3문항의 제한된 검증이다. 이전 CM018 및 본문 재검색 실패를 미사용 holdout으로 세지 않는다. 이유 문장과 행동의 의미 일치는 일반적으로 보증되지 않는다. 난이도별 예산·새 복구 전략·GENOS 현장 배포·전체 법률 품질 인증은 범위 밖이다.'),
 ('운영 결정·롤백 조건',decision+' 통과시 검토한 변경만 백업 후 작업 코드에 선별 통합하고 동일 코드 계약검사를 수행한다. stable prepare/apply --confirm-main, 활성 포인터와 실제 service.service HEALTH/RAG_SEARCH 및 새 모듈 선택을 확인한다. 심각한 인용·권한·상태·hash·선택 문제가 있으면 직전 MAIN48로 별도 generation을 발행해 롤백한다. 사용자 MAIN 적용 요청이 명시 승인이다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0710/run_all.py, run_case.py, audit.py. 기존 실행 디렉터리를 덮어쓰지 않는다. 반복 실험은 새 ADR. 전체 원시 기록은 멤버별 hash 검증 후 무손실 압축하며 새 빈 폴더에서 복원한다.')]
fm=f"---\nadr_id: ADR-0710\ntitle: 통합 앞단 설정 결속과 공개 분리 MAIN 검증\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-09\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 동일 코드 공개 분리 검증\n\n'+table+'\n'+ '\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0710','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact outcomes, raw archive and qualification evidence','contains_raw_prompts_and_outputs':p.name in ('result.json','raw.tar.gz')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup'))]})
print('Recorded', 'Accepted' if ok else 'Rejected',failed)

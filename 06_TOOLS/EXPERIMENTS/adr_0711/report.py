"""Record qualification without rewriting frozen inputs or raw outcomes."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0711-compact-selection-source-input';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success'];failed=[k for k,v in r['checks'].items() if not v]
table='| 방식 | 원문 근거 응답 | 실제 호출 | 입력 토큰 | 요청 시간 합계 |\n|---|---:|---:|---:|---:|\n'
for a,v in r['by_arm'].items():table+=f"| {a} | {v['supported']}/3 | {v['calls']} | {v['input_tokens']:,} | {v['request_seconds']:.1f}초 |\n"
decision=('사전 기준 통과. 동일 서빙 파일을 로컬 MAIN 승격 후보로 채택한다. 실제 적용은 별도 receipt를 따른다.' if ok else '사전 기준 미통과. MAIN49 유지. 실패 기준: '+', '.join(failed))
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text()+'\n\n| arm | HTTP | 호출 | 입력 토큰 | 요청 시간 | 원문 근거 응답 |\n|---|---:|---:|---:|---:|---|\n'
 for a,v in r['by_arm'].items():
  c=next(x for x in v['cases'] if x['case_id']==q['case_id']);s+=f"| {a} | {c['http_status']} | {c['physical_model_attempts']} | {c['usage']['input_tokens']:,} | {c['request_seconds']:.3f}초 | {c['supported_response']} |\n"
 s+='\n전체 답변·사용량은 각 arm/case/result.json, 실제 전송·journal은 raw.tar.gz와 raw-archive.json을 따른다. 본문을 이 보고서에 반복 복사하지 않는다. 회수·탈락은 retrieval-ledger.json.gz, 원문 보존은 wire-audit.json, 세부 의미는 SEMANTIC_REVIEW.md에 분리했다.\n';p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
parts=[('결정 요약',decision),
('문제와 변경 전 구조','MAIN49는 앞단을 한 호출로 통합하고 문장·법령명 힌트로 구조/본문 검색을 선택한다. 그 뒤 미선택 법령의 상세 구조·조문·행동 메뉴와 중복 원문이 매번 함께 전달된다. 이전 읽기 전용 감사에서 넓은 검색의 첫 판단이 입력66,883토큰이었다. 행동 이력에는 이미 원문 전체가 없었으므로 이 사실을 보존한다.'),
('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json): 공개3문항 두 방식6요청, 입력 합계15% 이상 감소, 호출 합계 증가 없음. 후보 원문 근거 응답2/3 이상 및 baseline 비열등·개별 회귀0, 모든 주 조문 실제 전달, 인용·권한·상태·실행 hash·표시 경계 보존, 계약 회귀0. 세부 판단의 완전 정답과 구분하며 결과 후 기준은 바꾸지 않는다.'),
('실험 설계','부모는 완료 ADR0710/integrated, 기준은 실제 MAIN49다. compact_input 선택 기능으로 미선택 법령의 상세 목차를 펼칠 때 생성하고 초기 적중 조문은 상위2개와 전체 더보기/바로 읽기를 제공한다. 검색 순위·접근 범위·원문 읽기/채택 검증은 유지한다. 같은 입력 안의 원문 복사본은 원문1개와 정확 위치 참조로 치환한다. 모든 행동 이력은 대상·행동·결과·짧은 이유로 남긴다. 빈 배열 스키마만 의미가 같은 간단한 항목으로 표현한다.'),
('데이터·모델·재현성','동일 term-source-8729f978a28924cb8c5b·승인 공개65문서·Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 이전 공개 호출과 겹치는5,330원문 ID를 제외한3개 주 조문, 서로 다른3문서를 사용했다. gold는 제품 입력과 분리했다. 요청별 새 프로세스, 교대 순서1회씩이며 OS 캐시는 비우지 않았다. 추가 요약 LLM은 없다.'),
('결과',table+'\n계약287개 통과(기존271+신규16). 원문·범위·참조/복귀·중복 검색 거절·프로필 결속을 검사했다. 실제 입력 원문과 저장본의 동일성은 wire-audit.json을 따른다. 소표본 시간 차이를 일반 성능으로 주장하지 않는다.'),
('사례별 오류 분석','H01은 구조 설명 질문에서 원문 바로 읽기 대신 목차 탐색을 먼저 골라4→5회로 늘었다. H03은 핵심 조문을 인식하고도 다른 법령 페이지로 이동했다가 복귀했다. 이는 입력 축소만으로 행동 효율이 보장되지 않음을 보여준다. [의미 검토](SEMANTIC_REVIEW.md)에 답변 세부 문제를 따로 기록했다. rev001의 engine 해시 갱신 누락은 모델0회인 사전 준비 실패로 보존하고, 갱신한 rev002를 재동결한 뒤 최초 모델 호출했다.'),
('비용·지연·회수 규모','모든 물리 호출과 사용량·요청 시간을 포함한다. 확보·모델 전달·채택은 별도 계수한다. 상세 후보를 숨긴 효과와 모델이 선택한 행동 변화가 함께 반영된 E2E 비교이며 각 변경의 독립 효과는 분리 측정하지 않았다. 비용 미보고는0으로 추정하지 않는다.'),
('해석','필요한 원문은 호출마다 완전하게 유지하면서 같은 호출 안의 중복 표현만 제거한다. 일찍 목록을 짧게 보여주는 것만으로 불필요한 탐색이 사라지지 않았다. 기존 장문의 지침에는 미열람 후보를 보류하고 다른 법령을 보라는 표현과 바로 읽기 안내가 섞여 있어 후속 후보에서 선택 맥락을 더 명확히 할 필요가 있다. 개별 행동의 원인을 이 한 번의 비교만으로 확정하지 않는다.'),
('한계와 일반화 가능 범위','공개3문항의 제한된 비교다. 과거 CM018·0708 재검색 실패 해결이나 법률 품질·망분리 성능을 인증하지 않는다. 구조화/본문 검색은 계속 모델이 선택하는 도구이며 구조 검색을 강제하지 않는다. 사라진 상세 메뉴는 열기와 다음 페이지로 접근 가능하지만 추가 호출이 생길 수 있다.'),
('운영 결정·롤백 조건',decision+' 사전 기준 미통과 시 작업 코드와 활성 포인터는 수정하지 않는다. 통과시 선별 통합·동일 코드 검증·hash 고정 승격·실제 서비스 선택 확인까지 수행한다. 이전 MAIN49로 rollback할 receipt를 보존한다. GENOS 반입/배포는 별도다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0711/run_all.py, run_case.py, audit.py, wire_audit.py, archive.py. 기존 결과를 덮어쓰지 않는다. 후속 수정·모델 재실행은 새 ADR. raw.tar.gz는 멤버별 hash 검증 후 중복만 제거하며 새 빈 폴더에서 복원한다.')]
fm=f"---\nadr_id: ADR-0711\ntitle: MAIN49 선택 메뉴와 중복 원문 입력 축소\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-09\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 공개 분리 검증\n\n'+table+'\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0711','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact outcomes, raw archive and qualification evidence','contains_raw_prompts_and_outputs':p.name in ('result.json','raw.tar.gz')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup','preflight-rev001-release'))]})
print('Recorded','Accepted' if ok else 'Rejected',failed)

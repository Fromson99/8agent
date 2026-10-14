"""Finalize predeclared qualification; no changes to frozen gates or model outputs."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success'];failed=[k for k,v in r['checks'].items() if not v]
tests=len(list(E.parse(A/'artifacts/contracts/required.xml').iter('testcase')))
table='| 신규 공개3문항 | 원문 근거 응답 | 실제 호출 | 입력 토큰 | 요청 시간 합계 |\n|---|---:|---:|---:|---:|\n'
for a,v in r['primary_comparison'].items():table+=f"| {a} | {v['supported']}/3 | {v['calls']} | {v['input_tokens']:,} | {v['request_seconds']:.1f}초 |\n"
known=[x for x in r['by_arm']['compact']['cases'] if x['case_id'].startswith('R')]
ktable='| 알려진 회귀 사례(후보만) | 원문 근거 응답 | 호출 | 입력 토큰 | 시간 |\n|---|---:|---:|---:|---:|\n'
for x in known:ktable+=f"| {x['case_id']} | {x['supported_response']} | {x['physical_model_attempts']} | {x['usage']['input_tokens']:,} | {x['request_seconds']:.1f}초 |\n"
decision=('사전 기준 통과. 동일 코드의 로컬 MAIN 승격 후보로 채택한다. 실제 적용·선택은 MAIN_RESULT.md와 별도 영수증을 따른다.' if ok else '사전 기준 미통과. MAIN49 유지. 실패 기준: '+', '.join(failed))
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text()+'\n\n| arm | HTTP | 호출 | 입력 토큰 | 요청 시간 | 원문 근거 응답 |\n|---|---:|---:|---:|---:|---|\n'
 for a,v in r['by_arm'].items():
  c=next((x for x in v['cases'] if x['case_id']==q['case_id']),None)
  if c:s+=f"| {a} | {c['http_status']} | {c['physical_model_attempts']} | {c['usage']['input_tokens']:,} | {c['request_seconds']:.3f}초 | {c['supported_response']} |\n"
 s+='\n'+('알려진 회귀 사례다. 신규 holdout 및 주 비교 합계에서 제외한다.\n' if q['case_id'].startswith('R') else '결과 확인 전 선택한 신규 주 조문 사례다.\n')
 s+='전체 출력·사용량은 각 arm/case/result.json, 실제 요청·응답·journal은 raw.tar.gz와 raw-archive.json, 회수·탈락은 retrieval-ledger.json.gz를 따른다. 본문을 보고서마다 복사하지 않는다.\n';p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
parts=[('결정 요약',decision),
('문제와 변경 전 구조','MAIN49는 앞단1회 통합·실제 법령 제목 힌트·선택형 구조/본문 검색을 사용한다. 완료0711은 미선택 상세 메뉴·중복 원문을 줄였지만 넓은 검색에서 핵심 조문을 인식하고도 다른 페이지로 이동·복귀·재검색했다. H03 판단 그룹도 root와 연결되지 않아 최종 거절됐다. 총 입력156,315→161,313, 호출13→17, 응답3→2로 실패했고 MAIN49는 유지했다.'),
('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json): 신규 공개3문항 paired6요청과 알려진 회귀2요청을 분리한다. 신규 주 비교 입력 토큰 합계15% 이상 감소, 호출 합계 증가 없음. 원문 근거 응답2/3 이상·baseline 비열등·개별 회귀0, 모든 주 원문 실제 전달, 인용·권한·상태·실제 코드/데이터·표시 경계 보존. 알려진2문항 모두 응답, 각각5회 이하. 기준은 출력 후 변경하지 않는다.'),
('실험 설계','완료0711/compact 위에서 탐색 지침을 간결하게 바꿨다. 관련 후보의 read_action은 바로 읽기, 추가 목차/페이지/검색은 부족한 위치를 찾기 위한 도구라고 구분한다. 명확히 찾은 구조 위치의 상세 구조를 유지한다. 원문 중복을 줄이는 전송 표현은 탐색 단계에 한정하고, 최종 판단에는 기존 구절-인용ID 연결을 유지한다. 이전의 지연 목차·상위2개/더보기·간결한 전체 행동 이력·빈 배열 스키마 축소는 계승한다. 실행·검색 중복·읽기/채택 검증 함수는 MAIN49와 동일하다.'),
('데이터·모델·재현성','동일 term-source-8729f978a28924cb8c5b·승인 공개65문서·Qwen3.8/Parasail FP8/reasoning none/fallback 없음. 이전 기록의5,397원문 ID를 제외한 신규3주 조문을 출력 전에 고정했다. R01/R02는0711의 알려진 문제로 별도 표시한다. gold는 제품 입력 비공개, 요청별 새 프로세스, 교대 순서1회씩, OS 캐시는 비우지 않는다. 내부 CM 질문은 반출하지 않았다. 추가 판단/요약 모델은 없다.'),
('결과',table+'\n'+ktable+f'\n계약 {tests}개 검사. 원문 전달 및 위치 참조는 [전송 감사](artifacts/run-001/wire-audit.json), 인용·권한·상태·회수/탈락은 [결과](artifacts/run-001/result.json)를 따른다. 사례별 답변 내용은 SEMANTIC_REVIEW.md에 별도 검토했다.'),
('사례별 오류 분석','[의미 검토](SEMANTIC_REVIEW.md)를 따른다. 입력·호출·원문 근거 응답은 서로 다른 지표다. 새 후보로 옛 원시 결과를 대체하거나 고친 것으로 보고하지 않는다. 준비 중 신규 합성 테스트에서 실제 요청 질문과 coordinate_scope가 없는 이전 fixture 문제가 드러났고 모델0회 상태에서 수정했다. 해당 실패와 이전 freeze를 보존했으며 제품 코드는 동일한 rev003으로 최종 동결했다.'),
('비용·지연·회수 규모','실제 물리 호출은 실패/수정을 포함한다. 입력·출력 토큰, 모델별 시간, 요청 시간을 모두 원본 사용량에서 계산한다. 신규와 알려진 사례를 합쳐 비교 효과를 부풀리지 않는다. 데이터 확보·모델 전달·근거 채택과 canonical 조문 회수·탈락은 별도 기록한다. 시간은3문항 단일 실행 관측치이며 일반 속도 인증이 아니다.'),
('해석','선택 환경을 줄이는 것은 필요한 근거를 덜 읽는 것과 다르다. 법령 상세 목차는 필요할 때 펼치고 요구한 조/항/호 원문은 전체로 읽는다. 같은 호출 안의 중복 원문은 탐색에서 위치 참조로 표시하지만 최종 판단에는 근거 구절을 붙여 준다. 모든 행동은 대상·결과·짧은 이유로 유지하고 이전 원문 전체는 다시 싣지 않는다. 모델이 이유와 같은 행동을 고르는 것을 보증하거나 실행 코드가 의미를 대신 판단하지 않는다.'),
('한계와 일반화 가능 범위','신규 공개3문항과 알려진2문항의 제한된 검증이다. 전체 법률 품질·미공개 CM·GENOS·난이도별 예산 최적화는 인증하지 않는다. 구조/본문 검색은 선택형 도구로 유지한다. 탐색 프롬프트와 표시 변경의 독립 효과는 분리 측정하지 않았다. 최종 판단 중복 원문 압축과 더 작은 수정 입력은 후속 과제로 남긴다.'),
('운영 결정·롤백 조건',decision+' 통과시 변경38파일만 백업해 선별 통합하고 동일287서빙 파일의 hash와 작업 코드 계약 검사를 확인한다. stable prepare/apply --confirm-main, 활성 포인터, 실제 service.service HEALTH/RAG_SEARCH의 코드·프로필·데이터 선택을 확인한다. 심각한 인용·권한·상태·실행 binding 문제가 있으면 직전 MAIN49로 별도 generation을 발행해 롤백한다. 작업 코드 백업과 포인터 롤백은 구분하며 GENOS 배포는 별도다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0712의 run_all.py/run_case.py/audit.py/wire_audit.py/archive.py. 기존 출력은 덮어쓰지 않고 후속 실행은 새 ADR로 기록한다. 원시 기록은 hash 검증 후 무손실 압축하며 새 빈 폴더로 복원한다.')]
fm=f"---\nadr_id: ADR-0712\ntitle: 간결한 탐색 입력과 바로 읽기 선택 맥락\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-09\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 공개 분리 검증\n\n'+table+'\n'+ktable+'\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0712','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, exact output, raw archive and qualification','contains_raw_prompts_and_outputs':p.name in ('result.json','raw.tar.gz')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup'))]})
print('Recorded','Accepted' if ok else 'Rejected',failed)

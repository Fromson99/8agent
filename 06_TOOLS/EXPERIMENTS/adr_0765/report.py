from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall';D=A/'artifacts'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(D/'run-001/result.json');passed=r['strict_success']
assert m['reservation']['status']=='in_progress'
table='| arm | 원문 근거 응답 | 호출 | 입력 토큰 | 요청시간 합계 |\n|---|---:|---:|---:|---:|\n'
for arm,v in r['by_arm'].items():table+=f"| {arm} | {v['supported']}/{len(v['cases'])} | {v['calls']} | {v['input_tokens']:,} | {v['request_seconds']:.2f}초 |\n"
for q in m['questions']:
 p=A/'실험'/q['file'];text=p.read_text()+'\n\n| arm | HTTP | 호출 | 입력 토큰 | 초 | 근거 응답 |\n|---|---:|---:|---:|---:|---|\n'
 for arm,v in r['by_arm'].items():
  c=next(x for x in v['cases'] if x['case_id']==q['case_id'])
  text+=f"| {arm} | {c['http_status']} | {c['model_calls']} | {c['usage']['input_tokens']:,} | {c['request_seconds']:.2f} | {c['supported_response']} |\n"
 text+='\n[실행 산출물](../artifacts/run-001/), [원문 의미 검토](../SEMANTIC_REVIEW.md). 실제 전송·응답·journal은 raw.tar.gz와 raw-archive.json의 SHA/복원 방법으로 보존한다.\n'
 p.write_text(text);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
failed=[k for k,v in r['checks'].items() if not v]
sections=[
 ('결정 요약','동결 기준 통과, 동일 코드 로컬 MAIN 승격 후보.' if passed else 'Rejected. MAIN53 유지. 실패 기준: '+', '.join(failed)),
 ('문제와 변경 전 구조','MAIN53은 동일 조건 핵심 원문 경로를 재사용하지만 표현이 다른 질문에서 목적·문맥으로 기록을 찾아 기존 판단에 제공하는 경로가 없다. 위키 markdown 투영의 존재와 실시간 회수를 구분한다.'),
 ('가설과 사전 판정 기준','저장 시 이미 생성된 INTENT 목적과 문맥, 원질문 발췌 요약·원기록 ID를 SQL 검색 카드로 투영한다. 질문마다 최대1회 검색, 최대3개·2400자, 기존 판단에서 최대2개 선택. 별도 모델 호출0. 권한·세대·정정·인용·원문·상태 보존, 신규 회귀0, 공개3개 원문 근거 응답, 일치2개 선택과 불일치1개 기존 조사, 합산 호출 증가0 및 요청시간1.5배 이내를 호출 전 동결했다. [정확한 기준](artifacts/design/criteria.json).'),
 ('실험 설계','완료 ADR0761/integrated·선택 MAIN53이 부모다. 기준과 후보에 같은 공개 모의 과거기록2개, 동일 데이터·권한·모델·예산과 API를 적용했다. 고정3쌍·6요청, 반복1. 후보296서빙파일 동결, 실행 후 질문 교체·재호출·후보 수정 없음. 과거기록은 실제 이전 모델 성과가 아닌 출처가 표시된 테스트 fixture다.'),
 ('데이터·모델·재현성','상법 공개 원문 중 대리권 존속·대화자간 청약·상사법정이율의 새로 작성한 질문3개. 현재 선택 원문 세대와 공개65문서 허용 범위를 사용했다. 질문 및 원문 ID는 결과 전에 동결했으며 전체 과거 실험에 대한 미노출을 인증하지 않는다. 이번 구현 개발 질문과 분리한 전향적 소표본이다. gold 원문은 평가기에만 제공했다. Qwen3.8 / qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음. 내부CM은 외부 전송하지 않았다.'),
 ('결과',table+'\n[전체 기준별 결과](artifacts/run-001/result.json). 원문 근거 응답은 독립적인 법률 정답률이 아니다.'),
 ('사례별 오류 분석','[의미 검토](SEMANTIC_REVIEW.md). 저장·권한·세대·정정·원문 불변·단회 조회·무효 선택·실패 복귀·예산 관련 새22검사 통과. 관련 기존171검사의25실패는 양쪽 동일하며 신규 회귀0이다. 미통과 기존 검사를 통과로 세지 않는다.'),
 ('비용·지연·회수 규모','물리 요청/응답·단계별 원장·사용량·시간은 artifacts/run-001에 보존했다. 검색은 SQL 단어/한글2글자 색인, shortlist24·SQL80ms 중단·후보확인120ms 제한이다. DB 잠금과 OS 스케줄링까지 포함한 절대 응답시간 상한을 보장하지 않는다. 모델 추가 호출0이며 호출 수·지연 전체 비교는 위 표와 result의 memory_lookup에서 확인한다. [회수·탈락 원장](artifacts/run-001/retrieval-ledger.json.gz).'),
 ('해석','검색 카드는 탐색 힌트다. 기존 request-entry 또는 memory-intent 판단에서 관련성을 선택하고, 선택한 현재 유효 원문 좌표를 읽는 RECALL 경로로 전달한다. 과거 결론·사실·판단·절차를 답변 근거나 현재 사실로 복제하지 않는다. 정확 조건 경로는 기존대로 우선하며 새 bounded 모드에서 과거 procedure/judgment 재생은 사용하지 않는다. miss·권한 불일치·세대 변경·무효 선택은 기존 조사를 계속하고 위키 재탐색하지 않는다.'),
 ('한계와 일반화 가능 범위','벡터 없이 단어가 겹치는 후보를 찾으므로 완전히 다른 표현은 누락될 수 있다. 요약은 기존 문맥과 질문에서 발췌하며 저장 때 별도 LLM으로 재작성하지 않는다. 세 공개 질문은 전체CM 검색률·의미 판단·장기 성능·대규모 지연의 인증이 아니다. GENOS 현장 실행은 미확인이다.'),
 ('운영 결정·롤백 조건','통과한 경우만 변경 파일을 선별 통합하고 동일 코드 검사 → hash 고정 승격 → 선택 포인터 → 실제 service 진입점 → 기존 저장소 검색 카드 재구축을 확인한다. 원문·불변 기록과 기존 파이프라인은 보존한다. 직전 MAIN53 및 작업 코드 백업으로 원복할 수 있으며 새 파생 색인은 이전 코드에서 비활성이다. 배포 결과는 별도 MAIN_RESULT.md에 기록하고 완료 실험 manifest를 사후 수정하지 않는다.'),
 ('재현 명령','`06_TOOLS/EXPERIMENTS/adr_0765/{prepare,contracts,freeze_run,run_all,audit,report,archive}.py`. WSL의 `.venv/bin/python`으로 실행한다. 완료 산출물에 재실행하지 않는다. 결과를 본 뒤 재실행·후속 수정은 새 ADR로 남긴다.')]
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if passed else 'Rejected')).replace('decision_eligible: false','decision_eligible: true')
if passed:front=front.replace('main_wiring: unchanged','main_wiring: promotion-candidate')
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 공개 과거기록 회수 검증\n\n'+table+'\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
put(D/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, exact outputs and integrity evidence','contains_raw_prompts_and_outputs':p.name in ('raw.tar.gz','result.json')} for p in D.rglob('*') if p.is_file() and p.name!='manifest.json' and not any(x in p.parts for x in ('provider','runtime','binding-runtime','sessions','working-backup','setup-check'))]})
print('Report',passed,failed)

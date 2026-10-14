"""Write the decision from preserved outcomes, without changing criteria or code."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success'];c=r['by_arm']['repaired'];b=r['by_arm']['baseline']
failed=[k for k,v in r['checks'].items() if not v]
for q in m['questions']:
 p=A/'실험'/q['file'];text=p.read_text();text=text.replace('Results will be recorded once in result.json; no rerun, case replacement or post-output candidate modification.',
  '결과는 아래 실제 기록을 따른다. 코드·기준·질문 교체와 제품 재실행은 하지 않았다.')
 text+='\n\n| arm | 실제 HTTP | 모델 호출 시도 | 원문 인용 확인 | 기록 |\n|---|---:|---:|---|---|\n'
 for arm in ('baseline','repaired'):
  x=next(v for v in r['by_arm'][arm]['cases'] if v['case_id']==q['case_id'])
  http=x['http_status'] if x['http_status'] is not None else ('미실행' if not x['attempted'] else '외부 중단·응답 미확인')
  text+=f"| {arm} | {http} | {x['model_calls']} | {'확인' if x['supported_response'] else '최종 답변 미확인'} | [원 결과](../artifacts/run-001/{arm}/{q['case_id']}/result.json), [진단](../artifacts/run-001/{arm}/{q['case_id']}/diagnostic.json) |\n"
 p.write_text(text);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
table='| arm | 신규8사례 중 근거 포함 응답 | 기존3사례 중 근거 포함 응답 | 모델 호출 시도 | 관측 요청 중앙값 |\n|---|---:|---:|---:|---:|\n'
for arm in ('baseline','repaired'):
 x=r['by_arm'][arm];table+=f"| {arm} | {x['supported_primary']}/8 | {x['supported_known']}/3 | {x['calls']} | {x['request_p50']:.1f}초 |\n"
decision='사전 기준을 충족해 정확히 검증한 패키지를 로컬 MAIN 승격 후보로 채택한다. 실제 활성화 결과는 별도 MAIN_RESULT.md와 영수증으로 남긴다.' if ok else '사전 기준 미충족으로 이번 패키지를 MAIN에 승격하지 않는다. 미통과 기준: '+', '.join(failed)+'. 구현과 모든 원시 결과는 보존한다.'
sections=[('결정 요약',decision),
 ('문제와 변경 전 구조','앞선 판단 루프 정리의8파일 수정과 완료된 조사 경로를 유지했다. 검토 R1 의존 해시, R2 대상 생략 시 부족 충돌, R3 공유 근거의 쟁점 누락, R4 라운드 전체 근거로 서로 다른 부족을 종료하는 문제를 보완했다. ADR0689에서 발견한 약칭 projection 누락을 포함해 서비스 의존 묶음을 완성했다.'),
 ('가설과 사전 판정 기준','[호출 전 기준](artifacts/design/criteria.json)에 신규 계약37개, 새 회귀0, 신규8사례 중7개·기존3사례 중2개 이상 근거 포함 응답, MAIN45 대비 응답 수 비열등과422 수 비증가, 원문·권한·상태·해시 위반0을 고정했다. 법률 세부 판단 오류는 진단이며 절대 승격 차단 기준이 아니다. [실제 검사](artifacts/run-001/result.json)는 이 기준을 바꾸지 않는다.'),
 ('실험 설계','정확한 MAIN45 코드와 repaired/rev-001 패키지275파일을 같은 source generation·공개 문서145개·질문11개·provider/model 제한으로 비교했다. 질문마다 arm 순서를 교대하도록 동결했다. 실제로10개 실행을 시도했고, 후보H01·H05는 중단되어 최종 응답을 받지 못했다. 나머지12개는 미실행으로 기록했다. 기존3사례는 인샘플이며, 신규8조문과 섞어 미사용 holdout으로 주장하지 않는다. 완료된 ADR0689/repaired를 extends한다. 기존 개발 이력과 후보 내 원형을 보존했다.'),
 ('데이터·모델·재현성','[선택 감사](artifacts/design/selection-audit.json), [이전 입력 제외 기록](artifacts/design/exclusion-scan.json), [완전 패키지 동결](artifacts/design/freeze.json)을 따른다. Qwen3.8 / Parasail FP8 / reasoning none / provider·model fallback없음. 각 요청40호출·출력6400 token 한도다. gold 원문은 별도 파일에 두며 제품 실행기는 읽지 않는다. 사용한 원문은 고정 세대 판본이며 최신 법률 일반 해석을 인증하지 않는다.'),
 ('결과',table+'\n보완 계약37개 통과. 유지 회귀는 양쪽112개 통과·동일한 역사적 knowledge fixture1개 실패다. 후보H01의8번째 호출과 후보H05의5번째 호출은 turn 중단 때문에 응답을 확인하지 못했다. 재전송하지 않았고, 모두 원래 분모에서 성공0으로 셌다. 사전7/8 기준 달성이 불가능해 나머지12개를 미실행으로 기록하고 이번 ADR을 미통과로 종료했다.'),
 ('사례별 오류 분석','[질문별 기록](실험/README.md), case별 diagnostic.json과 [기계 검사 결과](artifacts/run-001/result.json)를 따른다. 외부 중단은 제품 오류나 성공으로 추정하지 않는다. 각 모델의 법률 의미 판단과 근거 미확보는 별도 SEMANTIC_REVIEW.md에 기록한다. 인용 문자열이 원문에 있다는 사실만으로 법률적 추론의 타당성이 검증된다고 보지 않는다.'),
 ('비용·지연·회수 규모','모델 usage·비용은 manifest의 arm별 reported usage와 provider/usage.json에 보존한다. 후보H01·H05의 미확인 호출2개 비용은 합계에 포함할 수 없어 보고 비용은 하한이다. 중단 요청의 지연 역시 하한이며, 미실행 요청과 함께 중앙값에서 제외한다. 소규모 표본의 속도 개선을 주장하지 않는다. [단계별 회수 원장](artifacts/run-001/retrieval-ledger.json.gz)은 catalogue→recall→실제 원문 취득→모델에 원문 전달 순서로 canonical 조문 root를 집계하며 gold는 출력 후 결합했다.'),
 ('해석','부족을 개별 행동·근거와 연결하고, 새로 채택한 근거·완료된 조사의 참조를 검증한다. 공유 판단 문장은 한 번 쓰되 관련 쟁점 모두에서 위치를 표시한다. 대상이 생략된 부족은 이유까지 식별에 사용한다. 모듈은 법률 의미가 같은지 자동 증명하지 않으며, 같은 행동을 여러 부족에 연결한 모델 판단의 타당성도 별도 검토 대상이다.'),
 ('한계와 일반화 가능 범위','공개4법률의 신규8조문과 알려진3질문이다. 새로운 문서 유형·비공개 계약·GENOS 내부 모델로 일반화하지 않는다. 외부 중단2건은 응답 미확인이며12개는 미실행이다. 구 지식 저장 계약을 기대하는 유지 테스트1개는 수정 전후 동일하게 실패했다. 병행 factorized-audit 개발은 이번 서빙 후보에 넣지 않았고 작업 파일을 덮어쓰지 않는다.'),
 ('운영 결정·롤백 조건',decision+' 검증을 통과해 적용할 때에는 작업 코드의 수정2파일과 계약 검사만 선택 반영하고, 현재 작업 코드의 실제 해시로 engine pin을 갱신한다. stable prepare/apply --confirm-main, 선택 포인터, 새 service.service의 실제 binding을 확인한다. 원문·권한·상태·코드/데이터 해시·서빙 연결의 문제는 이전 선택 포인터로 rollback한다. GENOS 반입·배포·Git main 병합은 별도다.'),
 ('재현 명령','원 실행기: `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0690/run_case.py --arm <arm> --case <case>`. 결과가 있는 경로를 다시 실행하지 않는다. 사용자 중단 후에는 continue_remaining.py가 결과가 없는 새 사례만 실행했다. 재실행·후속 변경·재채점은 새 ADR을 선점한다. 결정적 원장 감사는 audit.py이며 제품 결과를 수정하지 않는다.')]
fm=f"---\nadr_id: ADR-0690\ntitle: 판단 루프 완전 패키지와 공개 분리 검증\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-08\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 공개 분리 검증 및 기존 사례\n\n'+table+'\n'+ '\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n\nH01·H05 후보 중단과12개 미실행은 원 분모에 남기고 성공으로 세지 않았다. 실제 원문·모델 입출력·실패 기록의 정본은 사례별 result.json/provider/runtime이다.\n')
items=[]
for p in (A/'artifacts').rglob('*'):
 if not p.is_file() or p.name=='manifest.json' or 'prepared-generations' in p.parts or 'runtime' in p.parts or 'provider' in p.parts:continue
 items.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Immutable design, raw-output reference or post-output deterministic audit','contains_raw_prompts_and_outputs':p.name in ('result.json','model-transcript.json')})
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0690','created_at':m['reservation']['created_at'],'files':items})
print('Recorded decision', 'Accepted' if ok else 'Rejected',failed)

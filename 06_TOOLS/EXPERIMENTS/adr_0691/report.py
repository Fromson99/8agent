"""Record the prospectively frozen continuation without changing its gates."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');ok=r['strict_success']
failed=[k for k,v in r['checks'].items() if not v]
table='| arm | 신규3사례 근거 포함 응답 | 기존3사례 근거 포함 응답 | 모델 호출 시도 | 관측 요청 중앙값 |\n|---|---:|---:|---:|---:|\n'
for arm in ['baseline','repaired']:
 x=r['by_arm'][arm];table+=f"| {arm} | {x['supported_primary']}/3 | {x['supported_known']}/3 | {x['calls']} | {x['request_p50']:.1f}초 |\n"
for q in m['questions']:
 p=A/'실험'/q['file'];s=p.read_text();s=s.replace('Results will be recorded once in result.json; no rerun, case replacement or post-output candidate modification.','실제 결과는 아래와 같다. 후보·질문·기준을 결과 확인 뒤 변경하지 않았다.')
 s+='\n\n| arm | 실제 HTTP | 모델 호출 | 원문 근거 포함 응답 |\n|---|---:|---:|---|\n'
 for arm in ['baseline','repaired']:
  x=next(v for v in r['by_arm'][arm]['cases'] if v['case_id']==q['case_id']);s+=f"| {arm} | {x['http_status']} | {x['model_calls']} | {x['supported_response']} |\n"
 s+=f"\n[기준 원 기록](../artifacts/run-001/baseline/{q['case_id']}/result.json) · [후보 원 기록](../artifacts/run-001/repaired/{q['case_id']}/result.json)\n";p.write_text(s);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
decision='동결한 전체 기준을 충족해 동일275파일 패키지를 로컬 MAIN 승격 후보로 채택한다. 실제 활성화 여부는 별도 MAIN_RESULT.md와 영수증을 따른다.' if ok else '미통과로 기록하고 MAIN을 변경하지 않는다. 미통과 기준: '+', '.join(failed)+'.'
parts=[('결정 요약',decision),
 ('문제와 변경 전 구조','부족 이유 충돌, 공유 판단이 연결 쟁점에서 사라지는 표시, 다른 부족의 조사·근거를 전용하는 종료를 보완한 코드다. ADR0690은 두 외부 실행 중단으로 원래7/8 기준을 달성할 수 없어 미통과로 종료했다. 그 결과·중단·미실행 기록은 그대로 보존했다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json): 신규3개 모두, 알려진3개 중2개 이상 근거 포함 응답; 기준 대비 응답 수 비열등·422 수 비증가; 모든12개 요청 실행; 인용·권한·상태·해시 위반0; 계약37개 통과·새 회귀0. 의미상 세부 오류는 별도 진단이다.'),
 ('실험 설계','완료된 ADR0690/repaired의275파일을 바이트 변경 없이 retests한다. 이전 계획에서 미실행인 H06~H08과 알려진3질문을 모두 선택했고, 결과에 따라 사례를 고르거나 바꾸지 않았다. 새 실험에서 전체3/3 신규 사례 응답을 요구하며 이전 실험의 실패를 성공으로 바꾸지 않는다.'),
 ('데이터·모델·재현성','[선택·노출 감사](artifacts/design/selection-audit.json)와 prior-product-exposure.json에서 신규3조문의 이전 모델 노출이 없음을 확인했다. 제품은 gold를 읽지 않는다. 원문은 고정된 로컬 공개 법령 세대이며 Qwen3.8 / Parasail FP8 / reasoning none / fallback없음을 유지한다. 요청당40호출·출력6400token 한도다. 새 원문 세대나 내부 질문을 사용하지 않았다.'),
 ('결과',table+'\n동일 후보에서37개 필수 계약을 다시 통과했다. 넓은 회귀 검사는 바이트가 같은 제품·검사 파일에 대한 부모의112통과·동일한 역사적fixture1실패를 해시로 결속해 재사용했다. [상속 검사 영수증](artifacts/contracts/inherited-receipt.json).'),
 ('사례별 오류 분석','[의미 검토](SEMANTIC_REVIEW.md)와 사례별 diagnostic.json을 따른다. 원문 인용의 일치는 법률 의미 정확성을 자동 증명하지 않는다. 부모 H04 후보의 과도한 “예외 없이” 단정과 반복 문장도 후속 개선 항목으로 유지한다.'),
 ('비용·지연·회수 규모','usage·비용·지연은 실험 manifest와 실제 provider 기록을 따른다. [단계별 원장](artifacts/run-001/retrieval-ledger.json.gz)은 catalogue→recall→원문 취득→실제 모델 전달을 canonical 조문 단위로 집계하며 gold는 제품 출력 뒤 결합했다. 작은 표본으로 속도 개선을 일반화하지 않는다.'),
 ('해석','부족별 완료 행동과 신규 채택 근거를 검증하고, 다른 부족의 행동이나 완료되지 않은 검색을 근거로 해결 처리하지 않는다. 공유 claim은 본문을 한 번 표시하면서 연결 쟁점에 위치를 남긴다. 같은 행동을 여러 부족에 연결한 의미 타당성이나 서로 다른 claim의 의미 중복까지 증명하는 것은 아니다.'),
 ('한계와 일반화 가능 범위','독립된 신규 조문은2법률3개뿐이며 알려진3질문은 인샘플이다. 사전학습 미노출·광범위 법률 정확도·내부 자료 품질을 주장하지 않는다. 이전 실험 중단2건은 여전히 미확인이다. GENOS 내부 모델과 현장 배포는 확인하지 않았다.'),
 ('운영 결정·롤백 조건',decision+' 통과 시 두 보완 런타임 파일과 관련 검사만 작업 코드에 통합한다. 병행 저장공간·감사 수정은 보존하고, 검증한 패키지를 stable prepare/apply --confirm-main으로 선택한 뒤 실제 service.service의 binding을 확인한다. 인용·권한·상태·코드/데이터 해시·서빙 연결 실패 시 이전 선택 포인터로 롤백한다.'),
 ('재현 명령','원 실행기는 `06_TOOLS/EXPERIMENTS/adr_0691/run_all.py`와 `run_case.py`다. 동결 해시는 artifacts/design/freeze.json에 있다. 기존 결과 또는 부분 실행이 있으면 재실행하지 않는다. 새 재실행·후속 후보·재채점은 새 ADR에 기록한다. 원시 기록은 raw.tar.gz와 복원 해시를 함께 보존한다.')]
fm=f"---\nadr_id: ADR-0691\ntitle: 판단 루프 동일 패키지 미실행 사례 분리 검증\nstatus: {'Accepted' if ok else 'Rejected'}\ndecision_date: 2026-10-08\nphase: holdout\nin_sample: false\ndecision_eligible: true\nmain_wiring: {'promotion-candidate' if ok else 'unchanged'}\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 미실행 사례의 분리 검증\n\n'+table+'\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
items=[]
for p in (A/'artifacts').rglob('*'):
 if not p.is_file() or p.name=='manifest.json' or any(x in p.parts for x in ['prepared-generations','runtime','provider']):continue
 items.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Design, raw output or post-output audit','contains_raw_prompts_and_outputs':p.name in ('result.json','raw.tar.gz')})
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0691','created_at':m['reservation']['created_at'],'files':items})
print('Recorded', 'Accepted' if ok else 'Rejected', failed)

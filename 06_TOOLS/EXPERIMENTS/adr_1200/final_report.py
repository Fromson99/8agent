"""Read-only result documentation; no model, product or active selection changes."""
from common import *
import re
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-supervisor-recovery-live';O.mkdir(parents=True,exist_ok=True)
r=read(RUN/'result.json');P=ART/'live/cm-007';d=read(P/'diagnosis.json');g=read(P/'gate.json');rec=read(P/'recovery-audit.json');review=read(P/'content-review.json');f=read(DES/'freeze-preflight-002.json')
assert not g['passed'] and not (ART/'live/cm-009/dispatch.json').exists()
assert rec['trigger_observed'] and rec['recovery_observed'] and rec['bylaw15_acquired'] and rec['bylaw15_cited']
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['scripts'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
receipt={'same_candidate466_after_run':True,'frozen_runner_scripts_unchanged':True,'main117_pointer_unchanged':True,'recovery_trigger_and_original_acquisition_verified':True,'full_cm007_passed':False,'cm009_executed':False,'new_model_calls_during_audit':0,'read_only_audit_scripts_added_after_dispatch':['recovery_audit.py','content_review.py','final_report.py'],'preparation_corrections':['Initial validate used --adr-dir instead of --path; original error log retained.','Inherited runner descriptive text and duplicate TestClient close fixed before dispatch; original freeze retained and corrected freeze-preflight-002 used. Product bytes unchanged.'],'known_nonblocking_observation':'wiki.projection_pending appeared as in1198; COMPLETE request and seven stage receipts passed. Wiki projection success is not claimed.'}
put(ART/'post-run-integrity.json',receipt)
observations={'result':r,'diagnosis':d,'recovery':rec,'content_review':review,'gate':g,'storage':read(P/'storage-audit.json'),'composition':read(P/'composition-audit.json'),'post_run':receipt}
put(O/'observations.json',observations)
summary=f"조사 복구는 실제로 동작했고,7번 전체 내용 기준은 미통과했다. 실제7번1회 {d['elapsed_seconds']:.3f}초·물리10회=예산차감10회·도구39회. 코스닥 시행세칙15 본문 확보·최종 인용 성공. 취득 의무의 조건화와15(5)의6개월 보유 사유 누락이 남아9번은 실행하지 않았다."
sections=[
 ('결정 요약',summary+' MAIN117 선택은 유지한다.'),
 ('문제와 변경 전 구조','1198은 감독이 FINISH를 RESEARCH로 바꾸면서 CONTINUE_TARGETED를 반환해 계약 오류 후 조사를 끝냈다.1199는 잘못된 지시의 거절 기록을 유지하면서 현재 메뉴·권한·원문·상태·예산으로 독립 검증한 비종료 조사 행동을 실행한다. 의무/조건 구분은 온톨로지 문서에만 반영했고 런타임 의미 교정은 구현하지 않았다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json), [실제 동결](artifacts/design/freeze-preflight-002.json). 원문/권한/예산/저장/요구검토/내용이 모두 통과해야009를 실행한다. 같은 실패 자동 재시험0. 결과 확인 뒤 제품·기준·자원 한도를 바꾸지 않았다.'),
 ('실험 설계','부모 ADR1199-experiment-v1/recovered와 byte동일466파일을 새동결했다. 활성MAIN117을 실행한 것이 아니라 격리후보 native /v1/rag/ask와 실제 서빙 전송기를 실행했다. 동일65문서 권한·같은 질문·빈runtime. 기준답변/필수좌표는 평가 전용이며 제품에 넣지 않았다. 최종ASSESS와 보완 실제 지시문7250자 동일.'),
 ('데이터·모델·재현성','MAIN117의 같은 데이터·프로필·Qwen3.8-27B·Parasail FP8 기본. Parasail 정상2회 뒤4291회→NearAI1회 전환·정상7회. 물리10=차감10.40/1024/1800·개별180초·출력상한없음·온톨로지OFF·자원기준 동일. 사용원문/스키마/모델/입출력/코드 해시는 동결과 raw/canonical에 결속했다.'),
 ('결과','실제 감독 응답에서 CONTINUE_TARGETED+RESEARCH 모순 재현. SUPERVISOR_DIRECTIVE_REJECTED와 SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED 각각1건; 추가모델보완0. RESEARCH APPLIED 뒤 주모델이 다시FINISH를 시도했으나 기존 두번째감독이 정상REDIRECT+READ를 반환하여 시행세칙15 본문을 읽었다. 이후 최종ASSESS·기존보완1회·서버조립을 거쳐3주장2273자·HTTP200READY·COMPLETE 저장. 감독2회 안에서 복구했으며 독립복구1회가 직접 모든 읽기를 끝냈다고 확대하지 않는다.'),
 ('사례별 오류 분석',review['reason']+'\n\n코스닥13(5) block192와 시행세칙15(5) block97의 정확한 원문이 최초·보완 최종 요청 모두에 전달됐다.15(5)의 최근3년 주선·상장후2년·투자주의환기/관리종목/상장폐지사유가 답변에서 빠졌다. 세칙15(4)의 사모·취득시기·미인수잔량 산입은 반영됐다. 두시장 수량·상한·기간, 국내소재외국지주회사 분류, 유가 국내/신청후 범위, 최초취득분모, 코스닥 재량 예외·유가3년 예외는 보존됐다.'),
 ('비용·지연·회수 규모',f"전체 {d['elapsed_seconds']:.3f}초 = 모델 전송 {d['model_transport_seconds']:.3f}초 + 기타 {d['elapsed_seconds']-d['model_transport_seconds']:.3f}초. 물리10·평가모델0·도구39. 원문257/입력521구간 대조, 불일치·권한위반0. 보고비용 {r['usage']['known_response_cost_usd']:.9f}달러;429사용량 미보고. UNKNOWN/기한만료/자원중단0·스왑증가0MiB·통신프로세스 회수. 관측후보→확보→인용 원장은 [원장](artifacts/run-001/retrieval-ledger.json)에 보존했다. 일반 속도·공급자 인과효과는 미인증."),
 ('해석','이번 실제 실행은 이전에 막혔던 지점에서 거절된 감독 지시와 별개로 조사를 재개해15조를 읽고 최종입력에 전달한 것을 검증했다. 이제 이 사례의 남은 결함은 원문 탐색보다 ASSESS의 의무/조건 분류와 읽은 위임 세부사항 반영에 있다. accepted-content-v1은 채택된 잘못된 내용까지 보존하므로 의미 교정 역할을 대신하지 않는다.'),
 ('한계와 일반화 가능 범위','알려진0071회이며009는 사전조건 미충족으로 미실행이다. 일반 법률 품질·최신 법령 효력·GENOS성능 인증이 아니다. 실제 감독출력과 후속판단은 이전1198과 다른 새생성이므로 통제A/B효과값을 산출하지 않는다. 최초 준비 validate 인자오류와 freeze정정 기록은 유지했다. wiki.projection_pending은1198에도 있었으며 이번 요청 COMPLETE와 별도로 남긴다.'),
 ('운영 결정·롤백 조건','작업제품·활성MAIN117·GENOS를 변경하지 않았다.1199후보는 자동선택하지 않는다. 이번에 코드 수정/MAIN승격/Git/메일/모델비교를 수행하지 않았으므로 운영 롤백은 필요하지 않다. 같은007/009 자동재요청0. 필요한 다음 수정은 일반적인 의무/적용조건 의미분리와 위임 세부사항의 주장 반영 검토이며 이번실험에서 구현한 것으로 주장하지 않는다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1200/setup.py, live.py cm-007, audit_result/audit_storage/prompt_audit/composition_audit/diagnose/recovery_audit/content_review/gate/aggregate/final_report.py. 실제실행은 freeze-preflight-002를 사용했다. 기존 dispatch 재실행은 거절한다. 평가 스크립트는 저장기록만 읽으며 새모델0. [전체 결과](artifacts/run-001/result.json)·[실제 답변](artifacts/live/cm-007/answer.txt)·[내용 검토](artifacts/live/cm-007/content-review.json).')]
p=ADR/'README.md';meta=p.read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Rejected',meta)
p.write_text('---'+meta+'---\n\n# 감독 조사 복구 실제007 및 조건부009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 요청 기록\n\n- [007](질문-001-cm-007.md): 복구·원문확보 통과, 내용미통과.\n- [009](질문-002-cm-009.md):007 전체조건 미충족으로 미실행.\n')
(O/'실험결과.txt').write_text('감독 조사 복구 실제 시험 결과\n\n'+'\n\n'.join(h+'\n'+v for h,v in sections)+'\n')
(O/'핵심결과.txt').write_text(summary+'\n\n'+review['reason']+'\n\nMAIN117 유지. 상세: 실험결과.txt / ADR1200.\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.parts];paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen recovery live experiment and read-only audit evidence','contains_raw_prompts_and_outputs':p.suffix=='.gz' and ('raw' in p.parts or 'canonical' in p.parts)} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print(summary)

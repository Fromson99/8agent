"""Post-run recovery/report only. Preserve the frozen runner and every failed record."""
from common import *
import sqlite3,re
P=ART/'live/review-whatif';F=read(DES/'freeze.json')
calls=[read(p) for p in sorted((P/'raw').glob('call-*/finished.json'))]
assert len(calls)==1 and calls[0]['status']=='responded' and calls[0]['http_status']==200
assert calls[0]['transport_diagnostics']['complete'] is True
put(P/'calls-reconciled.json',{'calls':calls,'authority':'Immutable per-call finished.json and full provider response; original calls.json remains started and is preserved.'})
journals=[]
for jp in sorted((P/'runtime').rglob('journal.sqlite')):
 db=sqlite3.connect(jp);db.row_factory=sqlite3.Row
 tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 row={'path':str(jp.relative_to(ROOT))}
 for table in ('run','budget','model_attempt'):
  if table in tables:row[table]=[{k:v for k,v in dict(r).items() if k in ('status','phase','model_reserved','attempt_id','run_id')} for r in db.execute('SELECT * FROM '+table)]
 db.close();journals.append(row)
assert sum(x['status']=='UNKNOWN' for j in journals for x in j.get('model_attempt',[]))==1
put(P/'fresh-process-failure-audit.json',{'journals':journals,'physical_unknown':0,'product_unknown':1,'new_model_calls':0})
turn=read(P/'initial-turn.json')
result={'status':'NOT_PASSED','failure_class':'EXPERIMENT_OBSERVER_WRITE_ONCE_VIOLATION',
 'physical_calls':1,'physical_unknown':0,'product_unknown':1,'http_status':502,
 'reported_cost_usd':calls[0]['usage']['cost'],'model_seconds':calls[0]['seconds'],
 'input_tokens':calls[0]['usage']['prompt_tokens'],'output_tokens':calls[0]['usage']['completion_tokens'],
 'initial_claims':0,'semantic_branches_attempted':0,'extra_model_calls_on_duplicate':turn['duplicate']['extra_model_calls'],
 'resource_stop':(P/'resource-stop.json').exists(),'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256'],
 'code_files':len(F['files']),'changed_code':[n for n,h in F['files'].items() if sha(ROOT/F['code_root']/n)!=h],
 'changed_inputs':[n for n,h in F['inputs'].items() if sha(ROOT/n)!=h],
 'changed_frozen_scripts':[n for n,h in F['scripts'].items() if sha(ROOT/n)!=h],
 'quality_certified':False,'no_original_journal_replay':True,
 'cause':'Observer wrote calls.json before sending, then attempted write_summary on the same path in finally. Immutable writer rejected overwrite after complete HTTP200; adapter recorded UNKNOWN. Outer finalizer repeated the same invalid write and exited1.',
 'recovery':'No rerun or journal change. Full response/cost recovered from immutable call receipt, fresh-process journal audit. New ADR1297 changes only experiment observer and starts a new isolated baseline.',
 'cleanup_note':'Runner exited1 before its explicit client/guard close. Process is gone; no store_closed assertion. Resource gzip may have an incomplete final trailer and is preserved unchanged.'}
put(P/'result.json',result);put(RUN/'result.json',result)
put(P/'cleanup.json',{'store_closed':False,'process_exited':True,'exit_code':1,'explicit_cleanup_completed':False,'posthoc_receipt':True,'reason':result['cleanup_note']})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':1,'reported_cost_usd':result['reported_cost_usd'],'input_tokens':result['input_tokens'],'output_tokens':result['output_tokens']},
 latency={'model_seconds':result['model_seconds']},error_taxonomy=[{'type':'other','detail':result['cause']}])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '미통과. 첫 실제 응답은 정상 HTTP200/stop였으나 실험 관측 기록기의 불변 파일 재작성으로 native API502·제품 UNKNOWN1이 됐다. 최종 답변·세 가정 미도달. MAIN134 유지.',
 'MAIN134의 현재 가정/기준 사건 이력 분리와 미확인ID 검사를 실제 모델로 확인하려 했다. 선택 서빙515파일이 완료1292/후보539파일과 정확히 일치했다. 신규 변경은 실험 관측 코드뿐이다.',
 '[사전 기준](artifacts/design/criteria.json). 기준 사건과 저액735000/고액1725000/규칙한도2450000 세 분기, 원문/권한/전송/저장 보존·미확인 유지. 실행 후 기준 변경0.',
 '합성3조문·기존 승인 온톨로지·격리 SQLite·native API·Qwen 실제1회. 동일 요청 재조회0추가 호출. 첫 가설 단계 이전 중단, 인과 A/B 아님.',
 'Qwen3.8-27b/Parasail FP8, 출력 상한 없음. 코드539/전송기/정책/입력/실행기 동결. 실제 payload·정상 전체 원응답·사용량·시작/종료 영수증 보존. ./artifacts/design/freeze.json.',
 json.dumps(result,ensure_ascii=False,indent=2),
 'write_summary는 기존 파일 재작성을 거절한다. 새 관측 코드가 calls.json을 시작에 쓴 뒤 완료와 최종화에서 다시 쓰며 AssertionError를 냈다. 첫 종료 영수증은 responded/HTTP200/complete=true이고 정상 응답과 비용이 남아 있어 공급자 응답불명과 구분한다. 제품 journal의 UNKNOWN/FAILED는 그대로 보존했다.',
 f'실제1호출·{result["model_seconds"]:.3f}초·보고${result["reported_cost_usd"]:.8f}, 입력{result["input_tokens"]}/출력{result["output_tokens"]}. 재조회 모델0. 회수 정책 변경0·검색 성능 비교 없음. 자원 감시 중단0이나 끝 자원기록은 프로세스 예외로 불완전할 수 있다.',
 '이번 중단은 모델 답변의 법률 의미나 MAIN134 제품 수정의 실패를 판정할 자료가 아니다. 실험기 자체 실패다. 정상 원응답을 사후 주입하여 실행을 이어가지 않았다.',
 '기준 최종검토·가정 계산·표시 분리·ID 보완·새 답변 저장을 실제 확인하지 못했다. 다른 세션의 ADR1296이 실행 중인 것을 종료 후 관측하여 동시 실행이 없었다고 주장하지 않는다. 새 실험은 시작 직전 다른 실행 종료를 확인한다.',
 '제품/MAIN/Gold/Oracle/운영DDL/Git push/메일/현장변경0. 실패 원본·runner·journal 보존. 동일 셀 재실행0. 후속 ADR1297은 관측기만 수정한 별도 실험이며 실제 외부 호출 전에 세 로컬 경로를 검증한다.',
 '이미 실행한 live.py를 재실행하지 않는다. prepare→freeze→preflight→live(실패) 원본 유지. close_observer_failure.py는 사후 읽기/새 보고서만 생성한다. runtime은 전체 파일 SHA 대조 후 무손실 압축; 후속은 ADR1297.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
p.write_text('---'+front+'---\n\n# ADR1295 MAIN134 실험 관측기 실패 보존\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified. 실제1호출; 물리응답 정상, 관측기 오류. 시각/코드/정책/입력은 design/freeze.json과 raw/call-001.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','외부 정답/채점모델0. 동결 criteria의 합성 의미 기준, 미도달이므로 의미판정0.'),('제품 입력을 구성한 원값','design/source.json/ontology-input.json/cases.json 및 raw/call-001/request.json.gz 전체 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 비교 없음, 변경0. 검색 단계 미완료.'),('제품 모델 호출 — run·arm별 실제 원문','실제 system/user/schema와 원응답: raw/call-001/*.json.gz. 전체 내용 SHA와 저장 SHA는 옆 reference에 보존.'),('중간 LLM 호출 — router/compiler/verifier/repair','request-entry1회; 후속·보완·채점0. 원응답을 제품에 다시 주입하지 않음.'),('채점 호출과 반복 판정','0. per-call 종료/원응답과 새 프로세스 journal 대조만 수행. 원래 calls.json의 started는 변경하지 않고 calls-reconciled.json에 정정 근거 보존.'),('사례 최종 판정','NOT_PASSED: 관측기 불변 파일 재작성 오류. 모델 의미/제품 표시 기능은 미판정. 후속 ADR1297 별도.')]
(ADR/'실험/질문-001-review-whatif.md').write_text('# 실패 보존\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-main134-display-live';report.mkdir(exist_ok=True)
(report/'초기실험_기록기실패_보존.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
print(json.dumps({k:result[k] for k in ('status','physical_calls','physical_unknown','product_unknown','reported_cost_usd')},ensure_ascii=False))

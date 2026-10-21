"""Measured synthetic canonical-unit visibility ledger, never a product input."""
from pathlib import Path
import json,hashlib,gzip,sys,tempfile,subprocess,os,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0799-workflow-handoff-task-context';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');sys.path[:0]=[str(R/f['code_root']/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS')];sys.dont_write_bytecode=True
from test_search_selection import metadata_generation
from lawrag.pipeline.search_selection import plan,activate
from semantic_runtime.storage import Store
m=read(A/'실험/manifest.json');plans=m['design']['retrieval_stage_plan']['stages_by_arm']
b=read(A/'artifacts/replay/baseline.json')['read'];c=read(A/'artifacts/replay/connected.json')['selected']
b=sorted(b,key=canon);c=sorted(c,key=canon)
G=c;arms=[];metrics={k:{} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}
for arm,selected in [('baseline',b),('connected',c)]:
 before=[];stages=[]
 for i,after in enumerate([b,selected,selected]):
  bm={canon(x):x for x in before};am={canon(x):x for x in after};gm={canon(x):x for x in G};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())];gb=[x for x in before if x in G];ga=[x for x in after if x in G];gain=[x for x in added if x in G];loss=[x for x in discard if x in G];reason='Not adopted in committed child claims; retained in child audit'
  stages.append({**plans[arm][i],'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discard,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in discard],'discard_reason_counts':{reason:len(discard)} if discard else {},'gold_total':len(G),'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'golden_recall':len(ga)/len(G),'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':x,'reason':reason} for x in loss],'gold_after_identities':ga});before=after
 case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':'K01','gold_total':len(G),'gold_identities':G,'stages':stages};arms.append({'arm_id':arm,'declared_stage_ids':[x['stage_id'] for x in plans[arm]],'cases':[case],'aggregate':{'cases':1,'presented_total':len(selected),'gold_total':len(G)}})
 metrics['before_filter'][arm]=len(b);metrics['after_filter'][arm]=len(selected)
 for k in ('presented_total','presented_mean','presented_p50','presented_p95'):metrics[k][arm]=len(selected)
 metrics['golden_recall'][arm]=1;metrics['selectivity'][arm]=len(selected)/len(b)
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'known_recorded_replay':True,'legal_quality_gate':False,'presentation_means':'handoff pool consists of exact already-read canonical article roots; gold means committed claim dependency, not legal correctness'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();p=A/'artifacts/run-001/retrieval-ledger.json.gz';p.write_bytes(gzip.compress(canon(ledger).encode(),mtime=0))
m['retrieval_accounting'].update(changed=True,corpus_total=len(b),not_applicable_reason=None,**metrics,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(p.relative_to(R)),'sha256':sha(p),'not_applicable_reason':None})
headings=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정']
body=['K01은 알려진 ADR0795 자식 반환 기록의 전달 경계 재생이다. 의미 정확도 평가가 아니다.','대사: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?','정답률 대신 이미 확정된 claim의 원문 의존성을 모두 보존하는지만 확인한다. 제품 실행 후 기록에만 결합한다.','같은 원문 세대와 동일한 자식 envelope. 기준 MAIN73 실제 export 함수와 후보 export 함수.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json.gz. corpus는 이 전달 경계의 읽은 조문 집합이다.','재생 모델 호출0. 별도 실제 Qwen 호출6건 원문은 ../artifacts/live/raw.','INTAKE1, 자식 진입/수정4, BASIS1. 실제 새 질문의 인용 오류로 자식 조사 실패.','평가 모델 호출 없음.','전달 재생94→16 근거,128976→26301자. 실제 실행은 자식 질문 인용 실패로 비교0행이므로 후보를 기각한다.']
p=A/'실험/질문-001-K01.md';p.write_text('\n\n'.join('## '+h+'\n\n'+v for h,v in zip(headings,body))+'\n');m['questions']=[{'number':1,'case_id':'K01','file':p.name,'sha256':sha(p)}];put(A/'실험/manifest.json',m);print(metrics)

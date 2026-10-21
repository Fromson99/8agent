"""Read-only E2E audit and experiment report. Never calls a model."""
from pathlib import Path
import gzip
import hashlib
import json
import os
import sqlite3
import statistics
import sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0959-legal-knowledge-e2e-wiring';D=A/'artifacts/design';O=A/'artifacts/run-001'
sys.dont_write_bytecode=True;os.environ['GENOS_RESIDENT_DATA']='off'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0959/integrated/revisions/rev-001/snapshot'
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.storage import Store

read=lambda p:json.loads(p.read_text())
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
hashtext=lambda s:hashlib.sha256(s.encode()).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def connect(p):
 d=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
def offered(value):
 found=set()
 if isinstance(value,dict):
  if value.get('source_id') and isinstance(value.get('text'),str) and value['text']:found.add(value['source_id'])
  for v in value.values():found.update(offered(v))
 elif isinstance(value,list):
  for v in value:found.update(offered(v))
 return found

cases=read(D/'cases.json');m=read(A/'실험/manifest.json')
source=Store(R/read(D/'selected-release.json')['data_path'])
nav=connect(source.path/'navigation/navigation.sqlite');cache={}
scope=read(O/cases[0]['case_id']/'request.json')['document_ids']
def lookup(sid):
 if sid not in cache:
  r=nav.execute('select json from source where id=?',(sid,)).fetchone()
  cache[sid]=json.loads(r[0]) if r else None
 return cache[sid]
def identities(sids):
 out={}
 for sid in sids:
  s=lookup(sid)
  if s and str(s.get('unit_id')).isdigit():
   value={'doc_id':s['document_id'],'node':int(s['unit_id'])};out[canon(value)]=value
 return [out[k] for k in sorted(out)]

marks=','.join('?' for _ in scope)
corpus=identities(r['id'] for r in nav.execute("select id from source where json_extract(json,'$.document_id') in ("+marks+")",scope))
journals={}
for p in (O/'runtime').rglob('journal.sqlite'):
 db=connect(p);request=json.loads(db.execute('select request_json from run').fetchone()[0]);db.close()
 for c in cases:
  if request.get('question')==c['question']:journals.setdefault(c['case_id'],[]).append(p)
rows=[];ledger_cases=[];audits=[]
for number,c in enumerate(cases,1):
 path=O/c['case_id'];result=read(path/'result.json')
 response=read(path/'response.json') if (path/'response.json').exists() else {'http_status':500,'body':{}}
 body=response['body']
 paths=journals.get(c['case_id'],[])
 journal=next((p for p in paths if p.parent.name==body.get('run_id')),paths[0] if paths else None)
 checks=[];acquired=set();knowledge_events=[]
 if journal:
  db=connect(journal)
  for e in db.execute('select * from evidence_unit'):
   acquired.add(e['source_id'])
   spans=list(db.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],)))
   valid=bool(spans)
   for s in spans:
    raw=source.source(e['document_id'],s['block_id'])
    valid=valid and raw['source_artifact_sha256']==e['source_artifact_hash'] and hashtext(raw['text'])==s['block_hash'] and raw['text'][s['start_cp']:s['end_cp']]==s['text'] and hashtext(s['text'])==s['span_hash']
   valid=valid and hashtext('\n'.join(s['text'] for s in spans))==e['text_hash']
   checks.append({'evidence_id':e['evidence_id'],'exact_original_match':bool(valid),'span_count':len(spans)})
  knowledge_events=[json.loads(r[0]) for r in db.execute("select payload_json from event where kind='LEGAL_KNOWLEDGE_BOUND'")]
  db.close()
 presented=set();guidance_calls=[]
 for p in sorted((path/'provider').glob('call-*/request.json')):
  value=read(p);assert value['model']=='qwen/qwen3.8-27b'
  for message in value['messages']:
   try:v=json.loads(message.get('content',''))
   except (ValueError,TypeError):continue
   presented.update(offered(v))
   if 'legal_review_guidance' in canon(v):guidance_calls.append(p.parent.name)
 assert all(lookup(s)['document_id'] in scope for s in presented if lookup(s))
 cited={s for cl in body.get('answer',{}).get('claims',[]) for s in cl.get('source_ids',[])}
 audit={'case_id':c['case_id'],'journal':str(journal.relative_to(R)) if journal else None,
        'auxiliary_journals':[str(p.relative_to(R)) for p in paths if p!=journal],
        'evidence_checks':checks,'original_mismatches':sum(not r['exact_original_match'] for r in checks),
        'knowledge_events':knowledge_events,'guidance_input_calls':guidance_calls,
        'acquired':identities(acquired),'presented':identities(presented),'cited':identities(cited),
        'model_calls':result['model_calls'],'http_status':response['http_status'],'status':result['status']}
 put(path/'audit.json',audit);audits.append(audit)
 before=[];stages=[]
 for plan,after,reason in zip(m['design']['retrieval_stage_plan']['stages_by_arm']['integrated'],[corpus,audit['acquired'],audit['presented']],['Approved source catalogue','No source acquisition observed','No text-bearing source ID observed in model input']):
  bm={canon(v):v for v in before};am={canon(v):v for v in after}
  added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
  stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
   'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
   'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
   'discard_receipts':[{'identity':v,'reason':reason} for v in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},
   'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
   'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
  before=after
 ledger_cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
  'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'integrated','case_id':c['case_id'],'gold_total':0,'gold_identities':[],'stages':stages})
 usage={k:sum(u.get(k,0) or 0 for u in result['usage']) for k in ('input_tokens','output_tokens','cost_usd','seconds')}
 row={'case_id':c['case_id'],'status':result['status'],'http_status':response['http_status'],'seconds':result['seconds'],
  'calls':result['model_calls'],'coverage':body.get('assembly',{}).get('term_agent',{}).get('answer_coverage'),
  'guidance_calls':len(guidance_calls),'evidence_checks':len(checks),'source_mismatches':audit['original_mismatches'],
  'knowledge_journal_events':len(knowledge_events),'usage':usage,'error':result.get('error')}
 rows.append(row)
 q=A/'실험'/f"질문-{number:03d}-{c['case_id']}.md"
 q.write_text('\n\n'.join(['# '+c['case_id'],'## 1. 실행 메타','ADR0959 / run-001 / integrated / 실제 로컬 API / Qwen3.8 Parasail FP8 / reasoning none.',
  '## 2. 사용자 질문 원문',c['question'],'주제 대응 '+c['topic_reference']+'의 기존 공개 합성 질문. 원본 risk_cm 동일 문항 평가 아님.',
  '## 3. 기준답변 — 채점 전용, 제품 입력 비공개','기준답변을 주입하거나 법률 정답 채점을 하지 않았다.',
  '## 4. 제품 입력을 구성한 원값','artifacts/design의 cases·seeds·freeze와 run-001/management.json에 게시·버전·원문 해시. 실제 제품 입력은 해당 사례 canonical-*.json.gz 및 provider/call-*/request.json.',
  '### 회수·탈락 단계 원장 — run·arm별','artifacts/retrieval-ledger.json.gz의 source→acquired→presented. 최종 인용 좌표는 사례 audit.json. 집계 집합이며 실행 순서의 재구성 아님.',
  '## 5. 제품 모델 호출 — run·arm별 실제 원문','모든 모델 입출력·스키마·사용량은 해당 사례 provider/에 exact payload로 보존. 답변: response.json. 숨은 judge 없음.',
  '## 6. 중간 LLM 호출 — router/compiler/verifier/repair','같은 provider/ 및 canonical-*에 기존 해석·조사·평가·답변의 중간 호출을 모두 보존. 지식 조회 LLM0회.',
  '## 7. 채점 호출과 반복 판정','법률 채점0회. 각 사례1회, 동일 요청 재전송은 추가 모델 호출 없는 멱등 검증.',
  '## 8. 사례 최종 판정','```json\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n```',body.get('answer',{}).get('text','답변 미발행')])+'\n')

nav.close();source.close()
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[{'arm_id':'integrated','declared_stage_ids':['source','acquired','presented'],'cases':ledger_cases,
 'aggregate':{'cases':3,'executed_cases':3,'skipped_cases':0,'presented_total':sum(len(a['presented']) for a in audits),'gold_total':0}}]}],
 'audit':{'semantics':'Sets observed after execution, no legal correctness or recall claim; source scope and original span hashes checked.'}}
ledger['artifact_sha256']=hashtext(canon(ledger));lp=A/'artifacts/retrieval-ledger.json.gz'
with gzip.open(lp,'wt',encoding='utf8') as f:f.write(canon(ledger))
counts=[len(a['presented']) for a in audits];total=sum(counts)
m['retrieval_accounting'].update(changed=False,corpus_total=len(corpus),before_filter=len(corpus),after_filter=sum(len(a['acquired']) for a in audits),
 presented_total=total,presented_mean=total/3,presented_p50=statistics.median(counts),presented_p95=max(counts),golden_recall=None,selectivity=total/3/len(corpus),not_applicable_reason='Existing retrieval algorithm and source generation unchanged; new advisory input was used so actual sets were measured. No approved gold; recall is null.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str(lp.relative_to(R)),sha256=sha(lp),not_applicable_reason=None)
m['runs'][0].update(status='complete',sha256=sha(O/'summary.json'))
usage={k:sum(r['usage'][k] for r in rows) for k in ('input_tokens','output_tokens','cost_usd','seconds')}
m['results'].update(status='complete',by_arm={'integrated':{'total_count':3,'correct_count':None,'correctness_reason':'No approved gold/semantic grading',
 'e2e_pass_count':sum(r['status'].startswith('PASS') for r in rows),
 'limited_answer_count':sum(r['status']=='PASS_LIMITED' for r in rows)}},comparisons=[],judge_disagreements=0,usage=usage,
 latency={'request_p50':statistics.median(r['seconds'] for r in rows),'request_p95':max(r['seconds'] for r in rows),'n':3},
 error_taxonomy=[{'case_id':r['case_id'],'type':'other','reason':r['error']} for r in rows if r['error']])
put(A/'실험/manifest.json',m)
put(A/'artifacts/audit-summary.json',{'cases':rows,'usage':usage,'source_checks':sum(r['evidence_checks'] for r in rows),'source_mismatches':sum(r['source_mismatches'] for r in rows),
 'legal_correctness_graded':False,'oracle_verified':False,'genos_verified':False,'main_changed':False})
table='\n'.join(f"| {r['case_id']} | {r['status']} | {r['calls']} | {r['seconds']:.1f} | {r['coverage']} |" for r in rows)
front=(A/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약','실제 관리 API 게시·RAG 답변·지식 버전·중복 확인 결과를 기록했다. Proposed / in_sample / decision_eligible=false. MAIN96 유지.'),
 ('문제와 변경 전 구조','ADR0958의 첫 실제 실행은 429 미수락2건과 표시 모듈 누락으로 API 응답이 실패했다. 그18물리호출과 실패 원본은 보존했다. 이번 후속 후보는 표시 의존성을 포함하고 429를 기존 gateway의 한도 안에서 처리하며, 원문을 보존한 제한 답변도 별도 상태로 확인한다.'),
 ('가설과 사전 판정 기준',read(D/'criteria.json')['hypothesis']+'\n\n'+read(D/'criteria.json')['success']+'\n\n'+read(D/'criteria.json')['failure']),
 ('실험 설계','단일 integrated arm, 기존 공개 합성 주제3건 각1회 순차. 453개 코드·계약 동결. 공개 지식 정의의 exact digest를 주입해 외부 입력을 제한. 기존 검색·원문 읽기·판단 핵심과 추가 지식 LLM0회를 유지한다. PASS_LIMITED는 원문 전달·버전·저널 연결 통과이며 법률 결론 완성은 아니다.'),
 ('데이터·모델·재현성','현재 선택된 원문 세대(1,547문서)에서 승인 공개·risk_team 교집합28문서. 원문·색인 복사 없이 읽기 전용 공유. 검토 지식 DB만 로컬 E2E 전용 SQLite, 운영 Oracle 검증 아님. Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. freeze.json 및 candidate rev-001.'),
 ('결과','| 사례 | E2E | 호출 | 초 | 답변 범위 |\n|---|---|---:|---:|---|\n'+table),
 ('사례별 오류 분석','각 사례 audit.json과 response.json의 미확인·부분 답변을 보존했다. E2E PASS는 연결 성공이며 법률 정답 판정이 아니다. 오류와 모델 원응답은 삭제하지 않았다.'),
 ('비용·지연·회수 규모',f"실제 {sum(r['calls'] for r in rows)}회. 입력 {usage['input_tokens']:,} / 출력 {usage['output_tokens']:,}, 공급자 USD {usage['cost_usd']:.8f}. p50 {m['results']['latency']['request_p50']:.1f}초. 원문 span 묶음 {sum(r['evidence_checks'] for r in rows)}건, 불일치 {sum(r['source_mismatches'] for r in rows)}건. 회수·제시 집합은 retrieval-ledger.json.gz. gold 미승인으로 recall 미측정."),
 ('해석','게시 지식이 기존 해석·조사 입력과 답변·저널에 연결되는지 확인하는 실행이다. 속도 개선이나 검색·법률 판단 품질 향상을 비교하지 않았다.'),
 ('한계와 일반화 가능 범위','공개 합성3건·로컬 외부 모델·분리 검증 저장소. 전체 risk_cm 원문105건, 사내 인증, Oracle 트랜잭션, GENOS 내부 모델은 이번 검증 범위 밖이다. 위키/숏컷 실자료 의존 연결은 기존 계약 검사만 있으며 이 E2E는 METHOD 게시를 사용했다.'),
 ('운영 결정·롤백 조건','활성 MAIN·원문 세대·운영 권한·Oracle·GENOS·Git 변경 없음. 실행 호스트를 종료하면 기존 서비스에 영향이 없다. 중단된 모델 요청은 새 예산으로 자동 재실행하지 않는다. 후보 검증 결과를 운영 자동 승격하지 않는다.'),
 ('재현 명령','`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0959/e2e.py check` (모델0), `run` (완료 사례 재호출 없이 결과 재사용), `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0959/serve.py` (127.0.0.1:8768/e2e/login). 화면은 별도 작업 DB를 편집하고 완료 실행 기록을 읽으며 모델 호출을 차단한다. 관리 화면은 같은 인증 토큰으로 연결. 신규 모델 실행/후속 후보는 새 ADR에서 동결. 전역 graph 기존 오류는 별도 기록.')]
(A/'README.md').write_text('---'+front+'---\n\n# 검토 지식 E2E\n\n'+'\n\n'.join('## '+str(i)+'. '+title+'\n\n'+text for i,(title,text) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 실제 실행 질문\n\n'+ '\n'.join(f"- [{c['case_id']}](질문-{i:03d}-{c['case_id']}.md)" for i,c in enumerate(cases,1))+'\n')
print(json.dumps({'cases':[{k:v for k,v in r.items() if k!='usage'} for r in rows],'usage':usage},ensure_ascii=False))

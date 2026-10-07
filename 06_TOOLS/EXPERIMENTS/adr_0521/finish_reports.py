"""Complete descriptive records without promoting either candidate."""
import json,hashlib,sqlite3,gc,statistics,math,importlib.util,sys
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
from adr_structure import _canonical_value_sha256
spec=importlib.util.spec_from_file_location('ledger_helpers',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def read(p):return json.loads(p.read_text())
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  while c:=f.read(8388608):d.update(c)
 return d.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def finish(number):
 suffix='shared-reference-root-workflow' if number==521 else 'scoped-reference-returns';arm='integrated' if number==521 else 'guarded'
 A=R/f'04_EXPERIMENTS/ADR/ADR-{number:04}-{suffix}';M=A/'실험/manifest.json';m=read(M);C=R/f'02_BACKEND/lawrag/research/candidates/adr_{number:04}/{arm}'
 cases={};coords={};gold={};inputs={};rootsets={};aftersets={};rows=[]
 if number==521:
  F=A/'artifacts/diagnostic-freeze.json';f=read(F);index=read(A/'artifacts/run-001/results.json');P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
  db=sqlite3.connect('file:'+str(Path(f['generation'])/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
  coords={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(uid).isdigit()};db.close()
  goldrows={x['case_id']:x for x in read(P/'gold-cases.json')['cases']};corpus=len({h.key(v) for sid,v in coords.items() if v['doc_id'] in f['public_scope_document_ids']})
  for c in f['cases']:
   cid=c['case_id'];v=read(R/index['cases'][cid]['path']);g=v['graph'];old=read(R/c['historical_raw'])
   rootsets[cid]={'baseline':old['selected_for_read'],arm:[r['extent']['source_id'] for r in g['roots']]}
   aftersets[cid]={'baseline':{'closure':old['read_complete'],'preserved':old['prepared_complete']},arm:{'closure':g['source_ids'],'preserved':g['source_ids']}}
   gold[cid]=goldrows[cid]['decisive_source_ids'];inputs[cid]=c['question_input'];cases[cid]=index['cases'][cid]
   rows.append({'case_id':cid,'roots':len(g['roots']),'sources':len(g['source_ids']),'states':len(g['states']),'pending':len(g['pending']),'status':g['status'],'seconds':g['seconds'],'artifact_bytes':(R/cases[cid]['path']).stat().st_size})
   print('reported',cid,flush=True);del v,g,old;gc.collect()
  decision='Deferred: complete generation and integration built; six broad-root replays remain PARTIAL; reciprocal return scope widening reproduced. Correction is isolated in ADR0522.'
  limitation='Six hash-selected historical cases; no new model selection or model delivery. Historical baseline and graph replay differ in execution. Full article recall is not exact provision recall or answer quality. ADR0521 is superseded by the guarded proposal for runtime use.'
 else:
  F=A/'artifacts/design-freeze.json';corpus=6
  for q in m['questions']:
   cid=q['case_id'];rootsets[cid]={};aftersets[cid]={};cases[cid]={};inputs[cid]={'fixture':cid,'question':'명시 DB 관계를 따라가되 동일 관계 왕복으로 제10호를 조 전체로 넓히지 말 것'}
   for which in ('baseline',arm):
    p=A/'artifacts/run-001'/which/(cid+'.json');v=read(p);g=v['graph'];coords.update(v['source_coordinates']);cases[cid][which]={'path':str(p.relative_to(R)),'sha256':sha(p)}
    rootsets[cid][which]=[r['extent']['source_id'] for r in g['roots']];aftersets[cid][which]={'closure':g['source_ids'],'preserved':g['source_ids']}
    rows.append({'case_id':cid,'arm':which,'sources':len(g['source_ids']),'status':g['status'],'seconds':g['seconds'],'scope_return_suppressions':sum(bool(e.get('suppressed_return_source_ids')) for e in g['edges'])})
   gold[cid]=list('abcdef') if cid in ('independent-root','multi-target') else list('abcef')
  index={'cases':cases,'completed':True,'fixture_only':True};write(A/'artifacts/run-001/results.json',index)
  decision='Deferred for MAIN: scoped reciprocal returns corrected; 103 deterministic contract/regression checks passed. No out-of-sample legal retrieval or answer-quality certification.'
  limitation='Four synthetic scenarios, including repeated narrow-return topology for the recursive-link contract. Same-reference immediate returns are suppressed; different explicit paths and independent roots can still reach a wider scope. Not a bound on real corpus closure size. Real model root judgment, new search and answer performance are unmeasured.'
  frozen=read(F);m['design'].update(hypothesis=frozen['policy'],primary_metric='Scope leak count and retained valid endpoints on fixed fixtures',success_criteria=frozen['success'],failure_criteria='Narrow scope widened by reciprocal return; independent root or other endpoints lost',criteria_frozen_before_run=True)
 plans=[{'stage_id':'roots','kind':'source','parent_stage_ids':[]},{'stage_id':'closure','kind':'expand','parent_stage_ids':['roots']},{'stage_id':'preserved','kind':'present','parent_stage_ids':['closure']}]
 m['design']['retrieval_stage_plan']={'schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'stages_by_arm':{a:plans for a in ('baseline',arm)}}
 arms=[];totals={}
 for which in ('baseline',arm):
  records=[]
  for cid in cases:
   g=h.ordered(coords[s] for s in gold[cid] if s in coords);prev=[];stages=[]
   pools={'roots':rootsets[cid][which],**aftersets[cid][which]}
   for plan in plans:
    after=h.ordered(coords[s] for s in pools[plan['stage_id']] if s in coords);ak={h.key(x) for x in after};pk={h.key(x) for x in prev};dropped=[x for x in prev if h.key(x) not in ak]
    stage=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in pk],dropped,{h.key(x):'historical_not_prepared' for x in dropped},g);stages.append(stage);prev=stage['after']
   records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':which,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages})
  counts=sorted(c['stages'][-1]['after_count'] for c in records);obt=sum(c['stages'][-1]['gold_after'] for c in records);ng=sum(c['gold_total'] for c in records)
  arms.append({'arm_id':which,'declared_stage_ids':[p['stage_id'] for p in plans],'cases':records,'aggregate':{'presented_total':sum(counts),'gold_after':obt,'gold_total':ng}})
  totals[which]={'cases':len(records),'gold_obtained':obt,'gold_total':ng,'golden_recall':obt/ng,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':counts[math.ceil(.95*len(counts))-1],'selectivity':statistics.mean(counts)/corpus,'before_filter':sum(c['stages'][0]['after_count'] for c in records),'after_filter':sum(counts)}
 ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'presentation':'Preserved original sources, not LLM input; model-delivered=0','limitation':limitation}}
 ledger['artifact_sha256']=_canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 accounting={'changed':True,'corpus_total':corpus,'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'summary_run_id':'run-001','artifact_path':str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),'sha256':sha(A/'artifacts/retrieval-stage-ledger.json'),'not_applicable_reason':None}}
 for key in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):accounting[key]={a:t[key] for a,t in totals.items()}
 m['retrieval_accounting']=accounting
 rev=read(C/'candidate.json')['revisions'][-1];runner=R/f'06_TOOLS/EXPERIMENTS/adr_{number:04}/bootstrap.py'
 m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'candidate_snapshot','reason':None,'production_paths_modified_before_decision':False,'runtime_import_allowed':False,'production_registry_registered':False,'main_wiring_unchanged':True,'candidates':[{'candidate_id':arm,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]}
 m['lineage']['hypothesis_delta']=m['design']['hypothesis']
 for a in m['design']['arms']:
  a['changes']='Historical ADR0513 acquisition replay' if number==521 and a['id']=='baseline' else ('ADR0521 frozen proposal on identical synthetic inputs' if a['id']=='baseline' else m['design']['hypothesis'])
  a['controls']='Fixed source/fixture inputs and no model calls; see limitations'
 m['runs'][0].update(purpose='audit',status='complete',artifact_path=str((A/'artifacts/run-001/results.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/results.json'))
 m['dataset'].update(name='Six hash-selected historical source acquisitions' if number==521 else 'Explicit reciprocal-scope synthetic fixtures',version='20260922-v1',frozen_source=str(F.relative_to(R)),sha256=sha(F),legal_version_checked=False,reference_version_checked=False)
 m['results'].update(status='complete',by_arm=totals,comparisons=[{'baseline':'baseline','candidate':arm,'interpretation':decision}],judge_disagreements=None,usage={'physical_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'raw_rows':rows},error_taxonomy=['remaining_frontier','reciprocal_scope_widening'] if number==521 else ['model_quality_unmeasured','real_corpus_size_unmeasured'])
 write(M,m);summary={'decision':decision,'limitations':limitation,'totals':totals,'rows':rows,'live_model_calls':0,'model_delivered':0,'active_changed':False,'quality_certified':False};write(A/'artifacts/summary.json',summary)
 original=(A/'README.md').read_text();front=original.split('---',2)[1].replace('status: Proposed','status: Deferred');heads=[l for l in original.splitlines() if l.startswith('## ')];body=[decision,'원문 보존 범위와 탐색 범위를 분리한다. DB 관계, 명시 누락 조사, 독립 검색을 서로 다른 이동 근거로 기록한다.',m['design']['hypothesis']+'\n\n성공 기준: '+m['design']['success_criteria'],'입력 동결, 계약 검사, 원문 기준 좌표 감사. 표본과 비교 한계는 아래에 명시한다.','모델 호출 0회. frozen input: '+str(F.relative_to(R))+'\nSHA256: '+sha(F),'```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```','실제 원시 결과와 실패 기록은 artifacts 및 각 질문 파일에 보존했다.','LLM 제시 0건. 표의 presented는 로컬 보존 원문이다. 정확한 단계·추가·탈락 좌표: artifacts/retrieval-stage-ledger.json.',limitation,'법률적 충분성·새 질문 일반화·실제 모델 판단을 인증하지 않는다. 90/90을 필수로 강제하지 않는다.','MAIN·활성 DB 포인터·GENOS 배포 변경 없음. 현재 dispatcher는 품질 우회를 요구하며, 이 실험에 재사용하지 않았다. 선택된 기존 릴리스를 유지한다.','```bash\n.venv/bin/python '+str(runner.relative_to(R))+'\n```\n완료 결과 재평가는 새 ADR을 사용한다. 원시 hash 목록: artifacts/manifest.json.']
 (A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' — 구현 및 검증 기록\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(heads,body))+'\n')
 links=[]
 for q in m['questions']:
  cid=q['case_id'];path=A/'실험'/q['file'];heads=[l for l in path.read_text().splitlines() if l.startswith('## ')]
  blocks=[f"- ADR: `{m['adr_id']}`\n- case ID: `{cid}`\n- run ID: `run-001`\n- 원본 상태: `exact`\n- 모델 호출: 없음",'```json\n'+json.dumps(inputs[cid],ensure_ascii=False,indent=2)+'\n```','채점 전용 원문 ID: '+json.dumps(gold[cid])+'\n실행 완료 후 결합; 실제 답변 기준이 아님.','원시 경로와 SHA256:\n```json\n'+json.dumps(cases[cid],ensure_ascii=False,indent=2)+'\n```\n전체 단계 원장: artifacts/retrieval-stage-ledger.json.','제품 모델 호출 0회. system/user/schema/provider response/usage 모두 해당 없음. 계약 테스트의 응답은 합성 입력이며 모델 응답으로 집계하지 않음.','```json\n[]\n```\n중간 모델 호출 없음.','오프라인 결정적 좌표 대조. 모델 채점 없음.',decision+'\n\n'+limitation]
  path.write_text('# '+cid+'\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(heads,blocks))+'\n');links.append(f"- [{cid}]({q['file']})")
 (A/'실험/README.md').write_text('# 검증 사례\n\n모델 호출 없는 진단이다.\n\n'+'\n'.join(links)+'\n')
 print(json.dumps({'adr':number,'totals':totals},ensure_ascii=False),flush=True)
if __name__=='__main__':finish(int(sys.argv[1]))

"""Render the full61 diagnostic report and exact per-question run records."""
import json,hashlib,statistics,math,csv
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0497-gemma4-fp8-source-workflow-cm51-fsc10';ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(R))
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```'
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def pct(a,b):return f'{a}/{b} ({a/b:.1%})' if b else '해당 없음'
def percentile(xs,q):return sorted(xs)[math.ceil(q*len(xs))-1]
def table(headers,rows):return '| '+' | '.join(headers)+' |\n| '+' | '.join('---' for _ in headers)+' |\n'+'\n'.join('| '+' | '.join(str(v).replace('|','／').replace('\n',' ') for v in row)+' |' for row in rows)
def main():
 m=read(A/'실험/manifest.json');z=read(ART/'metrics.json');ld=read(ART/'retrieval-stage-ledger-validated.json');fixture=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']};c=z['by_arm']['gemma'];audit=read(ART/'execution-audit.json');mechanism=read(ART/'mechanism-audit.json');relations=read(ART/'relations-delivery-audit.json');diag=read(ART/'workflow-diagnostics.json');dr={x['case_id']:x for x in diag['by_case']};rr={x['case_id']:x for x in z['by_case']};qmap={x['case_id']:x for x in fixture['cases']};ledgercases=ld['runs'][0]['arms'][0]['cases'];products=read(ART/'run-001/results.json');judges=read(ART/'run-001/judged-results.json');modelaudit=read(ART/'model-audit.json');judge_calls=modelaudit['summary']['judge']['requests'];d=diag['by_cohort']['all'];reviewed=d['reviewed_answer_cases'];usage_receipts=sum(len(v['gemma']['usage']) for v in products['cases'].values())
 cohortrows=[];cohorts={}
 for name,ids in [('CM51',[c for c in rr if c.startswith('cm-')]),('FSC 난문10',[c for c in rr if c.startswith('fsc-')]),('전체61',list(rr))]:
  vals=[rr[k] for k in ids];verdicts=[s for v in vals if v['publication_status']=='PUBLISHED' for s in v['sources']]
  row={'total':len(vals),'correct':sum(v['correct'] is True for v in vals),'reviewed':sum(v['claims']>0 for v in vals),'ungraded':sum(v['correct'] is None for v in vals),'gold':sum(v['gold_final'] for v in vals),'gold_total':sum(v['gold_total'] for v in vals),'source_relevant':sum(v['relevant'] for v in verdicts),'source_judged':len(verdicts),'publication':sum(v['publication_status']=='PUBLISHED' for v in vals)};cohorts[name]=row
  cohortrows.append([name,pct(row['correct'],row['total']),pct(row['reviewed'],row['total']),pct(row['gold'],row['gold_total']),pct(row['source_relevant'],row['source_judged']),row['ungraded']])
 cohorttable=table(['문항군','검토 답변 기준답 일치','검토 답변 생성','필수 조문 회수','게시 카드 관련성','미채점'],cohortrows)
 caserows=[];csvrows=[]
 for x in z['by_case']:
  cid=x['case_id'];r=products['cases'][cid]['gemma'];s=r.get('stages',{});q=next(q for q in m['questions'] if q['case_id']==cid)
  status='일치' if x['correct'] is True else '미채점' if x['correct'] is None else '답변 미완성' if not x['claims'] else '기준답 불일치'
  caserows.append([f"[{cid}](실험/{q['file']})",*[len(s.get(k,[])) for k in ['discovered','read','presented','selected','final_sources']],x['claims'],status,f"{x['gold_final']}/{x['gold_total']}",x['calls'],f"{x['seconds']:.1f}"])
  csvrows.append({'case_id':cid,'question':qmap[cid]['question'],'outcome':status,**{k:len(s.get(k,[])) for k in ['discovered','read','presented','selected','final_sources']},'claims':x['claims'],'gold_final':x['gold_final'],'gold_total':x['gold_total'],'calls':x['calls'],'seconds':x['seconds'],'judge_reason':x['judge_reason']})
 casetable=table(['문항','발견','읽기','전달','선택','게시 조문','검토 주장','답변','필수 조문','호출','초'],caserows)
 with (ART/'case-summary.csv').open('w',newline='') as out:
  writer=csv.DictWriter(out,fieldnames=list(csvrows[0]));writer.writeheader();writer.writerows(csvrows)
 stages=['discovered','read','presented','selected','payload_sources','final_sources'];labels=['후보 발견','서버 원문 읽기','성공 모델 호출에 전달','원문 선택','저장 payload','게시 결과']
 funnel=table(['단계','1개 이상 도달한 문항/61','조문 수 합계(문항 내 중복 제거)','필수 조문/90'],[[label,pct(d['stage_case_totals'][s],61),d['stage_source_totals'][s],pct(d['gold_by_stage'][s],90)] for s,label in zip(stages,labels)])
 errotable=table(['진단 항목','관측값','해석'],[
 ['발견했지만 READ 0',str(len(d['discovered_but_zero_read']))+'/61','검색 결과 존재와 원문 확보는 별개'],
 ['READ >0, 전달 0',str(len(d['read_but_zero_presented']))+'/61','입력 구성/호출 경로 확인 대상'],
 ['전달 >0, 선택 0',str(len(d['presented_but_zero_selected']))+'/61','읽어도 저장에 이르지 못함'],
 ['선택 >0, 검토 주장0',str(len(d['selected_but_no_claims']))+'/61','원문 패키지만 남고 검토 답변 미완성'],
 ['도구 실행조건 거부 문항',str(d['workflow_error_cases'])+'/61',f"거부 오류 {d['workflow_error_events']}건"],
 ['오류를 다음 성공 호출 입력으로 반환',pct(d['error_returned_next_view'],d['workflow_error_events']),'다음 호출 자체가 없으면 반환으로 세지 않음'],
 ['다음 응답에서 같은 tool+args 재제출',pct(d['same_rejected_operation_repeated_next_view'],d['workflow_error_events']),'설명 문장이 바뀌어도 동작이 같으면 반복'],
 ['실행 가능한 corrective_actions 없음',pct(d['no_corrective_action_errors'],d['workflow_error_events']),'오류 통보만으로 복구가 충분한지 별도 확인'],
 ['제공된 수정 동작이 이후 실행 성공',pct(d['supplied_correction_later_succeeded'],d['workflow_error_events']-d['no_corrective_action_errors']),'수정 동작이 제공된 오류만 분모; 답변 정답과 별개'],
 ['엄격 스키마 거부',f"{d['schema_error_events']}건 / {d['schema_error_cases']}문항",f"전체 {d['attempts']} 모델 시도와 구분"],
 ['화면에 있지만 선택하지 않은 ID 인용',str(d['draft_displayed_unselected_citation_cases'])+'/61','ID를 지어낸 오류와 구분'],
 ['해당 compose 화면에 없는 ID 인용',str(d['draft_not_displayed_citation_cases'])+'/61','과거 화면 ID일 수도 있어 환각으로 일괄 분류하지 않음']])
 loss=table(['필수 출처의 최초 누락 단계','개수/90'],[[k,pct(v,90)] for k,v in d['first_gold_loss_counts'].items()])
 aut=sum(x['auto_read_count'] for x in relations['rows']);aut_e=sum(g['automatic_evidence_count'] for x in relations['rows'] for g in x['groups']);aut_p=sum(g['automatic_evidence_presented'] for x in relations['rows'] for g in x['groups']);recursive=sum(len(x['recursive_auto_scans']) for x in relations['rows']);relreasons=Counter(g['decision'].get('reason',g['decision_status']) for x in relations['rows'] for g in x['groups']);integrity=all(all(s['evidence_was_delivered'] and s['span_hashes_valid'] and s['excerpt_equals_spans'] for s in row['source_checks']) for row in audit['rows'])
 rawtruegate=[cid for cid in rr if judges['cases'][cid]['by_arm']['gemma'].get('raw_answer_judge_correct') is True]
 allshown=[x for x in z['by_case'] if x['gold_shown']==x['gold_total']];wrongreviewed=[x for x in z['by_case'] if x['claims']>0 and x['correct'] is False]
 cost=c['usage']['cost_usd']+z['judge_usage']['cost_usd'];wall=products['finished_at']-products['started_at'];lat=[x['seconds'] for x in z['by_case']]
 for run in m['runs']:run.update(status='complete',sha256=sha(R/run['artifact_path']))
 counts=[x['stages'][-1]['after_count'] for x in ledgercases];ra=m['retrieval_accounting'];ra.update(corpus_total=z['corpus_total'],before_filter={'gemma':z['corpus_total']},after_filter={'gemma':sum(counts)},presented_total={'gemma':sum(counts)},presented_mean={'gemma':statistics.mean(counts)},presented_p50={'gemma':statistics.median(counts)},presented_p95={'gemma':percentile(counts,.95)},golden_recall={'gemma':c['gold_recall']},selectivity={'gemma':statistics.mean(counts)/z['corpus_total']});ra['stage_ledger'].update(summary_run_id='run-001',artifact_path=rel(ART/'retrieval-stage-ledger-validated.json'),sha256=sha(ART/'retrieval-stage-ledger-validated.json'))
 m['results']={'status':'complete','by_arm':z['by_arm'],'by_cohort':cohorts,'comparisons':[],'comparison_note':'Unchanged parent candidate, single run; no paired effect estimate','judge_disagreements':None,'judge_note':z['judge_note'],'criteria':z['criteria'],'verdicts':z['verdicts'],'usage':{'product_attempts':c['calls'],'product_usage_receipts':usage_receipts,'product_usage':c['usage'],'judge_calls':judge_calls,'judge_calls_planned':122,'judge_usage':z['judge_usage']},'latency':{'product_batch_wall_seconds':wall,'p50_seconds':statistics.median(lat),'p95_seconds':percentile(lat,.95),'max_seconds':max(lat)},'error_taxonomy':sorted({x['failure_type'] for x in z['by_case'] if x['correct'] is not True}),'reviewed_answer_count':reviewed,'source_integrity_checks':integrity,'contracts':{'inherited_parent_passed':35,'scoped_binding_checks_passed':9,'product_files_identical_to_parent':97},'main_wiring':'unchanged','diagnostics_path':rel(ART/'workflow-diagnostics.json')}
 for q in m['questions']:
  cid=q['case_id'];x=rr[cid];r=products['cases'][cid]['gemma'];folder=ART/'run-001'/cid/'gemma'
  parts=[f'# {cid} 전체 입출력', '## 1. 실행 메타','ADR0497/run-001/gemma. 부모 ADR0495 중97파일 동일,2파일은 Gemma 호출·게시 승인 설정 연결만 추가, 신규 단회. 공개145문서. 질문별 결과를 보고 수정·문항 단위 재실행을 하지 않았다. 후보에 내장된 오류 정정 경로는 그대로 실행했다.',table(['항목','결과'],[['기준답 일치',x['correct']],['검토 주장',x['claims']],['필수 출처',f"{x['gold_final']}/{x['gold_total']}"],['판정 이유',x['judge_reason']],['호출 / 전체초',f"{x['calls']} / {x['seconds']}"]]),'## 2. 사용자 질문 원문',qmap[cid]['question'],'### 질문 메타데이터',block({k:v for k,v in qmap[cid].items() if k!='question'}),'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',gold[cid]['reference_answer'],block(gold[cid]),'## 4. 제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별',block(next(x for x in ledgercases if x['case_id']==cid)),'## 5. 제품 모델 호출 — run·arm별 실제 원문','### 실제 최종 답변',r.get('result',{}).get('answer',{}).get('text') or '[빈 답변]','### 동작 진단',block(dr[cid])]
  for f in sorted(folder.rglob('*.json')):parts+=['### '+str(f.relative_to(folder)),block(read(f))]
  parts+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','investigate/select_sources/compose/review/repair 실제 요청·원응답·usage는 위 호출 원문과 journal에 기록한다. 실행되지 않은 단계를 성공 처리하지 않는다.','## 7. 채점 호출과 반복 판정']
  for f in sorted((ART/'run-001/judge'/cid).rglob('*.json')):parts+=['### '+str(f.relative_to(ART)),block(read(f))]
  parts+=['### 평가 결과',block(judges['cases'][cid]),'## 8. 사례 최종 판정',block(x)]
  p=A/'실험'/q['file'];p.write_text('\n\n'.join(parts)+'\n');q['sha256']=sha(p)
 write(A/'실험/manifest.json',m)
 manual=(A/'ANALYSIS.md').read_text() if (A/'ANALYSIS.md').exists() else '개별 실행의 의미 판단은 아래 질문별 기록과 원시 평가 이유를 참조한다.'
 front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected' if not all(z['verdicts'].values()) else 'status: Proposed').replace('in_sample: false','in_sample: true')
 sections=[('결정 요약',f"CM51과 별도 FSC 난문10, 총61문항을 최신 ADR0495 후보로 모두1회 실행했다. 검색·답변 로직은 유지하고 모델 호출·게시 승인 연결2파일을 변경했다. **검토를 통과한 답변 {reviewed}/61, 저장 기준답과 일치 {c['correct']}/61, 필수 조문 {sum(x['gold_final'] for x in rr.values())}/90**다. 최종 source payload 게시와 답변 완성은 별개의 성적이다. 엄격 품질 기준 결과는 아래와 같으며 MAIN은 변경하지 않았다.\n\n"+cohorttable+'\n\n'+block(z['verdicts'])),
 ('문제와 변경 전 구조','질문 → 모델 탐색/도구 호출 → 서버 원문 조회 → 모델 입력 구성 → 출처 선택 → 초안 → 검토 → 저장 → 게시 흐름이다. ADR0495는 명시 READ의 직접 연결을 양방향으로 조회하고 소량은 자동 읽기·전달한다. 많거나 크거나 미해소인 연결은 선택과 계속조회 대상으로 남긴다. 이번에는 그 구현을 바꾸지 않고 전체 문항으로 관측 범위를 넓혔다. 오류 반환 여부와 실제 복구, 올바른 자료 확보와 의미 판단을 분리한다.'),
 ('가설과 사전 판정 기준',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n61/61 기준은 배포 성능 보증 기준이 아니라 이번에 사전 고정한 엄격 통과 게이트다. 전체 실행 완료와 후보 품질 합격은 구분한다.\n\n'+block(z['criteria'])),
 ('실험 설계','제품 단일 gemma arm, 각 문항1회, 최대4개 독립 프로세스 동시 실행. Gemma4 google/gemma-4-31b-it / OpenRouter DeepInfra FP8 / thinking off. 문항당 모델14회·도구56회·controller300초·출력2800토큰. 전체 제품 실행이 끝난 뒤 질문당 답변-only1회와 출처-only1회로 분리 채점했다. 정답은 답변 채점기에만 주고 출처 채점기에는 질문과 실제 발췌만 준다. 검토 주장0이면 raw judge가 true여도 정답에서 제외한다. 채점 실패는 미채점이며 분모61에서 제외하지 않는다.\n\n모델·제품·데이터 고정 상태에서 전체를 실행했으며 동시 baseline, 반복 안정성 실험, 새 동시 Qwen arm이나 정답 원문 주입 비교는 하지 않았다. 따라서 이번 수치로 개선 효과나 모델 고유 추론 한계를 확정할 수 없다.'),
 ('데이터·모델·재현성',f"공개61문항은 ADR0114 원본, CM 기준답/현행 source ID는 ADR0473, FSC 기준답은 ADR0114를 사용했다. FSC15개 기준 조문은 법령명+조번호의 유일 일치와 node 동일성을 확인해 현재 세대 ID로 연결했다. CM75+FSC15=90개의 문항별 필수 출처다. 질문·정답·원문 세대·모델·정책·코드·호출기는 첫 호출 전에 해시로 고정했다.\n\n[계획](PLAN.md) · [고정 입력](artifacts/frozen-design.json) · [데이터 출처/좌표 검증](artifacts/dataset-provenance.json) · [97파일 동일 및 연결2파일 변경 확인](artifacts/code-identity.json) · [부모 계약 테스트35개 기록](artifacts/contracts.txt)\n\n제품에 제공한 자료는 공개145문서 범위, canonical 조문 {z['corpus_total']}개다. 기존 원문의 immutable 반출 속성은 유지하고 허용된 요청 범위만 사용했다. 공통 runtime/config도 부모 sealed 복사본이다. [실제 모델/FP8 요청/thinking/사용량 감사](artifacts/model-audit.json)."),
 ('결과',cohorttable+'\n\n### 단계별 도달과 필수 출처\n\n'+funnel+'\n\n'+loss+'\n\n### 61문항 전체 결과\n\n[문항별 질문·실제 답·기준답·실패 경로 해설](CASE_REVIEW.md)\n\n'+casetable+'\n\n발견/읽기/전달/선택/게시 숫자는 문항 안에서 canonical 조문 ID 중복을 제거한 개수다. 항·호 일부만 읽어도 조문 단위 hit가 되므로 완전한 원문 확보율로 해석하면 안 된다. 카드 관련성은 카드별 Qwen 판정이며 조문 단위 필수 출처 회수율과 분모가 다르다.'),
 ('사례별 오류 분석',errotable+'\n\n### 실제 거부 메시지\n\n'+table(['메시지','횟수'],sorted(d['workflow_error_messages'].items(),key=lambda x:-x[1]))+'\n\n### 모델 호출 상태\n\n'+table(['상태','호출 수'],list(d['attempt_statuses'].items()))+'\n\nSUCCEEDED는 응답 수신 상태다. 의미·형식 정답을 뜻하지 않는다. UNKNOWN은 응답을 확정하지 못한 전송 시도, IGNORED_LATE는 기한 후 돌아와 사용하지 못한 응답이다.\n\n### 의미·상태 검증 메시지\n\n'+table(['메시지','횟수'],sorted(d['semantic_error_messages'].items(),key=lambda x:-x[1]))+'\n\n'+manual),
 ('비용·지연·회수 규모',f"제품 물리 호출 시도 **{c['calls']}회**, 반환 usage 영수증 **{usage_receipts}개**, 평가 호출 **{judge_calls}회**다. 반환된 usage 기준 제품+평가 비용 합계 **${cost:.6f}**. 누락 영수증이 있으면 그 호출의 비용은 미확정이다. 병렬 제품 배치 전체 경과 {wall/60:.1f}분. 개별 문항 경과 p50 {statistics.median(lat):.1f}초, p95 {percentile(lat,.95):.1f}초, 최대 {max(lat):.1f}초. p95는 nearest-rank로 계산했다. 자원 초기화는 controller 시간에서 제외되며 총 경과에는 포함된다. 병렬 실행에 따른 로컬 자원 경쟁을 포함한 수치다.\n\n"+block(m['results']['usage'])+'\n\n'+block(m['results']['latency'])),
 ('해석',f"**출처 보존과 답변 판단을 분리해야 한다.** 실제 저장 카드의 span hash·발췌 동일성·모델 전달 이력 검사 결과는 {integrity}다. 직접 연결 자동 READ는 {aut}회, 자동 읽기 evidence 전달은 {aut_p}/{aut_e}, 자동 읽기를 기점으로 한 재귀 연결 조회는 {recursive}회였다. 이는 서버 동작의 관측치이며 LLM의 법률 판단 점수가 아니다.\n\n필수 조문이 모두 모델에 제시된 문항은 {len(allshown)}개이며 그중 기준답 일치 {sum(x['correct'] is True for x in allshown)}개다. 다만 조문 ID 단위이므로 항·호 전체가 주어졌다는 보증은 없다. 검토 답변까지 생성했지만 기준답과 불일치한 사례는 {len(wrongreviewed)}개다. 원시 채점은 true였으나 검토 주장0으로 제외한 문항: {', '.join(rawtruegate) or '없음'}. 이런 보정 없이 출처 요약문을 정답으로 세면 성능이 부풀려진다.\n\n관계 자동 처리의 결정 이유:\n\n"+table(['이유','그룹 수'],sorted(relreasons.items(),key=lambda x:-x[1]))),
 ('한계와 일반화 가능 범위','61문항 모두 기존 연구에 사용된 문항으로 새 holdout이 아니다. 문항당1회이므로 변동성·재현 성공률은 모른다. Gemma가 제품을, Qwen이 평가를 맡았으며 사람 기준으로 채점기를 보정하지 않았다. 원시 failure_type이 실제 journal 실패와 어긋날 수 있어 기계적 오류 원장과 분리했다.\n\n질문 메타의 과거 적용 기준일과 현재 원문 세대의 법령 버전은 독립 법률 검증하지 않았다. 현재 호출기는 question 문자열을 전달하고 별도 answer_as_of 메타를 질의 계약에 주입하지 않는다. FSC의 시점별 해석 문제는 특히 기준답 불일치와 현행 법률 오답을 동일시하면 안 된다. 일부 업무 문맥 괄호가 별도 question piece로 분리되는 기존 동작도 유지했다.\n\n공개 외부 Gemma FP8 thinking-off 성적이며 GENOS 내부 모델·망분리 환경의 성능이 아니다. 전체61 실행은 이 문항군 전수 확인이며 모든 법률 문제에 대한 능력 평가가 아니다.'),
 ('운영 결정·롤백 조건','이번 실행은 제품 변경 없이 격리 후보를 평가한 것이다. MAIN·운영 registry·활성 데이터 포인터·GENOS 배포는 변경하지 않았다. 실패 기록을 보존하며 결과를 본 뒤 수정/추가 실행/재채점은 새로운 ADR에서 해야 한다. 다음 구현 우선순위는 상세 분석의 실제 빈도와 실패 지점에 근거한다. 기존 이력을 덮어쓰지 않는다.'),
 ('재현 명령','완료 산출물을 덮어써서 재실행하지 않는다. 같은 조건의 후속 실험은 새 ADR로 선점한다.\n\n```bash\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+rel(A)+' --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0497/gemma\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n\n[질문별 전체 입출력](실험/README.md) · [지표](artifacts/metrics.json) · [CSV](artifacts/case-summary.csv) · [단계 원장](artifacts/retrieval-stage-ledger-validated.json) · [오류/행동 원장](artifacts/workflow-diagnostics.json) · [연결 전달 감사](artifacts/relations-delivery-audit.json)')]
 (A/'README.md').write_text('---'+front+'---\n\n# Gemma4 FP8 CM51 + FSC 난문10 실행 리포트\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(sections,1))+'\n')
 (A/'실험/README.md').write_text('# 61문항 전체 입출력\n\n'+casetable.replace('(실험/','(')+'\n\n'+ '\n'.join(f"- [{q['case_id']}]({q['file']}) — 질문/기준답/제품 호출 원문/도구/검토/평가/단계 원장" for q in m['questions'])+'\n')
 am=read(ART/'manifest.json');paths={p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and not p.name.endswith(('-wal','-shm'))};paths.update((R/'06_TOOLS/EXPERIMENTS/adr_0497').glob('*.py'));paths.update(A/x for x in ['PLAN.md','product-cases.json','gold-cases.json']);
 for name in ['ANALYSIS.md','CASE_REVIEW.md']:
  if (A/name).exists():paths.add(A/name)
 cand=R/'02_BACKEND/lawrag/research/candidates/adr_0497/gemma';paths.add(cand/'candidate.json');paths.update(R/f['frozen_path'] for f in read(cand/'candidate.json')['revisions'][-1]['files'])
 am['files']=[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input or measured execution/evaluation/audit receipt'} for p in sorted(paths)];write(ART/'manifest.json',am)
 print(cohorttable)
if __name__=='__main__':main()

"""Close the three frozen observations; preserve all failures; no model calls."""
from common import *
import statistics,sqlite3
cases=read(DES/'live-cases.json');audit=read(ART/'source-wire-audit.json')
reviews={
 'charter-natural':{'semantic_pass':False,'reason':'제433조만 모델에 원문 전달. 결의수치 미확인인데 ANSWER/evidence_sufficient=true 선택. 최종에서 수치 부족을 SCOPE로 분류해368/435 추가조사를 되물음. 사진과 같은 핵심 증상 재현.', 'taxonomy':'governing_rule_selection'},
 'charter-433':{'semantic_pass':False,'reason':'433조를 검색 범위로 좁히고 해당 조문만 설명. 두 결의수치 누락인데 open_questions=[] 및 COVERED로 저장. 조문을 지정한 별도 조건이며 일반질문 반복 성공률로 합치지 않음.','taxonomy':'required_issue_omission'},
 'charter-434':{'semantic_pass':True,'reason':'구조 SEARCH→434 READ→ANSWER. 두 수치와 분모를 실제434원문에 맞게 답변. 직접 조문 지정 대조이며 자연질문의 자동 탐색 성공을 뜻하지 않음.','taxonomy':None}}
rows=[];calls=[]
for case in cases:
 cid=case['id'];base=ART/'public-live'/(cid+'-selected');r=read(base/'result.json')['turns'][0]
 assert (base/'resource-final.json').exists()
 cs=read(base/'calls.json');calls.extend(cs)
 answer=(base/'turn-1/public-answer.txt').read_text();g=reviews[cid]
 sourceaudit=next(a for a in audit['cells'] if a['case_id']==cid)
 assert r['http_status']==200 and r['unknown']==0
 assert sourceaudit['budget_matches'] and not any(sourceaudit[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
 assert r['duplicate']['same_answer'] and r['duplicate']['extra_model_calls']==0
 g['response_sha256']=sha(base/'turn-1/response.json.gz')
 rows.append({'case_id':cid,'question':case['steps'][0]['question'],'answer':answer,'seconds':r['request_seconds'],'physical_calls':len(cs),'accepted_outcome':r['accepted_outcome'],'review':g,'source_audit':{k:sourceaudit[k] for k in ('source_checks','delivered_checks','acquired_articles','presented_articles','budget_matches')},'response_sha256':g['response_sha256']})
put(ART/'direct-review.json',reviews)
baseline=read(DES/'baseline.json');rel=baseline['release'];C=ROOT/rel['code_root']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(C/n)==h for n,h in rel['files'].items())
assert all(sha(ROOT/read(DES/'candidate-selected.json')['code_root']/n)==h for n,h in rel['files'].items())
data=ROOT/rel['data_path'];meta=read(data/'manifest.json');assert sha(data/'store.sqlite')==meta['store_sha256']
assert sha(data/'manifest.json')==rel['data_manifest_sha256']
natural=ART/'public-live/charter-natural-selected'
nav=read(natural/'canonical/004.json.gz')['view'];decision=read(natural/'canonical/004-output.json.gz')
wire=read(natural/'raw/call-004/request.json.gz');system=wire['messages'][0]['content']
assert decision['choice']=='ANSWER' and decision['evidence_sufficient']
assert len(nav['sources'])==1 and nav['sources'][0]['heading'].startswith('제433조')
assert nav['connection_scope_choices'] and not nav['connection_review']['required_before_finish']
assert not any(r.get('selected') for r in nav['connection_scope_choices'])
assert 'SOURCE는 검색·연결로 찾을 자료' in system and '확보한 본문으로 설명할 수 있거나 현재 조사를 마치면' in system
assert '원문이 세부 기준을 위임하면 해당 기준을 읽는다.' not in system
profile=read(natural/'binding.json')['profile'];assert profile['candidate_navigation']['guided_loop']
first=read(natural/'canonical/003.json.gz')['view']
db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
original=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',('7bbe815ff43b6635','1772')).fetchone()[0];db.close()
assert '3분의 2' in original and '3분의 1' in original
assert all(t in rows[2]['answer'] for t in ('3분의 2','3분의 1','출석한 주주','발행주식총수'))
facts={'current_MAIN':157,'initial_read_MAIN':156,'156_to157_change':'Oracle Agent mapping/pins only; navigation/guided code bytes identical',
 'source':{'document_id':'7bbe815ff43b6635','article':'제434조','unit_id':'1772','text_sha256':__import__('hashlib').sha256(original.encode()).hexdigest(),'registered_inverse_reference':'registered-434-to-433-reference.json'},
 'natural_initial_page':first['read_candidate_page'],'natural_initial_434_visible':any('제434조' in json.dumps(r,ensure_ascii=False) for r in first['read_candidates']),
 'natural_stop_434_visible':any('제434조' in json.dumps(r,ensure_ascii=False) for r in nav['read_candidates']),
 'natural_stop':{'decision':decision,'sources':[r['heading'] for r in nav['sources']],'connection_review':nav['connection_review'],'available_connection_scopes':[r.get('label') for r in nav['connection_scope_choices']]},
 'proven':['434 original exists and direct control retrieves/answers correctly','Natural run stops after433 without FOLLOW or new structure lookup','434 not in initial20 visible candidates; total100 across5pages; other pages not reviewed','434→433 paragraph1 explicit inverse index exists; natural run did not execute link API','Guided branch uses guidance.PROMPT instead of assembled navigation prompt; actual wire confirms','Natural final output recognizes missing quorum but asks user;433-explicit final incorrectly reports COVERED'],
 'code_references':{'projection':'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py:425,446,607-611,649','guided_prompt':'02_BACKEND/semantic_runtime/legal_agent/guided_navigation.py:20-32','answer_prompt':'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py:10-18','supervisor':'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py:27-29'},
 'limits':['No counterfactual prompt ablation; contribution size of individual prompt clauses unmeasured','No GENOS connection or current serving revision confirmation','Original photo question/prior turns unavailable','Initial search rank of434 outside displayed candidates not measured','Three different formulations once each; not a repeatability rate or general legal quality metric'],
 'proposed_followup':'Preserve user-guided dialogue, but continue READ/FOLLOW/SEARCH for missing content central to the current question. Ask when user facts or actual scope choices are required. Preserve generic required-source/navigation guidance in guided prompt and distinguish SOURCE shortage from SCOPE. Do not hardcode434 or add keyword bans.',
 'product_changes':0,'main_changed_by_this_work':False}
put(ART/'diagnosis.json',facts)
result={'state':'DIAGNOSIS_COMPLETE_WITH_TWO_INCOMPLETE_ANSWERS','selected_MAIN':157,'release_id':baseline['pointer']['release_id'],'serving_files':532,'serving_source_pointer_unchanged':True,'cases':rows,'correct':1,'total':3,'rate':1/3,'rate_scope':'Three deliberately different diagnostic formulations; not repeated trials or general accuracy.',
 'physical_calls':len(calls),'normal_responses':sum(c.get('http_status')==200 for c in calls),'unknown':sum(c['status']=='unknown' for c in calls),
 'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls),'reported_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in calls),'reported_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in calls),
 'source_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_checks':sum(a['delivered_checks'] for a in audit['cells']),'source_acl_wire_mismatches':0,'budgets_match':True,'duplicate_extra_model_calls':0,'quality_certified':False,'product_changes':0,'oracle_calls':0,'genos_calls':0,'judge_calls':0,'replay_calls':0,
 'latency_seconds':{'per_case':[r['seconds'] for r in rows],'median':statistics.median(r['seconds'] for r in rows),'p95':None,'p95_reason':'Three different diagnostic formulations, no population latency claim'}}
put(ART/'result.json',result)
summary='MAIN157 실제 Qwen 진단: 일반질문과433 명시는 결의수치 누락,434 직접 명시는 정확한 수치 답변. 원문 없음이 아니라 핵심 조문을 읽기 전 ANSWER로 끝내는 경로가 재현됨.'
lines=[summary,'','현재 메인: MAIN157 agent-a-unified-20261105-r1. 준비 중156→157 변경을 감지하고 모델 호출 전에157로 결속. 검색/대화 코드는156과 동일.','로컬 실제 root service·원문SQLite·기본 온톨로지OFF·Qwen3.8 Parasail FP8/none. GENOS 현장 재현은 아니다.','',
 '확인된 원인',
 '1. 일반질문 첫20 후보에434는 없고433이 먼저 제시됐다. 모델은433을 읽은 뒤 연결 범위 조회·다음 페이지·구조검색을 하지 않았다. 100후보 전체에434가 없었다고 단정하지 않는다.',
 '2. 네 번째 모델 호출은433만으로 결의요건 설명이 가능하다고 ANSWER/evidence_sufficient=true를 제출했다. 요청 한도40회 중5회만 사용했으므로 예산 소진이 아니다.',
 '3. guided 경로에서는 기존 구체적인 탐색 지침 대신 guided_navigation.PROMPT가 실제 전송된다. 미확보 자료를 이어서 조사할지 물어도 되며, 확보 본문으로 설명 가능하거나 현재 조사를 마치면 ANSWER를 허용한다. 연결 우선 확인은 필수가 아니고 조사감독·의미 재검토도 이 경로에서는 생략된다.',
 '4. 최종 guided_answer는 추가 조사 없이 읽은 원문으로 쓰고 남은 조사를 질문으로 제안하도록 지시한다. 일반질문은 부족을 감지해도 사용자에게 되묻기로 끝나며,433 명시는 부족 자체를 놓쳐COVERED로 저장했다.',
 '5.434 본문과434→433제1항 참조·역방향색인은 존재한다.434를 명시한 질문은 SEARCH→READ→ANSWER로 두 수치를 정확히 답했다. 정상 원문 접근과 자동 탐색의 누락을 구분한다.','',
 '수정 방향(이번 작업은 진단만, 코드 미수정)',facts['proposed_followup'],'',
 '실제 결과']
for row in rows:lines.extend([f"{row['case_id']}: {row['seconds']:.3f}초 / 모델{row['physical_calls']}회 / {'수치 일치' if row['review']['semantic_pass'] else '수치 누락'}",row['question'],row['answer'],'판정: '+row['review']['reason'],''])
lines.extend([f"총 {len(calls)}회 정상 / UNKNOWN {result['unknown']} / 보고비용 ${result['reported_cost_usd']:.8f}",f"원문검사 {result['source_checks']} / 전달검사 {result['delivered_checks']} / 원문·ACL·wire 불일치0 / 예산일치 / 중복요청3건 추가모델0",'각 질문1회, 사진 원질문·이전대화 및 GENOS 실리비전 미확인. 개별 지침의 인과 기여율이나 검색 순위 전체 원인은 미측정.','준비 오류(스키마컬럼/문서이름/MAIN교체/UI접두어/observer모듈명)와 사전검증 메타 보완 기록 보존. 제품·메인·현장·원문변경0.'])
(ART/'정관변경_원인과_Qwen실험결과.txt').write_text('\n'.join(lines)+'\n')
put(RUN/'result.json',{'result_path':str((ART/'result.json').relative_to(ROOT)),'sha256':sha(ART/'result.json'),'summary':summary})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'selected':{'correct':1,'total':3,'accuracy':1/3,'decision_eligible':False,'scope':'different diagnostic formulations, no general accuracy'}},comparisons=[],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','reported_cost_usd','reported_prompt_tokens','reported_completion_tokens','unknown')},latency=result['latency_seconds'],error_taxonomy=[{'type':g['taxonomy'],'case_id':cid} for cid,g in reviews.items() if g['taxonomy']])
for q,row in zip(m['questions'],rows):
 p=ADR/'실험'/q['file'];p.write_text(p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\n'+json.dumps(row,ensure_ascii=False,indent=2)+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1].replace('title: MAIN156','title: MAIN157')
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[summary,'사진에서433을 설명하고 결의수치를 추가 질문으로 미루는 현상. 원질문/이전대화는 미제공.156을 처음 읽었으나 동시작업157전환을 감지하고 최초 모델 전157 전체532파일을 고정했다.',
 json.dumps(read(DES/'criteria.json'),ensure_ascii=False),
 'selected만 실제 실행. baseline은 설정 기준으로 추가 시행 없음. 자연질문→433명시→434명시 각각1회/새세션/동일 프로필. 정답·사진은 제품에 전송하지 않았다. 소스 데이터는 기존financial팀 공개 범위와 허용목록 교집합44문서.',
 'actual root service / MAIN157 / immutable532 candidate bytes same / Qwen3.8 Parasail FP8 none / output cap absent / isolated journals / local SQLite. 실제 입력/스키마/응답/canonical/state 모두 artifacts/public-live. 원문 버전은 data manifest에 결속했다.',
 json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False,indent=2),
 '\n'.join(row['case_id']+': '+row['review']['reason'] for row in rows)+'\n\n준비 실패는 preparation-issues.json. 원래 로그/실패파일을 지우지 않았고 실제 모델 응답 재시도0.',
 '16물리 모두정상·UNKNOWN0. 보고비용/토큰은 result.json. source-wire-audit와 retrieval-stage-ledger는 원문 확보와 실제 전달을 구분한다. 자연질문의 부수원문획득12조문을 모두 모델이 읽은 것으로 세지 않으며 실제 전달1조문은433이다. 조문근거 확보/전달/의미정답은 별도 지표다.',
 '원문/역방향 참조/직접구조 검색은 존재한다. 자연질문의 직접 원인은433을 충분하다고 선택하고 연결검색 전에 끝낸 것. 코드에서 guided prompt가 기존 navigation 지침을 대체하고, 최종 단계가 추가 조사를 금지하는 경로를 wire와 대조했다. 원인 후보 각 조항의 독립 인과 크기는 미측정.',
 '\n'.join(facts['limits']),
 '진단만 수행. 제품/활성포인터/원문/Oracle/GENOS/메일 변경0. 품질미통과를 숨기지 않음. 수정·효과 비교는 새 ADR에서 사전 동결. 기존 대화형 정책과 안전검증을 보존한다.',
 '재실행은 새 ADR. 읽기전용 감사: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1415/audit_v2.py ; inspect_trace.py. 최초 전달 전체 결과: [정관변경 원인과 Qwen 결과](artifacts/정관변경_원인과_Qwen실험결과.txt). [질문별 기록](실험/README.md).']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN157 정관 변경 결의요건 진단\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headings,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 Qwen 진단 질문\n\n'+summary+'\n\n| 질문 | 결과 | 시간 |\n|---|---|---:|\n'+'\n'.join('| ['+r['case_id']+']('+q['file']+') | '+('수치 일치' if r['review']['semantic_pass'] else '수치 누락')+' | '+f"{r['seconds']:.3f}초 |" for q,r in zip(m['questions'],rows))+'\n')
put(ART/'FINAL_VALIDATION.json',{'selected_main':157,'unchanged_serving_files':532,'candidate_equals_selected':True,'source_store_unchanged':True,'active_pointer_unchanged_since_freeze':True,'source_checks':result['source_checks'],'delivered_checks':result['delivered_checks'],'source_acl_wire_mismatches':0,'budget_matches':True,'duplicate_checks':3,'duplicate_extra_model_calls':0,'actual_calls':len(calls),'unknown':0,'semantic_success':1,'semantic_cases':3,'quality_certified':False,'main_product_changed':False,'diagnosis_verified':True,'record_validation':'See adr-final-validation.log and graph-check.json after closure.'})
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'};paths.update(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1415','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'MAIN157 actual Qwen diagnostic evidence; original failures retained','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in sorted(paths)]})
print(summary);print('calls',len(calls),'cost',result['reported_cost_usd'])

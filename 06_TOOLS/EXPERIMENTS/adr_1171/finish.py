from common import *
import subprocess
f=read(DES/'freeze.json');r=read(ART/('check-'+f['candidate_revision']['revision_id']+'.json'));p=read(ART/'post-probe-audit.json')
assert r['passed']==77 and r['failed']==0 and not r['import_leaks']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
for name,h in f['files'].items():assert sha(ROOT/f['code_root']/name)==h
for name,h in {**f['inputs'],**f['scripts']}.items():assert sha(ROOT/name)==h,name
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1170-supervisor-pagination-contract/artifacts/design/freeze.json')
changed=[n for n,h in f['files'].items() if parent['files'].get(n)!=h]
result={'status':'complete','technical_passed':77,'technical_failed':0,'model_requests':5,'model_responses':4,'rate_limited':1,'full_cm_runs':0,'quality_certified':False,'main_unchanged':True,'candidate_revision':f['candidate_revision'],'changed_files':changed,'probe':read(ART/'model-probe/selection.json'),'offline_actual_response_audit':p,'decision':'Technical candidate retained; no eligible model or MAIN promotion. User rejected GENOS proxy as stronger-model comparison; keep data as historical failure only. Follow-up same Qwen provider change separately.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'controlled':{'status':'complete','technical_success':True,'quality_certified':False,'model_qualification_success':False}},comparisons=[],judge_disagreements=[],usage={'physical_requests':5,'responses':4,'rate_limited':1,'tokens':p['tokens'],'reported_cost_usd':p['reported_cost_usd']},latency={'technical_seconds':r['seconds'],'provider_seconds':p['reported_provider_seconds'],'performance_claim':False},error_taxonomy=['rev001 fixture cancelled FOLLOW treated as executed','rev002/003 API public diagnostic projection mismatch, fixed rev004','first probe import error before any call','Qwen38 Parasail429 shared upstream pool','GENOS proxy4/4 invalid response schema; CM007 two prose/action document mismatches','User corrected stronger-model comparison intent; GENOS proxy not accepted as replacement comparison'])
m['retrieval_accounting']['not_applicable_reason']='Saved next-action probes only; no new full retrieval. Conditional full CM3 not started: no model passed4/4.'
m['questions']=[]
qheads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for i,c in enumerate(read(DES/'cases.json'),1):
 cid=c['id'];name=f'질문-{i:03}-{cid}.md';texts=['run-001 / controlled / saved-state probe; full run conditional',c['request']['json']['question'],'법률 정답률 미채점. 평가 전용 원문은 artifacts/evaluation-only에 보존하고 제품에 넣지 않았다.',f'../artifacts/design/probe/{cid}/body.json 및 canonical.json' if cid!='cm-009' else '전체 실행 조건 미충족으로 미실행.',f'../artifacts/model-probe/genos122/{cid}/ 및 qwen38/{cid}/' if cid!='cm-009' else '신규 호출0.','추가 감시·보완 호출 없음. saved-state 출력만 검사.','외부 채점0. 전체 형식 검증·정확 목표 여부의 사전4/4 기준.','001: 두 응답 모두 실행 형식 위반; 1회 FINISH, 1회 미지원 READ_SCOPE. Qwen429/미실행.' if cid=='cm-001' else '007: 두 응답 모두 설명D5, 실제T136은D4 BROWSE_STRUCTURE. 서버 거절 확인. Qwen미실행.' if cid=='cm-007' else '전체 실행 미실행.']
 (ADR/'실험'/name).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{t}' for n,(h,t) in enumerate(zip(qheads,texts),1))+'\n');m['questions'].append({'number':i,'case_id':cid,'file':name,'sha256':sha(ADR/'실험'/name)})
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'명시 원문 목표 집행·목표 유지·미해결 종료 제어를 격리 후보에 구현했다. 기술77통과. 실제 공급자 요청5(429한 번+122B응답4), 실행 계약 통과0/4. 통과 모델이 없어 전체 CM3은 시작하지 않았다. 사용자는 GENOS 대리 모델을 더 좋은 모델 비교 대상으로 삼은 선택이 취지와 다르다고 정정했다. 이 비교로 모델 교체를 판단하지 않는다. MAIN112 유지.',
'필요한 법령·조항을 서술하면서 다른 문서 도구를 선택하고, 별도 원문 읽기를 목표 충족으로 오인하거나 FINISH하는 실패. 이전1170은 NEXT/PREV 계약만 수정했다. 현재 Qwen38은 Parasail만 허용해429 후 공급자 전환이 없었다.',
'[사전 기준](artifacts/design/criteria.json): 명시 목표 정확조회/읽기, 불변 권한·문서·좌표, resume·동일동작 재사용, 미해결 종료제어, 기존46검사 보존. 저장001/007 각각2회 모두 정확 다음행동4/4일 때만 전체3실행. 임의 골드 기반 경로 생성 없음.',
'1170 완료 후보에서 제품6모듈+프로필1 및pin31, 총38파일 변경. source_goal_control이 명시 조회 대상·조항을 보존하고 기존 LOCATE/READ를 집행한다. 검증된 ASSESS EXACT부족은 새 선택기가 빠뜨려도 유지한다. 정확 원문이 도착한 뒤 ACQUIRED이며 법률 충분성은 별도. 목표별 LOOKUP/READ각1회, 중간경로공유2회, 목표최대16·기존 최종예산 유지. 비교 입력에는 목표 필드와 페이지 행동 계약만 추가했다.',
'모든 제품은 동결460파일. 기술77검사는rev004에서 실행, 이후 제품 동일 revision에 상속한다. 기본Qwen38/Parasail FP8 reasoningnone, 대리Qwen3.5-122B/AtlasCloud FP8 reasoningoff. 기준답변 미전송. 실제wire/response/정책을 저장했다. 첫429 뒤 사용자 정정 전에는 Qwen나머지3호출을 생략하고 사전 등록한 독립122B4셀만 실행했다. 429가모델판단실패는 아니다.',
'기술77/77, import누출0. 새AS​​SESS 목표·범위오류·고정원문 도착·종료방지·정상/OFF·API 저장/멱등 재조회 확인. 실제응답4개의스키마거절을 오프라인 재현했고007의 잘못된T136도2/2서버거절. 추가 자원검사8은 전역PSI만으로는중단하지않되RAM/RSS/swap/disk한도를 유지함을 확인했다. 실서비스 법률답변 성공미검증.',
'rev001 65pass/1fixture실패; 취소된FOLLOW를 실행완료로 취급해최종연결검토 실패. rev002 65/1·rev00376/1은공개API가failure필드를제거한뒤 판단표시해시불일치. 정렬만으로안고쳐졌다는정정진단보존, 기존공개projection을해시전에적용해rev00477통과. 실제007 두응답은D5가필요하다쓰고D4의T136(구조이동)을READ로제출;001은세칙필요를알면서FINISH또는지원하지않는READ_SCOPE. 모든실패보존.',
f'물리요청5·응답4·429한번·미실행3. 응답4기준입력{p["tokens"]["input"]}·출력{p["tokens"]["output"]}·thinking0, 공급자보고비용${p["reported_cost_usd"]:.7f}, 공급자시간{p["reported_provider_seconds"]:.3f}초. 429비용은보고없음. 신규전체회수없으므로recall/원문확보시간/전체속도해당없음. 출력상한필드0.',
'서버가잘못된행동을채택하지않는것과모델이맞는행동을내는것은별개다. 이번의반복된문서-도구불일치는모델교체만으로해결된다는가정을지지하지않는다. Qwen실제응답이없어두모델성능차이는비교할수없다. 사용자취지에맞는더좋은모델비교도아니다.',
'알려진두실패상태의인샘플소표본. 전체원문조사/법률정답/실서비스속도/GENOS현장미인증. 목표선언자체의잘못된문서·조항의법률의미를서버가추론해고치지않는다. 잘못된형식은거절하며자동으로법률판단을생성하지않는다.',
'MAIN112·GENOS·일반제품코드변경없음. 공통실험validator에이ADR의명시승인된GENOS모델비교만허용하는검증을추가했고8손상조건을검사했다. 사용자정정후이대리모델비교를새개선근거로사용하지않는다. 다음Qwen공급자전환은별도기록한다. 롤백은후보를선택하지않고기존MAIN유지.',
'완료된실험은덮어쓰지않는다. 기술검사: 06_TOOLS/EXPERIMENTS/adr_1171/check.py. 실제응답오프라인검사: post_probe.py. probe.py의완료셀재실행은거부한다. 새외부실험은새동결기록에서수행한다.'
]
path=ADR/'README.md';meta=path.read_text().split('---',2)[1];path.write_text('---'+meta+'---\n\n# 명시 원문 목표 집행과 실패 입력 실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n77기술검사통과. 저장001/007 입력의물리요청5: Qwen429한번, GENOS대리모델형식실패4. 전체CM3미실행. '+ '\n'.join(f'[{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
audit=ROOT/'09_ARTIFACTS/AUDITS/20261028-source-goal-control';audit.mkdir(exist_ok=True)
(audit/'결과.txt').write_text('원문 목표 집행 구현·실험 — ADR1171\n\n정확 조회→읽기, 목표 유지, ASSESS 미확보 목표 보존, 미해결 상태에서 충분한 답변으로 종료 방지. 법률 판단은 자동 채택하지 않는다. MAIN112 기반 격리 후보460파일·부모1170대비38변경.\n기술77통과, 실제007 잘못된도구2건 실행전차단, 실제응답4개 형식거절 재현. 자원가드8확인.\n실제호출: Qwen38 Parasail429 1건, GENOS대리모델4건 모두형식실패. 007설명은유가증권(D5),실제번호T136은코스닥(D4)구조이동. 전체CM3미실행,법률품질미인증,MAIN112유지.\n사용자정정: 대리모델은더좋은모델비교가아니며이번선택은취지불일치. 모델교체판정에사용하지않는다. 현재Qwen은Parasail단독이고복수공급자설정은122B쪽이다. 사용자429공급자전환지시에따라후속작업에서같은Qwen의공급자변경을진행한다.\n')
a=read(ART/'manifest.json');paths=[x for x in ART.rglob('*') if x.is_file() and x!=ART/'manifest.json' and 'test-runtime' not in x.parts and 'view-diagnostic' not in x.parts];paths += list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path'],ROOT/'06_TOOLS/COMMANDS/adr_structure.py',audit/'결과.txt']
a['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen evidence, source, actual raw request/response or preserved failure','contains_raw_prompts_and_outputs':x.suffix=='.log' or 'model-probe' in x.parts} for x in paths];put(ART/'manifest.json',a)
for name,args in [('hash-final',('hash','--path',str(ADR))),('validate-before-completion',('validate','--path',str(ADR))),('status-final',('status','--path',str(ADR),'--status','completed','--note','77technical pass; 5physical requests,429one/proxy4schemafail; fullCM0; user rejects proxy comparison; MAIN112unchanged')),('validate-final',('validate','--path',str(ADR),'--final'))]:
 out=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(name+'.txt')).write_text(out.stdout+out.stderr);assert out.returncode==0,out.stdout+out.stderr
print('ADR1171 completed; actual failure records preserved; MAIN112 unchanged')

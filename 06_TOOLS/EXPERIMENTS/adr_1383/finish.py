from common import *
rows={r['case_id']:r for r in read(ART/'answer-evidence.json')['rows']}
grades=read(ART/'semantic-review.json')
cases=read(DES/'live-cases.json')
assert set(grades['cases'])==set(rows)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert ptr==read(DES/'baseline.json')['pointer']
for n,h in read(DES/'freeze.json')['files'].items():assert sha(ROOT/n)==h,n
usage={'physical_calls':sum(r['physical_calls'] for r in rows.values()),'unknown':sum(r['unknown'] for r in rows.values()),
       'reported_cost_usd':sum(r['reported_cost_usd'] for r in rows.values()),'reported_tokens':sum(r['reported_tokens'] for r in rows.values())}
stop=read(ART/'STOP_EXTERNAL.json') if (ART/'STOP_EXTERNAL.json').exists() else None
summary={'selected':ptr,'planned':[c['id'] for c in cases],'completed_cells':list(rows),'unattempted':[c['id'] for c in cases if c['id'] not in rows],
 'usage':usage,'grades':grades,'global_stop':stop,'source_checks':sum(r['source_checks'] for r in rows.values()),'wire_checks':sum(r['delivered_checks'] for r in rows.values()),'mismatches':sum(r['mismatches'] for r in rows.values()),'budget_ok':all(r['budget_matches'] for r in rows.values()),'duplicate_extra':sum(r['duplicate_extra'] or 0 for r in rows.values()),'production_publications':0,'field_deployed':False}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference':'ADR1377/integrated'},'paired':summary},comparisons=[],judge_disagreements=0,usage=usage,latency={'request_seconds':{k:r['request_seconds'] for k,r in rows.items()}},error_taxonomy=grades['issues'])
put(ADR/'실험/manifest.json',m)
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-main143'
def cell_text(case):
    k=case['id']
    if k not in rows:return k+' | 미실행'
    r=rows[k]; g=grades['cases'][k]; delivery=r['scenario_deliveries'] if case['article']==365 else r['matching_inputs']
    return f"{k} | HTTP {r['http_status']} | {g} | 최종 주장 {r['claims']} | 묶음 입력 {delivery}회 | 확정 경로 사용 {len(r['verified_claim_uses'])}건 | {r['request_seconds']:.1f}초 · {r['physical_calls']}호출 · 보고 {r['reported_tokens']}토큰"
lines=[cell_text(c) for c in cases]
data_note='공개 상법 SQLite 한 문서와 MAIN145 서빙 528개 해시를 고정했다. 정관은 격리 DB의 승인 2판이며 충돌 3판은 보류 상태다. 365조는 승인된 시나리오 1판이다.'
lim='개발에 이미 사용한 질문 두 개다. ASSESS의 원문·범위·주장 검토는 실제 제품 검증기로 실행했다. 추가 모델 최종 검토 스위치는 릴리스 기본값(false)이다. 운영 지식 게시와 현장 성능 검증은 별도다.'
cost=f"유료 시도 {usage['physical_calls']}회, 결과 불명 {usage['unknown']}회, 공급자 보고 USD {usage['reported_cost_usd']:.8f}. 원문 {summary['source_checks']}개 구간 · 송신 {summary['wire_checks']}개 구간 대조 · 불일치 {summary['mismatches']}건. 예산 일치 {summary['budget_ok']}, 동일 요청 추가 호출 {summary['duplicate_extra']}회."
recovery='6셀 준비 확인 뒤 첫 실제 세션은 스왑 증가로 모델 전송 전에 종료됐다. 요청 기록 0건을 확인하고 중단 실행을 보존했다. 메모리 안정 확인 후 같은 동결 입력으로 새로 시작했다.'
(report/'온톨로지_Qwen_재검증.txt').write_text('\n\n'.join([grades['headline'],data_note,'\n'.join(lines),grades['interpretation'],cost,lim,recovery])+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=[grades['headline'],'1374의 명시 사용 성공과 1354의 365조 불안정 뒤 통합된 MAIN145에서 일반 활용을 재검증했다.',read(DES/'criteria.json')['hypothesis'],'같은 질문의 ON/OFF, 경로 명시 정관 ON, 365 ON 독립 반복. 공급자 결과 불명 발생 시 추가 송신 종료.',data_note,'\n\n'.join(lines),recovery+' '+' '.join(grades['issues']),cost,grades['interpretation'],lim,'MAIN145 선택을 확인했고 이 활용 시험을 위한 추가 운영 변경은 없다.','setup → run_live --preflight → run_live → audit → inspect_use_final → detail → ledger → archive_runtime → finish → seal → hash/status/validate. 수신 원문은 각 usage-live 셀의 raw·canonical 하위에 있다.']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN145 온톨로지 실제 활용\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,case in zip(m['questions'],cases):
    k=case['id'];r=rows.get(k);assert k==q['case_id']
    path='../artifacts/usage-live/'+k+'-'+case['arms'][0]+'/'
    fields=['run-001/paired, '+case['arms'][0],case['steps'][0]['question'],'정관의 두 기준 또는 365조의 세 소집 시기를 해당 원문·최종 주장과 대조했다.',
       '### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/retrieval-stage-ledger.json.gz. '+data_note,
       f'[{k} 실제 요청·응답]({path})' if r else '해당 셀 미실행.',
       str(r['repairs']) if r else '호출 0회.', '추가 평가 모델 0회. 최종 확정 응답 및 프롬프트별 묶음 송신과 사용 경로를 별도 확인했다.',
       cell_text(case)+ ('\n\n'+r['answer'] if r else '')]
    (ADR/'실험'/q['file']).write_text('# '+k+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,fields),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
print(cost)

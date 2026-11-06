from common import *
import statistics
cases=read(DES/'live-cases.json')
evidence=read(ART/'usage-inspection.json')['rows']
grade=read(ART/'semantic-review.json')
for r in evidence:
    r['quality']=grade['arms'][r['case_id']]
pub=read(ART/'publication-verified.json')
parent=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1371*/artifacts/build-live'))
assert all(sha(parent/n)==h for n,h in read(DES/'parent-files.json').items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
comparisons={case:read(ART/('followup-'+case)/'result.json') for case in ('corroborate','conflict')}
physical=sum(x['physical_calls'] for x in comparisons.values())+sum(x['physical_calls'] for x in evidence)
unknown=sum(x['unknown'] for x in comparisons.values())+sum(x['unknown'] for x in evidence)
cost=sum(x['reported_cost_usd'] for x in comparisons.values())+sum(x['reported_cost_usd'] for x in evidence)
work=read(ART/'working-integration.json')
summary={'grade':grade,'publication':pub,'comparisons':comparisons,'use':evidence,'physical_calls':physical,
         'unknown':unknown,'reported_cost_usd':cost,'parent_unchanged_files':len(read(DES/'parent-files.json')),
         'active_generation':read(DES/'baseline.json')['pointer']['generation'],'production_publications':0,
         'working_products':work['product_files'],'working_checks':read(ART/'working-service-check/result.json')['passed'],
         'candidate_checks':read(ART/'comparison-contracts-final/result.json')['passed']}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'parent':'1371/repaired'},'repaired':summary},
  comparisons=[],judge_disagreements=0,usage={'physical_calls':physical,'unknown':unknown,'reported_cost_usd':cost},
  latency={'one_request_per_arm':{r['arm']:r['request_seconds'] for r in evidence}},error_taxonomy=grade['issues'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
notes=[grade['headline'],'완료1371의 같은 작업공간 그래프에 다른 질문의 관찰을 새 검토 판본으로 연결하는 경로를 추가했다. 기존 문장과 실행 그래프, 기록별 판본을 보존한다.',
       str(read(DES/'criteria.json')['success']),m['runs'][0]['selection_rule'],'공개 상법·1371의 실제 SQLite 작업 복제본, 1369/1341의 다른 세션에서 실제 나온 판단, 동일 Qwen3.8 FP8 설정. 분리된 실험용 승인으로 DB 조회 경로를 확인한다.',
       grade['detail'],grade['conflict'],f'총 {physical}회·결과불명 {unknown}회·보고비용 USD {cost:.8f}. 회수·원문 대조는 artifacts/source-wire-audit.json 및 단계별 원장 참조.',
       grade['reuse'],grade['limits'],'기존 지식은 자동 변경하지 않고 대조 결과를 같은 ID의 새 검토 판본에 보존한다. 그 결과를 운영 승인·현장 게시로 연결하지 않았다. 작업 코드 3개와 엔진 핀, 원복 바이트 artifacts/working-before.',
       'setup, 후보 동결 및 계약 검사, 복제 저장소·모델 없는 준비 검사, 실행 동결, compare, activate_copy, run_usage, audit, inspect_use, 무손실 보관 및 최종 검사. 기존 외부 요청 재전송 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 정관 지식의 축적과 재사용\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,notes),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    row=next((r for r in evidence if r['case_id']==q['case_id']),None)
    case=next((c for c in cases if c['id']==q['case_id']),None)
    qs=['run-001/repaired/rev002', case['steps'][0]['question'] if case else '기존 정관 판단과 별도 실제 지지·충돌 판단을 원문으로 대조한다.',
        '저장된 공개 원문에 적힌 두 분모·비율을 검토한다. 정답키를 모델 입력에 넣지 않는다.',
        '### 회수·탈락 단계 원장 — run·arm별\n\n실제 회수는 artifacts/retrieval-stage-ledger.json.gz, source-wire-audit.json. 구축 비교는 고정 원문.',
        'followup-*/raw 및 usage-live/<cell>/raw에 실제 전송과 응답 보관, canonical에 모델별 논리 입력.',
        '단계별 calls.json/generations.json과 검토 원본.', '채점 모델 0. 원문·DB·실제 전송·확정 주장 연결을 대조. 동일 요청의 중복 동작 확인.',
        str(row) if row else grade['detail']+' '+grade['conflict']]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qs),1))+'\n')
(ADR/'실험/README.md').write_text('# 사례\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
out=ROOT/'09_ARTIFACTS/AUDITS/20261105-charter-accumulation-reuse';out.mkdir(exist_ok=True)
(out/'축적과_활용결과.txt').write_text('\n\n'.join([grade['headline'],grade['detail'],grade['conflict'],grade['reuse'],grade['limits'],notes[7],'실제 응답',*[r['arm']+' '+r['answer'] for r in evidence]])+'\n')
print(grade['headline'])

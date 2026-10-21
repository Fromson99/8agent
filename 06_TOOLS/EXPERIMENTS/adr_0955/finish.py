"""Write offline review and the completed probe record; no product or model changes."""
from pathlib import Path
import hashlib,json,statistics
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=read(O/'result.json');metrics=result['cases']['observed'];total=result['by_arm']['observed']
gold=read(D/'gold-evaluation-only.json');cases=read(D/'cases.json');post=read(O/'post-audit.json')
ledger=read(O/'retrieval-ledger.json')
review={
    'kind':'offline_manual_review_of_synthetic_specification','model_calls':0,
    'legal_accuracy_certified':False,'criteria_unchanged':True,
    'cases':{
        'anchor-scope':{
            'prospective_checks':[True,True,False],'answer_semantics_pass':False,
            'error_taxonomy':['numeric_temporal','governing_rule_selection'],
            'finding':'투자매매업자 원문을 선택하고 유지상한과 보고조건을 분리했지만, 120% 이하 내규가 130% 이하 외규보다 엄격하다는 이유로 CONFLICT/상충을 표시했다. 둘을 동시에 충족할 수 있으므로 이 합성 사례의 충돌 판정은 잘못이다.',
            'additional_observations':'질문에 없는 산식·분자/분모를 부족으로 설정하여 내규·외규에 각각 명시 후속 검색을 했다. 총21호출 중 전부가 낭비라는 뜻은 아니지만 업무 범위 확장이 비용을 유발했다. 선택 개념은 내규 제1조인데 제2·3조의 승인 외규 연결도 먼저 읽었다.',
        },
        'approved-scope':{
            'prospective_checks':[True,True,True],'answer_semantics_pass':False,
            'error_taxonomy':['numeric_temporal','governing_rule_selection'],
            'finding':'고의로 승인한 은행12% 연결을 최종 적용에서 제외하고 연결 없는 투자매매업자6% 조항을 찾아 내규8%와 비교했다. 연결 적용성 탐침은 통과했다.',
            'additional_observations':'추가 관찰: 최종 verdict는 8% 이상과 6% 이상이 다르다는 이유로 CONFLICT/상충이다. 더 엄격한 내부 최소기준과 모순을 혼동했다. 사전 연결 적용성 기준을 사후 변경해 실패로 바꾸지 않고, 전체 답변의 별도 의미 오류로 기록한다.',
        },
        'reference-exception':{
            'prospective_checks':[True,True,True],'answer_semantics_pass':True,
            'error_taxonomy':[],
            'finding':'내규→모의이체절차규정 제1조→모의장애대응규정 제2조를 확보하고 전산장애·사전승인불가능·3영업일·장애기록 조건을 보존해 부합으로 설명했다. 순환 참조로 무한 조사하지 않았다.',
            'additional_observations':'동일 모의이체절차규정 제1조의 같은 세대·원문 해시·인용문이 서로 다른 evidence ID로 최종표와 연결 후보에 두 번 나타났다. 표시 중복은 확인됐으나 물리 DB 재조회 비용이나 순환 참조가 원인이라는 인과 주장은 하지 않는다.',
        },
        'missing-source':{
            'prospective_checks':[True,True,True],'answer_semantics_pass':True,
            'error_taxonomy':[],
            'finding':'제공 범위 밖 별표9를 창작하지 않고 내규 기한을 미확인으로 남겼다. 외규의 통지 다음 영업일·장애 입증 시3영업일은 원문으로 제시하고 판정을 보류했다.',
            'additional_observations':'별표를 찾는 명시적 추가 조사1회 후 제한 답변으로 종료했다. 미확보를 별표 부재나 사용자의 사실 부족으로 바꾸지 않았다.',
        },
    },
    'priorities':[
        '선택한 내규 개념의 실제 span으로 승인 관계를 좁힌 후 외규 우선 읽기를 수행한다. 관련 범위 확대는 이유가 있는 별도 조사로 기록한다.',
        'LLM이 동일 대상·조건·시점에서 양쪽 의무를 동시에 이행할 수 없는지 원문으로 설명하도록 비교 판단을 구체화한다. ADDITIONAL_INTERNAL은 이미 있으며 자동 수치 규칙으로 법률 결론을 만들지 않는다.',
        '원문 세대·문서·위치·span/해시의 동일성을 별도로 관리해 경로별 evidence ID를 하나의 표시 출처로 묶고, 원래 경로와 감사 기록은 보존한다.',
        '질문에 반드시 필요한 확인과 참고적 산식·정의·예외 확장을 LLM이 구분하게 하고, 새 조사의 목적과 실제 신규 근거를 추적한다.',
    ],
    'not_tested':['위 개선안의 효과 A/B','실제 risk_cm 원본105문항','전체 MAIN corpus 규모','GENOS 내부 모델·Oracle 현장 성능'],
}
put(O/'manual-review.json',review)
m=read(A/'실험/manifest.json')
correct=sum(v['answer_semantics_pass'] for v in review['cases'].values())
total.update(synthetic_answer_semantics_correct=correct,synthetic_answer_semantics_total=4,
    synthetic_answer_semantics_accuracy=correct/4,
    prospective_case_goals_pass=sum(all(v['prospective_checks']) for v in review['cases'].values()),
    prospective_case_goals_total=4,
    synthetic_required_source_recall=1.0,
    legal_accuracy=None)
result['manual_review']=str((O/'manual-review.json').relative_to(R));put(O/'result.json',result)
m['results']['by_arm']=result['by_arm']
m['results']['error_taxonomy']=[{'type':'numeric_temporal','count':2,'denominator':4},
    {'type':'governing_rule_selection','count':2,'denominator':4},
    {'type':'other','count':1,'denominator':4,'description':'Identical source duplicated in final display; not counted as a semantic answer failure.'}]
m['results']['judge_disagreements']=0
m['results']['manual_judge_note']='One offline record review, no evaluator model or independent rater; disagreement=0 means no competing rating, not inter-rater agreement.'
m['runs'][0]['sha256']=sha(O/'result.json')
put(A/'실험/manifest.json',m)
summary=f"""MAIN94 설계 탐침 — ADR0955 / 2026-10-20

변경 없는 MAIN94 제품 코드로 합성 문서7개·조항16개, 질문4개를 실제 Qwen3.8/Parasail FP8에 순차 실행했다.
사전 필수 원문10/10을 최종 인용했다. 원문·span·해시89검사 불일치0.
정확히 같은 쿼리·범위의 성공한 검색 재실행은 관측0이며 저장/중복 응답4/4 일치, 소비자 추가 모델 호출0이다.
회수 성공과 답변 판단은 다르다. 수치 사례2건에서 잘못된 상충 판정이 나왔다.

확인된 약점과 우선순위
1. 승인 외규를 고르는 범위가 선택 개념보다 넓다.
   운영완충비율 질문의 개념은 내규 제1조인데, 이미 읽은 제2·3조에서 은행 유동성완충금·긴급 이체 연결도 끌어와 자동 원문 읽기를 했다.
   parent_task가 개념 인용 대신 확보된 모든 내규 evidence로 snapshot을 구성하고, 그 뒤 internal_anchors가 붙는 코드 순서와 실제 로그가 일치했다.
2. 더 엄격한 내규를 상충으로 오판한다.
   내규120% 이하/외규130% 이하, 내규8% 이상/외규6% 이상을 모두 상충으로 표시했다.
   두 의무를 동시에 지킬 수 있다. ADDITIONAL_INTERNAL enum은 이미 있으므로 항목 부족보다 모델의 판단 기준·이유 연결 문제다.
3. 같은 원문이 경로별 ID로 중복 표시된다.
   참조 예외 사례에서 동일 문서·조항·세대·원문 해시·문구가 외규1/2로 두 번 등장했다.
   원문 정체성과 조사 경로 ID를 분리해 표시 중복을 줄일 여지가 있다. 물리 DB 중복 조회 비용을 입증한 것은 아니다.
4. 질문보다 조사 범위가 넓어질 수 있다.
   유지상한·보고조건 질문에서 산식·분자/분모까지 부족으로 설정하고 양쪽 후속 검색을 했다.
   첫 사례는21호출·150.9초였다. 명시적 조사이므로 MAIN94의 자동 과제 제거로 없어지지 않는다.

잘 된 점
- 잘못 승인한 은행12% 연결을 최종 적용에서 제외하고 투자매매업자6% 원문을 찾아냈다.
- 외규에서 다른 외규를 참조하는 예외 기한·조건을 끝까지 확보했다.
- 제공하지 않은 별표9는 미확인으로 남기고 외규 원문과 판정 보류를 제시했다.

사례별 결과
"""
labels={'anchor-scope':'유지상한·보고조건','approved-scope':'승인 오연결·업권','reference-exception':'외규 연속 참조·예외','missing-source':'누락 별표'}
for c in cases:
    k=c['id'];r=metrics[k]
    summary+=f"- {labels[k]}: {r['status']}, {r['model_calls']}호출, {r['elapsed_seconds']:.1f}초. {review['cases'][k]['finding']}\n"
summary+=f"""
측정
실제 제품 모델46호출, 입력{total['input_tokens']:,}토큰·출력{total['output_tokens']:,}토큰.
공급자 사용량에 보고된 비용 ${total['cost_usd']:.8f}, 호출별/단계별 원시 사용량 보존.
전체 사례 소요시간 합계 {sum(r['elapsed_seconds'] for r in metrics.values()):.1f}초. p50/p95는4표본의 기술통계일 뿐이다.
고정 사례 목표3/4 통과. 전체 답변의 합성 의미 검토는2/4: 두 수치 사례의 상충 판정 실패.
이는 사전 목표와 별도 의미 판정을 구분한 결과이며, 실제 법률 정답률이나 GENOS 성능 인증이 아니다.

재현성과 한계
코드393파일 중 제품 동작은 MAIN94와 동일, 합성 데이터 승인 구성·종속 pin만 candidate snapshot에 격리했다.
공통 ExperimentClient와 기존 gateway 예산을 사용했고 모델/provider fallback·자동 반복 실행은 없었다.
서비스 진입에 격리 앱·단위 검색색인을 주입했다. 선택된 운영 데이터나 실제 GENOS 연결을 사용한 검증은 아니다.
작은 합성 사례·단회·한 평가자의 사후 원문 검토이며 개선안 A/B는 실행하지 않았다.
준비 중 기존 fulltext 경로 중복/arm 역할 오류2건은 모델0회 로그로 보존했다.
결과 원장의 gold 목록 정렬 오류는 원본을 압축 보존하고 집합·수치·판정이 같은 정렬만 수행했다.
MAIN94 선택·작업 제품 코드·GENOS·Git·메일은 변경하지 않았다.
결정: Proposed, decision_eligible=false, main_wiring=unchanged.
"""
(A/'RESULT.txt').write_text(summary)
old=(A/'README.md').read_text();front=old.split('---',2)[1]
parts=[
    '설계 탐침 완료. 필요한 조항10/10 회수와 원문 검증은 통과했으나 수치2사례에서 상충을 오판했다. 선택 개념 밖 승인 연결2개와 같은 원문 표시 중복1그룹도 확인했다. Proposed, MAIN unchanged.',
    'MAIN94는 내규 검색→개념 선정→승인 외규 우선 읽기/조사→항목 판단→대사표 경로다. 동일 검색과 자동 미확보 과제는 막지만, 승인 관계의 선택 범위와 LLM의 조사 목적·최종 판단은 별도다.',
    json.dumps(read(D/'criteria.json'),ensure_ascii=False,indent=2),
    '단일 observed arm,4사례1회씩 고정 순서. 기존 MAIN94 제품 동작·프롬프트·정책·예산 유지. 합성 원문과 시험 승인 관계2개만 구성했다. 기준과 gold는 제품 입력에 포함하지 않았다. 비교 arm이 없어 paired delta·회귀쌍은 해당 없다.',
    '합성7문서16조항, 기준 버전20261020-r1. 외부 Qwen3.8/Parasail FP8, reasoning none, temperature0, fallback 없음. exact revision과393파일·프로필·선택 포인터·원문/색인 해시는 artifacts/design/freeze.json에 있다. MAIN94는 maintenance release이므로 미존재 ADR 부모를 만들지 않고 정확 릴리스를 root binding으로 기록했다.',
    summary,
    json.dumps(review,ensure_ascii=False,indent=2),
    json.dumps({'totals':total,'retrieval':m['retrieval_accounting']},ensure_ascii=False,indent=2),
    '원문 회수·인용 문자 일치가 의미 판단을 보증하지 않는다. 연결 적용성 검사는 잘못 승인한 은행 조항을 배제했지만, 관련성 밖 승인 연결을 먼저 읽는 범위 누수와 숫자 차이를 충돌로 단정하는 판단은 남았다. 조사 범위 확장과 표시 중복은 정확 검색 중복과 다른 문제다.',
    '\n'.join(read(D/'criteria.json')['limitations'])+'\n한 평가자의 원문 기반 검토이며 독립 채점자 일치도를 측정하지 않았다. GENOS 내부 모델·Oracle·전체 MAIN corpus·실제 risk_cm105문항은 실행하지 않았다.',
    'MAIN unchanged. 고정 목표 미충족과 의미 오류를 보존하고, 제안4개를 후속 격리 A/B 대상으로 남긴다. 이번은 개선 코드나 승격 후보가 아니며 롤백할 운영 변경이 없다.',
    '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0955/prepare.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0955/preflight.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0955/run_sequence.py\n완료된 실행을 재사용/덮어쓰지 않는다. 재실행은 새 ADR과 예산을 사전 동결한다. 사후 집계: report.py → format_ledger.py → post_audit.py → finish.py. 원시 실패·입출력·사용량은 artifacts에 보존한다.',
]
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
(A/'README.md').write_text('---'+front+'---\n\n# ADR-0955: MAIN94 설계 취약점 탐침\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(zip(headings,parts),1))+'\n')
index=['# 실험 사례 인덱스','','단일 observed arm, 합성4사례. 기준답변은 제품에 비공개.']
for i,c in enumerate(cases,1):
    k=c['id'];P=O/'observed'/k;ld=next(x for x in ledger['runs'][0]['arms'][0]['cases'] if x['case_id']==k)
    rows=['| 단계 | before | added | discarded | after | gold after/total |','|---|---:|---:|---:|---:|---:|']
    rows += [f"| {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_after']}/{s['gold_total']} |" for s in ld['stages']]
    links=[]
    for p in sorted(P.glob('raw/call-*')):
        files=[x for x in p.iterdir() if x.is_file()]
        links.append('- '+p.name+': '+', '.join('['+f.name+']('+str(f.relative_to(A/'artifacts')).join(['../artifacts/',''])+')' for f in files))
    question=f"""# {k}

run-001 / observed / qwen/qwen3.8-27b / Parasail FP8 / 합성 사례 / 원시 exact payload 보존

## 사용자 질문 원문
{c['question']}

## 기준과 필수 원문 — 채점 전용, 제품 입력 비공개
{json.dumps(gold[k],ensure_ascii=False,indent=2)}

## 실제 답변
{(P/'answer.txt').read_text()}

## 제품·중간 호출 원값
원문 source corpus: [documents.json](../artifacts/design/documents.json).
제품에 보인 view·schema와 수용된 출력은 [canonical](../artifacts/run-001/observed/{k}/canonical)에,
system/user/schema·provider 원응답·usage는 아래 각 request.json/response.json/receipt에 생략 없이 저장했다.
{"\n".join(links)}

## 단계별 원문 회수·반환·인용
{"\n".join(rows)}
[전체 exact identity·gold·탈락 이유 원장](../artifacts/run-001/retrieval-ledger.json).

## 오프라인 판정
모델 judge 호출0. 합성 사전 기준에 대해 저장 답변·원문을 수동 검토했다.
{json.dumps(review['cases'][k],ensure_ascii=False,indent=2)}
{json.dumps(metrics[k],ensure_ascii=False,indent=2)}
paired comparison은 단일 arm이므로 해당 없다. 추가 관찰과 사전 통과 조건은 구분한다.
"""
    filename=f'질문-{i:03d}-{k}.md';(A/'실험'/filename).write_text(question)
    index.append(f"- [{k}]({filename}): {metrics[k]['status']}, {metrics[k]['model_calls']} calls; 사전 기준 {'통과' if all(review['cases'][k]['prospective_checks']) else '미충족'}, 의미 {'통과' if review['cases'][k]['answer_semantics_pass'] else '오류'}")
(A/'실험/README.md').write_text('\n'.join(index)+'\n')
registry=R/'04_EXPERIMENTS/ADR/README.md';s=registry.read_text()
entry='- [ADR-0955 MAIN94 설계 탐침](ADR-0955-main94-design-weakness-probe/README.md) — 합성4사례 실제 Qwen46호출, 필수원문10/10·원문불일치0. 수치2건 상충 오판, 개념 밖 승인연결2개, 동일 원문 중복표시 확인. Proposed, MAIN94 불변.\n'
assert 'ADR-0955 MAIN94 설계 탐침' not in s
first=s.index('\n');registry.write_text(s[:first+1]+'\n'+entry+s[first+1:])
print(summary)

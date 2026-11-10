"""Record the golden-article match (no semantic grading, per user instruction) and fill README/manifest."""
from common import *
import csv,statistics,subprocess
P=read(Path(__file__).with_name('recall_params_1468.json'))
rows=read(ART/'review-input.json')['rows'];audit={c['case_id']:c for c in read(ART/'source-wire-audit.json')['cells']}
def tsets(a):
    out={}
    for r in read(ROOT/'04_EXPERIMENTS/ADR'/a/'artifacts/review-input.json')['rows']:
        for t in r['targets']:
            if t['role']=='required':out[(r['case_id'],t['law'],t['article'])]=t['acquired']
    return out
cur={(r['case_id'],t['law'],t['article']):t['acquired'] for r in rows for t in r['targets'] if t['role']=='required'}
cmp={}
for name,a in P['priors'].items():
    X=tsets(a);cmp[name]={'acquired':sum(X.values()),'gain':[list(k) for k in cur if cur[k] and not X[k]],'loss':[list(k) for k in cur if X[k] and not cur[k]]}
stats={'physical_calls':sum(c['physical_calls'] for c in audit.values()),'unknown':sum(c['unknown'] for c in audit.values()),
 'reported_cost_usd':round(sum(c['reported_cost_usd'] for c in audit.values()),6),'request_seconds_median':round(statistics.median(r['request_seconds'] for r in rows),1),
 'request_seconds_total':round(sum(r['request_seconds'] for r in rows)),'required_acquired':sum(r['required_acquired'] for r in rows),'required_cited':sum(r['required_cited'] for r in rows),
 'required_total':sum(r['required_total'] for r in rows),'source_mismatches':sum(len(c['source_mismatches']) for c in audit.values()),'acl_violations':sum(len(c['acl_violations']) for c in audit.values()),
 'http_status':{str(k):sum(1 for r in rows if r['http_status']==k) for k in sorted({r['http_status'] for r in rows})}}
G={r['case_id']:[f"확보 {r['required_acquired']}/{r['required_total']}",f"인용 {r['required_cited']}/{r['required_total']}",'필수 조문 일치만 집계(답변 의미 채점 없음)'] for r in rows}
put(ART/'grades.json',{'grades':G,'stats':stats,'comparisons':cmp,'grader':'golden required-article match only (acquired paths / cited sources); no semantic grading and no judge model, per user instruction 2026-11-09'})
with (ART/'CM51_결과.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['case_id','http_status','required_acquired','required_cited','required_total','acquired_articles','seconds','physical_calls','question'])
    for r in rows:w.writerow([r['case_id'],r['http_status'],r['required_acquired'],r['required_cited'],r['required_total'],'; '.join(r.get('acquired_articles',[])),round(r['request_seconds'],1),r['physical_calls'],r['question']])
S=stats;A,Ci,T=S['required_acquired'],S['required_cited'],S['required_total']
def fill(p,pairs):
    t=p.read_text()
    for old,new in pairs:
        assert old in t,(p,old[:60]);t=t.replace(old,new,1)
    p.write_text(t)
gl=lambda n:'·'.join(f"{k[0][3:]} {k[2]}" for k in cmp[n]['gain']) or '-'
ll=lambda n:'·'.join(f"{k[0][3:]} {k[2]}" for k in cmp[n]['loss']) or '-'
fill(ADR/'README.md',[
 ('TODO: 채택·기각·보류와 운영 배선 변경 여부를 먼저 적는다.',P['summary'].format(A=A,C=Ci,T=T,**S)),
 ('TODO: 관찰된 문제, 기존 흐름, 재현 가능한 실패를 적는다.',P['problem']),
 ('### 가설\n\nTODO','### 가설\n\n'+P['hypothesis']),
 ('TODO: primary metric, 비열등 한계, 허용 회귀 수, 비용·지연 한계를 실행 전에 고정한다.','design/criteria.json(실행 전 동결)의 원문/ACL/전송 불일치 0·예산 500호출/$4/150분. 사용자 지시(2026-11-09 "최종 선택한 문서들이 골든셋과 얼마나 동일한지만, llm 저지 필요없음")로 지표는 필수 조문 98개의 확보(읽은 원문 경로)·인용(답변 근거) 일치만 쓴다. 동결 기준의 문항별 PASS/PARTIAL/FAIL 채점은 하지 않았다(편차 기록).'),
 ('### 반증 기준\n\nTODO','### 반증 기준\n\n원문/ACL/전송 불일치, 예산 초과, 필수 조문 확보가 ADR-1465(77/98) 이하.'),
 ('| baseline | TODO | TODO | baseline |','| baseline | 참조만: ADR-1465 하이브리드(RRF) | 같은 문항·같은 집계 | baseline |'),
 ('| candidate | TODO | TODO | candidate |','| candidate | '+P['arm']+' | 같은 프로필·범위 44문서·같은 원문 세대 | candidate |'),
 ('- 데이터셋과 버전: TODO','- 데이터셋과 버전: financial CM 51(cm-field-core-e2e-v3), 원문 세대 latest-selection-20261015-r1(d4d1d8b4…)'),
 ('- frozen source와 SHA-256: TODO','- frozen source와 SHA-256: artifacts/design/live-cases.json '+sha(DES/'live-cases.json')),
 ('- 반복 수와 다수결: TODO','- 반복 수와 다수결: 문항당 1회, 다수결 없음'),
 ('- 법령·기준답변 버전 점검: TODO','- 법령·기준답변 버전 점검: 등록 필수 조문을 현재 저장 원문 좌표로 대조, 판정 모델 없음'),
 ('| baseline | TODO | TODO | - | TODO | TODO |','| baseline | ADR-1464 벡터만 / ADR-1465 하이브리드 | 확보 74/98·인용 66 / 확보 77/98·인용 68 | - | 291회·$1.41 / 295회·$1.43 | - |'),
 ('| candidate | TODO | TODO | TODO | TODO | TODO |',f"| candidate | {P['arm_short']} | 확보 {A}/{T}·인용 {Ci} | 1465 대비 +{len(cmp['1465']['gain'])}/-{len(cmp['1465']['loss'])} | {S['physical_calls']}회·${S['reported_cost_usd']:.2f} | 중앙 {S['request_seconds_median']}초 |"),
 ('| 비교 arm만 정답 | TODO | TODO |',f"| 비교 arm만 확보(1465 대비) | {len(cmp['1465']['gain'])} | {gl('1465')} |"),
 ('| 기준 arm만 정답(회귀) | TODO | TODO |',f"| 기준 arm만 확보(1465 대비) | {len(cmp['1465']['loss'])} | {ll('1465')} |"),
 ('| 둘 다 정답 | TODO | TODO |','| 둘 다 확보 | '+str(A-len(cmp['1465']['gain']))+' | artifacts/CM51_결과.csv |'),
 ('| 둘 다 오답 | TODO | TODO |','| 둘 다 미확보 | '+str(T-A-len(cmp['1465']['loss']))+' | artifacts/grades.json |'),
 ('| TODO | TODO | TODO | TODO |',P['taxonomy']),
 ('| 전체 corpus | TODO | TODO |','| 전체 corpus | 요청 범위 44문서, 벡터 19문서 | article root 단위 |'),
 ('| 필터 전/후 후보 | TODO | TODO |','| 필터 전/후 후보 | '+P['filter']+' | 문항당 |'),
 ('| LLM 제시 수 | TODO | 평균·p50·p95 |','| LLM 제시 수 | 첫 화면 20 | 평균·p50·p95 |'),
 ('| golden recall | TODO | TODO |',f"| golden recall | 필수 조문 확보 {A}/{T}·인용 {Ci} | ADR-1464 74·ADR-1465 77 |"),
 ('| 제시 비율 | TODO | 제시 수 / 전체 corpus |','| 제시 비율 | 미집계 | 제시 수 / 전체 corpus |'),
 ('| LLM 호출·토큰·지연 | TODO | TODO |',f"| LLM 호출·토큰·지연 | {S['physical_calls']}회·${S['reported_cost_usd']:.3f}·결과 불명 {S['unknown']} | 요청 합계 {S['request_seconds_total']}초 |"),
 ('| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |',f"| run-001 | candidate | 16 | {len(rows)} | {S['physical_calls']} | 0 | ${S['reported_cost_usd']:.2f} | {S['request_seconds_total']}초 | {S['source_mismatches']} | {S['acl_violations']} |"),
 ('TODO: 결과가 어떤 가정을 지지·반증하는지 사실과 추론을 분리한다.',P['interpretation']),
 ('TODO: 인샘플 여부, 표본 크기, judge 변동성, 데이터·법령 버전 한계를 적는다.','계획 16문항 중 7문항 완료·1문항 자원 중단·8문항 미실행. 모두 이전 실험 진단에 쓴 알려진 질문(in-sample), 1회. 지표는 필수 조문 경로 일치이며 답변의 의미 정확도는 채점하지 않았다(사용자 지시). 1회 실행의 문항별 편차가 차이 폭과 비슷하다.'),
 ('TODO: 메인 배선 여부, 유지할 진단 부품, 롤백 trigger를 적는다.',P['wiring']),
 ('```bash\nTODO\n```','```bash\ncd 06_TOOLS/EXPERIMENTS/'+P['dir']+'\nexport ADR_TARGET=1468\npython setup.py && python embed_server.py --port 8765 --profile-files <design/embed-profile-files.json> --log <artifacts/embed-server> &\npython live_hybrid.py cm-051 --preflight && python batch.py\npython audit.py && python collect_review.py && python finalize_1468.py\n```'),
])
E=ADR/'실험';qs=[]
grading={g['id']:g for g in read(DES/'grading-only.json')}
for i,r in enumerate(rows,1):
    c=r['case_id'];f=f'질문-{i:03d}-{c}.md'
    req='\n'.join(f"- {t['law']} {t['article']}: 확보 {'예' if t['acquired'] else '아니오'}, 인용 {'예' if t['cited'] else '아니오'}" for t in r['targets'] if t['role']=='required') or '- (필수 조문 없음)'
    t=(f"# {c}\n\n## 1. 실행 메타\n\n{P['arm_short']} 스냅숏, 하이브리드 환경(선택 세대 SQLite 원문, Oracle Gold bge-m3 벡터), Qwen3.8 Parasail/none, 출력상한 없음, 외규 모드, 1회. HTTP {r['http_status']}.\n\n"
       f"## 2. 사용자 질문 원문\n\n{r['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n{grading[c]['reference_answer']}\n\n"
       f"## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/{c}-candidate (canonical 입력).\n\n"
       f"## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c}-candidate/raw, 물리 {r['physical_calls']}회, 결과 불명 {1 if r['unknown'] else 0}.\n\n"
       f"## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n판정 모델 0. 필수 조문 좌표 일치만 집계.\n\n"
       f"## 8. 사례 최종 판정\n\n필수 조문 확보 {r['required_acquired']}/{r['required_total']}, 인용 {r['required_cited']}/{r['required_total']}\n\n{req}\n")
    (E/f).write_text(t);qs.append({'number':i,'case_id':c,'file':f,'sha256':sha(E/f),'grade':G[c][0]})
idx='\n'.join(f"| {q['number']:03d} | `{q['case_id']}` | `run-001` | {G[q['case_id']][0]} | {G[q['case_id']][1]} | 필수 조문 일치 | [{q['file']}]({q['file']}) |" for q in qs)
fill(E/'README.md',[('- 이 분기의 변경 가설: TODO','- 이 분기의 변경 가설: '+P['hypothesis']),
 ('| `baseline` | baseline | ROOT | TODO | TODO |','| `baseline` | baseline | ROOT | ADR-1464 벡터만·ADR-1465 하이브리드 참조 | 미실행 |'),
 ('| `candidate` | candidate | baseline | TODO | TODO |',f"| `candidate` | candidate | baseline | {P['arm_short']} | 16문항 중 7 완료·자원 중단 |"),
 ('| - | - | - | - | - | - | 질문 단위 평가 없음 |',idx),
 ('- arm별 정답: TODO',f"- arm별 정답: 의미 채점 없음. 필수 조문 확보 {A}/{T}·인용 {Ci} (ADR-1464 74·66, ADR-1465 77·68)"),
 ('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO',f"- 사전 지정 비교쌍별 신규 정답 / 회귀: ADR-1465 대비 확보 +{len(cmp['1465']['gain'])} / -{len(cmp['1465']['loss'])}"),
 ('- judge 불일치: TODO','- judge 불일치: 판정 모델 없음'),
 ('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |',f"| `run-001` | candidate | {len(rows)} | {S['physical_calls']} | {S['unknown']} | ${S['reported_cost_usd']:.2f} | {S['request_seconds_total']}초 | {A}/{T} | artifacts/CM51_결과.csv |")])
m=read(E/'manifest.json');m['questions']=qs;put(E/'manifest.json',m)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',artifact_path=str((ART/'review-input.json').relative_to(ROOT)),sha256=sha(ART/'review-input.json'))
m['results']={'status':'complete','by_arm':{'candidate':{'questions':len(rows),'planned':16,'stopped':'cm-018 worker swap growth above 128MiB (resource guard), 8 not executed',**{k:S[k] for k in S}},'baseline':{'reference':'ADR-1464 vector-only / ADR-1465 hybrid RRF','required_acquired':'74 / 77','required_cited':'66 / 68'}},
 'comparisons':[{'metric':'required acquired','adr1464':74,'adr1465':77,'candidate':A},{'metric':'required cited','adr1464':66,'adr1465':68,'candidate':Ci},
   {'metric':'vs ADR-1465 gained','articles':cmp['1465']['gain']},{'metric':'vs ADR-1465 lost','articles':cmp['1465']['loss']},*P.get('extra_comparisons',[])],
 'judge_disagreements':None,'usage':{'physical_calls':S['physical_calls']},'latency':{'request_seconds_total':S['request_seconds_total'],'request_seconds_median':S['request_seconds_median']},
 'error_taxonomy':P['error_taxonomy'],'deviation':'Per user instruction 2026-11-09 only the golden required-article match is recorded; the frozen per-question PASS/PARTIAL/FAIL grading was not performed.','grades_by':'artifacts/grades.json (article match only)'}
put(ADR/'실험/manifest.json',m)
subprocess.run([sys.executable,str(Path(__file__).with_name('manifest.py')),P['adr']],check=True,cwd=Path(__file__).parent)
print('ok',A,Ci,T,S)

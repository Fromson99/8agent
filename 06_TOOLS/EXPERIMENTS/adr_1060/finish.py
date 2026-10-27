"""Bundle successful audit observations; correct only the new ledger arm label."""
from run import ROOT,ADR,ART,PRIOR,P,read,save,sha,rel
import sys,copy,sqlite3,json,statistics
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1059'))
import wire_audit
from exact_wire_audit import restore,test_rejection
f=read(P/'design-freeze.json');fixed=read(ART/'design-freeze.json')
assert all(sha(ROOT/p)==h for p,h in fixed['files'].items())
assert all(sha(ROOT/r['path'])==r['sha256'] for r in read(P/'manifest.json')['files'])
cs=wire_audit.load_frozen_codecs(f);cs['restore']=restore
from lawrag.runtime.retrieval_stage_ledger import (_capture_projection,_capture_without_hash,
    deterministic_sha256,grade_capture,build_run_artifact,build_experiment_artifact)
ledgers=[];cells=[];attempts=tests=0
for cell in f['execution_order']:
    name=f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}";out=ART/'matrix'/name;src=P/'matrix'/name
    metrics=read(out/'metrics.json');assert not metrics['source_integrity']['failures'] and metrics['source_integrity']['mismatch_count']==0
    assert metrics['request_acl_check']=='CHECKED'
    for p in src.glob('runtime/legal-agent/runs/*/*/journal.sqlite'):
        with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row;_,failures=wire_audit.journal_records(db,cs,rel(p));assert not failures
            attempts+=db.execute('SELECT count(*) FROM model_attempt').fetchone()[0]
            receipts={json.loads(r[0]).get('attempt_id'):json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='MODEL_INPUT_PROJECTION'")}
            for row in db.execute('SELECT a.attempt_id,a.request_json,v.body_json FROM model_attempt a JOIN model_view v USING(view_id)'):
                receipt=receipts.get(row['attempt_id'],{})
                if 'navigation_values' not in receipt:continue
                stored=json.loads(row['body_json']);expected=cs['compact'](cs['navigation'](stored).view(stored),stored['phase'])
                test_rejection(expected,wire_audit.request_view(json.loads(row['request_json'])),receipt);tests+=3
    value=read(out/'retrieval-ledger-case.json');capture=_capture_projection(value)
    capture['capture_sha256']=deterministic_sha256(_capture_without_hash(capture))
    value=grade_capture(capture,value['gold_identities']);save(out/'retrieval-ledger-case.json',value);ledgers.append(value)
    cells.append({'case_id':cell['case_id'],'answer_coverage':metrics['answer_coverage'],
        'source_integrity':metrics['source_integrity'],'request_acl_check':metrics['request_acl_check'],
        'metrics_path':rel(out/'metrics.json'),'metrics_sha256':sha(out/'metrics.json')})
assert attempts==21
save(ART/'retrieval-ledger.json',build_experiment_artifact('ADR-1060','ADR-1060-experiment-v1',
    [build_run_artifact('run-001',ledgers,{'wire-audit':['original_read','delivered','final_cited']})]))
result={'status':'complete','cells':cells,'actual_requests_verified':attempts,'corruption_rejection_checks':tests,
    'live_model_calls':0,'source_integrity_failures':0,'parent_preserved':True,'semantic_grade_changed':False,
    'bundle_repair':'Initial output bundler changed the audit arm label without rebuilding capture hash. Retained audit.log; rebuilt only new audit ledger hashes through the frozen validator. No product or source changes.'}
save(ART/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results']={'status':'complete','by_arm':{'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None},
    'wire-audit':{'status':'complete','total':3,'correct':None,'accuracy':None,'requests_verified':attempts}},
    'comparisons':[],'judge_disagreements':None,'usage':{'model_calls':0},'latency':{},'error_taxonomy':[]}
counts=[v['stages'][-1]['after_count'] for v in ledgers];gt=sum(v['gold_total'] for v in ledgers);ga=sum(v['stages'][-1]['gold_after'] for v in ledgers)
m['retrieval_accounting'].update(presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=max(counts),golden_recall=ga/gt,selectivity=statistics.mean(counts)/m['retrieval_accounting']['corpus_total'])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
questions={v['case_id']:v['question'] for v in read(ROOT/f['product_cases_path'])['cases']};m['questions']=[]
for i,row in enumerate(cells,1):
    cid=row['case_id'];p=ADR/'실험'/f'질문-{i:03d}-{cid}.md'
    p.write_text(f'''# 질문{i:03d} — {cid}

## 1. 실행 메타
ADR1060 / run-001 / wire-audit.1059 실제 저장 요청의 사후 검사만 수행. 새 모델 호출0회.

## 2. 사용자 질문 원문
{questions[cid]}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
1059의 승인 평가 좌표를 제품 선택 후 동일하게 결합한다. 의미 채점 변경 없음.

## 4. 제품 입력을 구성한 원값
[1059 실제 기록](../../{PRIOR.name}/artifacts/matrix/{i:03d}-{cid}-A0/). 같은 파일을 읽기 전용 참조한다.

### 회수·탈락 단계 원장 — run·arm별
[사후 원장](../artifacts/retrieval-ledger.json). 전체 후보를 페이지에서 추정하지 않는다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
새 호출 없음.1059의 request/response/schema/usage는 그대로다. [새 전달 검사](../artifacts/matrix/{i:03d}-{cid}-A0/metrics.json).

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
없음. 압축 표와 저장 원문·상태를 코드로 정확히 복원·검사한다.

## 7. 채점 호출과 반복 판정
judge0회, 법률 정답 판정 변경 없음. [검사 결과](../artifacts/result.json).

## 8. 사례 최종 판정
원문 불일치0, 실제 전송 복원 오류0, 권한 확인. 답변 범위는 기존 {row['answer_coverage']} 그대로다.
''')
    m['questions'].append({'number':i,'case_id':cid,'file':p.name,'sha256':sha(p)})
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약',f'1059의 실제 요청21개 모두 원문·상태에 정확히 복원됐다. 추가 모델 호출0회.변조 거부{tests}검사도 통과했다. 이전 집계는 보존하고 새 결과를 별도 저장했다.'),
('문제와 변경 전 구조','공통 값 번호는 요청 안에서만 유효하다. 저장 JSON의 키 순서로 번호를 다시 만들면서8개 요청의 감사 hash 대조가 실패했으나 실제 전송표를 풀면 원래 값과 동일했다.'),
('가설과 사전 판정 기준','artifacts/implementation-plan.json. 실제 표의 hash·버전·내용을 검사하고 서버 정본과 모든 필드·범위·상태를 대조한다. 잘못된 값과 stale 상태는 거부한다.'),
('실험 설계','1059/compact-input의3완료 셀·21요청 전수 사후 감사. 제품 동작·모델·데이터·답변·사용량을 바꾸지 않는다. 실제 전송 검사의 수정이지 법률 정답 재채점이 아니다.'),
('데이터·모델·재현성','artifacts/design-freeze.json으로 입력 기록과 감사 코드를 검사 전에 고정했다. 기존 동결의 순수 presentation 코드만 allowlist로 불러온다. 원기록은 읽기 전용 링크로 참조하고 source DB는 공유한다.'),
('결과',f'21요청 복원 성공,3질문의 원문 span 합계{sum(r["source_integrity"]["evidence_count"] for r in cells)}개 불일치0·전달 검사 오류0·권한 확인. 질문 해결 여부는 PARTIAL/INSUFFICIENT 그대로다. artifacts/result.json 참조.'),
('사례별 오류 분석','검사기의 번호 재생성 가정을 제거했다. 실제 수신/전송 payload는 바꾸지 않았다. 최종 원장 묶음의 arm 이름 변경 시 capture hash 재생성이 빠진 포장 오류는 audit.log에 보존하고 표준 생성·검증 함수로 새 원장만 바로잡았다.'),
('비용·지연·회수 규모','새 모델·채점 비용0, 회수·선택 변화0. 실제 전송 범위 집계만 복원했으며 이전 출력·usage·gold는 그대로다. artifacts/retrieval-ledger.json 참조.'),
('해석','번호 재생성의 비결정성과 실제 전달 내용의 손상을 구분한다. 실제 표를 복원한 값·원문·권한·상태의 독립 비교가 통과해야 전달로 인정한다.'),
('한계와 일반화 가능 범위','이번21요청의 무손실·권한 검사다. 입력 한도 확대나 모델 판단 품질 인증이 아니다.1059의 부족한 법률 답변은 계속 미완료로 남긴다.'),
('운영 결정·롤백 조건','MAIN103·GENOS·1059 동결 제품 코드 및 원결과 보존. 향후 같은 참조표의 감사에는 이 읽기 전용 adapter를 사용하며, hash 불일치에서 멈춘다.'),
('재현 명령','새 모델 호출 없이 .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1060/finish.py로 원기록 복원·변조 거부를 다시 확인할 수 있다. run.py는 신규 출력 폴더를 요구하며 완료 결과를 덮어쓰지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n# 실제 전송 참조표 감사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 전송21요청 사후 감사\n\n[결과](../artifacts/result.json) · [원장](../artifacts/retrieval-ledger.json)\n')
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1060','created_at':m['reservation']['created_at'],
    'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Isolated read-only audit artifact or exact link',
        'contains_raw_prompts_and_outputs':p.name in ('request.json','response.json')}
        for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
print(json.dumps(result,ensure_ascii=False))

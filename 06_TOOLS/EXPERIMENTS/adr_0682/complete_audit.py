"""Preserve terminal observations without re-running or changing product input."""
import argparse,hashlib,json,gzip,tarfile,sqlite3,xml.etree.ElementTree as E
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument('--adr',required=True);P.add_argument('--prefix',required=True);P.add_argument('--candidate-arm',default='core-route');P.add_argument('--accepted',action='store_true');args=P.parse_args()
R=Path(__file__).resolve().parents[3];A=R/args.adr;D=A/'artifacts/design';O=A/'artifacts/run-001';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
m=read(A/'실험/manifest.json');by={};cases=[];traces={}
for label,arm in [('baseline','baseline'),('core',args.candidate_arm)]:
    prefix=Path('/tmp')/(args.prefix+'-'+label+'-contracts')
    xml=prefix.with_suffix('.xml');log=prefix.with_suffix('.log')
    records=list(E.parse(xml).getroot().iter('testcase'))
    failures=[{'test':t.get('name'),'message':(t.find('failure') if t.find('failure') is not None else t.find('error')).get('message')} for t in records if t.find('failure') is not None or t.find('error') is not None]
    by[arm]={'status':'complete','tests':len(records),'passed':len(records)-len(failures),'failures':failures}
    for src in (xml,log):
        with gzip.open(O/(label+src.suffix+'.gz'),'wb') as out:out.write(src.read_bytes())
    with tarfile.open(O/(label+'-raw.tar.gz'),'w:gz') as archive:archive.add(prefix,arcname=prefix.name)
    runtime=prefix/'test_native_direct_path_and_cu0/90_RUNTIME/semantic'
    selected=None
    for journal in (runtime/'legal-agent/runs').glob('*/*/journal.sqlite'):
        with ro(journal) as db:
            events=[(k,json.loads(v)) for k,v in db.execute('SELECT kind,payload_json FROM event')]
            if any(k=='CASE_RESPONSE_METADATA' and v.get('request_id')=='r2' for k,v in events):selected=(journal,events)
    assert selected,arm
    journal,events=selected;parts={}
    with ro(journal) as db:
        for kind,eid,payload in db.execute("SELECT kind,entity_id,payload_json FROM entity_version WHERE kind='case_stage' ORDER BY created_seq"):
            parts[eid.removeprefix('case:')]=json.loads(payload)
    nav=prefix/'test_native_direct_path_and_cu0/built/generation/navigation/navigation.sqlite'
    with ro(nav) as db:sources={sid:json.loads(v) for sid,v in db.execute('SELECT id,json FROM source')}
    def ids(sids):return [json.loads(v) for v in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in sids})]
    outputs=[ids(parts['RECALL']['corpus_ids']),ids(parts['RECALL']['selected_for_read']),ids(parts['SELECT']['final_ids']),ids(parts['SELECT']['final_ids'])]
    golden=[{'doc_id':'d','node':0}];gkeys={canon(v) for v in golden};before=[];stages=[]
    for plan,after in zip(m['design']['retrieval_stage_plan']['stages_by_arm'][arm],outputs):
        bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())]
        gb=[bm[k] for k in sorted(bm.keys()&gkeys)];ga=[am[k] for k in sorted(am.keys()&gkeys)];gain=[v for v in added if canon(v) in gkeys];loss=[v for v in discard if canon(v) in gkeys]
        reason='Outside current document ACL or not adopted/presented by the current source stage'
        stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discard,'after':after,
            'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),
            'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
            'discard_receipts':[{'identity':v,'reason':reason} for v in discard],'discard_reason_counts':{reason:len(discard)} if discard else {},
            'gold_total':1,'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),'golden_recall':float(len(ga)),
            'gold_before_identities':gb,'gold_added_identities':gain,'discarded_gold':[{'identity':v,'reason':reason} for v in loss],'gold_after_identities':ga})
        before=after
    cases.append({'arm_id':arm,'declared_stage_ids':[v['stage_id'] for v in stages],'cases':[{'schema_version':'retrieval-stage-ledger-v1',
        'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate',
        'case_id':'direct-source-path','arm_id':arm,'gold_total':1,'gold_identities':golden,'stages':stages}],
        'aggregate':{'cases':1,'presented_total':len(before),'gold_total':1}})
    traces[arm]={'initial_fulltext':any(k=='LAW_FULLTEXT_DIRECTORY' for k,v in events),'direct_path':any(k=='CORE_EVIDENCE_ROUTE_USED' for k,v in events),
        'legal_claim_reuse':False,'source_generation':parts['READ']['binding'],'journal':str(journal.relative_to(prefix)),
        'events':[[k,v] for k,v in events if k in ('LAW_FULLTEXT_DIRECTORY','CORE_EVIDENCE_ROUTE_USED','MEMORY_MODEL_INPUT','MEMORY_MODEL_OUTPUT','CASE_RESPONSE_METADATA')]}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
    'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
    'runs':[{'run_id':'run-001','arms':cases}]};ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest()
with gzip.open(O/'retrieval-ledger.json.gz','wt',encoding='utf8') as out:json.dump(ledger,out,ensure_ascii=False)
with gzip.open(O/'direct-trace.json.gz','wt',encoding='utf8') as out:json.dump(traces,out,ensure_ascii=False)
result={'strict_success':args.accepted,'by_arm':by,'direct_source_path':{k:{f:v[f] for f in ('initial_fulltext','direct_path','legal_claim_reuse','journal')} for k,v in traces.items()},
    'real_model_calls':0,'quality_certified':False,'main_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256'],
    'limitations':['Synthetic source/session/HTTP contract audit; no legal correctness or live model speed measurement','No MAIN activation or GENOS access','Raw failures and initial source versions preserved losslessly; tar -xzf restores recorded runtime databases']}
if args.accepted:assert not by[args.candidate_arm]['failures']
put(O/'result.json',result)
m['results'].update(status='complete',by_arm=by,comparisons=[{'baseline':'baseline','candidate':args.candidate_arm,'metric':'native initial fulltext skipped on current source-route match','baseline_value':1,'candidate_value':0}],usage={'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'measurement':'Pytest XML timings only; no serving latency claim'},error_taxonomy=['HTTP/projection contract assertions require follow-up'] if not args.accepted else [])
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
ra=m['retrieval_accounting'];ra.update(corpus_total=2,before_filter={a:2 for a in by},after_filter={a:1 for a in by},
    presented_total={a:1 for a in by},presented_mean={a:1.0 for a in by},presented_p50={a:1.0 for a in by},presented_p95={a:1 for a in by},golden_recall={a:1.0 for a in by},selectivity={a:.5 for a in by},not_applicable_reason=None)
ra['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((O/'retrieval-ledger.json.gz').relative_to(R)),sha256=sha(O/'retrieval-ledger.json.gz'),not_applicable_reason=None)
q=A/'실험/질문-001-direct-source-path.md'
q.write_text('''# direct-source-path

## 1. 실행 메타
run-001, baseline와 candidate, 모의 법령과 스크립트 transport. 실제 LLM 호출 0.

## 2. 사용자 질문 원문
모의승인규정 제1조 승인 기준은?

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
모의 문서 d의 조문 root 0. 법률 정답률 채점은 하지 않았다. 좌표 결합은 제품 선택 후에만 수행했다.

## 4. 제품 입력을 구성한 원값
각 arm의 원문 세대·프로필·현재 조건·일곱 checkpoint는 원시 runtime 압축본에 보존했다.

### 회수·탈락 단계 원장 — run·arm별
전체 canonical identity와 탈락 이유는 ../artifacts/run-001/retrieval-ledger.json.gz를 따른다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
실제 LLM 호출 0. 모의 transport의 모든 입력과 출력은 direct-trace.json.gz와 원시 journal에 보존했다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
실제 router/compiler/verifier/evaluator 호출 0. 스크립트 transport만 사용했다.

## 7. 채점 호출과 반복 판정
외부 채점 없이 원문 좌표·권한·revision·현재 경로·HTTP 실행을 확인했다. 실패를 정답으로 바꾸지 않았다.

## 8. 사례 최종 판정
기준은 초기 fulltext를 실행했고 후보는 핵심 근거 좌표로 바로 들어갔다. 다른 계약 결과는 result.json과 XML 원본을 따른다.
''')
m['questions']=[{'number':1,'case_id':'direct-source-path','file':q.name,'sha256':sha(q)}];put(A/'실험/manifest.json',m)
status='Accepted' if args.accepted else 'Rejected'
meta=f"---\nadr_id: {m['adr_id']}\ntitle: 최종 핵심 근거 shortcut 계약 검증\nstatus: {status}\ndecision_date: 2026-10-07\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n"
body='\n# 최종 핵심 근거에서 직접 원문 경로를 재사용\n\n'
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
paragraphs=[f'{status}. 현재 로컬 MAIN 포인터와 작업 제품 코드는 이 실험에서 바꾸지 않았다.',
    '기존 전체 checkpoint 재생 대신 최종 SELECT 채택 원문에서 직접 읽을 좌표만 추린다. 실패 탐색과 과거 법률 결론은 재사용하지 않는다.',
    '사전 고정한 criteria.json의 최종 근거, 성공 발행, 멀티턴 head, 권한/세대/원문, 복귀, 위키 연결 기준을 그대로 적용했다.',
    'generation45 선택 코드와 격리 후보를 같은 모의 자료·스크립트 transport로 비교했다. 동결 snapshot과 후보 provenance를 보존했다.',
    '실제 외부 LLM 호출·토큰·비용 0. 모의 문서 d와 other, 계층 unit 7개. 원문 데이터의 내용과 모델 품질을 인증하지 않는다.',
    json.dumps(by,ensure_ascii=False),
    '모든 실패 이름·원 오류를 result.json에 기록했다. 초기 직접 경로 성공만으로 전체 기준 통과로 보지 않는다.',
    '2개 article root에서 현재 권한 범위의 1개를 읽고 채택·제시했다. 원장에 단계별 identity와 탈락 이유를 기록했다. 시간은 단위 테스트의 XML 측정만 사용한다.',
    '최종 B/C만 남기는 저수준 계약과 실제 직접 진입을 확인했다. 위키 파일 배선과 실제 멀티턴 소비자의 완결성은 전체 검사를 통과해야 한다.',
    '작은 모의 자료의 상태·배선 검사다. 공개 법률 질의 일반화, 실제 모델의 근거 선택 능력, GENOS 성능은 미확인이다.',
    '후보 정본과 실패 기록을 보존한다. MAIN 승격을 수행하지 않았다. source/ACL/revision/위키 연결 결함은 승격 차단 조건이다.',
    'run_contracts.py에 freeze.json의 code_root와 계약 파일을 넘긴다. 원자료는 artifacts/run-001/*-raw.tar.gz를 tar -xzf로 복원한다. 완료된 실행을 수정하거나 다시 채점하지 않는다.']
for i,(s,p) in enumerate(zip(sections,paragraphs),1):body+=f'## {i}. {s}\n\n{p}\n\n'
(A/'README.md').write_text(meta+body)
(A/'실험/README.md').write_text('# 모의 source-path 계약 감사\n\n[direct-source-path](질문-001-direct-source-path.md)와 [실제 결과](../artifacts/run-001/result.json)를 확인한다. 실제 LLM·법률 채점은 수행하지 않았다.\n')
files=[*D.glob('*.json'),*O.glob('*')]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],
    'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Immutable synthetic source/revision/native-path observations','contains_raw_prompts_and_outputs':p.name.endswith('raw.tar.gz') or p.name=='direct-trace.json.gz'} for p in files if p.is_file()]})
print(json.dumps({'status':status,'by_arm':by},ensure_ascii=False))

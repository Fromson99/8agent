"""Offline gold join and complete v4 accounting; never imported by product."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[3]
ARMS = ['baseline','graph']
SCHEMA = 'retrieval-stage-ledger-v1'
UNIT = 'case_id + canonical article-root coordinate'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v): return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def encoded(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def keys(values): return {encoded(v) for v in values}
def identities(values): return [json.loads(v) for v in sorted(set(values))]


def stage(plan,b,a,g,reason,executed=True):
    b,a,g = keys(b),keys(a),keys(g);added=a-b;discarded=b-a
    receipts = [{'identity':json.loads(v),'reason':reason} for v in sorted(discarded)]
    return {**plan,'executed':executed,'skip_reason':'' if executed else 'NOT_EXECUTED_AFTER_EARLY_STOP',
        'before':identities(b),'added':identities(added),'discarded':identities(discarded),'after':identities(a),
        'before_count':len(b),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(a),
        'occurrence_counts':{'before':len(b),'after':len(a),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
        'discard_receipts':receipts,'discard_reason_counts':{reason:len(discarded)} if discarded else {},
        'gold_total':len(g),'gold_before':len(g&b),'gold_added':len(g&added),'gold_discarded':len(g&discarded),
        'gold_after':len(g&a),'golden_recall':len(g&a)/len(g) if g else None,
        'gold_before_identities':identities(g&b),'gold_added_identities':identities(g&added),
        'gold_after_identities':identities(g&a),'discarded_gold':[r for r in receipts if encoded(r['identity']) in g]}


def journal_reads(out):
    ids = set();paths=[]
    for p in out.rglob('journal.sqlite'):
        with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
            ids.update(row[0] for row in db.execute('SELECT source_id FROM evidence_unit'))
        paths.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p)})
    return sorted(ids),paths


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adr',required=True);args=parser.parse_args()
    adr=ROOT/args.adr;run=adr/'artifacts/run-001'
    if not (run/'result.json').exists():run=adr/'artifacts/native-contracts'
    m=read(adr/'실험/manifest.json');data=read(run/'result.json')
    if data['status']!='complete':raise ValueError('incomplete run')
    # The native fulltext object is shared. Diagnostic wrappers retained older
    # lists, so end-of-run aggregate FTS arrays include later cases. Per-case
    # immutable receipts were serialized at completion and remain exact.
    # Use them and preserve the aggregate raw file without modification.
    data['results']=[read(run/'cases'/r['case_id']/r['arm']/'result.json') for r in data['results']]
    cases=read(adr/'artifacts/design/cases.json')['cases'];gold=read(adr/'artifacts/design/expected-offline.json')
    cat=read(run/'source-catalogue.json')
    def coords(ids):return identities({encoded({'doc_id':cat[sid]['document_id'],'node':int(cat[sid]['unit_id'])}) for sid in ids})
    ledger={'schema_version':SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
        'accounting_unit':UNIT,'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[]}],
        'audit':{'classification':'SYNTHETIC','gold_sha256':sha(adr/'artifacts/design/expected-offline.json'),
                 'presentation_unit':'unique original roots in final answer input; selector snippets are separately preserved in exact calls',
                 'scope_exclusion_source':'manually curated synthetic ontology, not automatically learned from successful logs'}}
    grades=[];by_arm={};retrieval=m['retrieval_accounting'];usage={};latency={}
    for arm in ARMS:
        rows=[]
        plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm]
        for case in cases:
            r=next((r for r in data['results'] if r['case_id']==case['id'] and r['arm']==arm),None)
            required=gold['required'][case['id']]
            scope=coords([s for s,c in cat.items() if c['document_id'] in case['documents']]) if r else []
            allowed=coords(r['policy']['allowed_node_ids']) if r and r.get('policy') else scope
            ids,journal=journal_reads(run/'cases'/case['id']/arm)
            reads=coords(ids);selected=coords(r.get('selected_ids',[])) if r else []
            presented=coords(r.get('presented_ids',[])) if r else []
            cited=coords({s for c in r.get('answer',{}).get('claims',[]) for s in c['source_ids'] if s in cat}) if r else []
            answer=r.get('answer',{}).get('answer','') if r else ''
            missing_terms=[t for t in gold['required_answer_terms'][case['id']] if t not in answer]
            missing_presented=keys(required)-keys(presented);missing_cited=keys(required)-keys(cited)
            passed=bool(r and r['status']=='ANSWER' and answer and not missing_presented and not missing_cited and not missing_terms)
            grade={'case_id':case['id'],'arm':arm,'pass':passed,'required':required,'read_ids':ids,
                'presented':presented,'cited':cited,'missing_presented':identities(missing_presented),
                'missing_cited':identities(missing_cited),'missing_answer_terms':missing_terms,
                'status':r['status'] if r else 'NOT_EXECUTED','error':r.get('error') if r else 'CONTRACT_EARLY_STOP',
                'classifier':r.get('classifier') if r else None,'policy_fallback':r.get('policy',{}).get('fallback_reason') if r and r.get('policy') else None}
            grades.append(grade)
            rows.append({'schema_version':SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,
                'accounting_unit':UNIT,'arm_id':arm,'case_id':case['id'],'gold_total':len(required),'gold_identities':identities(keys(required)),
                'stages':[stage(plan[0],[],scope,required,'REQUEST_DOCUMENT_SCOPE',bool(r)),
                          stage(plan[1],scope,allowed,required,'ACTIVE_DB_PURPOSE_EXCLUDES',bool(r)),
                          stage(plan[2],allowed,reads,required,'NATIVE_RECALL_NOT_ACQUIRED',bool(r)),
                          stage(plan[3],reads,selected,required,'NATIVE_MODEL_NOT_SELECTED' if r and r.get('selected_ids') else 'NO_SELECTION_AFTER_PRE_MODEL_ERROR',bool(r)),
                          stage(plan[4],selected,presented,required,'NO_ANSWER_INPUT',bool(r))],
                'audit':{'journals':journal,'native_read_roots':len(ids),
                         'selector_original_excerpts':str((run/'cases'/case['id']/arm/'selection.json').relative_to(ROOT)) if r and r.get('selected_ids') else None}})
        counts=[row['stages'][-1]['after_count'] for row in rows]
        total_gold=sum(row['gold_total'] for row in rows)
        metrics={'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),
                 'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],
                 'golden_recall':sum(row['stages'][-1]['gold_after'] for row in rows)/total_gold,
                 'selectivity':statistics.mean(counts)/len(cat)}
        ledger['runs'][0]['arms'].append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plan],'cases':rows,'aggregate':metrics})
        for k,v in metrics.items():
            if not isinstance(retrieval.get(k),dict): retrieval[k]={}
            retrieval[k][arm]=v
        relevant=[r for r in data['results'] if r['arm']==arm]
        us=[u for r in relevant for u in r['usage']]
        usage[arm]={'calls':sum(r['model_calls'] for r in relevant),'input_tokens':sum(u.get('input_tokens') or 0 for u in us),
            'output_tokens':sum(u.get('output_tokens') or 0 for u in us),'cost_usd':sum(u.get('cost_usd') or 0 for u in us)}
        latency[arm]={'total_seconds':sum(r['seconds'] for r in relevant),
                     'mean_seconds':statistics.mean(r['seconds'] for r in relevant) if relevant else None,
                     'fts_total_seconds':sum(x['seconds'] for r in relevant for x in r['fts']),
                     'recall_total_seconds':sum(r.get('recall_seconds',0) for r in relevant),
                     'recognition_total_seconds':sum(r.get('recognition_seconds',0) for r in relevant),
                     'executed_denominator':len(relevant)}
        by_arm[arm]={'correct':sum(g['pass'] for g in grades if g['arm']==arm),'total':len(cases),
                    'read_roots':sum(len(g['read_ids']) for g in grades if g['arm']==arm),
                    'app_read_roots':sum(len(g['read_ids']) for g in grades if g['arm']==arm and g['case_id'].startswith('APP')),
                    'metric_meaning':'required synthetic original/citation/answer-term contract, not certified legal answer correctness'}
    ledger['artifact_sha256']=hashlib.sha256(encoded(ledger).encode()).hexdigest()
    write(run/'retrieval-stage-ledger.json',ledger)
    retrieval.update(corpus_total=len(cat),before_filter={a:sum(s['stages'][0]['after_count'] for s in row['cases']) for a,row in zip(ARMS,ledger['runs'][0]['arms'])},
                     after_filter={a:sum(s['stages'][1]['after_count'] for s in row['cases']) for a,row in zip(ARMS,ledger['runs'][0]['arms'])})
    retrieval['stage_ledger'].update(artifact_path=str((run/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256=sha(run/'retrieval-stage-ledger.json'))
    compare=lambda metric: (1-metric['graph']/metric['baseline']) if metric['baseline'] else None
    wall_gain=compare({a:latency[a]['total_seconds'] for a in ARMS})
    cost_gain=compare({a:usage[a]['cost_usd'] for a in ARMS})
    read_gain=compare({a:by_arm[a]['app_read_roots'] for a in ARMS})
    functional=all(by_arm[a]['correct']==len(cases) for a in ARMS)
    summary={'classification':'SYNTHETIC','by_arm':by_arm,'usage':usage,'latency':latency,'grades':grades,
             'app_read_reduction':read_gain,'wall_reduction':wall_gain,'cost_reduction':cost_gain,
             'functional_pass':functional,'read_value_pass':functional and (read_gain or 0)>=.3,
             'end_to_end_value_pass':functional and ((wall_gain or 0)>=.1 or (cost_gain or 0)>=.1),
             'legal_quality_certified':False,'main_changed':False}
    write(run/'offline-grade.json',summary)
    m['runs'][0].update(status='complete',artifact_path=str((run/'result.json').relative_to(ROOT)),sha256=sha(run/'result.json'))
    m['results'].update(status='complete',by_arm=by_arm,usage={'by_arm':usage},latency={'by_arm':latency},
        comparisons=[{'baseline':'baseline','candidate':'graph','wall_reduction':wall_gain,'cost_reduction':cost_gain,'app_read_reduction':read_gain}],
        judge_disagreements=0,error_taxonomy=[g for g in grades if not g['pass']])
    # All question files carry actual wire inputs/outputs, not selected excerpts.
    for q,case in zip(m['questions'],cases):
        own=[r for r in data['results'] if r['case_id']==case['id']]
        text='# '+m['adr_id']+' / '+case['id']+'\n\n## 1. 실행 메타\n\n'+block({'run':'run-001','arms':ARMS,'mode':run.name})
        text+='\n## 2. 사용자 질문 원문\n\n'+case['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n'+block({k:gold[k][case['id']] for k in ['required','required_answer_terms','expected_purpose']})
        text+='\n## 4. 제품 입력을 구성한 원값\n\n### 회수 전 전체·후보·제시 규모\n\n'+block(m['retrieval_accounting'])
        text+='\n### 회수 좌표·조문·정의·Wiki·관계 — 전체\n\n'+block({'case':case,'corpus':read(adr/'artifacts/design/corpus.json'),'source_catalogue':cat,'results':own})
        text+='\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block([c for a in ledger['runs'][0]['arms'] for c in a['cases'] if c['case_id']==case['id']])
        text+='\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n'
        for arm in ARMS:
            text+='### run-001 / '+arm+'\n\n'
            calls=sorted((run/'cases'/case['id']/arm/'calls').glob('call-*'))
            if not calls:text+='모델 호출 없음. native 계약 또는 선행 오류로 미실행.\n\n'
            for call in calls:
                text+='#### '+call.name+'\n\n'
                text+=block({str(p.relative_to(ROOT)):read(p) for p in call.glob('*.json')})
        text+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n목적 분류·원문 선별의 전체 원값도 위 호출에 포함한다. query plan은 양쪽 공통 사전 입력이다. repair=0.\n'
        text+='\n## 7. 채점 호출과 반복 판정\n\n### judge system/user — 기준답변 포함\n\n'+block({'model_calls':0,'rubric':'required source presentation + citations + answer terms','repeats':1})
        text+='\n### judge 원응답과 최종 다수결\n\n'+block([g for g in grades if g['case_id']==case['id']])
        text+='\n## 8. 사례 최종 판정\n\n'+block(own)+'\n법률 정확도 인증이 아니다. 제품 결과를 변경하지 않았다.\n'
        path=adr/'실험'/q['file'];path.write_text(text);q['sha256']=sha(path)
    write(adr/'실험/manifest.json',m)
    front=(adr/'README.md').read_text().split('---',2)[1]
    front=front.replace('status: Proposed','status: '+('Proposed' if functional else 'Rejected'))
    sections=[('1. 결정 요약','실행 완료. '+('합성 기능 기준 충족.' if functional else '필수 기능 기준 미충족; 운영 적용 보류.')),
      ('2. 문제와 변경 전 구조','과거 안내 방식은 최소 근거를 이미 읽어서 절감 여지가 작았다. 이번에는 잡음 원문이 실제 회수되는 native 경로를 비교했다.'),
      ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),
      ('4. 실험 설계',block(m['design']['arms'])+'\n자료 생성·projection·DB 온톨로지는 오프라인 준비. 온라인은 개별 세션·목적 분류·실제 Fulltext/READ·native 선별·공통 모델 답변이다. full BoundedSourceSession/Compose API 전체 실행은 아니다.'),
      ('5. 데이터·모델·재현성','55개 합성 원문. Gemma Parasail FP8 thinking off, 출력1536, 재시도·수정0, arm 순서 교대. 기준답변은 offline report만 읽는다. 목적·자료 분류·제외 관계는 수작업 합성이며 로그 학습 성공으로 해석할 수 없다.'),
      ('6. 결과',block({k:v for k,v in summary.items() if k!='grades'})),
      ('7. 사례별 오류 분석',block([g for g in grades if not g['pass']])),
      ('8. 비용·지연·회수 규모',block({'usage':usage,'latency':latency})),
      ('9. 해석','원문 회수와 검색 SQL 시간을 구분한다. 현재 Fulltext SQL은 그대로이며 scope를 검색 행 회수 뒤 거른다. 후보의 목적 판별 호출까지 포함한 값이다.'),
      ('10. 한계와 일반화 가능 범위','소형 로컬 합성 corpus, 단일 paired 반복, 수작업 온톨로지, 기본 API 일부 단계 우회. 실제 사용자 로그·법률 정확도·내부 데이터·NFS·GENOS 성능은 미확인이다.'),
      ('11. 운영 결정·롤백 조건','MAIN·활성 release·코드 registry·GENOS 변경 없음. source version drift 시 후보는 기존 범위로 복귀한다. 운영 채택에는 실제 로그 검증과 분리 holdout이 필요하다.'),
      ('12. 재현 명령','`'+str((ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+m['adr_id'].split('-')[1])/'run.py').relative_to(ROOT))+' --live`를 `.venv/bin/python`으로 실행한다. 완료 산출물은 덮어쓰지 않으며 새 ADR/run을 선점한다.')]
    (adr/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' 조사 목적 온톨로지 가치\n\n'+'\n\n'.join('## '+h+'\n\n'+body for h,body in sections)+'\n')
    (adr/'실험/README.md').write_text('# '+m['adr_id']+' 질문·실행 인덱스\n\n[실험 manifest](manifest.json)에 선점·계보·arm·run·분석·hash를 보존한다.\n\n'+ '\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n\n'+block(summary))
    files=[]
    for p in (adr/'artifacts').rglob('*'):
        if p.is_file() and p!=adr/'artifacts/manifest.json':
            files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
                          'description':'Frozen synthetic input, native journal, exact calls or offline report',
                          'contains_raw_prompts_and_outputs':'calls' in p.parts})
    write(adr/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
    print(json.dumps({k:v for k,v in summary.items() if k!='grades'},ensure_ascii=False))


if __name__=='__main__':main()

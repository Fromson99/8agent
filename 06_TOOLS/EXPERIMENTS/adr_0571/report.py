"""Offline full native API accounting; golden data never enters the product."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sqlite3
import statistics

R=Path(__file__).resolve().parents[3]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v): return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adr',required=True);args=parser.parse_args()
    A=R/args.adr;out=A/'artifacts/run-001';m=read(A/'실험/manifest.json');data=read(out/'result.json')
    assert data['status']=='complete'
    gold=read(A/'artifacts/design/expected-offline.json');cases=read(A/'artifacts/design/cases.json')
    helper=runpy.run_path(str(R/'06_TOOLS/EXPERIMENTS/adr_0570/report.py'))
    stage,encoded,keys,identities=[helper[n] for n in ['stage','encoded','keys','identities']]
    with sqlite3.connect((out/'fixture/built/generation/navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        cat={row[0]:{'doc_id':row[1],'node':int(row[2])} for row in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source")}
    def coords(ids): return identities(keys([cat[s] for s in set(ids) if s in cat]))
    ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
      'accounting_unit':helper['UNIT'],'computed_post_selection':True,'gold_visible_to_product':False,
      'runs':[{'run_id':'run-001','arms':[]}],'audit':{'classification':'SYNTHETIC','gold_sha256':sha(A/'artifacts/design/expected-offline.json'),
      'early_failure_rule':'A pre-admission HTTP failure has zero executed stages; its latency is not successful answer latency.'}}
    grades=[];by_arm={};usage={};latency={}
    for arm in ['baseline','integrated']:
        rows=[];records=[r for r in data['results'] if r['arm']==arm]
        plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm]
        for case in cases:
            r=next(r for r in records if r['case_id']==case['id']);own=out/'cases'/case['id']/arm
            native=[];journals=[];events=[]
            for p in own.rglob('journal.sqlite'):
                journals.append({'path':str(p.relative_to(R)),'sha256':sha(p)})
                with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    native.extend(x[0] for x in db.execute('SELECT source_id FROM evidence_unit'))
                    events.extend({'kind':x[0],'value':json.loads(x[1])} for x in db.execute('SELECT kind,payload_json FROM event'))
            accepted=bool(journals);scope=coords(s for s,c in cat.items() if c['doc_id']=='d') if accepted else []
            allowed=scope
            reads=coords(native)
            selected=coords(x['id'] for x in r.get('assembly',{}).get('context',[]))
            presented=selected
            answer=r.get('answer',{});text=answer.get('text','')
            cited=coords(s for c in answer.get('claims',[]) for s in c.get('source_ids',[]))
            required=gold['required'][case['id']];miss_p=keys(required)-keys(presented);miss_c=keys(required)-keys(cited)
            miss_t=[t for t in gold['terms'][case['id']] if t not in text]
            passed=r['status']=='ANSWER' and bool(text) and not miss_p and not miss_c and not miss_t
            grades.append({'case_id':case['id'],'arm':arm,'pass':passed,'required':required,'presented':presented,'cited':cited,
                'missing_presented':identities(miss_p),'missing_cited':identities(miss_c),'missing_terms':miss_t,
                'status':r['status'],'error':r['error'],'native_reads':len(set(native)),
                'question_plan_reused':any(e['kind']=='QUESTION_PLAN_REUSED_FROM_SEARCH_PLAN' for e in events)})
            rows.append({'schema_version':ledger['schema_version'],'computed_post_selection':True,'gold_visible_to_product':False,
                'accounting_unit':helper['UNIT'],'arm_id':arm,'case_id':case['id'],'gold_total':len(required),'gold_identities':required,
                'stages':[stage(plan[0],[],scope,required,'REQUEST_SCOPE',accepted),stage(plan[1],scope,allowed,required,'NO_ACTIVE_EXCLUSION',accepted),
                  stage(plan[2],allowed,reads,required,'NOT_READ',accepted),stage(plan[3],reads,selected,required,'NOT_SELECTED',accepted),
                  stage(plan[4],selected,presented,required,'NO_ANSWER_INPUT',r['status']=='ANSWER')], 'audit':{'journals':journals}})
        counts=[r['stages'][-1]['after_count'] for r in rows]
        aggregate={'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),
            'presented_p95':sorted(counts)[round((len(counts)-1)*.95)],'golden_recall':sum(r['stages'][-1]['gold_after'] for r in rows)/sum(r['gold_total'] for r in rows),
            'selectivity':statistics.mean(counts)/len(cat)}
        ledger['runs'][0]['arms'].append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plan],'cases':rows,'aggregate':aggregate})
        by_arm[arm]={'correct':sum(g['pass'] for g in grades if g['arm']==arm),'total':len(cases),'completed':sum(r['status']=='ANSWER' for r in records),
            'read_roots':sum(g['native_reads'] for g in grades if g['arm']==arm),'metric_meaning':gold['meaning']}
        us=[u for r in records for u in r['usage']]
        usage[arm]={'calls':sum(r['calls'] for r in records),'input_tokens':sum(u.get('input_tokens') or 0 for u in us),
            'output_tokens':sum(u.get('output_tokens') or 0 for u in us),'cost_usd':sum(u.get('cost_usd') or 0 for u in us)}
        done=[r['seconds'] for r in records if r['status']=='ANSWER']
        latency[arm]={'completed_mean_seconds':statistics.mean(done) if done else None,'completed_total_seconds':sum(done),
            'completed_denominator':len(done),'failed_seconds':sum(r['seconds'] for r in records if r['status']!='ANSWER')}
    ledger['artifact_sha256']=hashlib.sha256(encoded(ledger).encode()).hexdigest();write(out/'retrieval-stage-ledger.json',ledger)
    retrieval=m['retrieval_accounting'];retrieval['corpus_total']=len(cat)
    for a in ledger['runs'][0]['arms']:
        arm=a['arm_id']
        for k,v in a['aggregate'].items(): retrieval.setdefault(k,{}) if retrieval.get(k) is not None else retrieval.update({k:{}});retrieval[k][arm]=v
        for k,i in [('before_filter',0),('after_filter',1)]:
            if not isinstance(retrieval.get(k),dict):retrieval[k]={}
            retrieval[k][arm]=sum(c['stages'][i]['after_count'] for c in a['cases'])
    retrieval['stage_ledger']['sha256']=sha(out/'retrieval-stage-ledger.json')
    functional=all(a['correct']==len(cases) for a in by_arm.values())
    g=data['generation'];generation_ok=g.get('state')=='COMPLETED' and g.get('actual_next_request_received_concepts') and g.get('followup_status')==200
    summary={'classification':'SYNTHETIC','functional_pass':functional,'generation_roundtrip_pass':bool(generation_ok),
       'by_arm':by_arm,'usage':usage,'latency':latency,'generation':g,'grades':grades,'main_changed':False,'legal_quality_certified':False}
    write(out/'offline-grade.json',summary)
    m['runs'][0].update(status='complete',sha256=sha(out/'result.json'))
    m['results'].update(status='complete',by_arm=by_arm,usage={'by_arm':usage},latency={'by_arm':latency},judge_disagreements=0,
        comparisons=[{'baseline':'baseline','candidate':'integrated','full_api_contract_pass':functional,'generation_roundtrip_pass':bool(generation_ok)}],
        error_taxonomy=[x for x in grades if not x['pass']])
    for q,case in zip(m['questions'],cases):
        own=[x for x in data['results'] if x['case_id']==case['id']]
        body='# '+m['adr_id']+' '+case['id']+'\n\n'
        sections=[('1. 실행 메타',block({'run':'run-001','arms':['baseline','integrated'],'classification':'SYNTHETIC'})),
            ('2. 사용자 질문 원문',case['question']),('3. 기준답변 — 채점 전용, 제품 입력 비공개',block({k:gold[k][case['id']] for k in ['required','terms']})),
            ('4. 제품 입력을 구성한 원값',block({'catalogue':cat,'results':own,'retrieval_accounting':retrieval})+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block([c for a in ledger['runs'][0]['arms'] for c in a['cases'] if c['case_id']==case['id']])),
            ('5. 제품 모델 호출 — run·arm별 실제 원문',''),('6. 중간 LLM 호출 — router/compiler/verifier/repair','별도 목적 판별 호출0. 실제 중간 호출의 원문은 5절과 동일하다.'),
            ('7. 채점 호출과 반복 판정',block({'model_calls':0,'repeats':1,'rubric':gold['meaning']})+block([x for x in grades if x['case_id']==case['id']])),
            ('8. 사례 최종 판정',block(own))]
        calls=[]
        for arm in ['baseline','integrated']:
            calls.append('### '+arm+'\n\n')
            paths=sorted((out/'cases'/case['id']/arm/'calls').glob('call-*'))
            calls.append('모델 호출 없음. HTTP 검증에서 미실행.\n' if not paths else '')
            calls.extend(block({str(p.relative_to(R)):read(p) for p in call.glob('*.json')}) for call in paths)
        sections[4]=(sections[4][0],''.join(calls))
        p=A/'실험'/q['file'];p.write_text(body+'\n\n'.join('## '+h+'\n\n'+b for h,b in sections)+'\n');q['sha256']=sha(p)
    write(A/'실험/manifest.json',m)
    front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if functional and generation_ok else 'Rejected'))
    sections=[('1. 결정 요약','전체 API 계약과 자동 생성·재사용 확인: '+str(functional and generation_ok)+'. MAIN 변경 없음.'),
        ('2. 문제와 변경 전 구조','계획·원문 선별의 추가 호출과 수작업 개념 생성이 기존 검증의 한계였다.'),
        ('3. 가설과 사전 판정 기준',block(m['design']['success_criteria'])),('4. 실험 설계',block(m['design']['arms'])),
        ('5. 데이터·모델·재현성','합성 승인 규정, 고정 native HTTP API. Gemma/ParasailFP8/thinking off. 재시도·스키마 수정0. 제품 입력에 golden 미노출.'),
        ('6. 결과',block({k:v for k,v in summary.items() if k!='grades'})),('7. 사례별 오류 분석',block(m['results']['error_taxonomy'])),
        ('8. 비용·지연·회수 규모',block({'usage':usage,'latency':latency,'retrieval':retrieval})),
        ('9. 해석','미완료 요청 시간은 성공 지연과 분리한다. 개념·GUIDE 생성과 검증된 EXCLUDES 활성화는 별개이다.'),
        ('10. 한계와 일반화 가능 범위','4개 합성 질문, 1회 반복. 실제 법률 정확도·현장 GENOS·성능 인증 아님. 야간 외부 학습은 현재 공개 반출 승인과 원문 세대에 결속된다.'),
        ('11. 운영 결정·롤백 조건','실패 기록 보존. 활성 release·registry·GENOS 미변경. 알려지지 않은 목적·세대 변경은 기존 허용 범위로 복귀한다.'),
        ('12. 재현 명령','완료 결과를 덮어쓰지 않고 새 ADR을 선점하여 같은 frozen 후보와 full API 실행기를 사용한다.')]
    (A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' native API 및 야간 개념 구축\n\n'+'\n\n'.join('## '+h+'\n\n'+b for h,b in sections)+'\n')
    (A/'실험/README.md').write_text('# 실행 인덱스\n\n[manifest](manifest.json)\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['grades','generation']},ensure_ascii=False))

if __name__=='__main__':main()

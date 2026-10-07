"""Report raw runs or systemic aborts without changing frozen product code/gold."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adr',required=True);parser.add_argument('--aborted',action='store_true');args=parser.parse_args()
    adr=ROOT/args.adr;run=adr/'artifacts/run-001';design=adr/'artifacts/design';m=json.loads((adr/'실험/manifest.json').read_text());number=m['adr_id'];arms=['PARENT','STRICT']
    spec=importlib.util.spec_from_file_location('report_ledger',ROOT/'06_TOOLS/EXPERIMENTS/adr_0594/run.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    inputs=json.loads((design/'inputs.json').read_text());gold=json.loads((design/'gold.json').read_text())
    if args.aborted:
        products=[];grades=[]
        for product in inputs:
            cid=product['case_id'];row={'case_id':cid,'arms':{},'structural':{}};grade={'case_id':cid,'arms':{}}
            for arm in arms:
                items=[]
                for ti,turn in enumerate(product['turns'],1):
                    p=run/cid/arm/f'turn-{ti:02d}.json'
                    items.append(json.loads(p.read_text()) if p.exists() else {'turn':ti,'product_input':turn,'observed':{'status':'NOT_RUN','reason':'Systemic journal contract failure; stopped further calls'},'snapshots':{},'seconds':0})
                row['arms'][arm]=items;row['structural'][arm]={'execution_aborted':True}
                grade['arms'][arm]={'checks':[{'field':'sequential_case_completed','expected':True,'observed':False,'pass':False}],'passed':0,'total':1,'all_pass':False}
            products.append(row);grades.append(grade)
        accounting,summaries=helper.ledger(products,gold,m)
        for ar in accounting['runs'][0]['arms']:
            for case in ar['cases']:
                for stage in case['stages']:stage['executed']=False;stage['skip_reason']='Systemic failure before source stage'
        accounting.pop('artifact_sha256');accounting['artifact_sha256']=hashlib.sha256(helper.canonical(accounting).encode()).hexdigest()
        write(run/'retrieval-stage-ledger.json',accounting)
        usages=json.loads((run/'provider/usage.json').read_text()) if (run/'provider/usage.json').exists() else []
        result={'schema_version':'rag-chain-sequential-probe-v1','run_id':'run-001','data_kind':'SYNTHETIC','execution_aborted':True,'products':products,'grades':grades,'summary':{'by_arm':{a:{'checks_passed':0,'checks_total':5,'sequences_passed':0,'sequences_total':5,'observed_turns':sum(i['observed']['status']!='NOT_RUN' for r in products for i in r['arms'][a]),'runtime_errors':sum(i['observed']['status']=='ERROR' for r in products for i in r['arms'][a])} for a in arms},'paired':{'candidate_only':0,'baseline_only':0,'both_correct':0,'both_incorrect':5},'usage':{'calls':len(usages),'input_tokens':sum(u.get('input_tokens',0) or 0 for u in usages),'output_tokens':sum(u.get('output_tokens',0) or 0 for u in usages),'reported_cost_usd':sum(u.get('usage',{}).get('cost',0) or 0 for u in usages)},'retrieval':summaries,'turn_latency_seconds':{}},'failure':'Native journal kind CHECK rejected synthetic chain_node before any stage completed','limits':m['design']['limits']}
        write(run/'result.json',result)
    result=json.loads((run/'result.json').read_text());summary=result['summary'];grades=result['grades']
    report=ROOT/'07_DOCS/REFERENCE/REPORTS'/f'{number}_RAG_CHAIN_PROTOTYPE_20261001.md'
    lines=['# RAG 멀티턴 체인 계약 강화 결과','',number+' · WSL 로컬 · 합성 원문 6단위 · 연속 대화 6개·49턴/arm · Qwen3.8 · MAIN 미변경','', '**실제 RAG API/Coordinator·GENOS 연결 검증은 포함하지 않는다. 점수와 기계적 안전 검사·모델 텍스트 평가는 별개다.**','', '## 직접 원인과 수정','', '| 원인 | 수정 |','|---|---|','| 조건이 같으면 FOLLOW를 COMPOSE로 덮어씀 | 명시 stage를 유지하고 변경 조건·pending과 가장 이른 단계를 결정 |','| 원본 없는 복원 명령을 적용 | 명령 검증·동일 goal 원발언 참조를 확인하고 원기록 값으로 복원; 없으면 CLARIFY |','| INSPECT/REUSE 응답 필드 누락 | 실제 소비 route의 immutable nodes로 assessment·retrieval·goal·revision 응답 |','| 다른 질문의 마지막 검색을 집계 | final response의 route_id/goal을 관측하고 그 경로의 원문 집합으로 집계 |','| 답변 문장이 현재 판단과 다름 | 사실값 일치 검사와 별도 제품 text 검증; 1회 수리 실패 시 게시 차단 |','| 긴급 미확인을 false로 취급 | null/false/true 3상태 유지, 판단과 작성 계약에서 일치 검사 |','| native 기록 실패에도 chain head가 바뀔 수 있음 | native 실패 시 node·head 트랜잭션 롤백 |','', '## 사전 검사 결과','', '| 흐름 | PARENT | STRICT |','|---|---|---|']
    for g in grades:
        lines.append('| '+g['case_id']+' | '+str(g['arms']['PARENT']['passed'])+'/'+str(g['arms']['PARENT']['total'])+' | '+str(g['arms']['STRICT']['passed'])+'/'+str(g['arms']['STRICT']['total'])+' |')
    lines+=['','모델 0회 adversarial 계약: '+str(result['guard_result']['passed'])+'/'+str(result['guard_result']['total'])+'. 정확한 각 검사·실패 원문은 guard-result.json을 따른다.','', 'score의 분모는 성공 응답의 필드 검사 수에 따라 달라질 수 있으므로, 모든 요청의 상태를 별도 diagnostic audit에서 확인해야 한다.','', '## 기능별 실제 관찰','']
    for case,g in zip(result['products'],grades):
        lines+=['### '+case['case_id'],'','| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |','|---|---|---|---|']
        for item in case['arms']['STRICT']:
            o=item['observed'];ans=o.get('answer') or {};lines.append('| '+str(item['turn'])+' | '+item['product_input']['utterance'].replace('|','/')+' | '+o['status']+' / '+str(ans.get('procedure',''))+' | '+','.join(o.get('executed',[]))+' |')
        failed=[c for c in g['arms']['STRICT']['checks'] if not c['pass']]
        lines+=['','미충족 항목:'+block(failed),'실제 오류:'+block([{'turn':i['turn'],'error':i['observed'].get('error')} for i in case['arms']['STRICT'] if i['observed']['status']=='ERROR'])]
    lines+=['','## 비용·지연·회수','',block(summary),'## 범위와 한계','',*['- '+s for s in result['limits']],'- 세션/경로용 SQLite와 Native WorkRepository 기록은 실제 실행했다. 원문 읽기·선별·판단·작성은 합성 stage executor다.','- 기본 네 port의 생산 Coordinator, 인증 adapter, 실제 READ/presentation ledger, two-DB worker·lease·SSE·캐시 서버는 붙이지 않았다.','- 현재 경로의 오래된 revision 거부를 검사했으며, 실제 동시 서버 경합·캐시 장애 시험은 아니다.','- 법률 승인·DB 관리 기능은 이번 실험 대상에서 제외했다.','- 정식 ADR graph 검사 결과는 별도 validation receipt에서 확인한다.','', '[ADR 기록](../../../'+args.adr+'/README.md) · [원시 결과](../../../'+args.adr+'/artifacts/run-001/result.json)']
    report.write_text('\n'.join(lines)+'\n')
    # Store every available exact request/schema/provider response inline per sequence.
    for question,product,g in zip(m['questions'],result['products'],grades):
        cid=question['case_id'];parts=['# '+cid,'','## 1. 실행 메타','',number+' / run-001 / PARENT·STRICT / qwen/qwen3.8-27b / 합성 연속 대화','', '## 2. 사용자 질문 원문',block(next(p for p in inputs if p['case_id']==cid)),'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid]),'## 4. 제품 입력을 구성한 원값',block(product),'### 회수·탈락 단계 원장 — run·arm별',block([c for a in json.loads((run/'retrieval-stage-ledger.json').read_text())['runs'][0]['arms'] for c in a['cases'] if c['case_id']==cid]),'## 5. 제품 모델 호출 — run·arm별 실제 원문','']
        for folder in sorted(list((run/'provider').glob('call-*'+cid+'-*'))+list((run/'offline-evaluator').glob('call-*'+cid+'-*'))):
            parts+=['### '+folder.name,'']
            for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
                p=folder/name
                if p.exists():parts+=['#### '+name,block(json.loads(p.read_text()))]
            if not (folder/'response.json').exists():parts+=['provider 원응답 없음: 전송 중 중단 또는 실패 기록을 확인한다.']
        parts+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','resolve/select/assess/compose, command/text verifier, explicit repair 및 offline evaluator의 실제 입력·원응답은 위에 모두 기록했다.','## 7. 채점 호출과 반복 판정','제품 verifier와 1회 한도의 명시적 compose repair는 제품 호출이다. 제품 실행 완료 후 별도 offline evaluator가 text를 검사했고 그 결과로 제품을 수정하지 않았다. 정확한 호출 횟수는 usage와 원시 receipt에 기록했다. gold는 제품 입력에 넣지 않았다.','## 8. 사례 최종 판정',block(g)]
        (adr/'실험'/question['file']).write_text('\n'.join(parts)+'\n')
    m['runs'][0].update(status='complete',artifact_path=str((run/'result.json').relative_to(ROOT)),sha256=sha(run/'result.json'))
    failures=[{'case_id':g['case_id'],'arm':a,'checks':[c for c in g['arms'][a]['checks'] if not c['pass']]} for g in grades for a in arms if not g['arms'][a]['all_pass']]
    m['results'].update(status='complete',by_arm=summary['by_arm'],comparisons=[{'baseline_arm':'PARENT','candidate_arm':'STRICT','metric':'complete sequential case pass','denominator':len(grades),**summary['paired']}],judge_disagreements=summary.get('judge_disagreements',0),usage=summary['usage'],latency=summary.get('turn_latency_seconds',{}),error_taxonomy=[{'type':'other','failures':failures}])
    m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((run/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256=sha(run/'retrieval-stage-ledger.json'))
    for key in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:
        m['retrieval_accounting'][key]={a:summary['retrieval'][a][key] for a in arms}
    write(adr/'실험/manifest.json',m)
    p=adr/'README.md';front=p.read_text().split('---',2)[1];front=front.replace('status: Proposed','status: Rejected' if args.aborted else 'status: Proposed')
    sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
    texts=[('journal 계약 불일치로 실행 중단. 후보 실패를 보존한다.' if args.aborted else '격리 프로토타입의 연속 실행 결과. 성공·미충족은 아래 원시 점수와 기능별 보고서를 따른다.')+'\n\n[상세 보고서](../../../'+str(report.relative_to(ROOT))+')','부모 CHAIN의 단계 덮어쓰기·원본 없는 복원·조회 누락·집계 소속·문장 모순 원인을 수정한다. 같은 frozen 입력에 새 검사 기준으로 비교하며 이전 76/77 점수와 직접 비교하지 않는다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'같은 DB에서 6개 연속 대화 49턴씩 PARENT/STRICT를 사례별 교대 순서로 실행. SEQ05의 계획된 ASSESS 실패 뒤 다음 명시 턴에서 복구. 모델 0회 adversarial 계약 21개는 별도 분모다.', '합성 자료만 전송. Qwen3.8-27b Parasail FP8 reasoning none, provider/model fallback 없음. 자동 schema repair는 없고 제품 compose repair는 1회 한도. 입력·gold·코드·runner 사전 hash 동결.',block(summary['by_arm']),block(failures),block({'usage':summary['usage'],'latency':summary.get('turn_latency_seconds',{}),'retrieval':summary['retrieval']}),'원시 결과와 상세 보고서를 따른다. 해석 실패와 실행 계약 실패를 구분한다. 새 후보 수정·재실험은 새 ADR이다.','인샘플·합성 실행기. 실제 사용자 질문·법률 품질·운영 API·GENOS·동시성 성능으로 일반화하지 않는다.','MAIN unchanged. 활성 포인터·원문·부모 ADR 보존. graph 전체 검사 실패 시 정식 절차 완료로 보고하지 않는다.','동결 runner를 실행하되 기존 run 경로는 덮어쓰지 않고 거부한다. 새 반복은 새 ADR/run 계약으로 진행한다.']
    p.write_text('---'+front+'---\n\n# '+number+' — RAG 멀티턴 체인 프로토타입\n\n'+'\n\n'.join('## '+str(i)+'. '+s+'\n\n'+t for i,(s,t) in enumerate(zip(sections,texts),1))+'\n')
    (adr/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | STRICT 검사 | PARENT 검사 |\n|---|---|---|\n'+'\n'.join('| ['+q['case_id']+']('+q['file']+') | '+str(g['arms']['STRICT']['passed'])+'/'+str(g['arms']['STRICT']['total'])+' | '+str(g['arms']['PARENT']['passed'])+'/'+str(g['arms']['PARENT']['total'])+' |' for q,g in zip(m['questions'],grades))+'\n')
    index=ROOT/'04_EXPERIMENTS/ADR/README.md';line='- ['+number+' — RAG 멀티턴 체인 프로토타입]('+adr.name+'/README.md)\n'
    if adr.name not in index.read_text():index.write_text(index.read_text()+'\n'+line)
    files=[p for p in adr.rglob('*') if p.is_file() and p!=adr/'artifacts/manifest.json']
    for cid in ['strict-chain','parent-chain']:
        folder=ROOT/'02_BACKEND/lawrag/research/candidates'/('adr_'+number.split('-')[1])/cid
        files.extend(p for p in folder.rglob('*') if p.is_file())
    files.extend(p for p in (ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+number.split('-')[1])).glob('*.py'))
    write(adr/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':number,'artifacts':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(files))]})
    print(json.dumps({'report':str(report.relative_to(ROOT)),'summary':summary['by_arm'],'failures':len(failures)},ensure_ascii=False))

if __name__=='__main__':main()

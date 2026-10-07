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
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adr',required=True);parser.add_argument('--aborted',action='store_true');args=parser.parse_args()
    adr=ROOT/args.adr;run=adr/'artifacts/run-001';design=adr/'artifacts/design';m=json.loads((adr/'실험/manifest.json').read_text());number=m['adr_id'];arms=['CURRENT_ONLY','CHAIN']
    spec=importlib.util.spec_from_file_location('report_ledger',ROOT/'06_TOOLS/EXPERIMENTS/adr_0592/run.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
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
    lines=['# RAG 멀티턴 체인 프로토타입 결과','',number+' · WSL 로컬 · 합성 원문 6단위 · 연속 대화 5개 · Qwen3.8 · MAIN 미변경','', '**실행 결과를 구현 범위 안에서 판정한다. 실제 RAG API/Coordinator·GENOS 연결 검증은 포함하지 않는다.**','', '| 흐름 | CURRENT_ONLY | CHAIN |','|---|---|---|']
    for g in grades:
        lines.append('| '+g['case_id']+' | '+str(g['arms']['CURRENT_ONLY']['passed'])+'/'+str(g['arms']['CURRENT_ONLY']['total'])+' | '+str(g['arms']['CHAIN']['passed'])+'/'+str(g['arms']['CHAIN']['total'])+' |')
    lines+=['','## 기능별 실제 관찰','']
    for case,g in zip(result['products'],grades):
        lines+=['### '+case['case_id'],'','| 턴 | 사용자 발언 | CHAIN 상태·절차 | 실행 단계 |','|---|---|---|---|']
        for item in case['arms']['CHAIN']:
            o=item['observed'];ans=o.get('answer') or {};lines.append('| '+str(item['turn'])+' | '+item['product_input']['utterance'].replace('|','/')+' | '+o['status']+' / '+str(ans.get('procedure',''))+' | '+','.join(o.get('executed',[]))+' |')
        failed=[c for c in g['arms']['CHAIN']['checks'] if not c['pass']]
        lines+=['','미충족 항목:'+block(failed),'실제 오류:'+block([{'turn':i['turn'],'error':i['observed'].get('error')} for i in case['arms']['CHAIN'] if i['observed']['status']=='ERROR'])]
    lines+=['','## 비용·지연·회수','',block(summary),'## 범위와 한계','',*['- '+s for s in result['limits']],'- 세션/경로용 SQLite와 Native WorkRepository 기록은 실제 실행했다. 원문 읽기·선별·판단·작성은 합성 stage executor다.','- 기본 네 port의 생산 Coordinator, 인증 adapter, 실제 READ/presentation ledger, two-DB worker·lease·SSE·캐시 서버는 붙이지 않았다.','- 현재 경로의 오래된 revision 거부를 검사했으며, 실제 동시 서버 경합·캐시 장애 시험은 아니다.','- 법률 승인·DB 관리 기능은 이번 실험 대상에서 제외했다.','- 정식 ADR graph 검사 결과는 별도 validation receipt에서 확인한다.','', '[ADR 기록](../../../'+args.adr+'/README.md) · [원시 결과](../../../'+args.adr+'/artifacts/run-001/result.json)']
    report.write_text('\n'.join(lines)+'\n')
    # Store every available exact request/schema/provider response inline per sequence.
    for question,product,g in zip(m['questions'],result['products'],grades):
        cid=question['case_id'];parts=['# '+cid,'','## 실행 메타','',number+' / run-001 / CURRENT_ONLY·CHAIN / qwen/qwen3.8-27b / 합성 연속 대화','', '## 사용자 질문 원문',block(next(p for p in inputs if p['case_id']==cid)),'## 기준답변 — 채점 전용, 제품 입력에 포함하지 않음',block(gold[cid]),'## 제품 입력·단계 산출물·실제 판정',block(product),'## 채점 결과',block(g),'## 제품·중간 모델 호출 원문','']
        for folder in sorted((run/'provider').glob('call-*'+cid+'-*')):
            parts+=['### '+folder.name,'']
            for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
                p=folder/name
                if p.exists():parts+=['#### '+name,block(json.loads(p.read_text()))]
            if not (folder/'response.json').exists():parts+=['provider 원응답 없음: 전송 중 중단 또는 실패 기록을 확인한다.']
        parts+=['별도 LLM judge·repair·fallback은 0회. 사전 동결 gold는 모든 제품 실행이 끝난 후에만 결합했다.']
        (adr/'실험'/question['file']).write_text('\n'.join(parts)+'\n')
    m['runs'][0].update(status='complete',artifact_path=str((run/'result.json').relative_to(ROOT)),sha256=sha(run/'result.json'))
    failures=[{'case_id':g['case_id'],'arm':a,'checks':[c for c in g['arms'][a]['checks'] if not c['pass']]} for g in grades for a in arms if not g['arms'][a]['all_pass']]
    m['results'].update(status='complete',by_arm=summary['by_arm'],comparisons=[{'baseline_arm':'CURRENT_ONLY','candidate_arm':'CHAIN','metric':'complete sequential case pass','denominator':5,**summary['paired']}],judge_disagreements=0,usage=summary['usage'],latency=summary.get('turn_latency_seconds',{}),error_taxonomy=[{'type':'other','failures':failures}])
    m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((run/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256=sha(run/'retrieval-stage-ledger.json'))
    for key in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:
        m['retrieval_accounting'][key]={a:summary['retrieval'][a][key] for a in arms}
    write(adr/'실험/manifest.json',m)
    p=adr/'README.md';front=p.read_text().split('---',2)[1];front=front.replace('status: Proposed','status: Rejected' if args.aborted else 'status: Proposed')
    sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
    texts=[('journal 계약 불일치로 실행 중단. 후보 실패를 보존한다.' if args.aborted else '격리 프로토타입의 연속 실행 결과. 성공·미충족은 아래 원시 점수와 기능별 보고서를 따른다.')+'\n\n[상세 보고서](../../../'+str(report.relative_to(ROOT))+')','r3의 초기 전제 역추적·단계 재실행·최종 경로 소비를 검증한다. 비교군은 새 실행기의 CURRENT_ONLY ablation이며 MAIN 성능 비교가 아니다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'같은 DB에서 5개 연속 대화 43턴. CHAIN/CURRENT_ONLY를 사례별 교대 순서로 실행. SEQ05의 계획된 ASSESS 실패 뒤 다음 명시 턴에서 복구.', '합성 자료만 전송. Qwen3.8-27b Parasail FP8 reasoning none, fallback·자동 repair 없음. 입력·gold·코드·runner 사전 hash 동결.',block(summary['by_arm']),block(failures),block({'usage':summary['usage'],'latency':summary.get('turn_latency_seconds',{}),'retrieval':summary['retrieval']}),'원시 결과와 상세 보고서를 따른다. 해석 실패와 실행 계약 실패를 구분한다. 새 후보 수정·재실험은 새 ADR이다.','인샘플·합성 실행기. 실제 사용자 질문·법률 품질·운영 API·GENOS·동시성 성능으로 일반화하지 않는다.','MAIN unchanged. 활성 포인터·원문·부모 ADR 보존. graph 전체 검사 실패 시 정식 절차 완료로 보고하지 않는다.','동결 runner를 실행하되 기존 run 경로는 덮어쓰지 않고 거부한다. 새 반복은 새 ADR/run 계약으로 진행한다.']
    p.write_text('---'+front+'---\n\n# '+number+' — RAG 멀티턴 체인 프로토타입\n\n'+'\n\n'.join('## '+s+'\n\n'+t for s,t in zip(sections,texts))+'\n')
    (adr/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | CHAIN 검사 | CURRENT_ONLY 검사 |\n|---|---|---|\n'+'\n'.join('| ['+q['case_id']+']('+q['file']+') | '+str(g['arms']['CHAIN']['passed'])+'/'+str(g['arms']['CHAIN']['total'])+' | '+str(g['arms']['CURRENT_ONLY']['passed'])+'/'+str(g['arms']['CURRENT_ONLY']['total'])+' |' for q,g in zip(m['questions'],grades))+'\n')
    index=ROOT/'04_EXPERIMENTS/ADR/README.md';line='- ['+number+' — RAG 멀티턴 체인 프로토타입]('+adr.name+'/README.md)\n'
    if adr.name not in index.read_text():index.write_text(index.read_text()+'\n'+line)
    files=[p for p in adr.rglob('*') if p.is_file() and p!=adr/'artifacts/manifest.json']
    for cid in ['stage-chain','current-context']:
        folder=ROOT/'02_BACKEND/lawrag/research/candidates'/('adr_'+number.split('-')[1])/cid
        files.extend(p for p in folder.rglob('*') if p.is_file())
    files.extend(p for p in (ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+number.split('-')[1])).glob('*.py'))
    write(adr/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','artifacts':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(files))]})
    print(json.dumps({'report':str(report.relative_to(ROOT)),'summary':summary['by_arm'],'failures':len(failures)},ensure_ascii=False))

if __name__=='__main__':main()

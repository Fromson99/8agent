"""Readable audit and exact raw question records, generated only after the run."""
import html
import json
import subprocess
import sys
from pathlib import Path
from summarize import A, R, read, write, sha

def block(x): return '\n```json\n'+json.dumps(x,ensure_ascii=False,indent=2)+'\n```\n'
def esc(x): return html.escape(str(x))

def main():
    m=read(A/'실험/manifest.json'); summary=read(A/'artifacts/trace-summary.json')
    res=read(A/'artifacts/run-001/results.json'); ledger=read(A/'artifacts/retrieval-stage-ledger.json')
    rows=summary['by_case']; totals=summary['by_arm']
    table='|질문|arm|읽은 gold|모델 전달 gold|최종 인용 gold|호출|\n|---|---|---:|---:|---:|---:|\n'
    table+='\n'.join(f"|{x['case_id']}|{x['arm']}|{x['gold_by_stage']['read']}/{x['gold_total']}|{x['gold_by_stage']['presented']}/{x['gold_total']}|{x['gold_by_stage']['answer']}/{x['gold_total']}|{x['calls']}|" for x in rows)
    review=['# 실제 추출값과 회수 결과',table,'원문 인용이 있는 실질 답변과 근거 부족 안내를 구분한다. 아래 집계는 법률 정답률이 아니다.']
    page=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>v5 선택형 역매칭 실험</title><style>body{font:16px/1.65 system-ui;max-width:1050px;margin:40px auto;padding:0 20px;color:#18283d;background:#f7f9fc}article,details{background:white;border:1px solid #d8dfeb;padding:16px;margin:12px 0;border-radius:8px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}small{color:#53647a}h1,h2{line-height:1.3}</style><h1>선택형 역매칭 · 실제 추출 결과</h1><p>명시 조문 → 본문 용어 → 참고 용어 순으로 주목합니다. 어떤 후보도 필수 읽기 대상이 아니며 일반 검색은 항상 가능합니다. 이 화면은 격리 실험 산출물입니다.</p>']
    for q in m['questions']:
        cid=q['case_id']; cases=[x for x in rows if x['case_id']==cid]; candidate=next(x for x in cases if x['arm']=='priority')
        review+=['## '+cid,candidate['question']]
        page+=['<article><h2>'+esc(cid)+'</h2><p>'+esc(candidate['question'])+'</p>']
        matches=candidate['matches']
        for key,label in [('explicit_structure','최우선: 명시 좌표'),('body_terms','1순위: 본문 용어'),('reference_terms','2순위: 참고 용어')]:
            values=matches.get(key,[])
            labels=[((v.get('document_name') or '')+' '+(v.get('coordinate') or '')).strip() if key=='explicit_structure' else v['label'] for v in values]
            review+=['### '+label+f' ({len(values)}개)',', '.join(dict.fromkeys(labels)) or '없음']
            page+=['<details><summary>'+esc(label)+f' · {len(values)}개</summary>']
            for value,labelvalue in zip(values,labels):
                page+=['<p><strong>'+esc(labelvalue)+'</strong>']
                if 'indexed_occurrence_count' in value:page+=[' · 연결 원문 '+str(value['indexed_occurrence_count'])+'건']
                page+=['<br><small>질문에서 추출: '+esc(', '.join(x['text'] for x in value.get('question_spans',[])))+'</small></p>']
            page+=['</details>']
        base=A/'artifacts/run-001'/cid/'priority'
        found=read(base/'found-sources.json') if (base/'found-sources.json').exists() else {'sources':[]}
        page+=['<h3>찾은 원문</h3>']
        if not found['sources']:page+=['<p>이번 실행에서 실제 READ를 완료한 원문이 없습니다. 위의 탐색 후보는 읽은 근거로 집계하지 않습니다.</p>']
        for source in found['sources']:
            page+=['<details><summary>'+esc(source['document_name']+' '+source['coordinate'])+'</summary><p>'+esc(source['status'])+'</p><pre>'+esc(source['text'])+'</pre></details>']
        for x in cases:
            result=res['cases'][cid][x['arm']]
            review+=['### '+x['arm'],block({'gold_by_stage':x['gold_by_stage'],'gold_total':x['gold_total'],'error':x['error'],'limitations':result.get('limitations'),'semantic_errors':x['semantic_errors']})]
            page+=['<p>'+esc(x['arm'])+': 근거 전달 '+str(x['gold_by_stage']['presented'])+'/'+str(x['gold_total'])+' · '+esc('; '.join(result.get('limitations',[])))+'</p>']
        page+=['</article>']
        raw=[]
        for arm in ('baseline','priority'):
            b=A/'artifacts/run-001'/cid/arm
            raw+=['### '+arm+' 실행 기록',block(res['cases'][cid][arm]),'### '+arm+' 탐색·읽기·선택 원값',block(read(b/'trace.json'))]
            for p in sorted((b/'calls').rglob('*.json')):raw+=['### '+str(p.relative_to(A)),block(read(p))]
        stages=[{'arm':a['arm_id'],'case':next(c for c in a['cases'] if c['case_id']==cid)} for a in ledger['runs'][0]['arms']]
        sections=[('실행 메타',block({'case_id':cid,'run':'run-001','arms':['baseline','priority'],'model':m['llm_policy']['required_model']})),('사용자 질문 원문',candidate['question']),('기준답변 — 채점 전용, 제품 입력 비공개',candidate['reference_answer']),('제품 입력을 구성한 원값','원시 trace 및 실제 system/user/schema 전체는 다음 절.\n\n### 회수·탈락 단계 원장 — run·arm별\n'+block(stages)),('제품 모델 호출 — run·arm별 실제 원문','\n'.join(raw)),('중간 LLM 호출 — router/compiler/verifier/repair','형식 수정 포함 모든 호출을 위에 보존했다. 별도 평가 모델 호출 없음.'),('채점 호출과 반복 판정','자동 judge 및 법률 정답률 채점 없음. 모델 선택 완료 뒤 고정 gold 조문과 trace를 대조한 회수 집계다.'),('사례 최종 판정',block([{k:x[k] for k in ['arm','gold_by_stage','gold_total','retained_source_count','retention_exact','error']} for x in cases]))]
        (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1)))
    page+=['</html>'];(A/'artifacts/review.html').write_text('\n'.join(page));(A/'CASE_REVIEW.md').write_text('\n\n'.join(review)+'\n')
    front=(A/'README.md').read_text().split('---',2)[1]
    sections=[('결정 요약','선택형 우선순위와 찾은 원문 보존을 격리 후보에 구현했다. 강제 읽기·일반 검색 차단 없음. 회수 개선 여부는 아래 실제 결과를 따른다. MAIN/GENOS unchanged.\n\n'+table),('문제와 변경 전 구조','선택된 로컬 v5 release legal-agent-v5-20260922-r3에는 용어집·본문 매처가 연결되어 있지만 자동 질문 역매칭의 주목 순서가 없었다. 후보는 matcher.starts→PriorityMatching→investigate view, term_occurrences→read, retained_sources→assembly.term_agent→로컬 /rag/ UI 흐름으로 연결한다. 용어 연결 목록은 선택 시 열고 원문은 다시 선택해 읽는다.'),('가설과 사전 판정 기준','[PLAN](PLAN.md)과 [동결 설계](artifacts/frozen-design.json)를 실제 호출 전에 고정했다. 질문별 gold 읽기 회귀 0, 전체 모델 전달 gold 증가, 읽은 원문 보존 100%, 강제 순서 없음, 입력 초과 0. 사용자 정정 전 계획은 별도 보존했다.'),('실험 설계','baseline은 선택된 v5 코드, priority는 rev-003 격리 후보. CM003·CM018·CM038 각 두 arm 한 번씩, 같은 데이터/모델/예산. 단회 in-sample probe, decision_eligible=false. 제품 runner는 gold를 읽지 않는다.'),('데이터·모델·재현성','공개 145문서 scope와 해시 검증한 기존 RAW. qwen/qwen3.5-122b-a10b, FP8, thinking off, temperature0, 자동 fallback 없음. GENOS 현장 성능 아님. 기준 원문·기준답의 현행 법률 버전은 이번 실험에서 재인증하지 않았다.'),('결과',table+'\n\n'+block(summary['criteria'])+'\n실질 답변 정확도는 미측정. 근거 없는 안내 응답을 성공 정답으로 집계하지 않는다.'),('사례별 오류 분석','[CASE_REVIEW](CASE_REVIEW.md), [추출값·찾은 원문 화면](artifacts/review.html), [질문별 전체 입출력](실험/README.md). 응답 스키마/도구 실행 실패와 회수 부족을 분리한다. 좌표 단편의 광범위 매칭도 그대로 기록했다.'),('비용·지연·회수 규모',block(totals)+'\n설정: context 60000 characters, output6400 tokens, wire2000000 bytes,14 model attempts,56 tools,300 seconds. 서로 다른 한도이며 실제 모델 token window를 뜻하지 않는다. 실제 전송 토큰·bytes·usage는 원시 기록. ledger 최종 stage는 answer이며 primary인 모델 전달 presented와 구분한다.\n\n[전체 단계별 원장](artifacts/retrieval-stage-ledger.json)'),('해석','주목 단서 제공, 모델의 후보 선택, 원문 READ, 모델에 실제 제시, 최종 채택은 별도 상태다. 형식 오류로 READ 이전에 중단된 실행은 원문 보존의 실모델 검증으로 볼 수 없다. 입력 초과 시 원문 보존은 긴 원문 합성 계약 검사로 확인했다.'),('한계와 일반화 가능 범위','3문항 단회, 자동 법률 judge/holdout/현장 검증 없음. 구조 좌표와 용어 수는 관련성 점수가 아니다. 모델이 보지 않은 원문은 사용자에게 제공하되 검토·인용 자격을 부여하지 않는다.'),('운영 결정·롤백 조건','실험 후보만 변경. MAIN 선택 포인터/배포 리비전 유지. 실제 결과가 성공 기준을 충족하지 못하면 승격 불가. 후속 품질 수정·재실행은 새 ADR로 분기한다. 기존 활성 릴리스 자체를 변경하지 않았으므로 운영 롤백은 불필요.'),('재현 명령','```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0507/summarize.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0507/report.py\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+str(A.relative_to(R))+' --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n완료 run은 덮어쓰지 않는다. 재호출은 새 ADR. 검증 결과는 artifacts/completion.json 참조.')]
    (A/'README.md').write_text('---'+front+'---\n\n# v5 선택형 역매칭 실험\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1))+'\n')
    (A/'실험/README.md').write_text('# 실제 입출력 인덱스\n\n'+table+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],cwd=R,check=True)
    excluded={'manifest.json','completion.json','validation-final.txt','graph-check.txt'}
    files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in excluded and not p.name.endswith(('-wal','-shm'))]
    files+=list(Path(__file__).parent.glob('*.py'))+[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',A/'CASE_REVIEW.md']
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0507/priority';files+=[C/'candidate.json']+[R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
    write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0507','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact run, frozen code/input or report'} for p in sorted(set(files))]})
    print('Reports generated; run completion validation separately.')

if __name__=='__main__':main()

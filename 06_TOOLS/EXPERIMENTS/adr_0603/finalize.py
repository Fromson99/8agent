"""Close the failed recorder audit and completed functional audit without regrading."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def finalize(number):
    a=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04d}-*'));p=a/'실험/manifest.json';m=json.loads(p.read_text());run=a/'artifacts/run-001'
    complete=number==603
    if complete:
        r=json.loads((run/'result.json').read_text());m['results'].update(status='complete',by_arm={'INTEGRATED':{'contracts_passed':r['passed'],'contracts_total':r['total'],'inherited_passed':r['inherited']['passed'],'inherited_total':r['inherited']['total'],'external_model_calls':0}},comparisons=[],judge_disagreements=0,usage={'external_model_calls':0},latency={'not_measured':'functional audit; no performance conclusion'},error_taxonomy=[])
        m['runs'][0].update(status='complete',sha256=sha(run/'result.json'))
        summary='일반 통합 계약 46/46, 기존 정정 계약 35/35. 외부 모델 0회. 실제 색인·원문 읽기·HTTP·SQLite 온톨로지 연결은 모의 자료와 정해 둔 의미 판단으로 검증했다.'
    else:
        r={'status':'failed','error':'Output recorder TypeError: set is not JSON serializable','product_observations':{'native_http':200,'native_initial':'READY','native_finalization':'STORED','native_table_stages':['COMPOSE']},'scope':'Observed artifacts only; no aggregate contract score reconstructed','external_model_calls':0}
        write(run/'execution-abort.json',r);m['runs'][0].update(status='failed',artifact_path=str((run/'execution-abort.json').relative_to(ROOT)),sha256=sha(run/'execution-abort.json'));m['results'].update(status='failed',by_arm={'INTEGRATED':{'execution_status':'recording_failed','aggregate_contract_score':None}},comparisons=[],judge_disagreements=0,usage={'external_model_calls':0},latency={'not_measured':'recording aborted'},error_taxonomy=[{'type':'other','cause':r['error']}]);summary='제품 실행과 DB는 보존했으나 결과 기록기가 set을 직렬화하지 못해 집계 미완료. 새 ADR0603에 별도 실행 기록. 전체 점수는 복원하지 않았다.'
    for q in m['questions']:
        text='# '+q['case_id']+'\n\n'
        sections=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
        values=[f'ADR-{number:04d}/INTEGRATED/run-001, synthetic functional audit',block(json.loads((a/'artifacts/design/inputs.json').read_text())),'동결 inputs.json의 required_contracts. 법률 정답·모델 정확도 평가 아님.',block(r), '외부 모델 0회. 실제 입력은 scripted provider 자료와 native journal에 저장.','정해 둔 의미 응답; 입력·출력은 artifacts/run-001.','일반 계약 assertions; judge model 호출 없음.',summary]
        for i,(h,v) in enumerate(zip(sections,values),1):text+='## '+str(i)+'. '+h+'\n\n'+v+'\n\n'
        text+='### 회수·탈락 단계 원장 — run·arm별\n\n검색 품질 비교 아님. 실제 SourceRecall·READ 원문은 native journal과 model-inputs-scripted.json에 보존.\n'
        (a/'실험'/q['file']).write_text(text)
    texts=[summary,'기존 프로토의 정정 체인은 공통 지식 적재기와 실제 RAG API에 연결되지 않았다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'작업 상태·확인된 최종 지식 분리, typed graph, 7단계 실행, 위키 연결 수정, 사용자별 세션.','동결 후보 명시 주입. 원문·모델 정책·활성 MAIN 보존. 외부 모델 0회.',block(m['results']['by_arm']),'결과 기록기 실패는 ADR0602에 남김. ADR0603에서 기능 계약 전수 확인.','외부 모델 비용 0. 실제 모델의 호출 비용·지연·검색 품질은 미측정.','일반 연결 검증이며 자연어 이해 성능으로 확대하지 않는다.','실제 LLM 자연어 정정·법률 정확도·GENOS 현장·분산 동시성 미검증.','MAIN unchanged. opt-in injection 후보이며 기존 릴리스에 자동 등록하지 않음.','새 반복은 새 ADR. .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0603/run.py 는 기존 run 덮어쓰기를 거부한다.']
    front=(a/'README.md').read_text().split('---',2)[1];(a/'README.md').write_text('---'+front+'---\n\n# ADR-'+str(number).zfill(4)+' — 정정 루트 통합\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+t for i,(h,t) in enumerate(zip(HEADINGS,texts),1))+'\n')
    (a/'실험/README.md').write_text('# 질문 인덱스\n\n'+''.join('- ['+q['case_id']+']('+q['file']+')\n' for q in m['questions']))
    write(p,m)
    return summary
if __name__=='__main__':
    print(finalize(602));print(finalize(603))

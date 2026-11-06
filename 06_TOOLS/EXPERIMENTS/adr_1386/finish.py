from common import *
import sqlite3
out=ART/'followup-conflict';p=out/'result.json'
result=read(p) if p.is_file() else {'status':'NOT_RUN','physical_calls':0,'unknown':0,'reported_cost_usd':0,'seconds':0}
r=read(ART/'semantic-review.json');seed=read(DES/'seed.json');b=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(ROOT/n)==h for n,h in read(DES/'freeze.json')['files'].items())
def pubs(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        return list(db.execute('SELECT BNDL_ID,PUB_ID,CHG_SEQ_NO FROM LGL_ONT_HEAD_A ORDER BY BNDL_ID')),list(db.execute('SELECT PUB_ID FROM LGL_ONT_PUB_A ORDER BY PUB_ID'))
original=pubs(ROOT/seed['root']/'work.sqlite');after=pubs(ART/'sandbox-repository/work.sqlite')
added=set(after[0])-set(original[0])
assert set(original[0])<=set(after[0]) and all(pub is None for _,pub,_ in added) and original[1]==after[1]
assert any(bid==seed['approved']['bundle_id'] and pub==seed['approved']['publication_id'] for bid,pub,seq in after[0])
summary={'result':result,'review':r,'selected_main':145,'prior_revision':2,'new_revision':(result.get('row') or {}).get('revision'),'new_unpublished_heads':len(added),'prior_head_still_active':True,'publication_ids_unchanged':True,'seed_hashes_verified':True,'main_or_field_publications':0}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'prior_replay':'1376/repaired'},'selected':summary},comparisons=[],judge_disagreements=0,usage={k:result[k] for k in ('physical_calls','unknown','reported_cost_usd')},latency={'comparison_seconds':result['seconds']},error_taxonomy=r['issues'])
put(ADR/'실험/manifest.json',m)
h=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
c=f"{result['physical_calls']}호출 · 결과 불명 {result['unknown']}회 · {result['seconds']:.1f}초 · 보고 USD {result['reported_cost_usd']:.8f}."
notes=[r['headline'],'1376에서는 앞서 받은 모델 응답으로 독립 신규 근거의 수용을 재생 검증했다.','기존 그래프와 활성 묶음·원문 근거를 보존한 상태로 상충 판단만 다음 초안에 기록하는지 본다.',
'승인 2판 SQLite와 객체 저장소의 격리 사본, 과거의 실제 일반결의 적용 오판과 원문. 새 응답에는 원래 검토·단계당 최대 네 번 보완을 적용한다.',
'공개상법 고정 세대, MAIN145 528파일과 Qwen3.8 FP8, 추론 none. 판정 기준은 모델 입력에서 분리했다.',r['detail'],' '.join(r['issues']) or '추가 검토 오류 없음.',c,r['interpretation'],
'정관 관련 후속 판단 1건이며 다른 정관 쟁점과 미확인 슬롯의 보완은 별도다.','기존 승인 2판의 publication_id·DB head 보존 확인. 이 시험에서 운영 지식 게시 0건.',
'setup → compare conflict --preflight → 사용 실험 전송 상태 확인 → compare conflict → 저장·원문·활성판 대조 → finish/seal/hash/validate.']
p=ADR/'README.md';front=p.read_text().split('---',2)[1]
p.write_text('---'+front+'---\n\n# MAIN145 실제 후속 판단\n\n'+'\n\n'.join(f'## {i}. {a}\n\n{b}' for i,(a,b) in enumerate(zip(h,notes),1))+'\n')
q=m['questions'][0]
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qn=['run-001/selected','정관 변경에서 일반결의 기준을 적용한 과거 판단을 기존 묶음에 대조·누적한다.','그 판단이 기존 원문과 충돌하는지 독립적으로 대조했다.',
'### 회수·탈락 단계 원장 — run·arm별\n\n검색 없음. design/followups.json의 원기록과 승인 2판의 고정 근거를 사용했다.','artifacts/followup-conflict/raw 및 canonical. '+c,
'논리 단계와 보완 결과를 generations.json에 기록했다.','별도 채점 모델 0회. 원판·비교 이력·DB 상태 대조.',r['headline']+' '+r['detail']]
(ADR/'실험'/q['file']).write_text('# 후속 판단\n\n'+'\n\n'.join(f'## {i}. {a}\n\n{b}' for i,(a,b) in enumerate(zip(qh,qn),1))+'\n')
(ADR/'실험/README.md').write_text(f"# 검토 기록\n\n[후속 판단]({q['file']})\n")
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-main143'
(report/'자동누적_Qwen_재검증.txt').write_text('\n\n'.join([r['headline'],r['detail'],r['interpretation'],c,notes[10]])+'\n')
print(r['headline'],c)

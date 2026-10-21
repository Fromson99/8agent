"""Offline final record from immutable calls plus a separately recorded human-style audit."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import math
import shutil
import tarfile

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0956-comparison-required-scope-retest'
D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
review=read(O/'manual-review.json');result=read(O/'result.json');m=read(A/'실험/manifest.json')
cases=read(D/'cases.json');gold=read(D/'gold-evaluation-only.json');criteria=read(D/'criteria.json')
ledger=read(O/'retrieval-ledger.json')
for n,h in read(D/'freeze.json')['files'].items():assert sha(R/n)==h,n
for arm in result['by_arm']:
    passed=sum(review['cases'][c['id']][arm]['scope_pass'] for c in cases)
    result['by_arm'][arm].update(scope_correct=passed,scope_total=len(cases),
        scope_accuracy=passed/len(cases),legal_accuracy=None)
paired={'baseline':'control','candidate':'scoped','metric':'scope_pass',
    'candidate_only':0,'baseline_only_regression':0,'both_pass':0,'both_fail':0}
for c in cases:
    b=review['cases'][c['id']]['control']['scope_pass'];s=review['cases'][c['id']]['scoped']['scope_pass']
    key='both_pass' if b and s else 'both_fail' if not b and not s else 'candidate_only' if s else 'baseline_only_regression'
    paired[key]+=1
paired['accuracy_delta']=result['by_arm']['scoped']['scope_accuracy']-result['by_arm']['control']['scope_accuracy']
for key in ('model_calls','input_tokens','output_tokens','cost_usd'):
    paired[key+'_delta']=result['by_arm']['scoped'][key]-result['by_arm']['control'][key]
result.update(paired=[paired],scope_success=review['scope_success'],scope_checks=review['checks'],
    manual_review=str((O/'manual-review.json').relative_to(R)))
put(O/'result.json',result)
m['results'].update(by_arm=result['by_arm'],comparisons=[paired],judge_disagreements=0,
    manual_judge_note='One offline record review. No evaluator model, no repeated judgment, no inter-rater agreement claim.',
    error_taxonomy=review.get('error_taxonomy',[]))
m['runs'][0]['sha256']=sha(O/'result.json');put(A/'실험/manifest.json',m)
summary=[
    'ADR0956 대사 필수 조사 범위 재검증 — 2026-10-20',
    '같은 합성7문서16조항, 승인 연결2개, 질문4개를 MAIN94(control)와 작업 workflow1.20.2(scoped)에 각1회 실행했다.',
    'Qwen3.8/qwen3.8-27b, OpenRouter Parasail FP8, reasoning none, fallback 없음. 실행 순서는 질문별로 번갈아 고정했고 무거운 요청은 순차 실행했다.',
    '판정: '+('고정 범위 검사 통과' if review['scope_success'] else '고정 범위 검사 미충족')+
    '. 인샘플 Proposed, decision_eligible=false, quality_certified=false.',
    '',
]
for c in cases:
    name=c['id'];b=result['cases']['control'][name];s=result['cases']['scoped'][name]
    summary.append(f"{name}: 호출 {b['model_calls']} → {s['model_calls']}, 시간 {b['elapsed_seconds']:.1f} → {s['elapsed_seconds']:.1f}초.")
    summary.append(review['cases'][name]['finding'])
b=result['by_arm']['control'];s=result['by_arm']['scoped']
summary+=['',f"전체 호출 {b['model_calls']} → {s['model_calls']}; 비용 ${b['cost_usd']:.8f} → ${s['cost_usd']:.8f}.",
    f"범위 판정 {b['scope_correct']}/{len(cases)} → {s['scope_correct']}/{len(cases)}. 실제 법률 정답률이 아니다.",
    '필수 원문 최종 인용 회수율: '+json.dumps(m['retrieval_accounting']['golden_recall'],ensure_ascii=False),
    f"원문·span·해시 검사 {b['stored_original_checks']}+{s['stored_original_checks']}, 불일치 {b['source_mismatches']}+{s['source_mismatches']}.",
    '과거 ADR0955의 호출 수를 비교 기준으로 재사용하지 않고 이번에 실행한 control과 비교했다.',
    'MAIN 선택은 이 실험 실행 중 유지했다. 사용자 요청에 따른 MAIN 반영은 별도 maintenance receipt로 수행하며 이 탐침을 일반화 품질 인증으로 바꾸지 않는다.',
    '선택 개념 밖 승인 연결 조회와 더 엄격한 내규의 상충 오판은 이번 수정 대상이 아니며 발견 시 그대로 기록했다.',
    '실제 risk_cm 자료·GENOS 내부 모델·Oracle 현장·전체 corpus 성능은 검증하지 않았다.',
    '사전 일반 validate는 아직 측정하지 않은 회수 집계값 누락을 보고했다. 두 코드 revision의 freeze/validate 및 설계 해시는 첫 호출 전 통과·고정했고, 최종 기록 검사는 측정값을 채운 뒤 별도 실행했다.',
    '',json.dumps(review['checks'],ensure_ascii=False,indent=2)]
(A/'RESULT.txt').write_text('\n'.join(summary)+'\n')
front=(A/'README.md').read_text().split('---',2)[1]
parts=[
    '\n'.join(summary[:5]),
    'MAIN94의 질문→내규→개념→연결 외규→선택 참조→대사표 경로. 같은 질문 밖 산식 확인으로 명시 추가 조사 과제가 확장된 ADR0955 관찰을 재검증했다.',
    json.dumps(criteria,ensure_ascii=False,indent=2),
    'control/scoped 두 frozen revision, 질문4개 각1회. 같은 합성 generation을 읽기 전용 공유. scoped는 이전 사용자 요청으로 작성한 유지보수4파일과 종속 pin만 다르며 실험 중 제품 코드를 수정하지 않았다.',
    'artifacts/design/freeze.json 및 두 arm-binding에 코드·자료·모델·profile·runner·정책 hash를 고정. 같은 common ExperimentClient와 제품 gateway. 제품 입력에는 gold가 없다.',
    '\n'.join(summary),
    json.dumps(review,ensure_ascii=False,indent=2),
    json.dumps({'by_arm':result['by_arm'],'paired':paired,'retrieval':m['retrieval_accounting']},ensure_ascii=False,indent=2),
    '범위 제한의 효과와 원문 회수·의미 정답을 분리한다. 문서·버전·위치 기반 표시 병합은 마지막 표시 단계이므로 앞선 모델 호출 감소의 원인으로 해석하지 않는다.',
    '\n'.join(criteria['limitations']),
    '실험 판정은 Proposed·in-sample·decision_eligible=false로 보존한다. 사용자 지시로 수행하는 유지보수 MAIN 전환은 별도 receipt에 기록하며, 인용·권한·해시·실제 서비스 검증은 생략하지 않는다.',
    '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0956/prepare.py\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0956/run_sequence.py\n완료 실행은 덮어쓰지 않는다. 재실행은 새 ADR·예산을 동결한다. 사후 집계 report.py, 수동 판정 manual-review.json, write_record.py. runtime 복원은 RESTORE.txt.']
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
(A/'README.md').write_text('---'+front+'---\n\n# ADR-0956: 대사 필수 조사 범위 재검증\n\n'+
    '\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(headings,parts),1))+'\n')
index=['# 사례 인덱스','','control=MAIN94, scoped=기존 작업 workflow1.20.2. 모든 gold는 제품 비공개.']
for i,c in enumerate(cases,1):
    name=c['id'];text=[f'# {name}','\n## 1. 실행 메타\n',
        'run-001 / control·scoped / qwen/qwen3.8-27b / Parasail FP8 / 단회 / 합성·in-sample',
        '\n## 2. 사용자 질문 원문\n',c['question'],
        '\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n',json.dumps(gold[name],ensure_ascii=False,indent=2),
        '\n## 4. 제품 입력을 구성한 원값\n',
        '[합성 원문](../artifacts/design/documents.json), [코드·자료 동결](../artifacts/design/freeze.json).',
        '\n### 회수·탈락 단계 원장 — run·arm별\n']
    for arm in ('control','scoped'):
        ld=next(x for a in ledger['runs'][0]['arms'] if a['arm_id']==arm for x in a['cases'] if x['case_id']==name)
        text+=['\n'+arm+'\n','| 단계 | before | added | discarded | after | gold after/total |',
               '|---|---:|---:|---:|---:|---:|']
        text += [f"| {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} | {s['gold_after']}/{s['gold_total']} |" for s in ld['stages']]
    text+=['[전체 exact identity·탈락 원장](../artifacts/run-001/retrieval-ledger.json).',
        '\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n']
    for arm in ('control','scoped'):
        Q=O/arm/name;text+=['\n### '+arm+'\n',(Q/'answer.txt').read_text()]
        for call in sorted((Q/'raw').glob('call-*')):
            text.append('- '+call.name+': '+', '.join(f'[{p.name}](../{p.relative_to(A)})' for p in sorted(call.iterdir()) if p.is_file()))
    text+=['\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n',
        '5절의 call 번호에 모든 중간 호출을 포함한다. system/user/schema·provider 원응답·usage를 원본 그대로 저장했다. 각 arm/case의 canonical 및 wire gzip에도 실제 입력을 보존한다.',
        '\n## 7. 채점 호출과 반복 판정\n',
        '모델 judge 0회, 저장 원문·답변·조사 과제를 한 평가자가 검토했다. 반복이나 다수결은 없으며 독립 평가자 일치도는 미측정이다.',
        '\n## 8. 사례 최종 판정\n',json.dumps(review['cases'][name],ensure_ascii=False,indent=2)]
    filename=f'질문-{i:03d}-{name}.md';(A/'실험'/filename).write_text('\n'.join(text)+'\n')
    index.append(f'- [{name}]({filename}) — '+review['cases'][name]['finding'])
(A/'실험/README.md').write_text('\n'.join(index)+'\n')
root_index=R/'04_EXPERIMENTS/ADR/README.md';text=root_index.read_text()
entry='- [ADR-0956 대사 필수 조사 범위 재검증](ADR-0956-comparison-required-scope-retest/README.md) — 같은 합성4사례 control/scoped 비교, 실제 '+str(result['model_calls'])+'호출. Proposed·in-sample, 유지보수 MAIN 선택은 별도.\n'
assert 'ADR-0956 대사 필수 조사 범위 재검증' not in text
offset=text.index('\n')+1;root_index.write_text(text[:offset]+'\n'+entry+text[offset:])

# Closed runtime only, exact member hashes verified before removing temporary copies.
runtime_roots=sorted(O.glob('*/*/runtime'));assert len(runtime_roots)==8
inventory={str(p.relative_to(R)):{'sha256':sha(p),'bytes':p.stat().st_size}
           for root in runtime_roots for p in root.rglob('*') if p.is_file()}
archive=A/'artifacts/completed-runtime.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz') as bundle:
    for root in runtime_roots:bundle.add(root,arcname=str(root.relative_to(R)))
with tarfile.open(archive,'r:gz') as bundle:
    members=[x for x in bundle if x.isfile()];assert {x.name for x in members}==set(inventory)
    for member in members:
        assert hashlib.file_digest(bundle.extractfile(member),'sha256').hexdigest()==inventory[member.name]['sha256']
put(A/'artifacts/completed-runtime-inventory.json',{'archive':str(archive.relative_to(R)),
    'sha256':sha(archive),'files':inventory,'all_members_verified':True})
for root in runtime_roots:shutil.rmtree(root)
(A/'RESTORE.txt').write_text('저장소 루트에서 완료 runtime 복원:\ntar -xzf '+str(archive.relative_to(R))+
    '\n개별 원본 SHA256: artifacts/completed-runtime-inventory.json\n완료 요청은 재호출하거나 덮어쓰지 않는다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']
files+=list(T.glob('*.py'))+[A/'RESTORE.txt']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0956',
    'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Exact paired experiment record or reproducibility input',
        'contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts} for p in sorted(files)]})
print('\n'.join(summary))

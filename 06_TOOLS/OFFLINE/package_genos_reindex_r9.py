"""R9 measurable progress on frozen R8; preserve all prior handoff bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import package_genos_reindex_r8 as previous

ROOT = previous.ROOT
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/reindex_progress_20261002_r9'
STEM = 'GENOS_REINDEX_PROGRESS_20261002_R9'
BASE_SHA = '75666b3ea527fc7d766602b616ef5ce3736a013f25f530b5d929d9df8a64cde8'
CHANGED = ['02_BACKEND/lawrag/pipeline/glossary_linking.py',
           '02_BACKEND/semantic_runtime/term_index.py',
           '02_BACKEND/semantic_runtime/fulltext.py',
           '06_TOOLS/OFFLINE/genos_reindex_logging.py']
GUIDE = '''GENOS R9 — R8 연결/색인 전용 + 실제 건수/속도/예상 잔여
R8 대신 ZIP과 TXT를 같이 ~/DEV/TRANSFER에 올립니다.
  cd ~/DEV
  export GENOS_PREPARED_RUN=financial-risk-success-20261001-r3
  export GENOS_OPTIMIZED_RUN=financial-risk-success-20261002-index-r9
  bash TRANSFER/GENOS_REINDEX_PROGRESS_20261002_R9.txt

동일 checkout/prepared 입력의 R8/R7 실행은 PID 신원 확인 후 SIGINT·종료 확인합니다.
이전 실행/입력/산출물을 삭제하지 않습니다. 새 run에서 처리합니다.
R8 최적화/선택 입력/연결·색인 범위는 유지합니다. 모델 호출·구조화·용어집 새 검토 없음.
변경은 처리 루프 계측과 로그이며 R8 코드 해시를 명시적으로 허용합니다.

5초 RUNNING 로그:
 task: 현재 세부 처리
 completed / total / unit / percent: 실제 완료 건수·전체 건수·단위·진행률
 recent_units_per_second: 최근 최대 60초 실측 속도
 average_units_per_second: 해당 처리 전체 평균 속도
 remaining_seconds / estimated_task_finish_utc: 현재 세부 처리 예상 잔여와 종료 UTC 시각
 estimate_comparison_seconds: 최근/평균 속도 추정 비교 범위(통계적 신뢰구간 아님)
 seconds_since_last_completion: 마지막 완료 이후 시간(30초 이상이면 ETA 표시 중지)
 overall_eta: 후속 단계 미측정; 전체 완료 시각으로 읽지 않습니다.

연결: block-matching 블록 수 → catalogue-linking 일치 표면 수.
navigation: document-navigation 문서 수 → references/감사/통계/검증 세부 처리.
전문 색인: tokenize-and-index source 수 → optimize/해시 검증.
진행률 100%는 현재 루프 완료이며 전체 작업 완료가 아닙니다.
계수 없는 준비/SQL/해시 구간은 total=null, ETA=null과 정확한 세부 이름을 표시합니다.
2건 이상·10초 이상 실측 뒤 ETA를 표시합니다. 크기/난이도가 달라 변할 수 있습니다.
실제 완료 건수는 정확히 계수하지만 미래 완료 시각을 정확히 보장할 수는 없습니다.
출력 source는 문서가 아니라 검색 단위입니다. 각 단계 단위를 구분합니다.

모든 이벤트: LOGS/<output-run>/reindex-only-r9/<시각-PID>/events.jsonl
터미널 전체: run.log / 현재 상태: current.json / 단계 시간: phases.csv / 종료: summary.txt
GENOS_LOG_INTERVAL=5 기본. 재실행은 같은 R9 명령, 완료 navigation 검증·재사용 가능.
완료: reindex VERIFIED 및 FINISHED status=0. 서빙 활성화는 별도.
출력: TERM_RELEASES/financial-risk-success-20261002-index-r9/reindex/
롤백과 기존 계약 세부 내용은 ZIP의 GUIDE_UTF8.txt 후반에 보존합니다.
GENOS 실제 실행·처리 속도·최종 시간은 아직 미확인입니다.
'''

def main():
    base = previous.OUT / (previous.STEM + '.zip')
    assert hashlib.sha256(base.read_bytes()).hexdigest() == BASE_SHA
    with zipfile.ZipFile(base) as z: payload = {n:z.read(n) for n in z.namelist()}
    manifest = json.loads(payload.pop('CODE_MANIFEST.json'))
    base_guide = payload['GUIDE_UTF8.txt']
    for row in manifest['files']:
        if row['path'] in CHANGED:
            old = row['sha256']
            row['allowed_predecessors'] = list(dict.fromkeys(row.get('allowed_predecessors', []) + [old]))
            payload[row['path']] = (ROOT / row['path']).read_bytes()
            row['sha256'] = hashlib.sha256(payload[row['path']]).hexdigest()
    manifest.update(schema_version='genos-reindex-progress-r9', base_r8_zip_sha256=BASE_SHA)
    payload['GUIDE_UTF8.txt'] = GUIDE.encode() + b'\n--- R8 historical base guide ---\n' + base_guide
    for row in manifest['files']:
        row['sha256'] = hashlib.sha256(payload[row['path']]).hexdigest()
    payload['CODE_MANIFEST.json'] = (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    OUT.mkdir(parents=True,exist_ok=True)
    archive = OUT / (STEM+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in payload.items():
            assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.writestr(n,b)
    zip_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    script=(previous.OUT/(previous.STEM+'.txt')).read_text().replace(previous.STEM,STEM).replace(BASE_SHA,zip_sha)
    script=script.replace('financial-risk-success-20261002-index-r8','financial-risk-success-20261002-index-r9').replace('reindex-only-r8','reindex-only-r9')
    runnable=OUT/(STEM+'.txt'); runnable.write_text(script)
    subprocess.run(['bash','-n',str(runnable)],check=True)
    guide=OUT/'GENOS_REINDEX_PROGRESS_R9_GUIDE_UTF8.txt'; guide.write_text(GUIDE)
    record=dict(files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive,runnable,guide)},
                code_manifest_sha256=hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
                changed=CHANGED,field_built=False,serving_packaged=False,model_calls=0)
    (OUT/'HANDOFF.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record))

if __name__ == '__main__': main()

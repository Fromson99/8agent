"""Build only search snapshots and installation/offline verification utilities."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[4]
PATCH = Path(__file__).resolve().parent
STEM = 'GENOS_FULLTEXT_LOCATION_20260929_R1'

def main():
    import transform
    from lawrag.platform.workspace import load_layout
    layout = load_layout(ROOT)
    base = layout.path('deployment')/'GENOS/patches'
    baseline = layout.path('runtime')/'diagnostics/fulltext-location-20260929-preimage-002402'/transform.TARGET
    candidate_root = layout.path('backend')/'lawrag/research/candidates/adr_0549/metadata-location'
    manifest = json.loads((candidate_root/'candidate.json').read_bytes())
    frozen = manifest['revisions'][-1]
    candidate = ROOT/frozen['files'][0]['frozen_path']
    assert transform.sha(candidate.read_bytes())==frozen['files'][0]['snapshot_sha256']
    source_rows = {}
    for name, source in [('baseline.py',baseline),('candidate.py',candidate)]:
        raw = source.read_bytes()
        _, snippet, _ = transform.method(raw)
        (PATCH/name).write_bytes(('class RelationsTools:\n'+snippet).encode())
        source_rows[name] = {'source_sha256':transform.sha(raw),'method_ast_sha256':transform.ast_sha(raw)}
    assert candidate.read_bytes()==(ROOT/transform.TARGET).read_bytes()
    assert manifest['production_loadable'] is False and manifest['revisions'][-1]['frozen_at']
    (PATCH/'MATRIX.json').write_text(json.dumps([{'team':team,'query':query}
        for team in ('risk_team','financial_team') for query in ('승인','영업일','공모가격','자금지원','준용')],ensure_ascii=False,indent=2)+'\n')
    assets = ['transform.py','baseline.py','candidate.py','benchmark.py','MATRIX.json']
    spec = {'format':'8agent-fulltext-location-patch/1','patch':'fulltext-location-20260929-r1',
            'files':{transform.TARGET:{'strategy':'approved-method-only'}},
            'assets':{name:transform.sha((PATCH/name).read_bytes()) for name in assets},
            'source_snapshots':source_rows,'candidate_manifest_sha256':transform.sha((candidate_root/'candidate.json').read_bytes()),
            'adr_id':'ADR-0549','generation_change':False,'workflow_change':False,'onsite_verified':False}
    (PATCH/'PATCH_MANIFEST.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    (PATCH/'NOTES.txt').write_text('''GENOS FULLTEXT 위치 구성 수정 R1 / 2026-09-29
필요 부분: RelationsTools.search 한 함수와 이를 소비하는 기존 engine manifest/PIPELINE의 해시만 갱신.
기존 현장 기능/데이터 세대/워크플로우 Python을 덮어쓰지 않음. FULLTEXT_DIAGNOSTICS R1의 검색 함수 필요.

1. 먼저 배포 없이 비교 (적용 전후 모두 실행 가능):
   bash GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt
   기존 ~/DEV, 기존 Python, 자동 선택 GENOS generation을 사용. 모델 호출/HTTP 요청 없음.
   2개 팀 x 5개 고정 검색어 x 4쌍. AB/BA 교차 순서, 매번 새 요청 SourceMap.
   FROZEN_PLAN에 코드/세대/범위/검색어 해시를 먼저 고정. 결과는 TRANSFER/.../offline-*/RESULTS.json.
   JSON에는 원문/검색어 대신 해시와 수치. runtime journal은 현장 내부에 보존하고 외부 반출하지 않음.
   결과 전체 위치 순서/중복제거/총개수/첫 페이지/미리보기 원문/해시를 대조.
   요청 binding이 달라지는 preview_hash는 각 요청 내에서 재검증하고 비교에서는 제외.
   observed_location_improvement=true: 결과 동일, 매핑 본문 SQL 0, 비어있지 않음,
   매핑 중앙값 20% 이상 감소, 4쌍 중 3쌍 이상 개선. false면 해당 케이스 개선 미확인.
   기본 검색어에 결과가 없으면 성공 판정 안 함. 다른 검색어는 CASES_FILE=/현장/행렬.json.
   행렬 형식: [{"team":"risk_team","query":"현장 검색어"}]. 결과를 보고 변경한 행렬은 새 run.
   DEPLOY_ROOT=/실제/checkout PYTHON_BIN=/실제/python GENOS_GENERATION=/실제/세대 PAIRS=4 지정 가능.
   OS/SQLite/NFS 캐시는 지우지 않음. 준비시간(setup_ms)은 별도. 첫 쌍의 warmup/order 영향을 포함.
   이 비교는 워크플로우/응답 생성/137초 초기 로딩/모든 cold I/O의 성능 인증이 아님.

2. 코드 적용 (ZIP 파일 별도 해제 불필요; TXT에 ZIP 포함):
   MODE=check bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
   bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
   ~/DEV에 백업 후 적용. 기존 모든 engine/schema pin이 맞아야 진행.
   BACKUP_READY의 실제 경로를 보존. 재실행은 이미 적용된 코드 확인. 중단된 쓰기는 백업 복구.
   표시된 changed_files만 검토/commit. git push/코드서빙 리비전 배포는 별도.
   commit 후 MODE=verify bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
   게이트는 push checkout 바이트/commit/선택 generation/E2E/verify_assets를 결속.
   현장 워크플로우 검증 전까지 실제 서비스 성능은 미확인. 이 수정은 워크플로우 Python 변경 불필요.

되돌리기:
   MODE=rollback ROLLBACK_FROM=/BACKUP_READY/실제경로 bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
   적용 후 수정된 파일은 안전을 위해 자동 rollback 거부.
   오래된 코드서빙 리비전/세대는 함께 보존.

디스크/NFS I/O는 원인 후보임. 개선의 근거는 조회 제거이며 NFS 장애 여부 판정이 아님.
구간 SQL execute/fetch/JSON/CPU/비CPU/Linux read_bytes를 기록하나 read_bytes는 NFS 네트워크 바이트 아님.
로컬 계약 검사는 모의 데이터이며 GENOS 실제 속도 결과는 아직 없음.
''')
    names = assets+['apply.py','verify.py','gate.py','PATCH_MANIFEST.json','NOTES.txt']
    archive = base/(STEM+'.zip')
    rows=[]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            raw=(PATCH/name).read_bytes()
            rows.append({'path':name,'bytes':len(raw),'sha256':transform.sha(raw)})
            z.writestr(name,raw)
        z.writestr('CODE_MANIFEST.json',json.dumps({'format':'8agent-code/1','patch':spec['patch'],'files':rows},indent=2)+'\n')
    zip_sha = transform.sha(archive.read_bytes())
    old = (base/'fulltext_diagnostics_20260928_r1/build.py').read_text()
    # Reuse the already tested bash extraction/inventory checker exactly.
    pre = old.split("shell=r'''",1)[1].split("'''+base64.encodebytes",1)[0]
    post = old.split("archive.read_bytes()).decode()+r'''",1)[1].split("\n'''\n    (BASE",1)[0]
    # The tail contains an interpolated SHA token; replace it with this ZIP's SHA.
    post = post.replace('"\'\'\'+zip_hash+r\'\'\'"','"'+zip_sha+'"')
    shell = pre+base64.encodebytes(archive.read_bytes()).decode()+post
    shell = shell.replace('GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1','GENOS_FULLTEXT_LOCATION_20260929_R1')
    shell = shell.replace('fulltext-diagnostics','fulltext-location').replace('20260928-r1','20260929-r1')
    shell = shell.replace('diagnostic code, request_report, engine manifests, PIPELINE.json','search method, engine manifests, PIPELINE.json')
    (base/(STEM+'_APPLY.txt')).write_text(shell)
    bench = shell[:shell.index('case "$MODE" in')] + '''ARGS=(--deploy-root "$DEPLOY_ROOT" --pairs "${PAIRS:-4}")
if [[ -n "${GENOS_GENERATION:-}" ]]; then ARGS+=(--generation "$GENOS_GENERATION"); fi
if [[ -n "${CASES_FILE:-}" ]]; then ARGS+=(--matrix "$CASES_FILE"); fi
"$PYTHON_BIN" "$PATCH_DIR/benchmark.py" "${ARGS[@]}"
'''
    bench = bench.replace('# MODE=check / MODE=verify / MODE=code-only / MODE=rollback ROLLBACK_FROM=/actual/BACKUP_READY/path',
                          '# Offline comparison: no apply, commit, push, serving revision or workflow deployment required.')
    bench = bench.replace('bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt','bash GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt')
    bench = bench.replace('MODE="${MODE:-apply}"','MODE="offline-benchmark"')
    (base/(STEM+'_BENCH.txt')).write_text(bench)
    shutil.copyfile(PATCH/'NOTES.txt',base/(STEM+'_NOTES.txt'))
    paths = [archive]+[base/(STEM+'_'+suffix+'.txt') for suffix in ('APPLY','BENCH','NOTES')]
    checks = base/(STEM+'_SHA256SUMS.txt')
    checks.write_text(''.join(transform.sha(p.read_bytes())+'  '+p.name+'\n' for p in paths))
    paths.append(checks)
    receipt = {'patch':spec['patch'],'zip_sha256':zip_sha,'attachments':[
        {'path':str(p),'filename':p.name,'sha256':transform.sha(p.read_bytes()),'bytes':p.stat().st_size} for p in paths],
        'code_root':str(ROOT),'push_checkout':None,'commit':None,'generation':None,
        'generation_manifest_sha256':None,'code_serving_revision':None,'onsite_verified':False}
    (PATCH/'BUILD_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':
    main()

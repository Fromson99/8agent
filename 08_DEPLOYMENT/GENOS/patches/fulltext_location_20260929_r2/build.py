"""R2 fixes offline data discovery; preserves the mailed R1 patch and snapshots."""
import base64
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[4]
PATCH=Path(__file__).resolve().parent
STEM='GENOS_FULLTEXT_LOCATION_20260929_R2'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def dump(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def main():
    from lawrag.platform.workspace import load_layout
    base=load_layout(ROOT).path('deployment')/'GENOS/patches'
    r1=base/'fulltext_location_20260929_r1'
    spec=json.loads((r1/'PATCH_MANIFEST.json').read_bytes())
    for name in ('baseline.py','candidate.py','MATRIX.json','transform.py','apply.py'):
        assert (PATCH/name).read_bytes()==(r1/name).read_bytes(), 'R2 only changes the offline handoff'
    assets=['apply.py','transform.py','baseline.py','candidate.py','benchmark.py','MATRIX.json','codespace_data.py']
    spec['assets']={name:sha((PATCH/name).read_bytes()) for name in assets}
    spec['handoff_revision']='R2-codespace-offline-selection'
    spec['supersedes_benchmark']='GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt'
    (PATCH/'PATCH_MANIFEST.json').write_bytes(dump(spec))
    notes='''GENOS FULLTEXT 위치 구성 배포 전 비교 — R2 / 2026-09-29
R1 BENCH를 이 R2 BENCH로 교체합니다. 검색 수정 함수/검색어/판정 기준은 R1과 동일합니다.
R1의 Code-serving settings are not present 오류는 검색 실행 전 데이터 선택기의 문제입니다.
R2는 genos_generation_e2e.operator_generation과 코드서빙 배포 설정에 의존하지 않습니다.

GENOS 코드스페이스의 기존 checkout에서 그대로 실행:
  bash TRANSFER/GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.txt
현재 폴더가 Git checkout 안이면 그 실제 root를 사용합니다. ~/DEV 심볼릭 링크도 처리합니다.
ZIP 내장 TXT이므로 추가 해제/설치/코드 적용/commit/push/워크플로우 배포가 필요 없습니다.

데이터 선택:
- GENOS_GENERATION이 이미 있거나 명시한 generation이 있으면 그 경로/metadata hash를 확인.
- 기존 데이터 root의 유효한 CURRENT가 있으면 해당 generation을 사용.
- 없으면 workspace의 논리 data root, GENOS_DATA, TERM_RELEASES, AUTHORING,
  공유 NFS /nfs-root/diamo/8-agent/term-releases의 기존 검색 generation을 확인.
- source/navigation/fulltext manifest와 database가 결속된 후보만 표시.
- 후보가 하나면 실행. 여러 개면 터미널에서 번호 선택. 이름/날짜를 기준으로 최신 세대를 고르지 않음.
  다른 mount의 데이터는 GENOS_BENCH_DATA_ROOTS=/실제/데이터루트를 지정 가능.
  반복 실행/비대화형은 GENERATION_INDEX=번호 또는 GENOS_GENERATION=/실제/generation을 명시.
- 실제 선택된 path/hash/선택 방식은 OFFLINE_DATA_SELECTED와 FROZEN_PLAN에 보존.
  이번 비교용 데이터 선택이며 코드서빙의 실제 배포 선택과 동일하다고 추정하지 않음.
  데이터/CURRENT/배포 환경변수는 변경하지 않음. 데이터가 없으면 재구축하지 않고 확인한 경로/제외 이유를 표시.

동일 세대/팀/검색 조건으로 기존 함수와 수정 함수를 직접 실행. 모델/HTTP 호출 0.
2개 팀 x 검색어 5개 x AB/BA 4쌍. 매회 새로운 요청 SourceMap.
전체 위치 순서/정확 total/첫 페이지/미리보기 원문을 대조하고 원문/preview hash를 요청별 검증.
observed_location_improvement=true는 결과가 있고 동일하며 위치 본문 SQL 0,
위치 중앙값 20% 이상 감소, 4쌍 중 3쌍 이상 개선했다는 의미. 빈 결과는 개선 미확인.
setup_ms, search_ms, 위치 시간, FTS SQL, CPU/비CPU/JSON/읽기 계수를 따로 보고함.
기존 코드/세대 hash 검증과 초기 준비가 먼저 실행됨. 준비시간을 개선 후 검색 지연으로 섞지 않음.
OS/NFS 캐시는 지우지 않으며 초기 로딩/전체 답변/배포 서비스 성능 인증은 별도.

실행 결과: checkout/TRANSFER/fulltext-location-20260929-r1/offline-*/RESULTS.json
원래 검색 수정의 patch ID R1은 유지하고 이번 실행 TXT만 R2로 수정함.
결과 JSON은 숫자/해시 중심. runtime journal은 현장 내부에 보존하고 외부 반출하지 않음.
로그는 시작부터 /tmp/genos-fulltext-location-r2-*.log에 저장되며 실패/성공 종료 코드를 남김.
배포 후 실제 속도와 디스크/NFS 원인은 여전히 별도 확인 대상.
'''
    (PATCH/'NOTES.txt').write_text(notes)
    names=assets+['PATCH_MANIFEST.json','NOTES.txt']
    archive=base/(STEM+'_BENCH.zip')
    rows=[]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            raw=(PATCH/name).read_bytes();z.writestr(name,raw)
            rows.append({'path':name,'bytes':len(raw),'sha256':sha(raw)})
        z.writestr('CODE_MANIFEST.json',dump({'format':'8agent-code/1','patch':spec['patch'],'handoff_revision':'R2','files':rows}))
    zip_hash=sha(archive.read_bytes())
    old=(base/'GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt').read_text()
    before=old.split("<<'FULLTEXT_DIAGNOSTICS_PAYLOAD'\n",1)[0]+"<<'FULLTEXT_DIAGNOSTICS_PAYLOAD'\n"
    tail=old.split('\nFULLTEXT_DIAGNOSTICS_PAYLOAD\n',1)[1]
    for r in json.loads((r1/'BUILD_RECEIPT.json').read_bytes())['attachments']:
        if r['filename'].endswith('.zip'):tail=tail.replace(r['sha256'],zip_hash)
    shell=before+base64.encodebytes(archive.read_bytes()).decode()+'FULLTEXT_DIAGNOSTICS_PAYLOAD\n'+tail
    shell=shell.replace('GENOS_FULLTEXT_LOCATION_20260929_R1','GENOS_FULLTEXT_LOCATION_20260929_R2')
    shell=shell.replace('genos-fulltext-location-r1-','genos-fulltext-location-r2-')
    shell=shell.replace('fulltext-location-r1-unpack-','fulltext-location-r2-unpack-')
    shell=shell.replace('DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/DEV}"', '''if [[ -z "${DEPLOY_ROOT:-}" ]]; then
    DEPLOY_ROOT="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$DEPLOY_ROOT" ]]; then DEPLOY_ROOT="$HOME/DEV"; fi
fi''')
    shell=shell.replace('if [[ -n "${CASES_FILE:-}" ]]; then', 'if [[ -n "${GENERATION_INDEX:-}" ]]; then ARGS+=(--generation-index "$GENERATION_INDEX"); fi\nif [[ -n "${CASES_FILE:-}" ]]; then')
    txt=base/(STEM+'_BENCH.txt');txt.write_text(shell)
    note_path=base/(STEM+'_NOTES.txt');note_path.write_text(notes)
    paths=[txt,note_path,archive]
    sums=base/(STEM+'_SHA256SUMS.txt');sums.write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in paths));paths.append(sums)
    receipt={'handoff_revision':'R2','supersedes':'GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt',
             'production_search_changed':False,'code_root':str(ROOT),'generation':None,'commit':None,'code_serving_revision':None,'onsite_verified':False,
             'zip_sha256':zip_hash,'attachments':[{'path':str(p),'filename':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in paths]}
    (PATCH/'BUILD_RECEIPT.json').write_bytes(dump(receipt))
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()

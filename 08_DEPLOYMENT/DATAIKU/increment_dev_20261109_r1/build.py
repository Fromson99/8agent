"""증분 처리 개발계 실험 R1 전달본 만들기.

INCREMENT_CODE_R1.zip : lawinc/ (02_BACKEND/lawrag/increment 의 필요한 모듈 + legal_generation 사본)
                        R6 안의 lawrag 패키지와 이름이 겹치지 않게 lawinc 로 묶는다.
DATAIKU_INCREMENT_R1.txt : Dataiku Python 노트북 한 셀 (R6 BOOTSTRAP 그대로 + 증분 코드 로드 + 실행)
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "02_BACKEND/lawrag/increment"
R6_SETUP = ROOT / "08_DEPLOYMENT/DATAIKU/agent_layer_zip_20261105_r6/DATAIKU_SETUP_R6.txt"
MODULES = ("normalize", "lawgo_parse", "addenda", "diff", "gate", "preview", "schema", "service", "structured",
           "corpus", "daily", "decide", "release_ops", "history", "dataiku_flow", "dataiku_cell")
ZIP_NAME = "INCREMENT_CODE_R1.zip"
FIXED = (2026, 1, 1, 0, 0, 0)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def code_zip() -> bytes:
    files = {"lawinc/__init__.py": b'"""Increment processing (bundled from lawrag.increment)."""\n'}
    for name in MODULES:
        text = (SRC / f"{name}.py").read_text(encoding="utf-8")
        text = text.replace("from lawrag.core.legal_generation import", "from .legal_generation import")
        if re.search(r"^\s*(from|import)\s+lawrag", text, re.M):
            raise SystemExit(f"{name}.py 에 패키지 밖 lawrag 참조가 남음")
        files[f"lawinc/{name}.py"] = text.encode("utf-8")
    files["lawinc/legal_generation.py"] = (ROOT / "02_BACKEND/lawrag/core/legal_generation.py").read_bytes()
    manifest = {"schema": "increment-code-v1", "files": {k: sha(v) for k, v in sorted(files.items())}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, FIXED)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[name])
        info = zipfile.ZipInfo("INCREMENT_MANIFEST.json", FIXED)
        z.writestr(info, json.dumps(manifest, indent=1, sort_keys=True))
    return buffer.getvalue()


INCREMENT_BOOTSTRAP = '''import hashlib, io, json, stat, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath
import dataiku
INC_ZIP_NAME = '%(name)s'
INC_ZIP_SHA256 = '%(sha)s'
def _open_increment():
    folder = dataiku.Folder(PARAMS['CODE_FOLDER_ID'])
    names = [p for p in folder.list_paths_in_partition() if PurePosixPath(p).name == INC_ZIP_NAME]
    if len(names) != 1: raise ValueError('UPLOAD_ONE_CODE_ZIP:' + INC_ZIP_NAME)
    with folder.get_download_stream(names[0]) as stream: raw = stream.read(8*1024**2+1)
    if len(raw) > 8*1024**2 or hashlib.sha256(raw).hexdigest() != INC_ZIP_SHA256: raise ValueError('INCREMENT_CODE_ZIP_HASH')
    root = Path(_inc_dir.name)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('INCREMENT_MANIFEST.json'))
        if set(z.namelist()) != set(manifest['files']) | {'INCREMENT_MANIFEST.json'}: raise ValueError('INCREMENT_CODE_MEMBERS')
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16): raise ValueError('INCREMENT_CODE_PATH')
            content = z.read(item)
            if item.filename != 'INCREMENT_MANIFEST.json' and hashlib.sha256(content).hexdigest() != manifest['files'][item.filename]:
                raise ValueError('INCREMENT_CODE_FILE_HASH')
            dest = root.joinpath(*p.parts); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(content)
    sys.path.insert(0, str(root))
_inc_dir = tempfile.TemporaryDirectory(prefix='increment-code-')
_open_increment()
'''

CELL = '''# 증분 처리 개발계 실험 R1 — Dataiku Python 노트북 한 셀 (R6 설치된 같은 프로젝트)
# CODE_FOLDER_ID 폴더에 DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip(이미 있음)과 %(zip)s 를 둡니다.
# ACTION 순서: 'check' → 'status' → 'decide' → 'publish' → 'activate'   (또는 'run' 한 번에)
#              되돌리기 'rollback', 남은 정리 이어서 'cleanup'
PARAMS = {
    'CODE_FOLDER_ID': '',            # R6 코드 ZIP과 증분 코드 ZIP이 있는 관리 폴더 ID
    'DROP_FOLDER_ID': '',            # 처리된 파일이 떨어지는 폴더 ID
    'STATE_FOLDER_ID': '',           # 증분 상태·기록 JSON을 둘 새 관리 폴더 ID (비어 있는 폴더)
    'R6_RECIPE': 'LGL_AGENT_R6_PROD_02_WAIT_AGENT',   # 설정을 읽을 R6 레시피 이름
    'TARGET': 'DEV_1',               # 개발계 실버 SIDDS.LGL_G19_*_S_1 / 운영은 'GOLD'
    'GOLD_OWNER': 'SIDDG',           # TARGET='GOLD'일 때만 사용
    'CHANNEL': 'main',               # 서빙이 읽는 채널 (g19_ 이름은 거절 — GUIDE 2번)
    'BASE_DATA_ZIP_NAME': '',        # 첫 실행: 지금 세대를 만든 원문 ZIP 이름 (R6 입력 폴더 안)
    'BASE_DOCUMENT_PREFIX': '',      # 또는 R6 입력 폴더의 낱개 원문 파일 접두 (그 아래 external/…·internal/…)
    'SUPPORT_ZIP_NAME': '',          # 실제 지원 ZIP 이름 (빈 값이면 R6 설치값 — 예시 지원 ZIP은 예시 원문 전용)
    'ACTION': 'check',
    'RUN': '',                       # publish/activate: 비우면 가장 최근 decide
    'HOLD_ON_STRONG': True,          # 강한 경고(조문 급감·대량 삭제 등)는 보류
    'RETRY_HOLD': False,             # True면 보류됐던 파일도 다시 판단
    'PRUNE_BATCH': 50000,            # 옛 세대 삭제 묶음 크기
    'TODAY': '',                     # 시험용 기준일 YYYYMMDD (비우면 오늘 KST)
}
%(r6_bootstrap_line)s
exec(BOOTSTRAP)
INCREMENT_BOOTSTRAP = %(inc_bootstrap)r
exec(INCREMENT_BOOTSTRAP)
from lawinc.dataiku_cell import main
RESULT = main(PARAMS)
'''


def main() -> int:
    data = code_zip()
    (HERE / ZIP_NAME).write_bytes(data)
    r6 = R6_SETUP.read_text(encoding="utf-8")
    line = next(l for l in r6.splitlines() if l.startswith("BOOTSTRAP = "))
    if "5201fb6d85eb627849187a8224325105a33e365bf5b97b7669833872aa4d7e39" not in line:
        raise SystemExit("R6 BOOTSTRAP 해시가 예상과 다름")
    cell = CELL % {"zip": ZIP_NAME, "r6_bootstrap_line": line,
                   "inc_bootstrap": INCREMENT_BOOTSTRAP % {"name": ZIP_NAME, "sha": sha(data)}}
    compile(cell, "DATAIKU_INCREMENT_R1.txt", "exec")
    (HERE / "DATAIKU_INCREMENT_R1.txt").write_text(cell, encoding="utf-8")
    print(ZIP_NAME, sha(data), len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())

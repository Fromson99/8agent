# 법제처 증분 처리 R1 — Dataiku Python 레시피/노트북 셀 템플릿 (현장 미검증)
#
# 준비
#   1. LAW_INCREMENT_CODE_R1.zip 을 관리 폴더(CODE_FOLDER_ID)에 압축 상태로 올린다.
#   2. LAW_INCREMENT_DDL_R1.sql 의 표 10개가 OWNER 스키마에 있어야 한다 (운영은 메타 등록·DBA 생성 신청).
#   3. 수집 결과(collect.py --source law 의 manifest.json + 본문 XML)를 INPUT_FOLDER_ID 폴더에 둔다.
# 단계
#   STEP="ingest"   : 매일 배치. 바뀐 문서만 PREVIEW 가 되고, 같은 파일은 그대로 넘어간다.
#   STEP="preview"  : LOAD_ID 의 대비표 HTML을 OUTPUT_FOLDER_ID 에 저장하고 승인 해시를 출력.
#   STEP="approve"  : 사람이 대비표를 본 뒤 LOAD_ID, PREVIEW_HASH, USER 를 넣고 실행.
#   STEP="index"    : 숨김 조문 행·참조 행을 만든다. Gold 새 세대 게시는 기존 적재기로 따로 (채널 전환 없이).
#   STEP="link_gold": 게시된 Gold 세대(DTLS_HASH)를 연결하고 GOLD 색인을 READY 로 표시.
#   STEP="activate" : 한 트랜잭션에서 옛 판본 닫기 + 새 판본 공개 (+ 선택: 조회 채널 포인터 CAS).

PARAMS = {
    "CONNECTION": "AIDP",
    "OWNER": "SIDDS",                 # 운영: Gold 소유자. 표 이름은 개발·운영 같다.
    "CODE_FOLDER_ID": "",
    "INPUT_FOLDER_ID": "",
    "INPUT_PREFIX": "",               # 폴더 안 manifest.json 위치 (예: "law/")
    "OUTPUT_FOLDER_ID": "",           # 대비표 HTML 저장 (preview 단계)
    "STEP": "ingest",
    "TODAY": None,                    # 기준일 KST YYYYMMDD, None 이면 오늘
    "LOAD_ID": "",
    "PREVIEW_HASH": "",
    "USER": "",
    "ACK_WARNINGS": False,
    "DTLS_HASH": "",
    "CHANNEL": None,                  # 예: {"table": "<OWNER>.IDD_B003_LGL_SRCH_CHNL", "channel": "...",
                                      #       "old_post": "...", "new_post": "...", "expected_no": 7}
}

import io
import json
import sys
import tempfile
import zipfile

import dataiku

code_dir = tempfile.mkdtemp(prefix="law_increment_r1_")
with dataiku.Folder(PARAMS["CODE_FOLDER_ID"]).get_download_stream("LAW_INCREMENT_CODE_R1.zip") as stream:
    zipfile.ZipFile(io.BytesIO(stream.read())).extractall(code_dir)
sys.path.insert(0, code_dir)

from lawrag.increment.db import DataikuDatabase  # noqa: E402
from lawrag.increment.lawgo_parse import (ParseError, attach_files, manifest_attachments,  # noqa: E402
                                          parse_lawgo_xml)
from lawrag.increment.preview import preview_hash, render_html  # noqa: E402
from lawrag.increment.service import ChannelSwitch, IncrementService  # noqa: E402

service = IncrementService(DataikuDatabase(dataiku.SQLExecutor2(connection=PARAMS["CONNECTION"])),
                           owner=PARAMS["OWNER"], today=PARAMS["TODAY"])
step = PARAMS["STEP"]

if step == "ingest":
    folder = dataiku.Folder(PARAMS["INPUT_FOLDER_ID"])
    paths = folder.list_paths_in_partition()
    with folder.get_download_stream(PARAMS["INPUT_PREFIX"] + "manifest.json") as stream:
        manifest = json.load(stream)
    results = []
    for item in manifest.get("items") or ():
        body = item.get("body_file")
        if not body or item.get("status") not in ("ok", "partial"):
            results.append({"name": item.get("name"), "state": "SKIPPED", "error": item.get("error")})
            continue
        suffix = body.replace("\\", "/").split("/")[-2:]
        match = [p for p in paths if p.endswith("/".join(suffix))]
        if len(match) != 1:
            results.append({"name": item.get("name"), "state": "FAILED", "error": f"본문 파일 {len(match)}개"})
            continue
        with folder.get_download_stream(match[0]) as stream:
            raw = stream.read()
        try:
            snapshot = attach_files(parse_lawgo_xml(raw), manifest_attachments(item))
        except ParseError as exc:
            results.append({"name": item.get("name"), "state": "FAILED", "step": "PARSE", "error": str(exc)})
            continue
        result = service.ingest(snapshot, source_name=match[0])
        results.append({"name": item.get("name"), "doc_cd": result.doc_cd, "load_id": result.load_id,
                        "state": result.state, "reused": result.reused, "counts": result.gate.get("counts"),
                        "stop": result.gate.get("stop_reason"),
                        "strong": [w["code"] for w in result.gate.get("warnings", []) if w.get("strong")]})
    print(json.dumps(results, ensure_ascii=False, indent=1))
    print("LAW_INCREMENT_INGEST_DONE", {s: sum(1 for r in results if r["state"] == s)
                                        for s in sorted({r["state"] for r in results})})
elif step == "preview":
    preview = service.preview(PARAMS["LOAD_ID"])
    digest = preview_hash(preview)
    name = f"law_increment_preview_{PARAMS['LOAD_ID']}.html"
    dataiku.Folder(PARAMS["OUTPUT_FOLDER_ID"]).upload_data(name, render_html(preview, digest).encode("utf-8"))
    print("PREVIEW_HASH", digest, "HTML", name)
elif step == "approve":
    job = service.approve(PARAMS["LOAD_ID"], user=PARAMS["USER"], preview_digest=PARAMS["PREVIEW_HASH"],
                          acknowledge=PARAMS["ACK_WARNINGS"])
    print("APPROVED", job["LOAD_WORK_ID"])
elif step == "index":
    print(service.prepare_index(PARAMS["LOAD_ID"], external=("GOLD",)))
elif step == "link_gold":
    print(service.link_gold(PARAMS["LOAD_ID"], dtls_hash=PARAMS["DTLS_HASH"]))
elif step == "activate":
    channel = ChannelSwitch(**PARAMS["CHANNEL"]) if PARAMS["CHANNEL"] else None
    print(service.activate(PARAMS["LOAD_ID"], user=PARAMS["USER"], channel=channel))
else:
    raise ValueError("STEP 확인")

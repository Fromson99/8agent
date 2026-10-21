"""Package one self-contained notebook; never call external/internal APIs."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "law_api_20261015_r1" / "relay_check.py"
NAME = "DATAIKU_RELAY_LAW_20261019_R1"

CONFIG = '''# 기존 사진의 개발계 주소입니다. 실제 사용할 주소가 다르면 바꾸세요.
CONFIG = {
    "relay_origin": "https://45.101.64.86:8443",
    "law_origin": "http://www.law.go.kr",
    "law_id": "010513",
    "law_name": "자본시장과 금융투자업에 관한 법률",
    "target_in_header": True,
    "ca_bundle": "",  # 사내 CA가 필요하면 실행 서버의 PEM 파일 경로
    "output_root": "dataiku_relay_law_results",
    "run_id": "relay-law-01",  # 새로 요청하려면 02, 03처럼 변경. 기존 기록은 보존됩니다.
}
'''

PREFLIGHT = '''# 법제처 인증 없이 중계 주소에 HEAD 요청을 1회 보냅니다.
run = NotebookRun(CONFIG)
print("요청: HEAD", run.url)
_relay_result = run.preflight()
'''

LAW = '''# 1단계에서 HTTP 응답을 확인한 뒤, 같은 중계 주소로 법제처 GET 요청 1회.
from getpass import getpass
run.ensure_config(CONFIG)
if run.law_ready():
    print("요청: GET", run.url)
    print("target_url:", CONFIG["law_origin"] + "/DRF/lawService.do?target=law")
    _oc = getpass("법제처에 등록된 OC: ")
    _cookie = getpass("현재 중계 Cookie (필요 없으면 Enter): ")
    try:
        _law_result = run.call_law(_oc, _cookie)
    finally:
        del _oc, _cookie
'''

RESULT = '''run.ensure_config(CONFIG)
_summary = run.show()
'''

def build():
    core = PARENT.read_text()
    expected = "b5f1718aa4d2a92e7525fd7809be3918990744109ebc392466c9598a59afd16e"
    assert hashlib.sha256(core.encode()).hexdigest() == expected
    flow = (HERE / "notebook_flow.py").read_text()
    code_hash = hashlib.sha256((CONFIG + core + flow + PREFLIGHT + LAW + RESULT).encode()).hexdigest()
    engine = core + "\nNOTEBOOK_CODE_SHA256 = " + repr(code_hash) + "\n\n" + flow
    cells = []
    def md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)})
    def code(text, collapsed=False):
        ast.parse(text, feature_version=(3, 9))
        metadata = {"jupyter": {"source_hidden": True}, "collapsed": True} if collapsed else {}
        cells.append({"cell_type": "code", "metadata": metadata, "execution_count": None,
                      "outputs": [], "source": text.splitlines(True)})
    md("# Dataiku · 중계서버 연결 → 법제처 호출\n\n이 노트북 하나만 가져와 위에서 아래로 실행합니다.\n"
       "**1단계:** 중계 주소에 HEAD 요청 → HTTP 응답 확인. **2단계:** 같은 중계를 통해 법령 XML 본문 GET 요청.\n"
       "법제처·중계 인증은 2단계에서만 입력합니다. 기존 노트북이나 별도 모듈 업로드는 필요 없습니다.\n")
    md("## 준비 · 주소와 조회할 법령\nPython 3.9 이상과 requests가 있는 Dataiku 코드 환경을 사용하세요.\n"
       "같은 run_id는 저장된 결과를 보여줍니다. 연결 설정을 고친 뒤 다시 확인할 때 run_id를 바꾸세요.\n")
    code(CONFIG)
    md("### 공통 코드 · 수정 없이 한 번 실행\n요청·검증·저장 함수입니다. 이 셀 자체는 네트워크 요청을 보내지 않습니다.\n")
    code(engine, collapsed=True)
    md("## 1. API 중계서버 통신 확인\n`HEAD https://중계주소/law/DRF` 요청 1회. OC·Cookie·target_url은 보내지 않습니다.\n"
       "HTTP 401·403·404·405도 **응답 수신**입니다. 법제처 호출 성공을 뜻하지 않습니다. "
       "프록시가 있다면 프록시 경로 응답일 수 있으므로 실제 중계/법제처 처리 여부는 다음 단계에서 확인합니다.\n"
       "시간 초과·TLS·연결 오류로 HTTP 응답이 없으면 2단계는 요청을 보내지 않습니다.\n")
    code(PREFLIGHT)
    md("## 2. 중계를 통해 법제처 법령 본문 호출\n법제처에 등록된 **국가법령정보센터 OC**와 필요한 경우 현재 중계 Cookie를 입력합니다. "
       "이전 입법센터 사진의 OC가 이 API에서도 유효하다고 가정하지 않습니다.\n"
       "중계 `/law/DRF`에 GET을 보내고 `target_url` 헤더로 `lawService.do?target=law`를 전달합니다.\n")
    code(LAW)
    md("## 3. 결과 확인\n`BODY_OK`는 HTTP 200과 XML 법령명·ID·조문 확인을 모두 통과한 상태입니다. "
       "HTML 로그인 화면이나 오류 XML은 성공으로 처리하지 않습니다.\n")
    code(RESULT)
    md("### 결과 보존과 다시 확인\n결과는 커널 실행 폴더의 `dataiku_relay_law_results/<run_id>/`에 저장됩니다. "
       "본문은 인증값을 가린 압축 파일로 보존하며, Oracle/Managed Folder에 자동 적재하지 않습니다.\n\n"
       "같은 run_id의 성공·실패·중단은 자동 재호출하지 않습니다. 커널 재시작 후에도 동일하게 처리합니다. "
       "중단된 요청의 기록을 먼저 확인하고 새 시도가 필요하면 run_id를 변경하세요. 자동 재시도 0회, "
       "한 실행에서 HEAD 1회 + GET 1회, 새 요청 시작 한도는 15분입니다.\n\n"
       "사내 연결 성공은 이 노트북의 현장 실행 결과로 확인해야 합니다. 인증값을 입력해 실행한 뒤에는 "
       "공유 전에 셀 출력을 지우세요. 이 파일에는 인증값이 저장되어 있지 않습니다.\n")
    notebook = {"nbformat": 4, "nbformat_minor": 4,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python", "version": "3.9"}}, "cells": cells}
    (HERE / (NAME + ".ipynb")).write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")
    runner = "# Dataiku Python Notebook 셀용 전체 코드. bash 파일이 아닙니다.\n\n"
    runner += "\n\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")
    (HERE / (NAME + "_RUN.txt")).write_text(runner)
    (HERE / "SOURCE_BINDING.json").write_text(json.dumps({"parent": str(PARENT), "parent_sha256": expected,
        "parent_transport_modified": False, "notebook_code_sha256": code_hash,
        "scope": "기존 연결 진단의 2단계 노트북 통합; MAIN·수집 파이프라인 미변경"}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"notebook": NAME + ".ipynb", "code_cells": 5, "credentials_embedded": False}))

if __name__ == "__main__":
    build()

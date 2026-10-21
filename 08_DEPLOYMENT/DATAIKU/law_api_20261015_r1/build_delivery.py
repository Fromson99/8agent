"""Build readable notebook/TXT/DOCX deliverables; no network or mail side effects."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

OUT = Path(__file__).resolve().parent
NAME = "DATAIKU_LAW_API_20261015_R1"

CONFIG = '''# [셀 1] 이 설정만 수정합니다. 사진의 주소는 개발계 샘플입니다.
CONFIG = {
    "mode": "relay",  # 사내 Dataiku에서는 relay 유지. 외부 직접 호출로 자동 전환하지 않음
    "relay_origin": "https://45.101.64.86:8443",
    "law_origin": "http://www.law.go.kr",  # 사진의 원본 URL; 중계서버 접속은 HTTPS
    "making_origin": "https://opinion.lawmaking.go.kr",  # 사진1 샘플. 사진2는 www 호스트
    "target_in_header": True,  # 사진2처럼 target_url에 ?target=law 등을 포함
    "ca_bundle": "",  # 사내 CA PEM이 필요하면 Dataiku 실행 서버의 실제 경로 입력
    "law_name": "자본시장과 금융투자업에 관한 법률",
    "law_id": "010513",  # 2026-10-15 외부 API에서 확인한 법령ID. MST와 다름
    "admrul_name": "금융투자업규정",
    "output_root": "law_api_check_results",
    "ip_lookup_url": "https://45.1.81.80:8443/oap/common/query/ip",
}
USE_RELAY_COOKIE = False  # 담당자가 쿠키가 필요하다고 확인한 경우만 True
RUN_IP_LOOKUP = False  # 운영 주소 조회가 필요할 때 별도 실행. 응답의 IP를 자동 선택하지 않음
EXTR_INSN_SECT_CODE = "0"  # 사진의 개발계 예시. 운영 값은 담당자 명세로 확인
RUN_NOTICES = False  # 입법/행정예고 확인까지 필요할 때 True; 별도 OC 입력
MANAGED_FOLDER_ID = ""  # Dataiku에서 만든 law_api_check_results 폴더의 ID 입력
'''

INIT = '''# [셀 3] 인증값은 입력창에만 입력합니다. 셀 코드에 붙여 넣지 마세요.
from getpass import getpass
if "check" not in globals():
    _law_oc = os.environ.get("LAW_OC") or getpass("법제처에 등록된 LAW_OC: ")
    _cookie = (os.environ.get("LAW_RELAY_COOKIE") or getpass("현재 중계 인증 Cookie: ")) if USE_RELAY_COOKIE else ""
    _making_oc = (os.environ.get("LAWMAKING_OC") or getpass("입법센터에 등록된 OC: ")) if RUN_NOTICES else ""
    check = RelayCheck(CONFIG, _law_oc, _making_oc, _cookie)
    del _law_oc, _making_oc, _cookie
    print("진단 준비:", check.run_id, " / 모드:", check.mode)
else:
    print("기존 진단을 유지합니다:", check.run_id)
    print("설정/인증을 바꾸어 새로 확인하려면 결과 저장 후 Kernel > Restart를 실행하세요.")
'''

IP = '''# [셀 4] 선택: 운영계 IP 조회. 기본은 실행하지 않습니다.
if RUN_IP_LOOKUP:
    check.request("ip_lookup", "ip", "", {"EXTR_INSN_SECT_CODE": EXTR_INSN_SECT_CODE}, "ip")
    print("IP 조회 응답은 결과 폴더에 저장했습니다. 성공코드/활성 주소/환경코드를 담당자 명세로 확인하세요.")
    print("운영 주소 확정 전에는 다음 법령 호출 셀을 실행하지 마세요.")
else:
    print("IP 조회 건너뜀: 개발계 주소 또는 이미 확인한 주소 사용")
'''

LAWS = '''# [셀 5] 법령/행정규칙 최대 5회. 쿠키/키/전체 응답은 출력하지 않습니다.
# 운영 IP 조회 중이면 이 셀은 실행하지 않습니다. 주소 확정 후 설정을 바꾸고 새 커널로 시작합니다.
if RUN_IP_LOOKUP:
    print("주소 조회 모드: 법령 호출 건너뜀. 주소 확정 후 RUN_IP_LOOKUP=False로 새 진단을 시작하세요.")
else:
    check.check_laws()
    print("법령/행정규칙 진단 종료. 셀 7의 각 상태를 확인하세요.")
'''

NOTICES = '''# [셀 6] 선택: 사진1의 행정예고와 입법예고 목록 수신 (각 1회)
if RUN_NOTICES and not RUN_IP_LOOKUP:
    check.request("administrative_notice", "ptcpAdmPp.xml", "",
                  {"lsClsCd": "BA0103", "closing": "Y", "asndOfiNm": "금융위원회",
                   "admRulNm": "지주", "pageIndex": "1", "pageSize": "10"}, "notice")
    check.request("legislative_notice", "ogLmPp.xml", "",
                  {"pageIndex": "1", "pageSize": "10"}, "notice")
    print("예고 XML은 현장 명세 대조 전까지 REVIEW_REQUIRED입니다. 예고안은 현행 법령이 아닙니다.")
else:
    print("예고 API 건너뜀")
'''

TABLE = '''# [셀 7] 성공/실패를 구분한 결과표와 CSV 생성
_result_rows = check.table()
try:
    import pandas as pd
    from IPython.display import display
    display(pd.DataFrame(_result_rows))
except ImportError:
    pass  # 위의 텍스트 표와 CSV는 이미 생성됨
'''

EXPORT = '''# [셀 8] Managed Folder에 저장 후 다시 읽어 SHA-256 확인
if MANAGED_FOLDER_ID:
    _saved_files = check.export_to_dataiku(MANAGED_FOLDER_ID)
else:
    print("아직 Managed Folder에 저장하지 않았습니다.")
    print("셀 1의 MANAGED_FOLDER_ID를 입력하고 셀 1과 셀 8을 다시 실행하세요. API는 재호출되지 않습니다.")
'''


def build():
    core = (OUT / "relay_check.py").read_text()
    sections = [
        ("1. 실행 설정", CONFIG),
        ("2. 공통 함수 — 수정 없이 실행", "# [셀 2] 요청·검증·원문/실패 기록 함수 정의\n" + core),
        ("3. 인증값 입력과 진단 준비", INIT),
        ("4. 선택: 중계 운영 주소 조회", IP),
        ("5. 법령과 행정규칙 확인", LAWS),
        ("6. 선택: 입법예고·행정예고 확인", NOTICES),
        ("7. 결과표 확인", TABLE),
        ("8. 결과를 Dataiku 폴더에 저장", EXPORT),
    ]
    cells = [{"cell_type":"markdown","metadata":{},"source":[
        "# Dataiku 법령 중계 API 확인\n",
        "첨부 GUIDE_UTF8.txt/DOCX의 순서로 실행하세요. 사내 Dataiku 실제 연결은 실행 후 판정합니다.\n",
        "외부 공개 API 확인과 사내 중계 확인은 별개입니다. 등록된 OC를 입력창에 넣으세요.\n",
        "기본 5회 호출, 자동 재시도 0회. 확인 결과는 RAW/MAIN에 자동 반영되지 않습니다.\n"]}]
    for title, code in sections:
        compile(code, title, "exec")
        cells += [{"cell_type":"markdown","metadata":{},"source":["## " + title]},
                  {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":code.splitlines(True)}]
    notebook = {"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
                 "language_info":{"name":"python","version":"3.9"}},"nbformat":4,"nbformat_minor":4}
    (OUT/(NAME+".ipynb")).write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+"\n")
    runner = "# Python 3 코드입니다. bash 실행 파일이 아닙니다.\n# Dataiku의 빈 Python Notebook 코드 셀에 전체를 붙여 넣고 Shift+Enter로 실행할 수 있습니다.\n# 셀 1 설정/Managed Folder ID를 먼저 수정하세요. 등록 인증값은 실행 중 입력합니다.\n\n"
    runner += "\n\n".join(code for _,code in sections)
    compile(runner, NAME+"_RUN.txt", "exec")
    (OUT/(NAME+"_RUN.txt")).write_text(runner)
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(.65)
    section.left_margin = section.right_margin = Inches(.75)
    style = document.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(10)
    style._element.rPr.rFonts.set(qn("w:eastAsia"),"맑은 고딕")
    style.paragraph_format.space_after = Pt(5)
    for name in ["Title","Heading 1","Heading 2"]:
        document.styles[name].font.name = "맑은 고딕"
        document.styles[name]._element.rPr.rFonts.set(qn("w:eastAsia"),"맑은 고딕")
    for line in (OUT/"GUIDE_UTF8.txt").read_text().splitlines():
        if line.startswith("DATAIKU 법령"):
            document.add_heading(line,0)
        elif re.match(r"^\d+\. ",line):
            document.add_heading(line,1)
        elif line.startswith("[표]"):
            document.add_heading(line[3:].strip(),2)
        else:
            document.add_paragraph(line)
    header=section.header.paragraphs[0]
    header.text="8-AGENT  |  DATAIKU API 연결 확인  |  2026-10-15 R1"
    header.style=document.styles["Caption"]
    footer=section.footer.paragraphs[0]
    footer.text="사내 Dataiku 연결은 현장 실행 결과로 별도 판정  ·  "
    field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
    document.save(OUT/(NAME+"_GUIDE.docx"))
    print("Notebook / standalone Python TXT / DOCX created")


if __name__ == "__main__":
    build()

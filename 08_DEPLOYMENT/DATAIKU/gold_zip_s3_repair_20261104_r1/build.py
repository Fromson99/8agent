import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'gold_zip_flow_20261104_r1'


def main():
    tree = ast.parse((PARENT / 'DATAIKU_GOLD_ZIP_FLOW_RUN_R1.txt').read_text())
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'install')
    bootstrap = ast.literal_eval(call.args[1])
    tree = ast.parse((PARENT / 'package/zip_config.py').read_text())
    stages = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == 'STAGES')
    header = '# 같은 LEGAL_RAG 프로젝트의 Python 노트북 새 셀에 전체 붙여넣고 실행\n# 기존 오류 셀은 다시 실행하지 않습니다. 이 셀은 폴더 복구만 하며 적재를 시작하지 않습니다.\nMODE = "REPAIR"  # 실행 전 원복만 필요한 경우 "ROLLBACK"\n'
    cell = header + (HERE / 'repair.py').read_text() + '\nimport dataiku\n'
    cell += 'BOOTSTRAP = ' + repr(bootstrap) + '\nSTAGES = ' + repr(stages) + '\n'
    cell += 'REPAIR_RESULT = repair(dataiku, BOOTSTRAP, STAGES, mode=MODE)\n'
    ast.parse(cell, feature_version=(3, 9))
    output = HERE / 'DATAIKU_GOLD_S3_REPAIR_RUN_R1.txt'
    output.write_text(cell)
    print(json.dumps({'bytes':output.stat().st_size, 'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()

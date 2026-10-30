"""Repair only the operator notebook entrypoint; reuse the sealed R1 client."""
import ast
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'pipeline_attempt_recovery_20261029_r1'


def main():
    assert not (HERE/'VALIDATION.json').exists(), 'Preserve sealed delivery'
    source = (BASE/'DATAIKU_ONE_ATTEMPT.txt').read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == '726236952388e1c355789da29d7269d411cea9124fb0b5f30b33624fb80e5ef0'
    old = 'import one_attempt\none_attempt.run(ACTION, CONFIRMATION, REASON)'
    new = ('import recipes_runtime\nfrom named_inputs import install_input_selection\n'
           'install_input_selection(recipes_runtime)\nimport one_attempt\n'
           'one_attempt.run(ACTION, CONFIRMATION, REASON)')
    assert source.count(old) == 1
    source = source.replace(old, new)
    source = source.replace("ACTION = 'inspect' # inspect / authorize_one_attempt", "ACTION = 'authorize_one_attempt' # inspect / authorize_one_attempt")
    source = source.replace("CONFIRMATION = '' #", "CONFIRMATION = 'AUTHORIZE_ONE_ADDITIONAL_COMPUTE_ATTEMPT' #")
    source = source.replace('# LEGAL_RAG 새 Python 노트북. 기본값은 조회만 합니다.', '# LEGAL_RAG 새 Python 노트북. 추가 1회 허용을 실행합니다. 계산은 자동 시작하지 않습니다.')
    ast.parse(source, feature_version=(3,9))
    (HERE/'DATAIKU_ONE_ATTEMPT_R2.txt').write_text(source)
    print('PREPARED_NOTEBOOK_ONLY_FIX')


if __name__ == '__main__':
    main()

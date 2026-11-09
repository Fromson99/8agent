"""Shared paths and helpers for ADR-1443 (document comparison with ordinary external search, 문서 대사)."""
from pathlib import Path
import hashlib, json, os, sys

ROOT = Path('/home/jin/8-AGENT')
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1443-document-compare-search-qwen'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-1440-document-compare-mode-qwen/artifacts'
ART = ADR / 'artifacts'; DES = ART / 'design'
TOOLS = Path(__file__).resolve().parent
STAGED = ROOT / '09_ARTIFACTS/AUDITS/20261106-document-compare/code'
SOURCE_GENERATION = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
GRANT = ROOT / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'
CASE = 'risk-model-code'
# The public guideline plays the internal rule; the four public rules it cites are the external side.
INTERNAL = '5c292593a5e4e4e4'      # 금융투자회사의 리스크관리 모범규준
EXTERNAL = ['5be4de51a89dc664',    # 자본시장과 금융투자업에 관한 법률
            '2a410c9dfc65dac1',    # 같은 법 시행령
            'c9b5b42627710637',    # 금융투자업규정
            'b0d8ff3732d1ab58']    # 금융투자회사의 영업 및 업무에 관한 규정
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '06_TOOLS/maintenance'))
from experiment_json import write_raw_json  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def put(path, value):
    """Small records; progress files (calls, generations) are rewritten as they grow."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', 'utf-8')
    os.replace(temporary, path)


def gz(path, value):
    """Raw request/response/view, written once as gzip with a small reference beside it."""
    reference = write_raw_json(path, value)
    put(Path(str(path) + '.ref.json'), reference)

"""Shared paths and helpers for ADR-1425 (reading-group row-limit probe)."""
from pathlib import Path
import hashlib, importlib, json, sqlite3, sys, types

ROOT = Path('/home/jin/8-AGENT')
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1425-reading-groups-row-limit-qwen'
ART = ADR / 'artifacts'; DES = ART / 'design'; RUN = ART / 'run-001'
TOOLS = Path(__file__).resolve().parent
GENERATION = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
GRANT = ROOT / '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'
PACKAGE = '02_BACKEND/semantic_runtime/basis_links'
CASES = {'risk-model-code': '5c292593a5e4e4e4', 'bond-demand-code': 'c48ac7332f552984'}
ARMS = {'baseline': 30, 'rows15': 15, 'rows60': 60}          # max_rows per arm
CODE = {'baseline': 'rows15', 'rows15': 'rows15', 'rows60': 'rows60'}  # frozen candidate each arm imports
FIXED = {'max_chars': 8000, 'max_spine_chars': 2000}
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '06_TOOLS/maintenance'))
from experiment_json import write_summary  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def put(path, value):
    """Write one new record; the experiment manifest is the only replaceable file."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path == ADR / '실험/manifest.json':
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    else:
        write_summary(path, value)


def modules(candidate_id):
    """Import reading_groups/group_review only from the frozen candidate revision."""
    pin = read(DES / 'candidates.json')[candidate_id]
    base = ROOT / pin['code_root'] / PACKAGE
    for name, expected in pin['files'].items():
        assert sha(ROOT / pin['code_root'] / name) == expected, 'frozen candidate file changed: ' + name
    package = 'adr1425_' + candidate_id
    if package not in sys.modules:
        module = types.ModuleType(package); module.__path__ = [str(base)]; sys.modules[package] = module
    return importlib.import_module(package + '.reading_groups'), importlib.import_module(package + '.group_review')


class Store:
    """Read-only view of the selected generation; nothing is copied or cached."""
    def __init__(self):
        self.db = sqlite3.connect('file:' + str(GENERATION / 'store.sqlite') + '?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row

    def check_unchanged(self):
        return None

    def name(self, did):
        return self.db.execute('SELECT name FROM document WHERE document_id=?', (did,)).fetchone()[0].split(' > ')[-1]

    def text(self, did, segments):
        parts = []
        for segment in segments:
            row = self.db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',
                                  (did, segment['block_id'])).fetchone()
            parts.append(row['text'][segment['start_cp']:segment['end_cp']])
        return '\n'.join(parts)

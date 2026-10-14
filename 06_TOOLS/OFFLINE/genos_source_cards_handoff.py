"""Build an editor-only update from sealed R4 and current source-card methods.

No model calls, runtime installation, backend ZIP, or generation changes.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/GENOS_WORKFLOW_LIVE_CARDS_20261008_R4_PASTE_ALL.txt'
BASE_SHA = 'b3f921977535ccf88c5906b27371e7167878e7390dc6ef82c4160d37f9a01abb'
# Historical R1 uses its sealed MAIN57 source, independent of newer UI revisions.
SOURCE = ROOT / '08_DEPLOYMENT/RELEASES/source-cards-20261013-r1/code/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
DEST = ROOT / '08_DEPLOYMENT/GENOS/handoffs/workflow_source_cards_20261013_r1'
NAME = 'GENOS_WORKFLOW_SOURCE_CARDS_20261013_R1_PASTE_ALL.txt'
METHODS = ('_card_rationale', '_append_source_card', '_flush_source_reads', '_source_progress')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unexpected source boundary: ' + old[:80])
    return text.replace(old, new, 1)


def build():
    original = BASE.read_bytes()
    if hashlib.sha256(original).hexdigest() != BASE_SHA:
        raise ValueError('sealed R4 editor hash mismatch')
    source = SOURCE.read_text(encoding='utf-8')
    lines = source.splitlines(keepends=True)
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == '_ChatProgress')
    selected = {n.name: ''.join(lines[n.lineno-1:n.end_lineno])
                for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in METHODS}
    text = original.decode('utf-8')
    text = replace_once(text, '        self.blocks = []\n',
        '        self.blocks = []\n        self.source_read_rows = []\n'
        '        self.source_read_context = None\n        self.source_card_number = 0\n')
    text = replace_once(text, '        kind = event.get("kind")\n',
        '        # Shared with the current workflow; preserve detailed R4 cards.\n'
        '        if await self._source_progress(event):\n'
        '            if event.get("kind") != "heartbeat" and len(self.flow_events) < 256:\n'
        '                self.flow_events.append({k: event[k] for k in ("label", "details", "kind", "basis") if k in event})\n'
        '            return\n'
        '        kind = event.get("kind")\n')
    text = replace_once(text, '    @staticmethod\n    def _plain(value):',
        '\n'.join(selected[name] for name in METHODS) + '\n\n    @staticmethod\n    def _plain(value):')
    text = replace_once(text, '        self.answer_seq = seq\n',
        '        await self._flush_source_reads()\n        self.answer_seq = seq\n')
    text = replace_once(text, '    async def finish(self, text):\n',
        '    async def finish(self, text):\n        await self._flush_source_reads()\n')
    text = replace_once(text, '{"visible_rationale": f"[{label}]\\n{visible}"}',
        '{"visible_rationale": (visible if full_error or full_judgment else self._card_rationale(message, details))}')
    for old, new in (
        ('rag-v6-live-cards-20261008-r4', 'rag-v6-source-cards-20261013-r1'),
        ('workflow-live-cards-20261008-r4', 'workflow-source-cards-20261013-r1'),
        ('rag-current-judgment-20261008-r2', 'rag-source-cards-20261013-r1')):
        text = replace_once(text, '"' + old + '"', '"' + new + '"')
    compile(text, NAME, 'exec')
    return text, selected


if __name__ == '__main__':
    text, selected = build()
    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / NAME
    if path.exists() and path.read_text(encoding='utf-8') != text:
        raise SystemExit('existing delivery differs; create a new revision')
    path.write_text(text, encoding='utf-8')
    manifest = {
        'purpose': 'existing-workflow-python-editor-only',
        'base_path': str(BASE.relative_to(ROOT)), 'base_sha256': BASE_SHA,
        'editor_file': NAME, 'editor_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'shared_source_path': str(SOURCE.relative_to(ROOT)),
        'shared_source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'shared_methods_sha256': {name: hashlib.sha256(value.encode()).hexdigest() for name, value in selected.items()},
        'grouping_basis': 'consecutive UNIT_READ_STARTED activity notifications; not a model-call ID',
        'model_calls': 0, 'backend_modified_by_delivery': False, 'data_generation_modified_by_delivery': False,
        'local_active_pointer_sha256': hashlib.sha256((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()).hexdigest(),
        'field_workflow_pasted': False, 'field_workflow_test': 'NOT_RUN',
        'field_git_commit': None, 'field_code_serving_revision': None,
        'field_generation': None, 'field_generation_manifest_sha256': None,
    }
    metadata = DEST / 'CODE_MANIFEST.json'
    value = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    if metadata.exists() and metadata.read_text(encoding='utf-8') != value:
        raise SystemExit('existing manifest differs; create a new revision')
    metadata.write_text(value, encoding='utf-8')
    print(path.relative_to(ROOT))

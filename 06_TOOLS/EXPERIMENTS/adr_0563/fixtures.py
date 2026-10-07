"""Synthetic adapters and migration from the exact completed prototype data."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0563-portable-investigation-memory'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0563/portable'
PARENT = ROOT/'04_EXPERIMENTS/ADR/ADR-0562-node-action-experience-closed-feedback'
KEY = 'synthetic-authority:mock-deal'
RAW = '외국인 인수 적용 여부를 확인한다.\n외국인의 정의와 거래의 예외를 확인한다.'
CUT = RAW.index('\n')+1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load():
    meta = json.loads((CANDIDATE/'candidate.json').read_text())
    revision = meta['revisions'][-1]
    for row in revision['files']:
        if sha(ROOT/row['frozen_path']) != row['snapshot_sha256']:
            raise ValueError('frozen candidate changed')
    p = CANDIDATE/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/lawrag/core/investigation_memory.py'
    spec = importlib.util.spec_from_file_location('adr0563_portable_memory', p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def node(m, raw, start, end, handle):
    return {'document_key': KEY, 'handle': handle,
        'origin_spans': [{'start_cp': start, 'end_cp': end, 'text': raw[start:end],
            'span_sha256': m.text_hash(raw[start:end])}]}


def setup(m, *, layout='separate', raw=RAW, projection_id='generation-1', include_target=True):
    if layout == 'merged':
        nodes = {'merged-current': node(m, raw, 0, len(raw), 'U-merged-new')}
    else:
        nodes = {'entry-current': node(m, raw, 0, CUT, 'U-entry-new')}
        if include_target:
            if layout == 'split':
                mid = CUT+(len(raw)-CUT)//2
                nodes.update({'part-1': node(m, raw, CUT, mid, 'P-new-1'),
                    'part-2': node(m, raw, mid, len(raw), 'P-new-2')})
            else:
                nodes['target-current'] = node(m, raw, CUT, len(raw), 'U-target-new')
    p = m.Projection(projection_id, {KEY: {'text': raw, 'origin_sha256': m.text_hash(raw)}}, nodes)
    return p


def bundle(m):
    c = {'id': 'concept:scope-check', 'label': '적용 범위 확인', 'objective': '정의와 예외를 확인한다',
        'expected_information': '적용 대상 여부를 판단할 정의와 예외',
        'exit_condition': '현재 원문의 거래 조건이 경험의 조건과 다르면 다른 경로를 탐색한다',
        'support_count': 2, 'transitions': [{'anchor': m.anchor(KEY, RAW, 0, CUT),
            'target': m.anchor(KEY, RAW, CUT, len(RAW)), 'operation': 'acquire_evidence'}]}
    return m.publish([c], {'classification': 'SYNTHETIC', 'test_contract': 'v1'})


def capabilities(tool='read'):
    if tool == 'read':
        return {'acquire_evidence': lambda n: {'tool': 'read',
            'args': {'target': n['handle'], 'extent': 'article', 'cursor': None}}}
    return {'acquire_evidence': lambda n: {'tool': 'fetch_fragment',
        'arguments': {'fragment_key': n['handle'], 'include_source': True}}}


def lift_parent(m):
    frozen = json.loads((ADR/'artifacts/design-freeze.json').read_text())
    path = ROOT/frozen['parent_bundle']
    if sha(path) != frozen['parent_bundle_sha256']:
        raise ValueError('completed parent bundle changed')
    previous = json.loads(path.read_text())
    if previous['sha256'] != m.digest({k: v for k, v in previous.items() if k != 'sha256'}):
        raise ValueError('parent bundle payload changed')
    path = PARENT/'artifacts/run-001/fixture/raw.sqlite'
    # Read the original synthetic blocks, not a regenerated approximation.
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        rows = db.execute('SELECT unit_id,text FROM source_block ORDER BY CAST(block_id AS INTEGER)').fetchall()
    raw, spans = '', {}
    for uid, text in rows:
        start = len(raw); raw += text+'\n'
        spans[uid] = (start, start+len(text), text)
    def map_stamp(stamp):
        lo, hi, text = spans[stamp['unit_id']]
        if m.text_hash(text) != stamp['text_sha256']:
            raise ValueError('parent source witness differs from recorded stamp')
        return m.anchor(KEY, raw, lo, hi)
    concepts = []
    for c in previous['concepts']:
        result = {k: deepcopy(c[k]) for k in ('id', 'label', 'objective',
            'expected_information', 'exit_condition', 'support_count')}
        result['transitions'] = [{'anchor': map_stamp(t['anchor']), 'target': map_stamp(t['target']),
            'operation': 'acquire_evidence'} for t in c['transitions']]
        concepts.append(result)
    memory = m.publish(concepts, {'classification': 'SYNTHETIC',
        'parent_bundle_sha256': frozen['parent_bundle_sha256'], 'episode_count': len(previous['episodes']),
        'origin_adapter': 'verified completed synthetic source_block text; joined origin document v1'})
    nodes = {f'new-node-{uid}': node(m, raw, lo, hi, f'new-handle-{uid}')
        for uid, (lo, hi, _) in spans.items()}
    projection = m.Projection('new-generation-with-new-nodes',
        {KEY: {'text': raw, 'origin_sha256': m.text_hash(raw)}}, nodes)
    return memory, projection

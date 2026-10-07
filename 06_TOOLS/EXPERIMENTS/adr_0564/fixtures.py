"""Synthetic ontology producer and named tool adapters; no retrieval engine."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0564-investigation-ontology-access'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0564/graph'
PURPOSE = 'purpose:applicable-regulation'
OTHER = 'purpose:complete-inventory'
SCOPE = {'resource:A','resource:B','resource:C'}
PROOF = {'classification':'SYNTHETIC','reference':'fixture:explicit-purpose-policy-v1',
    'basis':'모의 적용규정 탐색에서는 업무실적 자료 C를 제외한다는 명시적 조사 정책. 법률 적용 사실이 아니다.'}
OPS = {'search_fulltext':'discover','browse':'list','follow_relations':'traverse',
    'read':'read','lookup_definition':'definition','term_occurrences':'occurrences'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load():
    meta = json.loads((CANDIDATE/'candidate.json').read_text())
    rev = meta['revisions'][-1]
    for row in rev['files']:
        if sha(ROOT/row['frozen_path']) != row['snapshot_sha256']:
            raise ValueError('frozen graph candidate changed')
    p = CANDIDATE/'revisions'/rev['revision_id']/'snapshot/02_BACKEND/lawrag/core/investigation_graph.py'
    spec = importlib.util.spec_from_file_location('adr0564_graph', p)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def build(m, path, *, status='ACTIVE', conditions=None, child=False, rename=False, drift=False, unknown=False):
    g = m.Graph(path, create=True)
    g.concept(PURPOSE,'PURPOSE','적용규정 탐색')
    g.concept(OTHER,'PURPOSE','전체 자료 목록 확인')
    for ident, label in [('A','정의 자료'),('B','적용조건 자료'),('C','업무실적 자료'),('C-child','상세 실적 자료')]:
        g.concept('class:'+ident,'DATA_CLASS',label)
    g.relate('relation:exclude-C',PURPOSE,'EXCLUDES','class:C',proof=PROOF,status=status,conditions=conditions)
    if child:
        g.relate('relation:subclass','class:C-child','IS_A','class:C',proof=PROOF,status='ACTIVE')
    for ident in ('A','B','C'):
        g.add_resource('resource:'+ident,'모의 자료 '+ident)
        origin = hashlib.sha256(('immutable mock origin '+ident).encode()).hexdigest()
        if not (unknown and ident=='C'):
            g.classify('resource:'+ident,'class:C-child' if child and ident=='C' else 'class:'+ident,origin,proof=PROOF)
        current_origin = hashlib.sha256(b'changed C text').hexdigest() if drift and ident=='C' else origin
        g.bind_node('generation-2' if rename else 'generation-1',
            'changed-node-'+ident if rename else 'node-'+ident,'resource:'+ident,current_origin)
    return g


class ToolAdapter:
    """The access boundary sees an operation, regardless of the tool name.

    Backend returns the allowed ID inventory for contract verification only.
    It does not run Fulltext, ANN, original reads or the production tool handler.
    """
    def __init__(self, name, operation):
        self.name, self.operation = name, operation
        self.executions = []

    def execute(self, graph, purpose=PURPOSE, projection='generation-1', scope=SCOPE, *, targets=None, facts=None):
        def backend(operation, allowed):
            self.executions.append({'operation':operation,'allowed_node_ids':allowed})
            return allowed
        return graph.access(purpose, projection, scope, self.operation, backend, targets=targets,facts=facts)

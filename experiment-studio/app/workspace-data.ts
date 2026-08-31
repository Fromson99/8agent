export type WorkspaceDataset = {
  id: string;
  name: string;
  sourcePath: string;
  kind: 'golden' | 'corpus' | 'trace' | 'ontology';
  records: number;
  size: string;
  version: string;
  status: 'locked' | 'connected' | 'review';
  adapter: string;
  description: string;
  fields: string[];
};

export const workspaceSummary = {
  activeFiles: 5359,
  corpusFiles: 3118,
  wikiFiles: 1218,
  structureFiles: 708,
  wikiLedgerEvents: 129,
  capturedAt: '2026-08-26',
};

export const workspaceDatasets: WorkspaceDataset[] = [
  {
    id: 'golden-formal',
    name: 'Formal legal holdout',
    sourcePath: 'data/review/golden_holdout_formal.json',
    kind: 'golden',
    records: 113,
    size: '58.5 KB',
    version: 'formal-v3',
    status: 'locked',
    adapter: 'review-golden-v1',
    description: '법령해석 방향·법령·조문 회수 성능을 고정 측정하는 holdout입니다.',
    fields: ['case_no', 'direction', 'want_laws', 'want_arts', 'basis_hit'],
  },
  {
    id: 'golden-mix',
    name: 'Traffic mix 20/80',
    sourcePath: 'data/review/golden_mix2080_v3.json',
    kind: 'golden',
    records: 51,
    size: '51.5 KB',
    version: 'mix-v3',
    status: 'locked',
    adapter: 'review-golden-v1',
    description: '질의요지 원문과 구어 변환을 실제 사용 비율에 맞춰 혼합한 회귀 세트입니다.',
    fields: ['case_no', 'mode', 'text_kind', 'material', 'direction'],
  },
  {
    id: 'run-seven',
    name: 'Golden v2 run 7',
    sourcePath: 'data/review/golden_v2_run7.json',
    kind: 'trace',
    records: 44,
    size: '53.0 KB',
    version: 'run-7',
    status: 'review',
    adapter: 'legacy-run-import',
    description: '기존 실행 결과를 case-level trace와 비교 화면으로 가져오기 위한 import 대상입니다.',
    fields: ['case_no', 'basis_hit', 'got_laws', 'got_arts', 'sec'],
  },
  {
    id: 'legal-corpus',
    name: 'Canonical legal corpus',
    sourcePath: 'data/corpus',
    kind: 'corpus',
    records: 3118,
    size: '197.6 MB',
    version: 'workspace-live',
    status: 'connected',
    adapter: 'filesystem-manifest',
    description: '법령·규정 원문과 수집 manifest를 DataProduct 계약으로 노출합니다.',
    fields: ['source_id', 'document_id', 'checksum', 'effective_at', 'acl'],
  },
  {
    id: 'domain-wiki',
    name: 'Legal interpretation wiki',
    sourcePath: 'data/wiki',
    kind: 'ontology',
    records: 1218,
    size: '6.4 MB',
    version: 'workspace-live',
    status: 'connected',
    adapter: 'wiki-lineage',
    description: '해석 지식, 규칙, 적중 원장 129건을 ontology evidence로 연결합니다.',
    fields: ['article_id', 'status', 'source_ref', 'rule_id', 'ledger_event'],
  },
];

export const experimentRuns = [
  { id: 'run-042-a', name: 'gold-only / trial 3', adr: 'ADR-0042', layer: 'Solve', dataset: 'formal-v3', status: 'Gate review', score: 87.0, delta: 8.7, latency: '4.8s', changed: 'legal_effect_mode' },
  { id: 'run-041-b', name: 'definition card / B', adr: 'ADR-0041', layer: 'Ground', dataset: 'mix-v3', status: 'Complete', score: 84.1, delta: 5.8, latency: '5.2s', changed: 'knowledge_card' },
  { id: 'run-041-c', name: 'hard distractor', adr: 'ADR-0041', layer: 'Ground', dataset: 'challenge-16', status: 'Regression', score: 71.9, delta: -6.4, latency: '5.1s', changed: 'distractor_pool' },
  { id: 'run-040-a', name: 'frame-only baseline', adr: 'ADR-0040', layer: 'Solve', dataset: 'formal-v3', status: 'Baseline', score: 78.3, delta: 0, latency: '4.6s', changed: 'none' },
  { id: 'run-038-a', name: 'wiki hygiene', adr: 'ADR-0038', layer: 'Prepare', dataset: 'wiki-ledger', status: 'Complete', score: 76.4, delta: 2.1, latency: '4.7s', changed: 'definition_context' },
];

export const goldenSuites = [
  { name: 'formal-v3', cases: 113, owner: 'Eval Owner', split: 'locked', coverage: '법령·방향·근거', updated: '2026.08.25' },
  { name: 'mix-v3', cases: 51, owner: 'FDE', split: 'locked', coverage: '원문 20 · 구어 80', updated: '2026.08.24' },
  { name: 'challenge-16', cases: 16, owner: 'Domain SME', split: 'challenge', coverage: 'hard distractor', updated: '2026.08.25' },
  { name: 'rolling-shadow', cases: 29, owner: 'Ops', split: 'shadow', coverage: '최근 운영 실패', updated: '오늘' },
];

export const evaluatorRegistry = [
  { name: 'direction_exact', type: 'Code', input: 'output.direction', target: 'formal-v3', state: 'Active' },
  { name: 'basis_recall', type: 'Code', input: 'retrieved anchors', target: 'formal-v3', state: 'Active' },
  { name: 'citation_grounding', type: 'LLM judge', input: 'answer + context', target: 'mix-v3', state: 'Calibrated' },
  { name: 'first_failure_layer', type: 'Composite', input: 'full trace', target: 'all runs', state: 'Active' },
  { name: 'acl_zero_violation', type: 'Policy', input: 'actor + evidence', target: 'all runs', state: 'Required' },
];

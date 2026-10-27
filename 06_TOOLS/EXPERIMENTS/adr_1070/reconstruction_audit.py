"""Read-only original frames and transparent view timing/equivalence checks.

The original journal is never opened for writing. Input equivalence failures
remain separate from response validity and do not alter the native control flow.
No corpus/index is loaded by this helper, and no cProfile session is started.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import json
from pathlib import Path
import sqlite3
import time

from common import canonical_digest, exact_write, sha
from replay_transport import checked_file, require


def frame_hashes(frame):
    require(isinstance(frame, dict) and all(k in frame for k in ('data', 'actions', 'location')),
            'navigation frame is incomplete')
    return {key:canonical_digest(frame[key]) for key in ('data', 'actions', 'location')}


def compare_frame(expected, actual):
    """Compare value hashes, never substitute a stored frame into current state."""
    observed = frame_hashes(actual)
    return {'expected':deepcopy(expected), 'actual':observed,
            'fields_exact':{key:expected[key] == observed[key] for key in expected},
            'comparable':expected == observed}


def original_frames(item, expected_count):
    path = checked_file(item)
    wal = Path(str(path) + '-wal')
    # The frozen 1066 source has no WAL. Never silently ignore a committed WAL
    # or checkpoint an old journal to manufacture a convenient input.
    require(not wal.exists() or wal.stat().st_size == 0, 'nonempty original WAL is not supported by this frozen input')
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1')
    try:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute("SELECT payload_json,payload_hash,created_seq FROM entity_version "
                          "WHERE kind='case_stage' AND entity_id='case:SELECT' ORDER BY version").fetchall()
        require(len(rows) == 1 and len(rows[0][0]) < 8*1024*1024, 'original SELECT inventory changed')
        payload = json.loads(rows[0][0])
        require(canonical_digest(payload) == rows[0][1], 'original SELECT payload hash changed')
        frames = sorted(payload['investigation_state']['action_chain']['frames'].values(),
                        key=lambda row:row['number'])
        require(len(frames) == expected_count and [r['number'] for r in frames] == list(range(1, expected_count+1))
                and all(r['kind'] == 'NAVIGATION' for r in frames), 'original frame inventory changed')
        return [{'number':r['number'], 'id':r['id'], 'hashes':frame_hashes(r)} for r in frames]
    finally:
        db.close()
        require(sha(path) == item['sha256'], 'original journal changed while reading')


class ViewAudit:
    def __init__(self, frozen, out):
        contract = frozen['replay_contract']
        self.original = deepcopy(contract['native_journal'])
        self.expected = original_frames(self.original, contract['expected_navigation_views'])
        self.out = out
        self.views, self.checks = 0, []

    @contextmanager
    def install(self, code_root):
        from semantic_runtime.legal_agent import law_navigation
        require(Path(law_navigation.__file__).resolve().is_relative_to(Path(code_root).resolve()),
                'view audit imported outside frozen candidate')
        original = law_navigation.Investigation.view
        audit = self
        @wraps(original)
        def observed(inv):
            ordinal = audit.views + 1
            started = time.perf_counter()
            try:
                value = original(inv)
            except BaseException as exc:
                elapsed = time.perf_counter() - started
                audit.checks.append({'ordinal':ordinal, 'view_seconds':elapsed,
                                     'completed':False, 'comparable':False,
                                     'error_type':type(exc).__name__})
                raise
            elapsed = time.perf_counter() - started
            audit.views += 1
            data, actions = value
            chain = inv.p['action_chain']
            frame = chain['frames'][chain['current_frame']]
            row = {'ordinal':ordinal, 'view_seconds':elapsed, 'completed':True,
                   'state_turn':inv.p.get('turn'), 'state_version':inv.p.get('state_version'),
                   'actual_frame_id':frame['id'], 'returned_actions_sha256':canonical_digest(actions),
                   'returned_sources_sha256':canonical_digest(data.get('sources', [])),
                   'timing_boundary':'original Investigation.view only; post-return hash comparison and file I/O excluded'}
            if ordinal <= len(audit.expected):
                expected = audit.expected[ordinal-1]
                row.update(expected_frame_id=expected['id'], **compare_frame(expected['hashes'], frame))
            else:
                row.update(comparable=False, comparison_failure='EXTRA_NAVIGATION_VIEW')
            audit.checks.append(row)
            exact_write(audit.out / f'navigation-view-{ordinal:03d}.json', row)
            return value
        law_navigation.Investigation.view = observed
        try:
            yield self
        finally:
            law_navigation.Investigation.view = original

    def receipt(self, transport_checks):
        projection = [r for r in transport_checks if 2 <= r['recorded_call'] <= 9]
        count_exact = self.views == len(self.expected) == 8 and len(self.checks) == 8
        frame_exact = count_exact and all(r.get('comparable') is True for r in self.checks)
        projection_exact = len(projection) == 8 and all(r.get('projection_exact') is True for r in projection)
        return {'schema_version':'navigation-reconstruction-equivalence-v1',
            'original_journal':self.original, 'expected_views':8, 'completed_views':self.views,
            'view_count_exact':count_exact, 'frames_exact':frame_exact,
            'projected_sources_actions_exact':projection_exact,
            'primary_equivalence_gate_passed':frame_exact and projection_exact,
            'view_seconds_sum':sum(r['view_seconds'] for r in self.checks),
            'view_checks':deepcopy(self.checks),
            'projection_checks':[{'recorded_call':r['recorded_call'],
                'checks':r['projection_checks'], 'comparable':r['projection_exact']} for r in projection],
            'historical_211_seconds_reproduced':False,
            'interpretation':'New measured execution; comparable only where original frame and projection values match. Instrumentation overhead and startup are separate.'}


def completed_publication(runtime_root):
    """Check the actual new consumer, not just a successful HTTP envelope."""
    paths = list((Path(runtime_root) / 'legal-agent/runs').glob('*/*/journal.sqlite'))
    require(len(paths) == 1, 'new native journal missing or duplicated')
    db = sqlite3.connect(paths[0].resolve().as_uri() + '?mode=ro')
    try:
        db.execute('PRAGMA query_only=ON')
        run = db.execute('SELECT status,phase FROM run WHERE singleton=1').fetchone()
        published = db.execute('SELECT status,result_hash FROM publication WHERE singleton=1').fetchone()
        return {'journal':str(paths[0]), 'run_status':run[0] if run else None,
                'phase':run[1] if run else None, 'publication_status':published[0] if published else None,
                'publication_result_hash':published[1] if published else None,
                'complete':bool(run and run[0] == 'COMPLETED' and published and published[0] == 'PUBLISHED')}
    finally:
        db.close()

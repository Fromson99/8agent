"""Prepare ADR1063 catalogue requests from nine small ADR1062 checkpoints.

No source DB, index, credentials, model, HTTP client, product tool or live run is
opened. Historical journals are read-only. A stored sorted view is not the
original wire request: original PREPARED metrics are reported separately, and
only the newly compiled candidate request has an exact replay hash/size.
"""
from contextlib import contextmanager
from copy import deepcopy
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

from common import ROOT, ART, read, save, sha, canonical_digest as digest

DEFAULT_CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1063/catalogue-projection-r1/snapshot'
DEFAULT_MATRIX = ROOT / '04_EXPERIMENTS/ADR/ADR-1062-ontology-mvp-runner-binding/artifacts/matrix'


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def load_code(code):
    code = Path(code).resolve()
    for name, module in list(sys.modules.items()):
        if name == 'semantic_runtime' or name.startswith('semantic_runtime.'):
            require(Path(module.__file__).resolve().is_relative_to(code), 'candidate import already bound elsewhere')
    sys.path.insert(0, str(code / '02_BACKEND'))
    return code


def code_files(code):
    """Small candidate code/config map, excluding caches and runtime data."""
    return {str(path.relative_to(code)):sha(path) for folder in ('02_BACKEND','00_SYSTEM')
        for path in sorted((code/folder).rglob('*'))
        if path.is_file() and path.suffix in ('.py','.json') and '__pycache__' not in path.parts}


def capture_choice(stored, progress, profile, scope, budget):
    """Only the actual choice/schema compiler runs; invocation stops at preview."""
    from semantic_runtime.legal_agent import decision_projection as dp, output_contract as oc
    frame = progress['action_chain']['frames'][progress['action_chain']['current_frame']]
    data, actions = deepcopy(frame['data']), deepcopy(frame['actions'])
    require(stored['issues'] == progress['issues'], 'saved current issues differ from checkpoint issues')
    # The cached frame predates request-entry issue enrichment. The saved
    # presentation and checkpoint carry the actual enriched issue records.
    for field in ('issues','presentation_id','state_version','current_request','connection_review',
                  'navigation_review_tasks','input_mode'):
        if field in stored:
            data[field] = deepcopy(stored[field])
    for field in ('completion_contract','control_contract'):
        data[field] = deepcopy(progress[field])
    require(not data.get('sources') and not stored.get('sources'), 'offline catalogue fixture contains source text')
    captured, events = {}, []
    class Captured(Exception):
        pass
    def invoke(system, payload, schema, phase, timeout, **kwargs):
        require(kwargs == {'preview_only':True}, 'offline compiler attempted a physical call')
        captured.update(system=system, payload=deepcopy(payload), schema=deepcopy(schema), stage=phase)
        raise Captured()
    def bounded(repo, owner, payload, schema, invoke, expand, **kwargs):
        # No validator, transition, retry or execution runs during this capture.
        invoke(payload, 0, preview_only=True)
        raise AssertionError('preview capture did not stop')
    inv = NS(modern=True, completion=True, control=True, policy=profile['candidate_navigation'],
        p=deepcopy(progress), question=stored['request'], save=lambda:None, left=lambda:180,
        invoke=invoke, s=NS(profile=profile, scope=set(scope),
            repo=NS(event=lambda kind,value:events.append({'kind':kind,'payload':deepcopy(value)}),
                    budget=lambda:deepcopy(budget))))
    previous_rows, previous_bounded = dp.read_candidate_rows, oc.bounded_decision
    try:
        # Exact saved paths/coordinates avoid constructing any source matcher.
        dp.read_candidate_rows = lambda *args, **kwargs: deepcopy(stored['read_candidates'])
        oc.bounded_decision = bounded
        try:
            dp.choose_read(inv, data, actions, stored['source_stage'].removesuffix('-read-choice'))
        except Captured:
            pass
    finally:
        dp.read_candidate_rows, oc.bounded_decision = previous_rows, previous_bounded
    require(bool(captured), 'choice compiler did not reach preview')
    captured['events'] = events
    captured['canonical_actions_sha256'] = digest(actions)
    captured['canonical_action_count'] = len(actions)
    return captured


class SnapshotQueries:
    """Expose only the two step-state reads at the original prepared sequence."""
    def __init__(self, db, seq):
        self.db, self.seq = db, seq

    def execute(self, sql):
        if sql == 'SELECT tool,status FROM observation ORDER BY created_seq DESC LIMIT 1':
            return self.db.execute('SELECT tool,status FROM observation WHERE created_seq<? ORDER BY created_seq DESC LIMIT 1', (self.seq,))
        if sql == 'SELECT count(*) FROM evidence_unit':
            return self.db.execute('SELECT count(*) FROM evidence_unit WHERE created_seq<?', (self.seq,))
        raise ValueError('unexpected offline repository query: ' + sql)


def preview_transport(profile, binding, provider_request, code):
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    class PreviewOnly(LocalGemmaTransport):
        def __init__(self):
            # Do not call credential-loading transport constructor. The real
            # pure transport preview function below is inherited unchanged.
            self.binding = deepcopy(profile['model_binding'])
            self.policy = read(code / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
            self.response_reception = 'buffered-json-sse-v1'
            require(self.binding == binding['model'], 'recorded model binding differs')
            require(self.policy['model'] == self.binding['model'], 'candidate model differs')
            require(self.policy['max_output_tokens'] is None, 'output cap reintroduced')
            for key in ('provider','reasoning'):
                expected = self.policy['provider_routing' if key == 'provider' else key]
                require(provider_request[key] == expected, 'recorded provider policy differs')

        def validate_authorization(self, context):
            # This only binds the saved fixture. It grants no send permission.
            require(context.binding == binding, 'saved authorization binding differs')
            require(binding.get('external_authorization', {}).get('kind') == 'USER_AUTHORIZED_MVP_EXPERIMENT',
                    'saved experiment authorization missing')

        def send_once(self, **kwargs):
            raise AssertionError('offline replay must never send')
    return PreviewOnly()


def replay_cell(cell, code, *, preview_directory=None):
    from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
    from semantic_runtime.legal_agent import catalogue_input, input_modes
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences, expand_cards
    from semantic_runtime.legal_agent.gateway import compact_wire_view
    from semantic_runtime.legal_agent.repository import encoded
    from semantic_runtime.legal_agent import navigation_values as nv
    journals = list(cell.glob('runtime/legal-agent/runs/*/*/journal.sqlite'))
    require(len(journals) == 1, 'expected one journal in ' + cell.name)
    journal = journals[0]
    with readonly(journal) as db, readonly(cell / 'runtime/case-memory/cases-v4.sqlite') as case_db:
        event = db.execute("SELECT * FROM event WHERE kind='MODEL_INPUT_PREPARED' ORDER BY seq DESC LIMIT 1").fetchone()
        require(event is not None, 'prepared catalogue receipt missing')
        recorded = json.loads(event['payload_json'])
        require(recorded['input_mode'] == 'CATALOGUE' and not recorded['physical_attempt_reserved']
            and not recorded['model_delivery_claimed'], 'fixture was not an unsent catalogue preview')
        row = db.execute('SELECT * FROM model_view WHERE view_id=?', (recorded['view_id'],)).fetchone()
        stored = json.loads(row['body_json'])
        require(digest(stored) == row['body_hash'], 'saved presentation hash changed')
        run, budget = dict(db.execute('SELECT * FROM run').fetchone()), dict(db.execute('SELECT * FROM budget').fetchone())
        binding = json.loads(run['binding_json'])
        require(digest(binding) == run['binding_hash'], 'saved run binding hash changed')
        progress_rows = case_db.execute('SELECT payload,hash FROM stage_progress').fetchall()
        require(len(progress_rows) == 1, 'expected one saved investigation checkpoint')
        progress = json.loads(progress_rows[0]['payload'])
        require(digest(progress) == progress_rows[0]['hash'], 'saved checkpoint hash changed')
        profile = read(cell / 'effective-profile.json')
        captured = capture_choice(stored, progress, profile,
            binding['external_authorization']['scope_document_ids'], budget)
        payload = captured['payload']
        for name in ('law_matches','read_candidates','tool_options','article_candidate_page','request','current_request','issues'):
            require(payload.get(name) == stored.get(name), 'canonical catalogue field changed: ' + name)
        # Reproduce UnifiedExecution's existing domain augmentation, then call
        # the same candidate projection used by BoundedSourceSession. Source0
        # fixtures cannot contain a knowledge bundle or acquired source text.
        for name in ('catalogue','domain_choice','concept_policy'):
            if name in stored:
                payload[name] = deepcopy(stored[name])
        payload, augmentation = catalogue_input.project(payload, captured['stage'])
        view = {**payload, **{key:stored[key] for key in ('input_projection','source_stage',
            'budget_class','view_id','phase','base_state_revision','evidence_revision') if key in stored}}
        require(not view.get('sources'), 'candidate unexpectedly added source text')
        context = NS(binding=binding, binding_hash=run['binding_hash'], remaining=lambda:179)
        repo = NS(db=SnapshotQueries(db,event['seq']), run=lambda:run, budget=lambda:budget,
            event=lambda *args:(_ for _ in ()).throw(AssertionError('offline gateway attempted a journal write')))
        transport = preview_transport(profile,binding,read(cell/'model/call-001-service/request.json'),code)
        gateway = _Gateway(repo,context,profile,{},transport,
            message_protocol=_Protocol(captured['schema']),system=captured['system'])
        native, minimal, reuse, inputs, aliases, cost = gateway.prepare_input(
            'investigate',view,'BoundedSourceDecision',record=False)
        physical, receipt = input_modes.measure(profile,'investigate',view,native,transport.preview_request)
        user = json.loads(next(m['content'] for m in native['messages'] if m['role']=='user'))
        wire = user['view']
        compact = compact_wire_view(NavigationReferences(view).view(view),'investigate')
        require(inputs is not None, 'catalogue input codec receipt missing')
        restored = inputs.verify(compact,wire)
        inputs.verify_request_instructions(native)
        require(expand_cards(restored) == expand_cards(compact), 'candidate codec did not restore exact cards')
        # Compare the actual generated dictionary, never a regenerated original
        # request whose numbering depended on lost dict insertion order.
        if inputs.value_sharing:
            expected = expand_cards(inputs.pre_values,expand_shared=False) if inputs.expanded_cards else inputs.pre_values
            require(nv.expand(wire) == expected, 'actual candidate dictionary failed exact restoration')
        raw = encoded(physical).encode('utf-8')
        if preview_directory:
            target = preview_directory / (cell.name + '-candidate-request.json.gz')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(gzip.compress(raw,mtime=0))
        imported = {str(Path(module.__file__).resolve().relative_to(code)):sha(module.__file__)
            for name,module in sys.modules.items() if (name == 'semantic_runtime' or name.startswith('semantic_runtime.'))
            and getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(code)}
        return {'cell':cell.name, 'source_journal':str(journal.relative_to(ROOT)),
            'source_journal_sha256':sha(journal),
            'source_view_id':stored['view_id'],'source_view_sha256':row['body_hash'],
            'recorded_prepared':recorded, 'candidate_prepared':receipt,
            'original_wire_reconstructed':False,'original_wire_hash_comparison_performed':False,
            'replay_basis':'stored canonical checkpoint; saved read coordinates; candidate compiler and actual pure transport preview',
            'reconstruction_assumptions':{'step_seconds_remaining':179,
                'note':'original request bytes and dictionary insertion order were not saved; this is a new candidate preview'},
            'physical_calls':0,'source_database_loads':0,'model_delivery_claimed':False,
            'preserved':{'law_rows':len(stored['law_matches']['rows']),
                'read_candidates':len(stored['read_candidates']),
                'tool_options':len(stored['tool_options']),
                'article_candidate_page':stored['article_candidate_page'],
                'canonical_actions':captured['canonical_action_count'],
                'canonical_actions_sha256':captured['canonical_actions_sha256'],
                'fields_sha256':{k:digest(stored[k]) for k in ('law_matches','read_candidates','tool_options','request','current_request','issues')},
                'exact_restore_verified':True},
            'projection_events':captured['events'], 'augmentation_projection':augmentation,
            'codec':inputs.receipt,'input_cost':cost,
            'minimal_output_active':minimal is not None and minimal.node is not None,
            'candidate_request_sha256':hashlib.sha256(raw).hexdigest(),
            'candidate_code_files':imported,
            'field_chars':{k:len(encoded(v)) for k,v in wire.items()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code',type=Path,default=DEFAULT_CODE)
    parser.add_argument('--matrix',type=Path,default=DEFAULT_MATRIX)
    parser.add_argument('--cell',action='append',help='one matrix directory name; default all nine')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--write-previews',action='store_true')
    args=parser.parse_args()
    code=Path(args.code).resolve()
    before=code_files(code)
    proof_tools={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),Path(__file__).with_name('common.py').resolve())}
    code=load_code(code)
    require(args.output.resolve().is_relative_to(ART.resolve()), 'replay output must stay in new ADR1063 artifacts')
    cells=[args.matrix/name for name in args.cell] if args.cell else sorted(p for p in args.matrix.iterdir() if p.is_dir())
    if not args.cell:
        require(len(cells)==9,'expected nine saved catalogue cases')
    require(len({cell.name for cell in cells})==len(cells),'duplicate replay cell')
    rows=[]
    for cell in cells:
        result=replay_cell(cell,code,preview_directory=args.output.parent/(args.output.stem+'-previews') if args.write_previews else None)
        require(code_files(code)==before,'candidate bytes changed during replay; candidate measurements are not a stable-code result')
        require(all(sha(ROOT/path)==expected for path,expected in proof_tools.items()),'replay tool bytes changed during preview')
        rows.append(result)
        print(cell.name, result['recorded_prepared']['measured_chars'], '->',
            result['candidate_prepared']['measured_chars'],result['candidate_prepared']['status'],flush=True)
    report={'version':'adr1063-stored-catalogue-candidate-preview-v1','code_root':str(code.relative_to(ROOT)),
        'physical_calls':0,'original_request_reconstruction_claimed':False,
        'candidate_files_sha256':before,'candidate_filemap_sha256':digest(before),
        'replay_tool_hashes':proof_tools,
        'candidate_files_unchanged_during_replay':True,
        'all_within_24000':all(r['candidate_prepared']['status']=='WITHIN_BUDGET' for r in rows),'cells':rows}
    save(args.output,report)
    return 0 if report['all_within_24000'] else 2


if __name__=='__main__':
    raise SystemExit(main())

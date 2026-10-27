"""Compile new task requests from all nine saved ADR1063 failure states.

No source corpus/index, credentials, model or tool execution. Completed cases
use their immutable SELECT investigation_state; stopped cases use checkpoint.
These are NEW candidate previews, not reconstructed historical wire requests.
"""
from copy import deepcopy
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

from common import ROOT, ART, read, save, sha, canonical_digest as digest

HELPER = ROOT/'06_TOOLS/EXPERIMENTS/adr_1063/replay_catalogue.py'
spec = importlib.util.spec_from_file_location('historical_preview_utilities', HELPER)
util = importlib.util.module_from_spec(spec); spec.loader.exec_module(util)
require = util.require
MATRIX = ROOT/'04_EXPERIMENTS/ADR/ADR-1063-ontology-mvp-catalogue-projection/artifacts/matrix'


def capture(stored, progress, profile, binding, budget):
    from semantic_runtime.legal_agent import decision_projection as dp
    from semantic_runtime.legal_agent import output_contract as oc, navigation_tasks as tasks
    frame = progress['action_chain']['frames'][progress['action_chain']['current_frame']]
    data, actions = deepcopy(frame['data']), deepcopy(frame['actions'])
    original_actions_hash = digest(actions)
    # Keep the exact last attempted source page, including structural minimum.
    for field in ('issues','presentation_id','state_version','current_request','connection_review',
                  'navigation_review_tasks','input_mode','sources','review_structural_context'):
        if field in stored: data[field] = deepcopy(stored[field])
    for field in ('completion_contract','control_contract'):
        data[field] = deepcopy(progress[field])
    captured, events = {}, []
    class Captured(Exception): pass
    def invoke(system, payload, schema, phase, timeout, **kwargs):
        require(kwargs == {'preview_only':True}, 'preflight attempted a physical call')
        captured.update(system=system, payload=deepcopy(payload), schema=deepcopy(schema), stage=phase)
        raise Captured()
    def bounded(repo, owner, payload, schema, invoke, expand, **kwargs):
        invoke(payload, 0, preview_only=True)
        raise AssertionError('capture failed to stop at preview')
    scope = set(binding['external_authorization']['scope_document_ids'])
    session = NS(profile=profile, scope=scope,
        context=NS(request={'question':stored['request']}, query={'generation_id':binding['generation_id']}),
        matcher=NS(unit_fulltext=NS(manifest={'index_sha256':binding['index_sha256']})),
        repo=NS(event=lambda kind,payload:events.append({'kind':kind,'payload':deepcopy(payload)}),
                budget=lambda:deepcopy(budget)))
    inv = NS(modern=True, completion=True, control=True, policy=profile['candidate_navigation'],
        p=deepcopy(progress), question=stored['request'], save=lambda:None, left=lambda:180,
        invoke=invoke, s=session, _review_full_view=deepcopy(frame['data']))
    # This state was recorded before task-local navigation existed. Start at
    # the deterministic source/catalogue task, without selecting a legal rule.
    inv.p.setdefault('navigation_review_tasks', {}).pop('task_frame', None)
    data, visible_actions = tasks.project(inv, data, actions)
    saved_rows = deepcopy(stored.get('read_candidates', []))
    previous_rows, previous_bounded = dp.read_candidate_rows, oc.bounded_decision
    try:
        dp.read_candidate_rows = lambda data,candidates,*args: [deepcopy(r) for r in saved_rows if r['target'] in candidates]
        oc.bounded_decision = bounded
        try:
            dp.choose_read(inv, data, visible_actions, stored['source_stage'].removesuffix('-read-choice'))
        except Captured:
            pass
    finally:
        dp.read_candidate_rows, oc.bounded_decision = previous_rows, previous_bounded
    require(bool(captured), 'choice compiler did not reach preview')
    require(digest(actions) == original_actions_hash, 'task projection altered full action registry')
    require(captured['payload'].get('sources') == stored.get('sources'), 'first task changed current originals')
    captured.update(events=events, all_actions_hash=original_actions_hash,
        all_action_count=len(actions), visible_action_count=len(visible_actions),
        task=data['task_navigation']['task'])
    return captured


def replay(cell, code, output_dir):
    from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
    from semantic_runtime.legal_agent import catalogue_input, input_modes
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences, expand_cards
    from semantic_runtime.legal_agent.gateway import compact_wire_view
    from semantic_runtime.legal_agent.repository import encoded
    journal, = cell.glob('runtime/legal-agent/runs/*/*/journal.sqlite')
    source_paths = [journal, cell/'runtime/case-memory/cases-v4.sqlite',
                    cell/'effective-profile.json', cell/'model/call-001-service/request.json']
    # Completed historical SQLite stores may retain committed WAL bytes.
    # Bind them as inputs; never checkpoint or modify historical records.
    source_paths += [Path(str(p)+'-wal') for p in source_paths[:2]
                     if Path(str(p)+'-wal').exists()]
    source_inputs = {str(p.relative_to(ROOT)):sha(p) for p in source_paths}
    with util.readonly(journal) as db, util.readonly(cell/'runtime/case-memory/cases-v4.sqlite') as case_db:
        event = db.execute("SELECT * FROM event WHERE kind='MODEL_INPUT_PREPARED' AND json_extract(payload_json,'$.status')='EXCEEDED' AND json_extract(payload_json,'$.input_mode') IN ('CATALOGUE','REVIEW') ORDER BY seq DESC LIMIT 1").fetchone()
        require(event is not None, 'saved final input failure missing')
        recorded = json.loads(event['payload_json'])
        row = db.execute('SELECT * FROM model_view WHERE view_id=?',(recorded['view_id'],)).fetchone()
        stored = json.loads(row['body_json'])
        require(digest(stored) == row['body_hash'], 'saved view hash mismatch')
        run, budget = dict(db.execute('SELECT * FROM run').fetchone()), dict(db.execute('SELECT * FROM budget').fetchone())
        binding = json.loads(run['binding_json'])
        require(digest(binding) == run['binding_hash'], 'saved native binding mismatch')
        checkpoint = case_db.execute('SELECT payload,hash FROM stage_progress').fetchone()
        if checkpoint:
            progress = json.loads(checkpoint['payload'])
            require(digest(progress) == checkpoint['hash'], 'checkpoint hash mismatch')
            progress_origin = 'stage_progress'
        else:
            checkpoint = case_db.execute("SELECT payload,hash FROM node WHERE stage='SELECT' ORDER BY revision DESC LIMIT 1").fetchone()
            require(checkpoint is not None, 'completed case lacks SELECT artifact')
            selected = json.loads(checkpoint['payload'])
            require(digest(selected) == checkpoint['hash'], 'SELECT hash mismatch')
            progress = selected['investigation_state']; progress_origin = 'SELECT.investigation_state'
        profile = read(cell/'effective-profile.json')
        profile['candidate_navigation']['task_local_navigation'] = True
        captured = capture(stored, progress, profile, binding, budget)
        payload = captured['payload']
        for key in ('catalogue','domain_choice','concept_policy'):
            if key in stored: payload[key] = deepcopy(stored[key])
        payload, augmentation = catalogue_input.project(payload, captured['stage'], task_local=True)
        view = {**payload, **{k:stored[k] for k in ('input_projection','source_stage','budget_class',
            'view_id','phase','base_state_revision','evidence_revision','exact_evidence') if k in stored}}
        context = NS(binding=binding,binding_hash=run['binding_hash'],remaining=lambda:179)
        # Completed runs advanced after this unsent view. Reconstruct the
        # recorded presentation revision for the offline state briefing only.
        preview_run = {**run, 'state_revision':stored['base_state_revision'],
                       'evidence_revision':stored['evidence_revision']}
        repo = NS(db=util.SnapshotQueries(db,event['seq']),run=lambda:preview_run,budget=lambda:budget,
                  event=lambda *args:(_ for _ in ()).throw(AssertionError('offline gateway write')))
        transport = util.preview_transport(profile,binding,read(cell/'model/call-001-service/request.json'),code)
        gateway = _Gateway(repo,context,profile,{},transport,
            message_protocol=_Protocol(captured['schema']),system=captured['system'])
        native, minimal, reuse, inputs, aliases, cost = gateway.prepare_input('investigate',view,'BoundedSourceDecision',record=False)
        physical, measured = input_modes.measure(profile,'investigate',view,native,transport.preview_request)
        wire = json.loads(next(m['content'] for m in native['messages'] if m['role']=='user'))['view']
        compact = compact_wire_view(NavigationReferences(view).view(view),'investigate')
        if inputs is not None:
            restored = inputs.verify(compact,wire)
            require(expand_cards(restored) == expand_cards(compact), 'wire content restoration mismatch')
        raw = encoded(physical).encode()
        require(source_inputs == {str(p.relative_to(ROOT)):sha(p) for p in source_paths},
                'historical replay inputs changed')
        output_dir.mkdir(parents=True,exist_ok=True)
        (output_dir/(cell.name+'.json.gz')).write_bytes(gzip.compress(raw,mtime=0))
        return {'cell':cell.name,'checkpoint_source':progress_origin,
            'saved_view_sha256':row['body_hash'],'source_journal_sha256':sha(journal),
            'source_inputs':source_inputs,
            'recorded_prepared':recorded,'candidate_prepared':measured,
            'task':captured['task'],'server_action_count':captured['all_action_count'],
            'server_actions_sha256':captured['all_actions_hash'],'visible_action_count':captured['visible_action_count'],
            'current_originals_exact':True,'candidate_request_sha256':hashlib.sha256(raw).hexdigest(),
            'candidate_field_chars':{k:len(encoded(v)) for k,v in wire.items()},
            'projection_events':captured['events'],'augmentation':augmentation,'input_cost':cost,
            'original_request_reconstructed':False,'calls':0,'source_database_loads':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--code',type=Path,default=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1065/task-local-r1/snapshot')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); code=util.load_code(args.code)
    require(args.output.resolve().is_relative_to(ART.resolve()), 'output outside new ADR')
    require(not args.output.exists(), 'replay output already exists')
    before=util.code_files(code); helper_hash=sha(HELPER)
    tool_paths = [Path(__file__).resolve(), Path(__file__).with_name('common.py').resolve(), HELPER]
    tool_files = {str(p.relative_to(ROOT)):sha(p) for p in tool_paths}
    order=read(ART/'implementation-plan.json')['execution_order']
    rows=[]
    for item in order:
        cell=MATRIX/f"{item['ordinal']:03d}-{item['case_id']}-{item['arm']}"
        result=replay(cell,code,args.output.parent/(args.output.stem+'-requests'))
        rows.append(result)
        print(cell.name,result['recorded_prepared']['measured_chars'],'->',
            result['candidate_prepared']['measured_chars'],result['candidate_prepared']['status'],flush=True)
    require(util.code_files(code)==before,'candidate changed during input replay')
    require(sha(HELPER)==helper_hash,'read-only helper changed')
    require(tool_files == {str(p.relative_to(ROOT)):sha(p) for p in tool_paths}, 'preview tools changed')
    save(args.output,{'schema_version':'task-local-saved-failure-preview-v1','code_root':str(code.relative_to(ROOT)),
        'files':before,'helper_path':str(HELPER.relative_to(ROOT)),'helper_sha256':helper_hash,
        'tool_files':tool_files,
        'calls':0,'source_database_loads':0,'original_wire_reconstruction_claimed':False,
        'state_note':'Old final checkpoint and exact last attempted source page recompiled as a new task; briefing uses recorded failed-view revisions and fixed179s preview time, final recorded budget. No model/decision/tool execution.',
        'all_within_mode_budget':all(x['candidate_prepared']['status']=='WITHIN_BUDGET' for x in rows),'cells':rows})
    return 0 if all(x['candidate_prepared']['status']=='WITHIN_BUDGET' for x in rows) else 2


if __name__=='__main__':raise SystemExit(main())

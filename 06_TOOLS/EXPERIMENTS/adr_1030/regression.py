from common import *
import subprocess,sys
c=ROOT/read(ART/'stage.json')['roots']['candidate']
names=['answer_progress','answer_progress_api','goal_bound_navigation','goal_verdict_handoff','assessment_goal_binding','first_required_read','scope_first_grounded_navigation','connection_cycle_guard','retained_partial_connections','unattempted_gap_finish','truncated_review_source_reply']
with (ART/'contracts-final.log').open('x') as stream:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('run_contracts.py')),'-q',*[str(c/'05_TESTS/CONTRACTS'/('test_'+n+'.py')) for n in names]],stdout=stream,stderr=subprocess.STDOUT)
raise SystemExit(r.returncode)

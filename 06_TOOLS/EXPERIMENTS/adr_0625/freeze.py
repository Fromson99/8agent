"""Freeze revision, callable entrypoint and all pre-run inputs."""
import json,subprocess
from pathlib import Path
from run import ROOT,ADR,DESIGN,read,put,sha

def main():
    candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0625/exact-anchor'
    subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','refresh',str(candidate)],cwd=ROOT,check=True)
    subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(candidate)],cwd=ROOT,check=True)
    cm=read(candidate/'candidate.json');revision=cm['revisions'][-1]
    m=read(ADR/'실험/manifest.json');assert m['results']['status']=='not_run'
    m['design']['code_isolation']['candidates']=[{'candidate_id':'exact-anchor','experiment_id':m['experiment_id'],'arm_id':'exact-anchor','run_ids':['run-001'],
        'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),
        'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
        'runner_path':'06_TOOLS/EXPERIMENTS/adr_0625/run.py','runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0625/run.py')}]
    m['design']['contract_cases']=['required-direct-conditions-read','narrow-question-focus','required-budget-pending','missing-coordinate-pending','local-enumeration','ordinary-link-optional','inaccessible-condition-pending','incoming-group','verified-witness','chosen-paragraph-only','skip-no-read','defer-pending','scope-without-links','forged-witness','closed-scope','skip-read-denied','decision-coverage','duplicate-denied','empty-schema','many-edges-one-group','shared-assess-compose-confirm-two-wikis-reuse','compact-menu-columns','omission-summary-pending','one-redecision','invalid-redecision-stop']
    for name in ('06_TOOLS/EXPERIMENTS/adr_0625/run.py','06_TOOLS/EXPERIMENTS/adr_0625/contracts.py','06_TOOLS/EXPERIMENTS/adr_0625/package.py','05_TESTS/CONTRACTS/test_compact_reference_menu_repair.py','05_TESTS/CONTRACTS/test_batch_reference_navigation.py','05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py','05_TESTS/CONTRACTS/test_unit_read_canonical_boundaries.py','05_TESTS/CONTRACTS/test_exact_anchor_delegation_read.py'):
        m['design']['frozen_inputs'][name]=sha(ROOT/name)
    put(ADR/'실험/manifest.json',m)
    put(ADR/'artifacts/pre-run-freeze.json',{'criteria_frozen':True,'implementation_frozen':True,'baseline_exact_parent':m['lineage']['parents'][0],'candidate_revision':revision['revision_sha256'],'model_calls_before_freeze':0})
if __name__=='__main__':main()

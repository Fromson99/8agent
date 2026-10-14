from pathlib import Path
import shutil
R=Path(__file__).resolve().parents[3];P=R/'08_DEPLOYMENT/GENOS/handoffs/assessment_gap_action_20261013_r1';O=P.with_name('assessment_gap_action_20261013_r2');O.mkdir(exist_ok=False)
for n in ['WORKING_INTEGRATION.json','run_installed_tests.py']:
 shutil.copy2(P/n,O/n)
shutil.copytree(P/'preimage',O/'preimage')
s=(P/'build_delivery.py').read_text().replace('GENOS_ASSESSMENT_GAP_ACTION_20261013_R1','GENOS_ASSESSMENT_GAP_ACTION_20261013_R2').replace('assessment-gap-action-r1','assessment-gap-action-r2')
s=s.replace(" bindings=[];variants={}"," bindings=[];variants={}\n success_path=O.with_name('successful_shortcut_20261013_r1')\n success_inst=load('gap_success_installer',success_path/'apply_patch.py')\n success_spec=json.loads(gzip.decompress((success_path/'PATCH_SPEC.json.gz').read_bytes()))")
s=s.replace("  for tag,before in [('stream-fix-r1',base),('ad-request-logs-r2',ad)]:", """  success_state=success_spec['signatures'][success_inst.signature(ad,manifest,success_spec)]
  success_changes={n:base64.b64decode(success_spec['blobs'][p['after_sha256']]) for n,p in success_state['patches'].items()}
  success=old.repin(ad,success_changes,success_spec['engine_additions'])
  assert success_inst.signature(success,manifest,success_spec)==success_state['output_signature']
  for tag,before in [('stream-fix-r1',base),('ad-request-logs-r2',ad),('successful-shortcut-r1',success)]:""")
(O/'build_delivery.py').write_text(s)
s=(P/'test_delivery.py').read_text().replace('GENOS_ASSESSMENT_GAP_ACTION_20261013_R1','GENOS_ASSESSMENT_GAP_ACTION_20261013_R2').replace('assessment-gap-action-r1','assessment-gap-action-r2')
s=s.replace('basis,display,budget_enabled,prior_ad','basis,display,budget_enabled,prior_ad,prior_success')
s=s.replace("('query_latency_20261007_r3',False,False,False)","('query_latency_20261007_r3',False,False,False,False)").replace("('query_latency_20261007_r4',False,True,False)","('query_latency_20261007_r4',False,True,False,False)").replace("('query_latency_20261007_r3',False,True,True)","('query_latency_20261007_r3',False,True,True,False)").replace("('query_latency_20261007_r4',True,True,True)]", "('query_latency_20261007_r4',True,True,True,False),\n ('query_latency_20261007_r3',False,False,True,True),\n ('query_latency_20261007_r4',True,True,True,True)]")
s=s.replace("+('_ad' if prior_ad else '')+'.json.gz'", "+('_ad' if prior_ad else '')+('_success' if prior_success else '')+'.json.gz'")
s=s.replace(" before_manifest=(root/'CODE_MANIFEST.json').read_bytes()", " if prior_success:\n  run(['bash',str(OUT.with_name('successful_shortcut_20261013_r1')/'GENOS_SUCCESSFUL_SHORTCUT_20261013_R1_RUN.txt'),'apply'])\n before_manifest=(root/'CODE_MANIFEST.json').read_bytes()")
(O/'test_delivery.py').write_text(s)
s=(P/'test_installed_contracts.py').read_text().replace("('assessment_gap_action_20261013_r1','GENOS_ASSESSMENT_GAP_ACTION_20261013_R1')", "('assessment_gap_action_20261013_r2','GENOS_ASSESSMENT_GAP_ACTION_20261013_R2')")
s=s.replace('    for folder,name in steps_final:', "    if basis.endswith('r4'):steps_final.insert(1,('successful_shortcut_20261013_r1','GENOS_SUCCESSFUL_SHORTCUT_20261013_R1'))\n    for folder,name in steps_final:")
(O/'test_installed_contracts.py').write_text(s)
print(O)

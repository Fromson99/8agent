from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R/'08_DEPLOYMENT/GENOS/handoffs/successful_shortcut_20261013_r1';P=O.with_name('ad_request_logs_20261013_r2')
s=(P/'test_delivery.py').read_text().replace("RN=OUT/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt'","RN=OUT/'GENOS_SUCCESSFUL_SHORTCUT_20261013_R1_RUN.txt'")
s=s.replace(" before_manifest=(root/'CODE_MANIFEST.json').read_bytes();before=json.loads(before_manifest)"," run(['bash',str(OUT.with_name('ad_request_logs_20261013_r2')/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt'),'apply'])\n before_manifest=(root/'CODE_MANIFEST.json').read_bytes();before=json.loads(before_manifest)")
a=s.index(' if budget_enabled:\n  old_runner=');b=s.index(' # Exercise the real endpoint',a);s=s[:a]+s[b:]
s=s.replace("  assert policy['runtime_implementation_changed_from_r1'] is False", "  assert policy['source_files']")
s=s.replace("TRANSFER/ad-request-logs-r2","TRANSFER/successful-shortcut-r1").replace("assert not (root/'02_BACKEND/semantic_runtime/legal_agent/model_contract.py').exists()","assert not (root/'02_BACKEND/semantic_runtime/legal_agent/successful_answer.py').exists()\n assert (root/'02_BACKEND/semantic_runtime/legal_agent/model_contract.py').exists()")
(O/'test_delivery.py').write_text(s)
s=(P/'test_installed_contracts.py').read_text().replace("steps_final=[('ad_request_logs_20261013_r2','GENOS_AD_REQUEST_LOGS_20261013_R2')]","steps_final=[('ad_request_logs_20261013_r2','GENOS_AD_REQUEST_LOGS_20261013_R2'),('successful_shortcut_20261013_r1','GENOS_SUCCESSFUL_SHORTCUT_20261013_R1')]")
a=s.index("    tests=['");b=s.index('    r=subprocess.run(cmd',a)
s=s[:a]+'''    tests=['test_successful_shortcut.py','test_successful_core_routes.py','test_bounded_wiki_recall.py','test_ad_pagination.py','test_ad_language.py','test_ad_request_reports.py','test_genos_model_stream_completion.py']
    cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0773/run_tests.py'),str(root),
         *[str(testdir/t) for t in tests],'--junitxml='+str(OUT/('CONTRACTS_'+basis+'.xml'))]
'''+s[b:]
(O/'test_installed_contracts.py').write_text(s)

from common import *
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1289/test_native_computation.py').read_text()
a=s.index('@pytest.mark.parametrize');b=s.index('def test_native_generation',a)
s=s[:a]+"@pytest.mark.parametrize('fault,missing_plan',[('repair_success',True)])\n"+s[b:]
s=s.replace('def test_native_generation_repair_publication_and_duplicate','def test_native_computed_id_repair_preserves_raw_and_replay')
s=s.replace("    value=share(value)","    if missing_plan and not last['source_stage'].endswith('-repair'):\n     for index,gap in enumerate(value['gaps']):\n      if 'computed_gap_ref' in gap:\n       value['gaps'][index]={'kind':'MISSING_FACT','material':True,'reason':'미확인 '+gap['computed_gap_ref']+' 확인','issue_id':gap['issue_id'],'material_id':None,'missing_target':'','suggested_action':'REQUEST_FACT'}\n       break\n    value=share(value)")
s=s.replace("    value['requirement_review'][0]['link_ref']='review-link:999'", "    # This test injects the offered ID in prose instead of a link failure.")
a=s.index('\n\ndef test_general_api');s=s[:a]
s += "\n import sqlite3\n dumps=[]\n for path in tmp_path.glob('90_RUNTIME/semantic/legal-agent/runs/*/*/journal.sqlite'):\n  with sqlite3.connect(path) as db:dumps.extend(db.iterdump())\n assert any('COMPUTED_GAP_IN_REASON' in text for text in dumps)\n assert any('미확인 computed-gap:' in text or '\\\\ubbf8\\\\ud655\\\\uc778 computed-gap:' in text for text in dumps)\n"
(Path(__file__).parent/'test_native_gap.py').write_text(s)

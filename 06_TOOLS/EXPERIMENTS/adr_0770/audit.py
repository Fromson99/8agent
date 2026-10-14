"""Frozen transport-only paired boundary audit; no inference or semantic regrading."""
from pathlib import Path
import ast, hashlib, itertools, json, subprocess, sys, xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0770-token-answer-stream';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root'];base=R/b['manifest']['code_root']
assert not (O/'result.json').exists();O.mkdir(exist_ok=True)
for n,h in f['files'].items():assert sha(R/n)==h,n
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent.narrative_answer import TokenStream,ParagraphStream
p='02_BACKEND/semantic_runtime/legal_agent/narrative_answer.py'
def ast_base(path):
 t=ast.parse(path.read_text());t.body=[n for n in t.body if not(isinstance(n,ast.ClassDef) and n.name=='TokenStream')];return ast.dump(t)
assert ast_base(code/p)==ast_base(base/p),'Prompts/schema/validation/final rendering changed'
allowed={'answer_stream.py','narrative_answer.py','gateway.py','unified_runtime.py'}
for n in b['manifest']['files']:
 if n.startswith('02_BACKEND/semantic_runtime/') and Path(n).name not in allowed:assert sha(code/n)==sha(base/n),n
 if n.startswith('00_SYSTEM/LEGAL_AGENT/'):assert sha(code/n)==sha(base/n),n
rows=[];matrix=read(D/'criteria.json')['matrix']
for index,(width,ascii_mode,text) in enumerate(itertools.product(matrix['widths'],matrix['unicode_modes'],matrix['texts']),1):
 raw=json.dumps({'paragraphs':[{'claim_ids':['C1'],'text':text}]},ensure_ascii=ascii_mode,separators=(',',':'))
 content=raw[:-4] # Remove closing quote, object, array, envelope; text has not closed.
 assert raw[-4:]=='"}]}'
 sinks={name:[] for name in ('baseline','token')};stream={'baseline':ParagraphStream(sinks['baseline'].append,['C1']),'token':TokenStream(sinks['token'].append,['C1'])}
 first={}
 for part_index,at in enumerate(range(0,len(content),width)):
  for name,s in stream.items():
   s.feed(content[at:at+width])
   if sinks[name] and name not in first:first[name]=part_index
 partial={k:''.join(v) for k,v in sinks.items()}
 assert not partial['baseline'] and partial['token']==text
 for s in stream.values():s.feed(raw[-4:])
 assert ''.join(sinks['baseline'])==''.join(sinks['token'])==text
 rows.append({'id':f'T{index:02}','width':width,'escaped_unicode':ascii_mode,'input_sha256':hashlib.sha256(raw.encode()).hexdigest(),'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'baseline_before_close':False,'token_before_close':True,'canonical_answer_equal':True,'first_fragment':first,'token_delta_count':len(sinks['token'])})
put(O/'paired-boundaries.json',rows)
tests=[str(code/'05_TESTS/CONTRACTS/test_token_answer_stream.py')]+['05_TESTS/CONTRACTS/'+n for n in ('test_narrative_answer.py','test_genos_answer_stream.py','test_ad_language.py','test_ad_table_context.py','test_bounded_wiki_recall.py')]
cmd=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0770/run_tests.py'),str(code),*tests,'--junitxml='+str(O/'contracts.xml')]
with (O/'contracts.log').open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT)
cases=list(ET.parse(O/'contracts.xml').iter('testcase'));assert r.returncode==0 and len(cases)==142
assert not any(t.find(k) is not None for t in cases for k in ('failure','error','skipped'))
checks={'paired40_token_before_paragraph_close':len(rows)==40,'canonical_answers_identical':all(x['canonical_answer_equal'] for x in rows),'142_contracts_pass':True,'prompt_schema_render_unchanged':True,'retrieval_shortcut_AD_profile_unchanged':True,'no_real_model_calls':True,'source_generation_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'frozen_files_unchanged':all(sha(R/n)==h for n,h in f['files'].items()),'same297_serving_files':all(sha(code/n)==h for n,h in f['serving_files'].items())}
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':{'baseline':{'status':'complete','paired_cases':40,'immediate_before_close':0,'identical_final_text':40},'token':{'status':'complete','paired_cases':40,'immediate_before_close':40,'identical_final_text':40}},'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},'contracts_passed':len(cases),'inference_latency':'Not measured; deterministic delivery order only','limitations':['A provider delta may contain multiple tokens; no artificial splitting or paragraph buffering.','Whitespace/escape prefixes without a decoded display character produce no visible token.','External public transport buffered; GENOS internal native stream tested using synthetic transport.','Claim IDs must precede partial text; invalid or missing metadata fails closed.','Actual field model, proxy buffering and browser rendering unverified.','DEV installation, local MAIN selection and actual service binding recorded separately.']}
assert result['strict_success'];put(O/'result.json',result);print(json.dumps(result,ensure_ascii=False))

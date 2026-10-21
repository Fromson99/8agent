"""Execute the pinned source renderer against a minimal DOM, including hostile text."""
from pathlib import Path
import ast,json,subprocess,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0798-workflow-handoff-scoped-question'
f=json.loads((A/'artifacts/design/freeze.json').read_text());p=R/f['code_root']/'02_BACKEND/semantic_runtime/legal_agent/source_tiers_ui.py'
tree=ast.parse(p.read_text());script=ast.literal_eval(tree.body[1].value)
fixture={'schema_version':'workflow-source-v1','bundle_hash':'bound','sources':[
 {'selection_id':'E1','document_name':'내규','coordinate_label':'제1조','side':'internal','excerpt':'<script>alert(1)</script>'},
 {'selection_id':'E2','document_name':'외규','coordinate_label':'제2조','side':'external','excerpt':'원칙. 다만 예외.'}]}
js="""const assert=require('node:assert/strict');
class Element {constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.textContent='';}
 append(n){this.children.push(n)} replaceChildren(){this.children=[]}
 set innerHTML(v){throw Error('HTML execution forbidden')}}
const root=new Element('div');const document={getElementById:()=>root,createElement:tag=>new Element(tag)};
"""+script+'\nconst fixture='+json.dumps(fixture,ensure_ascii=False)+""";
renderSourceTiers(fixture);assert.equal(root.children.length,2);assert.equal(root.dataset.bundleHash,'bound');
assert.equal(root.children[0].children[2].textContent,fixture.sources[0].excerpt);
assert.equal(root.children[1].children[2].textContent,fixture.sources[1].excerpt);
renderSourceTiers({...fixture,sources:fixture.sources.slice(1)});assert.equal(root.children.length,1);
console.log(JSON.stringify({status:'PASS',checks:4}));
"""
raw=subprocess.check_output(['node','-'],input=js,text=True);out=json.loads(raw)
out.update(script_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),code_root=f['code_root'])
(A/'artifacts/ui-check.json').write_text(json.dumps(out,indent=2)+'\n');print(raw.strip())

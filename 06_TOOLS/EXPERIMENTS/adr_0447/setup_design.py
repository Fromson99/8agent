from pathlib import Path
import json,hashlib,copy
from lawrag.core.structure import pipeline,recipe_template,recipe_regions,viewer,recipe_basic
from lawrag.core.structure.model import Block
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0446-korean-legal-tool-routing/artifacts'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def new(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
rows=read(P/'dataset/synthetic-sources.json');cases=read(P/'dataset/product-cases.json');gold=read(P/'grading/gold.json');nodes_by_doc={};blocks_by_doc={};receipts=[]
for s in rows:
 did=s['document_id'];raw=[b['text'] for b in s['blocks']]
 if s['id']=='article:ko-article':raw=[x for x in raw[0].replace(' ①','\n①').replace(' ②','\n②').splitlines() if x]
 if s['id']=='article:ko-collision':raw=['부칙',raw[0].removeprefix('부칙 ')]
 blocks=[Block(i,t) for i,t in enumerate(raw)];template=copy.deepcopy(recipe_basic.default_template())
 # A distinct appendix region grammar, not a RAG heuristic.
 if s['id']=='article:ko-collision':template['heading_rules']['kr_article']['parent_family']='buchik'
 template=recipe_template.compile_recipe(template['heading_rules'],{k:{} for k in template['heading_rules']})
 recipe={'tag':recipe_regions.VERSION,'version':1,'source_block_count':len(blocks),'regions':[{'start_block':0,'end_block':len(blocks),'template_id':'selected','label':'synthetic region','reason':'predeclared synthetic numbering grammar'}],'templates':{'selected':template}}
 result=recipe_regions.build(pipeline,blocks,recipe);flat=[];viewer._flat_tree(result.tree,flat)
 assert any(n['family']=='kr_article' for n in flat),(s['id'],flat)
 out=nodes_by_doc.setdefault(did,[]);bidbase=blocks_by_doc.get(did,0);idbase=len(out)
 for n in flat:
  n['id']+=idbase
  if n['parent'] is not None:n['parent']+=idbase
  n['block']+=bidbase;n['span']=[n['span'][0]+bidbase,n['span'][1]+bidbase]
 out.extend(flat);blocks_by_doc[did]=bidbase+len(blocks)
 root=next(n for n in flat if n['family']=='kr_article');s['unit_id']=str(root['id']);s['article_coordinate']={'doc_id':did,'node':root['id']}
 actual=blocks[1:] if s['id']=='article:ko-collision' else blocks
 s['blocks']=[{'block_id':str(bidbase+b.idx),'text':b.text} for b in actual];s['block_id']=s['blocks'][0]['block_id'];s['text']='\n'.join(b['text'] for b in s['blocks']);s['text_sha256']=hashlib.sha256(s['text'].encode()).hexdigest()
 receipts.append({'source_id':s['id'],'document_id':did,'recipe':recipe,'structure_node_ids':[n['id'] for n in flat],'source_block_offset':bidbase,'template_issues':result.stats.get('template_issues',[])})
for did,nodes in nodes_by_doc.items():viewer.annotate_coordinate_scopes(nodes,document_kind='law')
for g in gold['cases']:
 if g['required_source_ids']:g['source_text']='\n\n'.join(s['text'] for s in rows if s['id'] in g['required_source_ids'])
new(A/'dataset/synthetic-sources.json',rows);new(A/'dataset/structure-units.json',nodes_by_doc);new(A/'dataset/structure-build-receipts.json',receipts);new(A/'dataset/product-cases.json',cases);new(A/'grading/gold.json',gold);new(A/'source-inventory.json',{'sources':rows});new(A/'authorization.json',{'authorized':True,'source_scope':'synthetic only','provider':'gemini','model':'gemini-3.1-flash-lite','private_or_real_corpus_sent':False,'user_steering':'조문은 구조화 틀의 값으로 판별; ID 선택 문제 보완','max_product_calls':384,'max_judge_calls':12})
m=read(D/'실험/manifest.json');h='Stored template-derived coordinates and opaque executable source handles replace heading regex/ID construction; scoped empty LIST recovery moves from prerequisite document to actual matching evidence.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,primary_metric='grounded complete answer + exact required-source adoption + explicit search/read order compliance',success_criteria={'bound_pass_min':11,'total':12,'recovery_required':True,'baseline_only_regressions_max':0,'invalid_quotes_max':0,'scope_escapes_max':0,'structure_contract_required':True},failure_criteria='Any failed criterion keeps Proposed; no MAIN.',criteria_frozen_before_run=True,limits=read(P/'design-before-snapshot.json')['design']['limits'],implementation_scope='Replace FIND_ARTICLE body regex with stored source_unit legal_coordinate/coordinate_scope/key and parent/family/ordinal. Use ingestion shared coordinate parser only for query and stored labels. Bind opaque read handles to source IDs. Carry all raw structure metadata in adapter. Empty LIST suggests relaxed optional document scope and executable source read actions. Parent Korean search preserved.',controls='Same new template-built synthetic generation, same12questions/model/budget/downstream; old and new both receive identical structures.',order='Alternate baseline/bound and anonymous X/Y positions',synthetic_notice='12 known developer cases, new structure generation built by existing numbering template engine; no independent holdout.',source_build='Existing recipe_regions.build + compiled basic numbering templates + viewer._flat_tree/annotate_coordinate_scopes; block/node IDs generated before queries, no answer-driven mapping.')
for arm in m['design']['arms']:
 arm['changes']='unchanged ADR0446 legal frozen code' if arm['id']=='baseline' else h;arm['controls']='same template-built source generation, queries, model and budgets'
stages=read(P/'pre-call-manifest.json')['design']['retrieval_stage_plan']['stages_by_arm']['legal'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','bound']};m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
m['dataset'].update(name='Template-built synthetic legal12',version='synthetic-447-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)),sha256=sha(A/'dataset/product-cases.json'),legal_version_checked=True,reference_version_checked=True,version_note='Synthetic source version/coordinates verified; no actual law assertion')
m['runs'][0].update(selection_rule='Same12known cases once per arm, identical new template-derived structure generation',artifact_path=str((A/'results.json').relative_to(R)))
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');new(A/'design-before-snapshot.json',m)
print('Template-derived structures:',{d:len(v) for d,v in nodes_by_doc.items()})

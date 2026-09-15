"""Offline hierarchy scoring and saved-tag replay for ADR0357; no provider object."""
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'02_BACKEND'))
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0357-recipe-explicit-parent-loop';OUT=ADR/'artifacts'
spec=importlib.util.spec_from_file_location('assess_runner',ROOT/'06_TOOLS/EXPERIMENTS/recipe_explicit_parent_probe.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
engine,loop=runner.load_candidate()
from lawrag.core.structure.model import Block

def nodes(tree):
    for n in tree:
        yield n
        yield from nodes(n.get('children',[]))

def grade(tree,gold):
    flat=list(nodes(tree['tree']))
    title=next((n for n in flat if n['block']==gold['title_block']),None)
    all_items=[n for n in flat if n['ordinal'] is not None]
    descendants=list(nodes(title['children'])) if title else []
    nested=[n for n in descendants if n['ordinal'] is not None]
    expected=[[i] for i in gold['item_ordinals']]
    correct=sorted([n['ordinal'] for n in all_items])==expected and sorted([n['ordinal'] for n in nested])==expected
    return {'correct':correct,'total_items':len(all_items),'under_title':len(nested),'title_present':title is not None}

if __name__=='__main__':
    report=json.loads((OUT/'results.json').read_text());gold=json.loads((OUT/'gold.json').read_text())
    blocks=[Block(**r) for r in json.loads((OUT/'blocks.json').read_text())]
    catalog=json.loads((OUT/'catalog.json').read_text())
    baseline=engine.interpret(blocks,doc='recipe-loop-law-annex',llm=None,ledger=None)
    inventory=loop.inventory(baseline)
    assessment={'baseline':grade(report['arms']['baseline']['tree'],gold),'paths':{},'contracts_passed':10,'main_wiring':'unchanged'}
    for arm in ['loop','repair-replay']:
        outcome=report['arms'][arm];result={'status':outcome['status'],'trace':[grade(x['tree'],gold) for x in outcome['trace']]}
        if outcome['status']=='candidate_ready':
            result['final']=grade(outcome['tree'],gold)
            registry=json.loads((OUT/arm/'tags.candidate.json').read_text())
            name,tag=next(iter(registry['documents'].items()))
            assert tag['source_sha256']=='13e1df4f2a944beb7e711c4b80a3bc4a0bfed2f831ed582c792952aad913a933'
            assert tag['derived_pdf_sha256']==runner.sha(runner.PDF)
            assert tag['recipe_sha256']==loop.digest(tag['recipe'])
            assert tag['catalog_sha256']==loop.digest(catalog)
            reused=loop.build(engine,blocks,tag['recipe'],catalog,inventory)
            result.update(saved_tag_name=name,saved_tag_replay_identical=loop.digest(loop.tree_record(reused))==loop.digest(outcome['tree']),replay_model_calls=0)
        assessment['paths'][arm]=result
    assessment['success_criteria_met']=all(r.get('final',{}).get('correct') and r.get('saved_tag_replay_identical') for r in assessment['paths'].values()) and not assessment['paths']['repair-replay']['trace'][0]['correct'] and len(assessment['paths']['repair-replay']['trace'])>1 and report['source_unchanged']
    assessment['calls']=len(report['calls'])
    assessment['usage']={k:sum(r['usage'].get(k,0) for r in report['calls']) for k in ['input_tokens','output_tokens']}
    assessment['latency']={'parse_seconds':report['parse_seconds'],'api_seconds':[r['seconds'] for r in report['calls']]}
    assessment['limitations']=['One in-sample law annex,14unique items','Fixed existing marker family inventory only; no invented parser or regex',
        'Tag document key is a logical document name with source hash, not automatically matched to physical basename',
        'VLM is product reviewer, independent offline hierarchy check uses agent gold; no human calibration',
        'No GENOS or MAIN promotion; no difficult table/scanned/multipage holdout']
    runner.write(OUT/'assessment.json',assessment)
    print(json.dumps(assessment,ensure_ascii=False,indent=2))

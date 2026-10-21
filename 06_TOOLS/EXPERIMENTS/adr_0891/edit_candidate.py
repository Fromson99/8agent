from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0891/continuity/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=C/(name+'.py');s=p.read_text();assert s.count(old)==1,(name,old[:90],s.count(old));p.write_text(s.replace(old,new))
edit('law_navigation',"if self.modern or search_window or self.p.get('window')=='law':", "if search_window or self.p.get('window')=='law':")
edit('law_navigation',"if (search_window or self.modern) else []\n", "if search_window else []\n")
edit('completion_v6',"related=(f'/claims/{ci}/rule/norms/{ni}/source_ref',),", "related=(f'/claims/{ci}/rule/norms/{ni}/evidence_refs',),")
edit('definition_entry',"    if seed:\n        expected=digest", "    if seed:\n        check_navigation_origin(seed)\n        expected=digest")
edit('definition_entry',"        inv.p['system_definition_seed']=seed;inv.save()", """        if getattr(inv,'modern',False):
            origin={k:deepcopy(inv.p[k]) for k in NAVIGATION_KEYS if k in inv.p}
            seed.update(navigation_policy='restore-automatic-definition-v1',
                        navigation_origin=origin,navigation_origin_hash=digest(origin))
        inv.p['system_definition_seed']=seed;inv.save()""")
edit('definition_entry',"        except Exception as error:\n            # Preserve", "        except BaseException as error:\n            # Preserve")
edit('definition_entry',"            inv.save();raise\n        completed.append(target)", """            inv.save();raise
        finally:
            if restore_navigation_origin(inv,seed):inv.save()
        completed.append(target)""")
edit('definition_entry',"        acquired.extend(g for g in inv.p.get('window_groups',[]) if g not in acquired)\n        inv.p['window_groups']=list(acquired);inv.save()", """        if seed.get('navigation_policy')=='restore-automatic-definition-v1':
            if receipt['group_id'] not in acquired:acquired.append(receipt['group_id'])
        else:
            acquired.extend(g for g in inv.p.get('window_groups',[]) if g not in acquired)
            inv.p['window_groups']=list(acquired)
        inv.save()""")
with (C/'definition_entry.py').open('a') as f:f.write('''

NAVIGATION_KEYS = ('window','window_groups','focus','structure_location')


def check_navigation_origin(seed):
    policy=seed.get('navigation_policy')
    if policy is None:return
    origin=seed.get('navigation_origin')
    if (policy!='restore-automatic-definition-v1' or not isinstance(origin,dict)
            or set(origin)-set(NAVIGATION_KEYS)
            or digest(origin)!=seed.get('navigation_origin_hash')):
        raise ContractError('definition navigation origin changed')


def restore_navigation_origin(inv,seed):
    """Restore only automatic reading focus; acquired originals are permanent."""
    check_navigation_origin(seed)
    if not seed.get('navigation_policy'):return False
    origin=seed['navigation_origin']
    for name in NAVIGATION_KEYS:
        if name in origin:inv.p[name]=deepcopy(origin[name])
        else:inv.p.pop(name,None)
    return True
''')
for p in C.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Only automatic definition focus restored; broad frontier reverted; all original receipts and other fixes retained')

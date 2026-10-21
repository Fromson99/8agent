"""Bind legacy child coordinates through persisted ancestry; never rewrite source_unit."""
from collections import defaultdict
from copy import deepcopy
import threading
from . import structure_navigation as previous
from .team_scope import generation_key

_BOUND_CACHE={};_BOUND_LOCK=threading.Lock()


def bind_structure(matcher,store):
    bound=previous.bind_structure(matcher,store)
    key=generation_key(store)
    with _BOUND_LOCK:
        cached=_BOUND_CACHE.get(key)
        if cached is None:
            cached=_derive_bindings(bound.units)
            _BOUND_CACHE.clear()
            cached=_BOUND_CACHE.setdefault(key,cached)
    bound.units,bound.stored_coordinates=cached
    return bound


def _derive_bindings(shared_units):
    """Derived per generation: never mutate the shared validated units in place."""
    units={key:dict(unit) for key,unit in shared_units.items()}
    coordinates={key:previous.stored_coordinate(units,*key) for key in units}
    pending={}
    for key,unit in units.items():
        raw=unit['raw_structure'];scope=raw.get('coordinate_scope');ckey=raw.get('coordinate_key')
        if scope and ckey:
            unit['coordinate_binding']={'mode':'stored','unit_id':key[1],'coordinate_key':ckey}
            continue
        # Partial fields are not a license to silently overwrite existing identities.
        if scope or ckey:
            unit['coordinate_binding']={'mode':'unresolved','reason':'PARTIAL_STORED_SCOPE_KEY'}
            continue
        coord=coordinates[key]
        if not coord or coord.unit!='조' or not coord.chain:continue
        did,uid=key;parent=unit['parent'];path=[uid];anchor=None
        while parent is not None:
            ancestor=units[(did,parent)];path.append(parent);a_raw=ancestor['raw_structure'];base=coordinates[(did,parent)]
            if a_raw.get('coordinate_scope') or a_raw.get('coordinate_key'):
                if (a_raw.get('coordinate_scope') and a_raw.get('coordinate_key') and base and base.unit=='조'
                    and base.key()==coord.key() and coord.chain[:len(base.chain)]==base.chain
                    and len(coord.chain)>len(base.chain)):
                    anchor=(parent,ancestor)
                break
            parent=ancestor['parent']
        if not anchor:
            unit['coordinate_binding']={'mode':'unresolved','reason':'NO_COMPATIBLE_STORED_ANCESTOR'}
            continue
        aid,a=anchor;scope=a['raw_structure']['coordinate_scope'];ancestor_key=a['raw_structure']['coordinate_key']
        # Preserve non-body source identities (including repeated/annex) by retaining
        # the stored ancestor key and child node ID, not flattening them into body keys.
        ckey='body:'+coord.canonical_surface() if scope=='body' else ancestor_key+' > '+coord.canonical_surface()+':'+uid
        pending[key]={'legal_coordinate':coord.as_dict(),'coordinate_scope':scope,'coordinate_key':ckey,
                      'coordinate_binding':{'mode':'stored_ancestry','ancestor_unit_id':aid,'ancestor_coordinate_key':ancestor_key,
                                            'node_path':list(reversed(path)),'raw_unchanged':True}}
    # Two legacy children must not acquire the same body coordinate silently.
    # Stored records remain authoritative; only ambiguous derived bindings are withheld.
    identities=defaultdict(list)
    for key,u in units.items():
        candidate=pending.get(key,u)
        if candidate.get('coordinate_key'):identities[(key[0],candidate['coordinate_key'])].append(key)
    duplicate_keys={key for group in identities.values() if len(group)>1 for key in group}
    for key,fields in pending.items():
        if key in duplicate_keys:
            units[key]['coordinate_binding']={'mode':'unresolved','reason':'DUPLICATE_DERIVED_COORDINATE'}
        else:units[key].update(fields)
    return units,coordinates


class InheritedSession(previous.BoundSession):
    def structure_card(self,key):
        card=super().structure_card(key)
        return {**card,'coordinate_binding':deepcopy(self.m.units[self.structure_keys[key]].get('coordinate_binding'))}

    def find_article(self,*args,**kwargs):
        result=super().find_article(*args,**kwargs)
        for item in result.get('items',[]):
            match=item['structure_match'];u=self.m.units[(match['document_id'],match['unit_id'])]
            match['coordinate_binding']=deepcopy(u.get('coordinate_binding'))
        for unresolved in result.get('unresolved',[]):
            u=self.m.units[(unresolved['document_id'],unresolved['unit_id'])]
            if u.get('coordinate_binding'):unresolved['coordinate_binding']=deepcopy(u['coordinate_binding'])
        result['authority']='stored structure fields and explicitly recorded ancestry binding; raw source unchanged'
        return result


class InheritedAgent(previous.previous.RoutedAgent):
    session_type=InheritedSession

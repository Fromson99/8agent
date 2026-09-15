"""Parent-graph compiler shared with the document grammar. Instance editing removed."""
import copy
from collections import defaultdict

ROOT = '$document'


def levels_from_parents(parents, catalog):
    if set(parents) != set(catalog):
        raise ValueError('Parent map must contain every catalog family exactly once')
    grouped = defaultdict(list)
    def depth(family, path=()):
        if family in path: raise ValueError('Parent cycle: '+str(path+(family,)))
        parent = parents[family]
        if not isinstance(parent,str) or (parent != ROOT and parent not in catalog):
            raise ValueError('Unknown parent family: '+str(parent))
        return 0 if parent == ROOT else 1 + depth(parent,path+(family,))
    for family in catalog: grouped[depth(family)].append(family)
    if len(grouped)>16: raise ValueError('Parent depth exceeds recipe contract')
    return [grouped[k] for k in sorted(grouped)]


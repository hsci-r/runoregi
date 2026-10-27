from collections import namedtuple, OrderedDict
from operator import itemgetter

import config
from utils import render_type_links


TypeTreeLine = \
    namedtuple('TypeTreeLine', ['prefix', 'depth', 'type_id', 'is_minor'])


class Type:
    def __init__(self, id):
        self.id = id
        self.ancestors = None
        self.children = None
        self.description = None
        self.name = None


# represents a set of poetic types
class Types:
    def __init__(self, types=None, ids=None):
        if types is not None:
            self.c = OrderedDict((t.id, t) for t in types)
        elif ids is not None:
            self.c = OrderedDict()
            for type_id in ids:
                self.c[type_id] = Type(id=type_id)

    def __contains__(self, key):
        return key in self.c

    def __getitem__(self, key):
        return self.c[key]

    def __iter__(self):
        return self.c.__iter__()

    def __len__(self):
        return self.c.__len__()

    def items(self):
        return self.c.items()

    def values(self):
        return self.c.values()

    def get_ancestors(self, db, add=False):
        if not self: return    # empty set? -> do nothing
        # ignore if the table is not available
        if not config.TABLES['types']: return
        db.execute(
            'SELECT t1.type_orig_id, t2.type_orig_id, t3.type_orig_id, t4.type_orig_id '
            'FROM types t1'
            '  LEFT OUTER JOIN types t2 ON t1.par_id = t2.t_id '
            '  LEFT OUTER JOIN types t3 ON t2.par_id = t3.t_id '
            '  LEFT OUTER JOIN types t4 ON t3.par_id = t4.t_id '
            'WHERE t1.type_orig_id IN %s ;', (tuple(self),))
        for t_id in self:
            self[t_id].ancestors = []
        for t1_id, t2_id, t3_id, t4_id in db.fetchall():
            ids = [x for x in [t2_id, t3_id, t4_id] if x is not None]
            self[t1_id].ancestors.extend(ids)
            if add:
                for i, t_id in enumerate(ids):
                    if t_id not in self:
                        self.c[t_id] = Type(id=t_id)
                        self[t_id].ancestors = ids[i+1:]

    def get_descendents(self, db, add=False):
        if not self: return    # empty set? -> do nothing
        # ignore if the table is not available
        if not config.TABLES['types']: return
        db.execute(
            'SELECT t1.type_orig_id, t2.type_orig_id, t3.type_orig_id, t4.type_orig_id '
            'FROM types t1'
            '  LEFT OUTER JOIN types t2 ON t1.t_id = t2.par_id '
            '  LEFT OUTER JOIN types t3 ON t2.t_id = t3.par_id '
            '  LEFT OUTER JOIN types t4 ON t3.t_id = t4.par_id '
            'WHERE t1.type_orig_id IN %s ;', (tuple(self),))
        for t_id in self:
            if self[t_id].ancestors is None:
                self[t_id].ancestors = []
            self[t_id].descendents = []
        for t1_id, t2_id, t3_id, t4_id in db.fetchall():
            ids = [x for x in [t1_id, t2_id, t3_id, t4_id] if x is not None]
            self[t1_id].descendents.extend(ids)
            if add:
                for i, t_id in enumerate(ids):
                    if t_id not in self:
                        self.c[t_id] = Type(id=t_id)
                        self[t_id].ancestors = ids[:i]
                        self[t_id].ancestors.reverse()

    def get_descriptions(self, db):
        if not self: return    # empty set? -> do nothing
        # ignore if the table is not available
        if not config.TABLES['types']: return
        db.execute(
            'SELECT type_orig_id, description FROM types '
            'WHERE type_orig_id IN %s', (tuple(self),))
        for type_id, description in db.fetchall():
            self[type_id].description = render_type_links(description)

    def get_names(self, db):
        if not self: return    # empty set? -> do nothing
        # ignore if the table is not available
        if not config.TABLES['types']: return
        db.execute(
            'SELECT type_orig_id, name FROM types '
            'WHERE type_orig_id IN %s', (tuple(self),))
        for type_id, name in db.fetchall():
            self[type_id].name = name

    def get_poem_ids(self, db, minor=True):
        if not self: return    # empty set? -> do nothing
        # ignore if the table is not available
        if not config.TABLES['types'] or not config.TABLES['p_typ']:
            return
        query_lst = [
            'SELECT nro, is_minor ',
            'FROM poems ',
            '  NATURAL JOIN p_typ ',
            '  NATURAL JOIN types ',
            'WHERE type_orig_id IN %s']
        if not minor:
            query_lst.append(' AND is_minor = 0')
        query_lst.append(';')
        db.execute(' '.join(query_lst), (tuple(self),))
        nros, minor_nros = [], []
        for nro, is_minor in db.fetchall():
            if is_minor:
                minor_nros.append(nro)
            else:
                nros.append(nro)
        return (nros, minor_nros) if minor else nros

    def get_poem_counts(self, db):
        if not self: return {}
        if not config.TABLES['types'] or not config.TABLES['p_typ']:
            return {}
        db.execute(
            'SELECT type_orig_id, p_id FROM p_typ NATURAL JOIN types '
            'WHERE type_orig_id IN %s;', (tuple(self),))
        poems = { t: set() for t in self }
        for type_id, p_id in db.fetchall():
            for t in [type_id] + (self[type_id].ancestors or []):
                if t in poems:
                    poems[t].add(p_id)
        return { t: len(p) for t, p in poems.items() if p }


def render_type_tree(types, minor_type_ids=None):

    def _arrange_type_list(types):
        result = []
        seen = set()
        for t in sorted(types):
            for i in range(len(types[t].ancestors)-1, -1, -1):
                if types[t].ancestors[i] not in seen:
                    d = len(types[t].ancestors)-1-i
                    result.append(TypeTreeLine(
                        prefix=[],
                        depth=d,
                        type_id=types[t].ancestors[i],
                        is_minor=False))
                    seen.add(types[t].ancestors[i])
            if t not in seen:
                result.append(TypeTreeLine(
                    prefix=[],
                    depth=len(types[t].ancestors),
                    type_id=t,
                    is_minor=minor_type_ids is not None \
                             and t in minor_type_ids))
                seen.add(t)
        return result

    def _compute_prefixes(typelist):
        for i in range(len(typelist)-1, -1, -1):
            depth = typelist[i].depth
            typelist[i].prefix.extend(['│'] * (depth-1) + ['├'] * (depth > 0))
            nextdepth = typelist[i+1].depth if i+1 < len(typelist) else 0
            # remove the tree branches ("|") that lead nowhere
            if nextdepth < depth:
                for j in range(nextdepth, depth-1):
                    typelist[i].prefix[j] = ' '
            if i+1 < len(typelist):
                for j in range(depth-1):
                    if j < nextdepth and typelist[i+1].prefix[j] == ' ':
                        typelist[i].prefix[j] = ' '
            if depth > 0 and (depth > nextdepth \
                              or (i+1 < len(typelist) \
                                  and typelist[i+1].prefix[depth-1] == ' ')):
                typelist[i].prefix[depth-1] = '└'

    typelist = _arrange_type_list(types)
    _compute_prefixes(typelist)
    return typelist


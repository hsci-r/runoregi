from collections import namedtuple
import lxml.etree as ET
from utils import render_xml, remove_xml

import config


Verse = \
    namedtuple('Verse',
               ['nro', 'pos', 'v_id', 'v_type', 'text', 'text_cl',
                'clust_id', 'clust_freq'])

class Verse:
    def __init__(self, nro, pos, v_id, v_type, text, text_cl, clust_id, clust_freq):
        self.nro = nro
        self.pos = pos
        self.v_id = v_id
        self.v_type = v_type
        self.text = text
        self.text_cl = text_cl
        self.clust_id = clust_id
        self.clust_freq = clust_freq
        self.text_norm = None
        self.text_rendered = None
        self.render_text_norm()

    def render_text(self, refs):
        self.text_rendered = render_xml(self.text, refs, tag=self.v_type)

    def render_text_norm(self):
        self.text_norm = remove_xml(self.text, tag=self.v_type)


def get_clusterings(db):
    # ignore if the table is not available
    if not config.TABLES['v_clusterings']:
        return []
    db.execute('SELECT * FROM v_clusterings;')
    return db.fetchall()


def get_verses(db, nro=None, start_pos=None, end_pos=None,
                   clust_id=None, clustering_id=0):
    query_args = []
    query_lst = [
        'SELECT ',
        '  p.nro, vp.pos, v.v_id, v.type, v.text, ',
    ]
    query_lst.append('  v_cl.text,' if config.TABLES['verses_cl'] else 'NULL,')
    query_lst.append('  vcf.clust_id, vcf.freq ' \
                     if config.TABLES['v_clust'] and config.TABLES['v_clust_freq'] \
                     else '  NULL, NULL')
    query_lst.extend([
        'FROM verses v',
        '  JOIN verse_poem vp ON vp.v_id = v.v_id',
        '  JOIN poems p ON vp.p_id = p.p_id'
    ])
    if config.TABLES['verses_cl']:
        query_lst.append('  LEFT OUTER JOIN verses_cl v_cl ON v_cl.v_id = v.v_id')
    if config.TABLES['v_clust'] and config.TABLES['v_clust_freq']:
        query_lst.extend([
            '  LEFT OUTER JOIN v_clust vc ON vc.v_id = v.v_id ',
            '                                AND vc.clustering_id = %s ',
            '  LEFT OUTER JOIN v_clust_freq vcf ',
            '    ON vcf.clust_id = vc.clust_id ',
            '       AND vcf.clustering_id = vc.clustering_id '
        ])
        query_args.append(clustering_id)

    if isinstance(nro, str):
        # get by passage of one poem
        query_lst.append('WHERE p.nro = %s')
        query_args.append(nro)
        if start_pos is not None and end_pos is not None:
            query_lst.append(' AND vp.pos BETWEEN %s AND %s')
            query_args.extend((start_pos, end_pos))
    elif isinstance(nro, tuple) or isinstance(nro, list):
        # get by poem IDs for multiple poems
        query_lst.append('WHERE p.nro IN %s')
        query_args.append(tuple(nro))
    elif (isinstance(clust_id, tuple) or isinstance(clust_id, list)) \
         and config.TABLES['v_clust'] and config.TABLES['v_clust_freq']:
        # get by cluster IDs
        # Skip if cluster ID list is empty
        if clust_id:
            query_lst.append('WHERE vc.clust_id IN %s')
            query_args.append(tuple(clust_id))
        else:
            # Empty cluster list - add a condition that always evaluates to false
            query_lst.append('WHERE vc.clust_id IS NULL')
    else:
        raise Exception('TODO message')

    query_lst.append(' ORDER BY p.p_id, vp.pos;')
    query = '\n'.join(query_lst)
    db.execute(query, tuple(query_args))
    result = []
    for nro, pos, v_id, v_type, v_text, \
            v_text_cl, clust_id, clust_freq in db.fetchall():
        result.append(Verse(
            nro, pos, v_id, v_type, v_text, v_text_cl, clust_id, clust_freq))
    return result


# TODO if this is too slow, consider grouping by vc2.clust_id
# and returning just one verse per neighboring cluster
def get_verse_cluster_neighbors(
        db, clust_id, clustering_id=0, by_cluster=False, limit=None):

    result = []
    # ignore if the tables are not available
    if not config.TABLES['v_clust'] or not config.TABLES['v_clust_freq']:
        return result
    query_args = [clustering_id, clustering_id, clust_id, clust_id]
    if by_cluster:
        query_lst = [
            'SELECT ',
            '   p1.nro, vp1.pos, v1.v_id, v1.type, v1.text, v1_cl.text,',
            '   vc1.clust_id, vcf1.freq, ',
            '   p2.nro, vp2.pos, v2.v_id, v2.type, v2.text, v2_cl.text,',
            '   vc2.clust_id, vcf2.freq, ',
            '   SUM(s.sim_cos) AS sim ',
            'FROM v_sim s ',
            '  JOIN verses v1 ON s.v1_id = v1.v_id',
            '  JOIN verses_cl v1_cl ON s.v1_id = v1_cl.v_id',
            '  JOIN verse_poem vp1 ON s.v1_id = vp1.v_id',
            '  JOIN poems p1 ON vp1.p_id = p1.p_id',
            '  JOIN v_clust vc1 ON s.v1_id = vc1.v_id ',
            '                      AND vc1.clustering_id = %s ',
            '  JOIN v_clust_freq vcf1 ON vc1.clust_id = vcf1.clust_id',
            '                         AND vc1.clustering_id = vcf1.clustering_id ',
            '  JOIN verses v2 ON s.v2_id = v2.v_id',
            '  JOIN verses_cl v2_cl ON s.v2_id = v2_cl.v_id',
            '  JOIN verse_poem vp2 ON s.v2_id = vp2.v_id',
            '  JOIN poems p2 ON vp2.p_id = p2.p_id',
            '  JOIN v_clust vc2 ON s.v2_id = vc2.v_id ',
            '                      AND vc2.clustering_id = %s ',
            '  JOIN v_clust_freq vcf2 ON vc2.clust_id = vcf2.clust_id',
            '                         AND vc2.clustering_id = vcf2.clustering_id ',
            'WHERE vc1.clust_id IN %s AND vc2.clust_id NOT IN %s ',
            'GROUP BY vc1.clust_id, vc2.clust_id',
            'ORDER BY sim DESC '
        ]
    else:
        query_lst = [
            'SELECT ',
            '   s.v1_id,',
            '   p2.nro, vp2.pos, v2.v_id, v2.type, v2.text, v2_cl.text,',
            '   vc2.clust_id, vcf2.freq, ',
            '   s.sim_cos ',
            'FROM v_sim s ',
            '  JOIN v_clust vc1 ON s.v1_id = vc1.v_id ',
            '                      AND vc1.clustering_id = %s ',
            '  JOIN verses v2 ON s.v2_id = v2.v_id',
            '  JOIN verses_cl v2_cl ON s.v2_id = v2_cl.v_id',
            '  JOIN verse_poem vp2 ON s.v2_id = vp2.v_id',
            '  JOIN poems p2 ON vp2.p_id = p2.p_id',
            '  JOIN v_clust vc2 ON s.v2_id = vc2.v_id ',
            '                      AND vc2.clustering_id = %s ',
            '  JOIN v_clust_freq vcf2 ON vc2.clust_id = vcf2.clust_id',
            '                         AND vc2.clustering_id = vcf2.clustering_id ',
            'WHERE vc1.clust_id IN %s AND vc2.clust_id NOT IN %s ',
            'ORDER BY s.v1_id, s.sim_cos DESC;'
        ]
    if limit is not None:
        query_lst.append('LIMIT %s')
        query_args.append(limit)
    query_lst.append(';')
    db.execute(' '.join(query_lst), tuple(query_args))
    for row in db.fetchall():
        if by_cluster:
            result.append((Verse(*row[:8]), Verse(*row[8:16]), row[16]))
        else:
            result.append((row[0], Verse(*row[1:-1]), row[-1]))
    return result


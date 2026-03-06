from flask import render_template, Response
import numpy as np
from operator import itemgetter
from pydantic import BaseModel, BeforeValidator, Field
import pymysql
import scipy.cluster.hierarchy
from typing import Annotated, List, Literal

from shortsim.align import align

import config
from data.logging import profile
from data.poems import Poems
from methods.verse_sim import compute_verse_similarity
from methods.hclust import make_sim_mtx, sim_to_dist
from utils import compact, link, render_csv, remove_xml, splitter


MAX_POEMS = 50


class Args(BaseModel):
    nro: Annotated[
        List[str],
        BeforeValidator(splitter(',')),
    ] = Field(max_length=MAX_POEMS)
    method: Literal["none", "complete", "average", "single"] = "none"
    t: float = Field(0.75, ge=0, le=1)
    format: Literal["html", "csv"] = "html"


def generate_page_links(args):
    def pagelink(**kwargs):
        return link('multidiff', args.model_copy(update=kwargs))

    result = {
        'csv': pagelink(format='csv'),
        'tsv': pagelink(format='tsv'),
        't': {}, 'method': {}
    }
    for method in ['none', 'complete', 'average', 'single']:
        result['method'][method] = pagelink(method=method)
    for t in [0, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1]:
        result['t'][t] = pagelink(t=t)
    return result


def merge_alignments(poems, merges, v_sims):
    # This computes the aggregated similarity (max) between verse tuples,
    # leaving Nones out.
    # e.g. _agr_sim((A, None, B), (None, C, None, D))
    #      = max(sim(A, C), sim(A, D), sim(B, C), sim(B, D))
    # Returns -1 if no verse pair is similar.
    def _agr_sim(x, y):
        x_ids = [vx.v_id for vx in x if vx is not None]
        y_ids = [vy.v_id for vy in y if vy is not None]
        sims = [-1] + [v_sims[i][j] \
                       for i in x_ids for j in y_ids if j in v_sims[i]]
        return max(sims)

    # FIXME passing x_size and y_size here is slow and clumsy!
    # A better solution would be to have parameters like
    # `ins` and `del` instead of `empty` for the `align()` function
    # (different `empty` values for the left and right side),
    # so that the Nones produced by it already have the right lengths.
    def _merge(x, y, x_size, y_size):
        mx = (None,) * x_size if x is None else x
        my = (None,) * y_size if y is None else y
        return mx+my

    alignments = [[(v,) for v in p.text if v.v_type == 'V'] for p in poems.values()]
    for i in range(merges.shape[0]):
        al_1 = alignments[int(merges[i,0])]
        al_2 = alignments[int(merges[i,1])]
        pair_al = align(al_1, al_2,
                        insdel_cost=0,
                        dist_fun = lambda x,y: \
                            _agr_sim(al_1[x], al_2[y]),
                        opt_fun=max,
                        empty=None)
        alignments.append([_merge(x, y, len(al_1[0]), len(al_2[0])) \
                           for x, y, w in pair_al])
    return alignments[-1]


@profile
def render(**kwargs):
    args = Args.validate(kwargs)
    poems = Poems(nros=args.nro)
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        poems.get_raw_meta(db)
        poems.get_structured_metadata(db)
        poems.get_text(db)
        poems.get_similar_poems(db, within=True)
        types = poems.get_types(db)
        types.get_names(db)

    m = make_sim_mtx(poems)
    m_onesided = make_sim_mtx(poems, onesided=True)
    d = sim_to_dist(m)
    v_sims = compute_verse_similarity(poems, args.t)
    clust, ids = None, None
    if args.method == 'none':
        # align the poems from left to right, in the order given by `nros`
        clust = np.zeros(shape=(len(poems)-1, 2))
        for i in range(len(poems)-1):
            clust[i,0] = 0 if i == 0 else len(poems)+i-1
            clust[i,1] = i+1
        ids = list(range(len(poems)))
    else:
        # arrange the poems using hierarchical clustering
        clust = scipy.cluster.hierarchy.linkage(d, method=args.method)
        ids = scipy.cluster.hierarchy.leaves_list(clust) 

    als = merge_alignments(poems, clust[:,:2], v_sims)

    poems = [poems[args.nro[i]] for i in ids]
    meta_keys = sorted(set([k for p in poems for k in p.meta.keys()]))
    meta = {}
    for p in poems:
        meta[p.nro] = {}
        for key in meta_keys:
            if key in p.meta:
                meta[p.nro][key] = remove_xml(p.meta[key], tag=key)
    if args.format in ('csv', 'tsv'):
        rows = [((v.text if v else '') for v in row) for row in als]
        page = render_csv(rows, header=tuple(p.nro for p in poems),
                          delimiter='\t' if args.format == 'tsv' else ',')
        return Response(compact(page), mimetype="text/plain")
    else:
        data = {
            'alignment': als, 'poems': poems, 'meta_keys': meta_keys,
            'meta': meta, 'types': types, 'm': m, 'm_onesided': m_onesided,
            'v_sims': v_sims, 'maintenance': config.check_maintenance()
        }
        links = generate_page_links(args)
        page = render_template('multidiff.html', args=args, data=data, links=links)
        return Response(compact(page))

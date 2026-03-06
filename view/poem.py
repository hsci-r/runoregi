from flask import render_template, Response
import lxml.etree as ET
from operator import itemgetter
import math
from pydantic import BaseModel, BeforeValidator, Field
import pymysql
import re
from typing import Annotated, List, Literal

from collections import Counter, defaultdict

import config
from data.logging import profile
from data.poems import Poems
from data.verses import get_clusterings, get_verses
from utils import compact, link, makecol, render_xml, splitter


class Args(BaseModel):
    nro: str = Field(max_length=16)
    hl: Annotated[
        List[int],
        BeforeValidator(splitter(',')),
    ] = Field([], max_length=100)
    clustering: int = 0
    format: Literal["html", "txt", "xml"] = "html"

    # arguments for the shared verses matrix
    max_similar: int = Field(50, ge=0, le=200)
    sim_thr: float = Field(1, ge=0, le=1)
    show_shared_verses: bool = False
    sim_order: Literal[
        "consecutive_rare",
        "consecutive",
        "rare",
        "any",
    ] = "consecutive_rare"


def generate_page_links(args, clusterings):
    global DEFAULTS

    def pagelink(**kwargs):
        return link('poem', args.model_copy(update=kwargs))

    result = {
        '+show_shared_verses':
            pagelink(show_shared_verses=True),
        '-show_shared_verses':
            pagelink(show_shared_verses=False),
        'txt': pagelink(format='txt', show_shared_verses=False),
        'xml': pagelink(format='xml', show_shared_verses=False),
        'sim_order': {}, 'max_similar': {}, 'clustering': {}
    }
    for val in ['consecutive_rare', 'consecutive', 'rare', 'any']:
        result['sim_order'][val] = pagelink(sim_order=val)
    for val in [10, 20, 30, 40, 50, 75, 100, 150, 200]:
        result['max_similar'][val] = pagelink(max_similar=val)
    for c in clusterings:
        result['clustering'][c[0]] = pagelink(clustering=c[0])
    return result


# TODO refactor and document!
def get_shared_verses(db, poem, max, thr, order, clustering_id=0):
    clust_ids = set(v.clust_id for v in poem.text if v.v_type == 'V' and v.text_cl)
    verses = get_verses(db, clust_id=tuple(clust_ids), clustering_id=clustering_id)

    poem_verses = defaultdict(set)
    poem_versecounts = Counter([v.nro for v in verses])
    verse_poemcounts = Counter([v.clust_id for v in verses])
    for v in verses:
        if v.nro != poem.nro:
            poem_verses[v.nro].add(v.clust_id)
    poem_weights = Counter()
    if order == "rare":
        for (nro, clust_ids) in poem_verses.items():
            for clust_id in clust_ids:
                poem_weights[nro] += 1.0/verse_poemcounts[clust_id]
    elif order == "consecutive" or order == "consecutive_rare":
        nros = [nro for nro, clust_ids in poem_verses.items()]
        last_index = {nro: -1 for nro in nros}
        for i, v in enumerate(poem.text):
            if v.v_type == 'V':
                current = { nro: (v.clust_id in clust_ids)
                            for nro, clust_ids in poem_verses.items() }
                for nro in nros:
                    if current[nro]:
                        if order == "consecutive_rare":
                            poem_weights[nro] += 1.0/(i-last_index[nro]/verse_poemcounts[v.clust_id])
                        else:
                            poem_weights[nro] += 1.0/(i-last_index[nro])
                        last_index[nro]=i
            else:
                for nro in nros:
                    last_index[nro] = i
    else:  #order == "shared"
        poem_weights = poem_versecounts
    verse_poems = defaultdict(list)
    linked_poems = set()
    top_poems = set([nro for nro, count in poem_weights.most_common(max)])
    for v in verses:
        if v.nro in top_poems and poem_versecounts[v.nro] >= thr:
            linked_poems.add(v.nro)
            verse_poems[v.clust_id].append(v.nro)
    linked_poems_sorted = sorted(linked_poems, reverse=True,
                                 key=lambda nro: poem_weights[nro])
    return verse_poems, linked_poems_sorted, len(poem_versecounts)


@profile
def render(**kwargs):
    args = Args.validate(kwargs)
    p = Poems(nros=[args.nro])
    clusterings = None
    sim_poems, types = None, None
    verse_poems, linked_poems, poems_sharing_verses = None, None, None
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        clusterings = get_clusterings(db)
        p.get_duplicates_and_parents(db)
        p.get_poem_cluster_info(db)
        p.get_raw_meta(db)
        p.get_refs(db)
        p.get_similar_poems(db, sim_thr=0.1, sim_onesided_thr=0.5)
        p.get_structured_metadata(db)
        p.get_text(db, clustering_id=args.clustering)
        # poem types
        types = p.get_types(db)
        types.get_names(db)
        # get metadata for related poems (similar, duplicates etc.)
        related_nros = list(set([x.nro for x in p[args.nro].sim_poems] \
                                + p[args.nro].duplicates + p[args.nro].parents))
        related = Poems(nros=related_nros)
        if related:
            related.get_structured_metadata(db)
        # get verse clusters for the matrix view
        if args.show_shared_verses:
            verse_poems, linked_poems, poems_sharing_verses = \
                get_shared_verses(db, p[args.nro], args.max_similar,
                                  args.sim_thr, args.sim_order,
                                  args.clustering)

    # render the XML-containing text
    poem = p[args.nro]
    for v in poem.text:
        v.render_text(poem.refs)

    # render the XML in the raw metadata
    for key, val in p[args.nro].meta.items():
        p[args.nro].meta[key] = render_xml(val, poem.refs, tag=key)

    data = {
        'poem': poem,
        'related': related,
        'types': types,
        'sim': [(x.nro, x.sim_al) for x in poem.sim_poems if x.sim_al >= 0.1],
        'sim_left': [(x.nro, x.sim_al_l) \
                     for x in poem.sim_poems \
                         if x.sim_al < 0.1 and x.sim_al_l >= 0.5],
        'sim_right': [(x.nro, x.sim_al_r) \
                      for x in poem.sim_poems \
                          if x.sim_al < 0.1 and x.sim_al_r >= 0.5],
        'colors': { x: makecol(math.log(x), '337ab7', math.log(5000)) \
                    for x in set(v.clust_freq for v in poem.text) \
                    if x is not None},
        'verse_poems': verse_poems,
        'linked_poems': linked_poems,
        'poems_sharing_verses': poems_sharing_verses,
        'clusterings': clusterings,
        'maintenance': config.check_maintenance()
    }
    links = generate_page_links(args, clusterings)
    page = render_template('poem.{}'.format(args.format),
                           args=args, data=data, links=links)
    if args.format == "xml":
        return Response(compact(page), mimetype="text/xml")
    elif args.format == "txt":
        return Response(compact(page), mimetype="text/plain")
    else:
        return Response(compact(page))

from collections import defaultdict
from flask import render_template, Response
from pydantic import BaseModel, Field
import pymysql

import config
from data.logging import profile
from data.verses import \
    get_clusterings, get_verses, get_verse_cluster_neighbors
from utils import compact, link


class Args(BaseModel):
    nro: str
    pos: int
    clustering: int = 0
    maxdepth: int = Field(1, ge=1, le=5)
    maxnodes: int = Field(20, ge=1, le=200)
    nophysics: bool = False


def generate_page_links(args, clusterings):

    def pagelink(**kwargs):
        return link('clustnet', args.model_copy(update=kwargs))

    result = { '*physics': pagelink(nophysics=not args.nophysics),
               'maxdepth': {}, 'maxnodes': {}, 'clustering': {} }
    for val in [1, 2, 3, 4, 5]:
        result['maxdepth'][val] = pagelink(maxdepth=val)
    for val in [10, 20, 30, 50, 70, 100, 150, 200]:
        result['maxnodes'][val] = pagelink(maxnodes=val)
    for c in clusterings:
        result['clustering'][c[1]] = pagelink(clustering=c[0])
    return result


def get_cluster_network(db, clust_id, clustering_id=0, maxdepth=3, maxnodes=30):
    nodes_set = { clust_id }
    nodes = []
    edges = defaultdict(lambda: 0)

    depth = 0
    while depth < maxdepth and len(nodes) < maxnodes:
        verses = get_verse_cluster_neighbors(
            db, clust_id=tuple(nodes_set), clustering_id=clustering_id,
            by_cluster=True, limit=maxnodes-len(nodes_set))
        for v1, v2, sim in verses:
            if v2.clust_id not in nodes_set:
                nodes_set.add(v2.clust_id)
                nodes.append(v2)
            edges[(v1.clust_id, v2.clust_id)] += sim
        depth += 1

    edges = [(c1_id, c2_id, sim) for (c1_id, c2_id), sim in edges.items()]
    return { 'nodes': nodes, 'edges': edges }


@profile
def render(**kwargs):
    args = Args.validate(kwargs)
    clustnet, clusterings, verse = None, None, None
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        verse = get_verses(
            db, nro=args.nro, start_pos=args.pos,
            end_pos=args.pos, clustering_id=args.clustering)[0]
        clusterings = get_clusterings(db)
        clustnet = get_cluster_network(db, verse.clust_id,
                                       clustering_id=args.clustering,
                                       maxdepth=args.maxdepth,
                                       maxnodes=args.maxnodes)
    data = {
        'verse': verse,
        'clustnet': clustnet,
        'clusterings': clusterings,
        'maintenance': config.check_maintenance()
    }
    links = generate_page_links(args, clusterings)
    return render_template('clustnet.html', args=args, data=data, links=links)


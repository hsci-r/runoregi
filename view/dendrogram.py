from flask import render_template, Response
from operator import itemgetter
import numpy as np
from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter
import pymysql
import scipy.cluster.hierarchy
from typing import Annotated, List, Literal, Union
from urllib.parse import urlencode

import config
from data.logging import profile
from data.misc import get_collector_data, get_place_data
from data.poems import Poems
from data.types import Types, render_type_tree
from methods.hclust import make_sim_mtx, sim_to_dist
from utils import compact, link, splitter


MAX_TYPE_STYLES = 8
MAX_POEMS = 500


class ArgsFromType(BaseModel):
    source: Literal["type"]
    type_id: str = Field(max_length=20)
    nb: float = Field(1.0, ge=0, le=1)
    method: Literal[
        "complete", "average", "single", "centroid", "ward"
    ] = "complete"


class ArgsFromCluster(BaseModel):
    source: Literal["cluster"]
    nro: str = Field(max_length=16)
    nb: float = Field(1.0, ge=0, le=1)
    method: Literal[
        "complete", "average", "single", "centroid", "ward"
    ] = "complete"


class ArgsFromPlace(BaseModel):
    source: Literal["place"]
    id: str = Field(max_length=10)
    nb: float = Field(1.0, ge=0, le=1)
    method: Literal[
        "complete", "average", "single", "centroid", "ward"
    ] = "complete"

class ArgsFromCollector(BaseModel):
    source: Literal["collector"]
    id: str = Field(max_length=10)
    nb: float = Field(1.0, ge=0, le=1)
    method: Literal[
        "complete", "average", "single", "centroid", "ward"
    ] = "complete"


class ArgsFromPoemIDs(BaseModel):
    source: Literal["nros"]
    nro: Annotated[
        List[str],
        BeforeValidator(splitter(',')),
    ] = Field(max_length=MAX_POEMS)
    nb: float = Field(1.0, ge=0, le=1)
    method: Literal[
        "complete", "average", "single", "centroid", "ward"
    ] = "complete"


Args = TypeAdapter(Annotated[
    Union[
        ArgsFromType,
        ArgsFromCluster,
        ArgsFromPlace,
        ArgsFromCollector,
        ArgsFromPoemIDs
    ],
    Field(discriminator="source")
])


def generate_page_links(args):
    global DEFAULTS

    def pagelink(**kwargs):
        return link('dendrogram', args.model_copy(update=kwargs))

    result = { 'method': {}, 'nb': { 'none': pagelink(nb=1.0) } }
    for nb in [ 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 ]:
        nb_fmt = '{:.1}'.format(nb)
        result['nb'][nb_fmt] = pagelink(nb=nb)
    for method in ['complete', 'average', 'single', 'centroid', 'ward']:
        result['method'][method] = pagelink(method=method)
    if args.source == 'type' and args.nb == 1:
        result['map'] = config.VISUALIZATIONS_URL \
            + '?vis=map_type&' \
            + urlencode({'type_ids': '"{}"'.format(args.type_id)}) \
            if config.VISUALIZATIONS_URL else None
        result['types'] = config.VISUALIZATIONS_URL \
            + '?vis=tree_types_cooc&' \
            + urlencode({'type_ids': '"{}"'.format(args.type_id),
                         'incl_erab_orig': False}) \
            if config.VISUALIZATIONS_URL else None
    elif args.source == 'cluster' and args.nb == 1:
        result['map'] = config.VISUALIZATIONS_URL \
            + '?vis=map_poem_cluster&' \
            + urlencode({'nro': args.nro}) \
            if config.VISUALIZATIONS_URL else None
        result['types'] = config.VISUALIZATIONS_URL \
            + '?vis=tree_poem_cluster&' \
            + urlencode({'nro': args.nro, 'incl_erab_orig': False}) \
            if config.VISUALIZATIONS_URL else None
    return result


# transform linkages to a vertical dendrogram
def transform_vert(dd, n, nros):

    def tx(x):
        return int(400*(1-x)+20)

    def ty(y):
        return int(75*y+7)

    result = []
    ill = np.zeros(n, dtype=np.uint16)   # inverse leaves list -- positions of leaf nodes
    ll = scipy.cluster.hierarchy.leaves_list(dd)
    for i in range(dd.shape[0]+1):
        ill[ll[i]] = i
    for i in range(dd.shape[0]):
        if dd[i, 2] < 1:
            x1 = tx(0) if dd[i,0] < n else result[int(dd[i,0])-n][4]
            x2 = tx(0) if dd[i,1] < n else result[int(dd[i,1])-n][4]
            y1 = ty(ill[int(dd[i,0])]) if dd[i,0] < n else result[int(dd[i,0])-n][5]
            y2 = ty(ill[int(dd[i,1])]) if dd[i,1] < n else result[int(dd[i,1])-n][5]
            x = tx(dd[i,2])
            y = (y1 + y2) // 2
            nros1 = [nros[int(dd[i,0])]] if dd[i,0] < n else result[int(dd[i,0])-n][6]
            nros2 = [nros[int(dd[i,1])]] if dd[i,1] < n else result[int(dd[i,1])-n][6]
            result.append((x1, y1, x2, y2, x, y, nros1+nros2))
    return result


@profile
def render(**kwargs):
    args = Args.validate_python(kwargs)

    poems, types, target_type, inner = None, None, None, None
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        if args.source == 'type':
            target_type = Types(ids=[args.type_id])
            target_type.get_descriptions(db)
            nros, minor_nros = target_type.get_poem_ids(db, minor=True)
            poems = Poems(nros=nros+minor_nros)
            target_type.get_ancestors(db, add=True)
            target_type.get_names(db)
        elif args.source == 'cluster':
            poems = Poems(nros=[args.nro])
            poems.get_poem_cluster_info(db)
            poems = Poems.get_by_cluster(db, poems[args.nro].p_clust_id)
            poems.get_poem_cluster_info(db)
        elif args.source == 'nros':
            poems = Poems(nros=args.nro)
        elif args.source == 'collector':
            poems = Poems.get_by_collector(db, args.id)
        elif args.source == 'place':
            poems = Poems.get_by_place(db, args.id)

        if len(poems) > MAX_POEMS:
            raise Exception(
                f"Cannot generate dendrograms for more than {MAX_POEMS} poems.")
        inner = set(poems)
        if args.nb is not None and args.nb < 1:
            poems.get_similar_poems(db, sim_thr=args.nb)
            if len(poems) > MAX_POEMS:
                raise Exception(
                    f"Cannot generate dendrograms for more than {MAX_POEMS} poems.")
            new_nros = set(poems)
            for nro in poems:
                for s in poems[nro].sim_poems:
                    new_nros.add(s.nro)
            poems = Poems(nros=new_nros)
            if args.source == 'cluster':
                poems.get_poem_cluster_info(db)
        poems.get_structured_metadata(db)
        poems.get_similar_poems(db, within=True)
        types = poems.get_types(db)
        types.get_names(db)

        title = None
        if args.source == 'type':
            title = target_type[args.type_id].name
        elif args.source == 'cluster':
            title = 'Poem cluster #{}'.format(poems[args.nro].p_clust_id)
        elif args.source == 'place':
            place_data = get_place_data(db, args.id)
            title = '{} \u2014 {}'.format(place_data.county_name, place_data.parish_name) \
                if place_data.parish_name is not None else place_data.county_name
        elif args.source == 'collector':
            title = get_collector_data(db, args.id).name

    d = sim_to_dist(make_sim_mtx(poems))
    clust = scipy.cluster.hierarchy.linkage(d, method=args.method)
    ll = scipy.cluster.hierarchy.leaves_list(clust)
    dd = transform_vert(clust, len(poems), list(poems))
    type_styles = {}
    for p in poems:
        for t in poems[p].type_ids + poems[p].minor_type_ids:
            if t not in type_styles:
                type_styles[t] = len(type_styles) % MAX_TYPE_STYLES
    data = {
        'poems': poems,
        'nros': list(poems),
        'title': title,
        'types': types,
        'typetree': render_type_tree(types),
        'target_type': target_type,
        'type_styles': type_styles,
        'max_type_styles': MAX_TYPE_STYLES,
        'inner': inner,
        'll': ll, 'dd': dd, 'n': len(poems),
        'maintenance': config.check_maintenance()
    }
    links = generate_page_links(args) 
    page = render_template('dendrogram.html', args=args, data=data, links=links)
    return Response(compact(page))

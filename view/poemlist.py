from collections import defaultdict
from flask import render_template, Response
from operator import itemgetter
from pydantic import BaseModel, Field
import pymysql
from typing import Literal
from urllib.parse import urlencode

import config
from data.logging import profile
from data.misc import get_collector_data, get_parishes, get_place_data
from data.poems import Poems
from data.types import Types, render_type_tree
from utils import compact


class Args(BaseModel):
    source: Literal["type", "collector", "place"]
    id: str = Field(max_length=20)


def get_by_type(db, type_id):
    upper = Types(ids=[type_id])
    nros, minor_nros = upper.get_poem_ids(db, minor=True)
    poems = None
    if nros or minor_nros:
        poems = Poems(nros=nros+minor_nros)
        poems.get_structured_metadata(db)
    upper.get_descriptions(db)
    upper.get_ancestors(db, add=True)
    upper.get_names(db)
    subcat = Types(ids=[type_id])
    subcat.get_descriptions(db)
    subcat.get_descendents(db, add=True)
    subcat.get_names(db)

    tree = render_type_tree(subcat)
    # remove the top hierarchy level from the tree
    tree.pop(0)
    for line in tree:
        line.prefix.pop(0)
    types = Types(types=[upper[t] for t in upper] + \
                        [subcat[t] for t in subcat if t != type_id])
    return { 'poems': poems,
             'types': types,
             'minor': set(minor_nros), 
             'tree': tree,
             'title': types[type_id].name,
             'description': types[type_id].description
           }


@profile
def render(**kwargs):
    args = Args.validate(kwargs)
    data = {}
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        if args.source == 'type':
            data = get_by_type(db, args.id)
        elif args.source == 'collector':
            poems = Poems.get_by_collector(db, args.id)
            poems.get_structured_metadata(db)
            title = get_collector_data(db, args.id).name
            data = { 'poems': poems, 'title': title }
        elif args.source == 'place':
            parishes = get_parishes(db, args.id)
            poems = Poems.get_by_place(db, args.id)
            poems.get_structured_metadata(db)
            place_data = get_place_data(db, args.id)
            title = '<a href="/poemlist?source=place&id={}">{}</a> \u2014 {}'\
                    .format(place_data.county_id, place_data.county_name,
                            place_data.parish_name) \
                if place_data.parish_name is not None else place_data.county_name
            data = { 'poems': poems, 'title': title, 'parishes': parishes }

    data['maintenance'] = config.check_maintenance()

    links = {}
    if args.source == 'type':
        links['dendrogram'] = '/dendrogram?source=type&type_id={}'.format(args.id)
    else:
        links['dendrogram'] = '/dendrogram?source={}&id={}'.format(args.source, args.id)
    if config.VISUALIZATIONS_URL is not None:
        if args.source == 'type':
            links['map'] = config.VISUALIZATIONS_URL + '/?vis=map_type&' \
                + urlencode({'type_ids': '"{}"'.format(args.id)})
            links['types'] = config.VISUALIZATIONS_URL \
                + '?vis=tree_types_cooc&' \
                + urlencode({'type_ids': '"{}"'.format(args.id),
                             'include_erab_orig': False})
        elif args.source == 'collector':
            links['map'] = config.VISUALIZATIONS_URL + '/?vis=map_collector&' \
                + urlencode({'collector': title})
            links['types'] = config.VISUALIZATIONS_URL \
                + '?vis=tree_types_col&' \
                + urlencode({'collector': title, 'include_erab_orig': False})
        elif args.source == 'place':
            if place_data.parish_name is not None:
                links['types'] = config.VISUALIZATIONS_URL \
                    + '?vis=tree_types_parish&' \
                    + urlencode({'parish_name': place_data.parish_name })

    page = render_template('poemlist.html', args=args, data=data, links=links)
    return Response(compact(page))

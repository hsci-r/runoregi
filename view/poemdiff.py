from collections import defaultdict
from flask import render_template, Response
from pydantic import BaseModel, Field
import pymysql
import re
from subprocess import Popen, PIPE
from typing import Literal

from shortsim.align import align

import config
from data.logging import profile
from data.poems import Poems
from methods.verse_sim import compute_verse_similarity
from utils import compact, link, makecol, render_csv, remove_xml


class Args(BaseModel):
  nro1: str = Field(max_length=16)
  nro2: str = Field(max_length=16)
  t: float = Field(0.75, ge=0, le=1)
  format: Literal["html", "csv", "tsv"] = "html"


COLOR_NORMAL = None
COLOR_CHARDIFF = 'blue'
COLOR_LINEDIFF = 'grey'


def generate_page_links(args):
    def pagelink(**kwargs):
        return link('poemdiff', args.model_copy(update=kwargs))

    result = {
        'csv': pagelink(format='csv'),
        'tsv': pagelink(format='tsv'),
        't': {}
    }
    for t in [0, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1]:
        result['t'][t] = pagelink(t=t)
    return result


@profile
def render(**kwargs):
    args = Args.validate(kwargs)

    # FIXME code duplication with poem.py!
    def _makecolcomp(value):
        result = hex(255-int(value*255))[2:]
        if len(result) == 1:
            result = '0'+result
        return result

    def _makecol(value):
        if value is None:
            value = 0
        rg = _makecolcomp(value)
        b = _makecolcomp(max(value-0.5, 0))
        return '#'+rg+rg+b 

    # TODO
    # - some refactoring
    # - bold for captions
    poems = Poems(nros=[args.nro1, args.nro2])
    with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
        poems.get_raw_meta(db)
        poems.get_structured_metadata(db)
        poems.get_text(db)
        types = poems.get_types(db)
        types.get_names(db)

    poem_1 = poems[args.nro1]
    poem_2 = poems[args.nro2]
    poem_1_text = [v for v in poem_1.text if v.v_type == 'V']
    poem_2_text = [v for v in poem_2.text if v.v_type == 'V']
    sims = compute_verse_similarity(poems, args.t)
    al = align(
        poem_1_text,
        poem_2_text,
        insdel_cost=0,
        dist_fun=lambda i, j:
          sims[poem_1_text[i].v_id][poem_2_text[j].v_id] \
          if poem_2_text[j].v_id in sims[poem_1_text[i].v_id] else 0,
        opt_fun=max,
        empty=None)
    if args.format in ('csv', 'tsv'):
        page = render_csv([(x.text_norm if x is not None else None,
                            y.text_norm if y is not None else None,
                            w) for x, y, w in al],
                          header=(args.nro1, args.nro2, 'sim_cos'),
                          delimiter='\t' if args.format == 'tsv' else ',')
        return Response(compact(page), mimetype="text/plain")

    # render HTML
    meta_keys = sorted(list(set(poem_1.meta.keys()) | set(poem_2.meta.keys())))
    meta_1, meta_2 = {}, {}
    for key in meta_keys:
        meta_1[key] = remove_xml(poem_1.meta[key], tag=key) if key in poem_1.meta else ''
        meta_2[key] = remove_xml(poem_2.meta[key], tag=key) if key in poem_2.meta else ''
    alignment = []
    # TODO rendering the verse-level alignments - ugly code, refactor this!
    for row in al:
        verse_1, verse_2 = [], []
        if row[2] > 0:
            v_al = align(row[0].text_norm, row[1].text_norm)
            chunk_1, chunk_2, different, col = [], [], False, COLOR_NORMAL
            for x, y, c in v_al:
                if (x != y) != different:
                    if chunk_1:
                        verse_1.append((col, ''.join(chunk_1)))
                    if chunk_2:
                        verse_2.append((col, ''.join(chunk_2)))
                    chunk_1, chunk_2 = [], []
                    different = (x != y)
                    col = COLOR_CHARDIFF if different else COLOR_NORMAL
                if x == ' ' and different: x = '_'
                if y == ' ' and different: y = '_'
                chunk_1.append(x)
                chunk_2.append(y)
            if chunk_1:
                verse_1.append((col, ''.join(chunk_1)))
            if chunk_2:
                verse_2.append((col, ''.join(chunk_2)))
        else:
            if row[0] is not None:
                verse_1.append((COLOR_LINEDIFF, row[0].text_norm))
            if row[1] is not None:
                verse_2.append((COLOR_LINEDIFF, row[1].text_norm))
        alignment.append((verse_1, verse_2, (row[2], makecol(row[2]**2, '337ab7', 1))))
    raw_sim = sum(w for x, y, w in al)
    scores = [
        raw_sim,
        2*raw_sim / (len(poem_1_text) + len(poem_2_text)),
        raw_sim / len(poem_1_text),
        raw_sim / len(poem_2_text),
        sum([int(w > 0) for x, y, w in al]) / len(al),
    ]
    links = generate_page_links(args)
    data = {
        'p1': poem_1, 'p2': poem_2,
        'meta_1': meta_1, 'meta_2': meta_2, 'meta_keys': meta_keys,
        'alignment': alignment, 'scores': scores, 'types': types,
        'maintenance': config.check_maintenance()
    }
    page = render_template('poemdiff.html', args=args, data=data, links=links)
    return Response(compact(page))

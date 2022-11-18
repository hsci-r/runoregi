from collections import defaultdict
from flask import render_template
import pymysql
import re
from subprocess import Popen, PIPE

from shortsim.align import align

import config
from data.poems import Poems
from methods.verse_sim import compute_verse_similarity
from utils import link, render_csv


DEFAULTS = {
  'nro1': None,
  'nro2': None,
  't': 0.75,
  'format': 'html'
}

COLOR_NORMAL = None
COLOR_CHARDIFF = 'blue'
COLOR_LINEDIFF = 'grey'


def generate_page_links(args):
    global DEFAULTS

    def pagelink(**kwargs):
        return link('poemdiff', dict(args, **kwargs), DEFAULTS)

    return {
        'csv': pagelink(format='csv'),
        'tsv': pagelink(format='tsv'),
        '-t': pagelink(t=max(args['t']-0.05, 0)),
        '+t': pagelink(t=min(args['t']+0.05, 1)),
    }


def render(**args):

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
    poems = Poems(nros=[args['nro1'], args['nro2']])
    with pymysql.connect(**config.MYSQL_PARAMS) as db:
        poems.get_raw_meta(db)
        poems.get_structured_metadata(db)
        poems.get_text(db)
        types = poems.get_types(db)
        types.get_names(db)

    poem_1 = poems[args['nro1']]
    poem_2 = poems[args['nro2']]
    poem_1_text = [v for v in poem_1.text if v.v_type == 'V']
    poem_2_text = [v for v in poem_2.text if v.v_type == 'V']
    sims = compute_verse_similarity(poems, args['t'])
    al = align(
        poem_1_text,
        poem_2_text,
        insdel_cost=0,
        dist_fun=lambda i, j:
          sims[(poem_1_text[i].v_id, poem_2_text[j].v_id)] \
          if (poem_1_text[i].v_id, poem_2_text[j].v_id) in sims else 0,
        opt_fun=max,
        empty=None)
    if args['format'] in ('csv', 'tsv'):
        return render_csv([(x.text if x is not None else None,
                            y.text if y is not None else None,
                            w) for x, y, w in al],
                          header=(args['nro1'], args['nro2'], 'sim_cos'),
                          delimiter='\t' if args['format'] == 'tsv' else ',')

    # render HTML
    meta_keys = sorted(list(set(poem_1.meta.keys()) | set(poem_2.meta.keys())))
    meta_1, meta_2 = {}, {}
    for key in meta_keys:
        meta_1[key] = poem_1.meta[key] if key in poem_1.meta else ''
        meta_2[key] = poem_2.meta[key] if key in poem_2.meta else ''
    alignment = []
    # TODO rendering the verse-level alignments - ugly code, refactor this!
    for row in al:
        verse_1, verse_2 = [], []
        if row[2] > 0:
            v_al = align(row[0].text, row[1].text)
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
                verse_1.append((COLOR_LINEDIFF, row[0].text))
            if row[1] is not None:
                verse_2.append((COLOR_LINEDIFF, row[1].text))
        alignment.append((verse_1, verse_2, (row[2], _makecol(row[2]**2))))
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
        'p1': poem_1, 'p2': poem_2, 'meta_keys': meta_keys,
        'alignment': alignment, 'scores': scores, 'types': types
    }
    return render_template('poemdiff.html', args=args, data=data, links=links)


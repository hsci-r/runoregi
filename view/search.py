from collections import defaultdict
from flask import redirect, render_template, Response
import pymysql
from pydantic import BaseModel, Field

import config
from data.logging import profile
from data.pages import get_page_content
from data.poems import get_poem_by_id_or_title
from data.search import search_meta, search_types, search_verses, search_smd
from data.types import render_type_tree, Types
from utils import compact


DEFAULT_PAGES = [
  {
    'position': 'left',
    'title': 'Search',
    'helptext':
      '<p>'
      'This is a full-text search in poem type indices, metadata and texts using \n'
      ' <a target="_blank" href="https://mariadb.com/kb/en/full-text-index-overview/#in-boolean-mode">Boolean syntax</a>.'
      '</p>',
    'content':
      '<center>\n'
      '<form method="GET" action="/search">\n'
      '<div class="input-group">\n'
      '  <input type="text" class="form-control" name="q">\n'
      '  <span class="input-group-btn">\n'
      '    <button class="btn btn-default" type="button submit">Search</button>\n'
      '  </span>\n'
      '</div>\n'
      '</form>\n'
      '</center>\n'
  },
  {
    'position': 'main',
    'title': '',
    'helptext': '',
    'content':
      '<h2>About the project</h2>\n'
      'This is some text...'
  },
]


class Args(BaseModel):
    q: str | None = Field(None, max_length=100)


@profile
def render(**kwargs):
    args = Args.validate(kwargs)
    maintenance = config.check_maintenance()
    if args.q is None:
        with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
            pages = get_page_content(db, 'search_idx')
        data = { 'pages': pages if pages is not None else DEFAULT_PAGES }
        return render_template('search_idx.html', data = data)
    else:
        # otherwise, perform the search
        r_verses, r_types, r_meta = [], [], []
        with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
            # if a poem ID was entered -- go directly to the poem view
            nro = get_poem_by_id_or_title(db, args.q)
            if nro is not None:
                return redirect('/poem?nro={}'.format(nro))

            # otherwise, perform the search
            r_types = search_types(db, args.q)
            r_meta = search_meta(db, args.q)
            r_smd = search_smd(db, args.q)
            r_verses_and_inline = search_verses(db, args.q)
            r_verses = [(nro, pos, text) \
                        for (nro, pos, vtype, text) in r_verses_and_inline \
                        if vtype == 'V']
            r_inline = [(nro, pos, text) \
                        for (nro, pos, vtype, text) in r_verses_and_inline \
                        if vtype != 'V']
        data = { 'r_verses': r_verses, 'r_types': r_types,
                 'r_meta': r_meta, 'r_inline': r_inline,
                 'r_smd': r_smd,
                 'limit': config.SEARCH_LIMIT, 'maintenance': maintenance }
        page = render_template('search_results.html', args=args, data=data, links={})
        return Response(compact(page))

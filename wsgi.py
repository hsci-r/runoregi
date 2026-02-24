from flask import Flask, Response, redirect, request
from werkzeug.middleware.proxy_fix import ProxyFix
import pymysql
import re

import config
from data.poems import get_poem_by_id_or_title
import view.clustnet
import view.dendrogram
import view.multidiff
import view.passage
import view.poem
import view.poemdiff
import view.poemlist
import view.poemnet
import view.search
import view.verse


application = Flask(__name__)
if config.ENABLE_PROXY:
    # Used only to get the client's IP address, which is not used now.
    # The environment variable "PROXY" thus shouldn't be set.
    application.wsgi_app = ProxyFix(application.wsgi_app)
config.setup_tables()


def _compact(string):
    'Remove empty lines from the HTML code.'
    return re.sub(r'\n(\s*\n)+', '\n', string)


def getargs(request, defaults):
    result = {}
    for key, defval in defaults.items():
        dtype = type(defval) if defval is not None \
                                 and not isinstance(defval, list) \
                             else str
        result[key] = request.args.get(key, defval, dtype)
        # Try to convert the values to integers, but only if possible.
        if isinstance(result[key], str) and isinstance(defval, list):
            result[key] = result[key].split(',')
            try:
                result[key] = list(map(int, result[key]))
            except ValueError:
                pass
    return result


@application.route('/clustnet')
def show_clustnet():
    args = getargs(request, view.clustnet.DEFAULTS)
    result = view.clustnet.render(**args)
    return _compact(result)


@application.route('/dendrogram')
def show_dendrogram():
    # Temporarily disabled - return 403 Forbidden
    return "Access to dendrogram temporarily disabled", 403


@application.route('/passage')
def show_passage():
    args = getargs(request, view.passage.DEFAULTS)
    result = view.passage.render(**args)
    if args['format'] in ('csv', 'tsv'):
        return Response(result, mimetype='text/plain')
    else:
        return _compact(result)

@application.route('/poemdiff')
@application.route('/runodiff')
def show_diff():
    args = getargs(request, view.poemdiff.DEFAULTS)
    result = view.poemdiff.render(**args)
    if args['format'] in ('csv', 'tsv'):
        return Response(result, mimetype='text/plain')
    else:
        return _compact(result)

@application.route('/multidiff')
def show_multidiff():
    args = getargs(request, view.multidiff.DEFAULTS)
    result = view.multidiff.render(**args)
    if args['format'] in ('csv', 'tsv'):
        return Response(result, mimetype='text/plain')
    else:
        return _compact(result)

@application.route('/poem')
@application.route('/runo')
def show_poem():
    args = getargs(request, view.poem.DEFAULTS)
    result = view.poem.render(**args)
    if args['format'] == 'txt':
        return Response(result, mimetype='text/plain')
    elif args['format'] == 'xml':
        return Response(result, mimetype='text/xml')
    else:
        return _compact(result)

@application.route('/poemlist')
def show_poemlist():
    args = getargs(request, view.poemlist.DEFAULTS)
    result = view.poemlist.render(**args)
    return _compact(result)

@application.route('/poemnet')
def show_poemnet():
    args = getargs(request, view.poemnet.DEFAULTS)
    result = view.poemnet.render(**args)
    return _compact(result)


@application.route('/verse')
def show_verse():
    args = getargs(request, view.verse.DEFAULTS)
    result = view.verse.render(**args)
    if args['format'] in ('csv', 'tsv'):
        return Response(result, mimetype='text/plain')
    else:
        return _compact(result)


@application.route('/search')
@application.route('/')
def show_search():
    args = getargs(request, view.search.DEFAULTS)
    # If a poem ID or title was entered in the search box -> redirect to the poem.
    if args['q'] is not None:
        with pymysql.connect(**config.MYSQL_PARAMS).cursor() as db:
            nro = get_poem_by_id_or_title(db, args['q'])
            if nro is not None:
                return redirect('/poem?nro={}'.format(nro))
    result = view.search.render(**args)
    return _compact(result)


@application.route('/theme')
@application.route('/type')
def show_type():
    type_id = request.args.get('id', None, str)
    return redirect('/poemlist?source=type&id={}'.format(type_id))

@application.route('/robots.txt')
def show_robots_txt():
    return application.send_static_file('robots.txt')


if __name__ == '__main__':
    application.run()


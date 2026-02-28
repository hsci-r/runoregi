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


# Maximum limits for input validation
MAX_NRO_COUNT = 5000  # Max poem IDs allowed
MAX_TYPE_ID = 999999999  # Max type ID value
MAX_CLUSTER_ID = 999999999  # Max cluster ID value


def getargs(request, defaults):
    result = {}
    for key, defval in defaults.items():
        dtype = type(defval) if defval is not None \
                                 and not isinstance(defval, list) \
                             else str
        result[key] = request.args.get(key, defval, dtype)
        # Handle list-type parameters (comma-separated)
        if isinstance(result[key], str) and isinstance(defval, list):
            result[key] = result[key].split(',')
            try:
                result[key] = list(map(int, result[key]))
            except ValueError:
                pass
        # Validate nro list size
        if key == 'nro' and isinstance(result[key], list):
            if len(result[key]) > MAX_NRO_COUNT:
                result[key] = result[key][:MAX_NRO_COUNT]
    return result


@application.route('/clustnet')
def show_clustnet():
    try:
        args = getargs(request, view.clustnet.DEFAULTS)
        result = view.clustnet.render(**args)
        return _compact(result)
    except Exception as e:
        import sys
        print(f'Clustnet error: {e}', file=sys.stderr)
        return 'Unable to generate cluster network', 400


@application.route('/dendrogram')
def show_dendrogram():
    try:
        args = getargs(request, view.dendrogram.DEFAULTS)
        # Validate parameters before rendering
        if args.get('source') == 'type':
            type_id = args.get('type_id')
            # type_id can be either an integer or a string like 'skvr_t010100_0320'
            if type_id is None:
                return 'Invalid type_id parameter', 400
            if isinstance(type_id, int) and type_id > MAX_TYPE_ID:
                return 'Invalid type_id parameter', 400
        elif args.get('source') == 'cluster':
            nros = args.get('nro')
            if nros is None or not isinstance(nros, list) or len(nros) == 0:
                return 'Invalid cluster parameter', 400
            if not isinstance(nros[0], int) or nros[0] > MAX_CLUSTER_ID:
                return 'Invalid cluster parameter', 400
        result = view.dendrogram.render(**args)
        return _compact(result)
    except Exception as e:
        import sys
        print(f'Dendrogram error: {e}', file=sys.stderr)
        return 'Unable to generate dendrogram', 400


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
    try:
        args = getargs(request, view.poemnet.DEFAULTS)
        result = view.poemnet.render(**args)
        return _compact(result)
    except Exception as e:
        import sys
        print(f'Poemnet error: {e}', file=sys.stderr)
        return 'Unable to generate poem network', 400


@application.route('/verse')
def show_verse():
    try:
        args = getargs(request, view.verse.DEFAULTS)
        result = view.verse.render(**args)
        if args['format'] in ('csv', 'tsv'):
            return Response(result, mimetype='text/plain')
        else:
            return _compact(result)
    except Exception as e:
        import sys
        print(f'Verse error: {e}', file=sys.stderr)
        return 'Unable to process verse', 400


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

# Health check endpoint (no database required)
@application.route('/health')
def health_check():
    return 'OK', 200


if __name__ == '__main__':
    application.run()


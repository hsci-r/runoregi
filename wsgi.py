from flask import Flask, Response, redirect, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
import pymysql
import re
from traceback import format_exception

import config
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


@application.errorhandler(Exception)
def show_error(e):
    data = {
        'title': 'Unexpected error',
        'msg': 'An unexpected error occurred.',
        'stacktrace': ''.join(format_exception(e)),
    }
    return render_template('error.html', data=data)

@application.route('/clustnet')
def show_clustnet():
    return view.clustnet.render(**request.args)

@application.route('/dendrogram')
def show_dendrogram():
    return view.dendrogram.render(**request.args)

@application.route('/passage')
def show_passage():
    return view.passage.render(**request.args)

@application.route('/poemdiff')
@application.route('/runodiff')
def show_diff():
    return view.poemdiff.render(**request.args)

@application.route('/multidiff')
def show_multidiff():
    return view.multidiff.render(**request.args)

@application.route('/poem')
@application.route('/runo')
def show_poem():
    return view.poem.render(**request.args)

@application.route('/poemlist')
def show_poemlist():
    return view.poemlist.render(**request.args)

@application.route('/poemnet')
def show_poemnet():
    return view.poemnet.render(**request.args)

@application.route('/verse')
def show_verse():
    return view.verse.render(**request.args)

@application.route('/search')
@application.route('/')
def show_search():
    return view.search.render(**request.args)

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


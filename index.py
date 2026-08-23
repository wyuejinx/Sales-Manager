import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from werkzeug.middleware.proxy_fix import ProxyFix
import urllib.parse

class VercelPathFixer:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Ensure HTTPS scheme for Vercel
        if environ.get('HTTP_X_FORWARDED_PROTO') == 'https' or environ.get('VERCEL') == '1':
            environ['wsgi.url_scheme'] = 'https'

        # 2. Extract real path from Vercel query string or matched headers
        query = environ.get('QUERY_STRING', '')
        qs = urllib.parse.parse_qs(query)
        if 'path' in qs:
            val = qs['path'][0]
            real_path = '/' + val.lstrip('/')
            environ['PATH_INFO'] = real_path
            # Remove 'path' parameter so application doesn't see it in request.args
            clean_qs = {k: v for k, v in qs.items() if k != 'path'}
            environ['QUERY_STRING'] = urllib.parse.urlencode(clean_qs, doseq=True)
        else:
            path = environ.get('PATH_INFO', '')
            if path in ['/api/index', '/api/index/', '/api', '/api/']:
                environ['PATH_INFO'] = '/'
            elif path.startswith('/api/index/'):
                environ['PATH_INFO'] = path[10:]

        return self.wsgi_app(environ, start_response)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.wsgi_app = VercelPathFixer(app.wsgi_app)

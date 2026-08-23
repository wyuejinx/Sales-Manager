import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from werkzeug.middleware.proxy_fix import ProxyFix

class VercelPathFixer:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # Ensure HTTPS scheme is set for Vercel
        if environ.get('HTTP_X_FORWARDED_PROTO') == 'https' or environ.get('VERCEL') == '1':
            environ['wsgi.url_scheme'] = 'https'

        path = environ.get('PATH_INFO', '')
        if path in ['/api/index', '/api/index/', '/api', '/api/']:
            environ['PATH_INFO'] = '/'
        elif path.startswith('/api/index/'):
            environ['PATH_INFO'] = path[10:]
        return self.wsgi_app(environ, start_response)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.wsgi_app = VercelPathFixer(app.wsgi_app)

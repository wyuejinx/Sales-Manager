import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

class VercelPathFixer:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path in ['/api/index', '/api/index/', '/api', '/api/']:
            environ['PATH_INFO'] = '/'
        elif path.startswith('/api/index/'):
            environ['PATH_INFO'] = path[10:]
        return self.app(environ, start_response)

app.wsgi_app = VercelPathFixer(app.wsgi_app)

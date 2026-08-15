import sys, os, time, webbrowser, threading
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app

def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)

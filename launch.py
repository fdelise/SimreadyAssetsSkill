# coding: utf-8
"""
SimReady Asset Browser launcher.
Starts the local server, opens the browser, and auto-stops when done.

Usage:
    python3 launch.py
"""
import sys
import os
import time
import threading
import webbrowser

# Make sure server module resolves from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import ThreadedServer, Handler, PORT, free_port

print('SimReady Asset Browser')
print('Freeing port ' + str(PORT) + '...')
free_port(PORT)
time.sleep(1)

print('Starting server on http://localhost:' + str(PORT) + ' ...')
with ThreadedServer(('', PORT), Handler) as httpd:
    ThreadedServer._instance = httpd

    # Open browser after a short delay so the server is ready
    def open_browser():
        time.sleep(0.5)
        webbrowser.open('http://localhost:' + str(PORT))
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    print('Browser opened.')
    print('Click "Folder" on any asset to download it as a ZIP.')
    print('Server auto-stops 30 seconds after your last download.')
    print('Press Ctrl+C to stop now.\n')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

print('\nServer stopped.')

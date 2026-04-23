# coding: utf-8
"""
SimReady Asset Browser launcher.

1. Fetches the asset list from both S3 buckets (server-side — no CORS issues)
2. Starts a local server that serves index.html and the /assets endpoint
3. Opens http://localhost:8081 in your browser automatically

Usage: double-click launch.bat (Windows) or launch.command (Mac)
       — or run: python3 launch.py
"""
import os
import sys
import time
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import ThreadedServer, Handler, PORT, free_port, init_assets

print('SimReady Asset Browser')
print('Scanning S3 for assets...\n')
init_assets()   # fetch from S3 server-side — no CORS restrictions

print('Starting server on http://localhost:' + str(PORT) + ' ...')
free_port(PORT)
time.sleep(0.3)

with ThreadedServer(('', PORT), Handler) as httpd:
    ThreadedServer._instance = httpd

    def open_browser():
        time.sleep(0.5)
        webbrowser.open('http://localhost:' + str(PORT))

    threading.Thread(target=open_browser, daemon=True).start()
    print('Browser opened. Press Ctrl+C to stop.\n')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

print('\nStopped.')

# coding: utf-8
"""
SimReady Asset Browser - local server
Serves index.html and zips asset folders from S3 on demand.

Usage:
    python3 server.py
Then open: http://localhost:8081
"""
import http.server
import socketserver
import urllib.request
import urllib.parse
import zipfile
import io
import re
import os
import sys
import threading

PORT = 8081
DIR  = os.path.dirname(os.path.abspath(__file__))

SKIP_PREFIXES = ('.thumbs/', 'textures/.thumbs/')
SKIP_SUFFIXES = ('.wrapp',)


def s3_list(bucket, prefix):
    url = (
        'https://' + bucket + '.s3.amazonaws.com/'
        '?list-type=2'
        '&prefix=' + urllib.parse.quote(prefix, safe='') +
        '&max-keys=1000'
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        xml = r.read().decode('utf-8')
    keys = re.findall(r'<Key>([^<]+)</Key>', xml)
    return [k.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') for k in keys]


def should_skip(key, prefix):
    rel = key[len(prefix):]
    return (any(rel.startswith(p) for p in SKIP_PREFIXES) or
            any(rel.endswith(s) for s in SKIP_SUFFIXES))


def build_zip(bucket, prefix):
    keys = [k for k in s3_list(bucket, prefix)
            if not k.endswith('/') and not should_skip(k, prefix)]
    if not keys:
        raise ValueError('No files found under prefix')

    base = 'https://' + bucket + '.s3.amazonaws.com/'
    buf  = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for key in keys:
            rel = key[len(prefix):]
            sys.stderr.write('  + ' + rel + '\n')
            sys.stderr.flush()
            url = base + urllib.parse.quote(key, safe='/')
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    zf.writestr(rel, r.read())
            except Exception as exc:
                sys.stderr.write('  ! skip ' + rel + ': ' + str(exc) + '\n')
                sys.stderr.flush()
    buf.seek(0)
    return buf.read()


class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        sys.stderr.write('[' + self.address_string() + '] ' + (fmt % args) + '\n')
        sys.stderr.flush()

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if parsed.path == '/health':
                self.send_response(200)
                self.send_cors()
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'ok')
                return

            if parsed.path == '/zip':
                bucket = params.get('bucket', ['omniverse-content-production'])[0]
                prefix = params.get('prefix', [''])[0]
                if not prefix:
                    self.send_error(400, 'Missing prefix')
                    return

                asset_name = prefix.rstrip('/').rsplit('/', 1)[-1]
                zip_name   = asset_name + '.zip'
                sys.stderr.write('\nZipping s3://' + bucket + '/' + prefix + '\n')
                sys.stderr.flush()

                data = build_zip(bucket, prefix)

                sys.stderr.write('Done: ' + str(len(data) // 1024) + ' KB -> ' + zip_name + '\n')
                sys.stderr.flush()

                self.send_response(200)
                self.send_cors()
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition',
                                 'attachment; filename="' + zip_name + '"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

                # Auto-shutdown after IDLE_SECONDS of inactivity
                IDLE_SECONDS = 30
                if ThreadedServer._instance is not None:
                    if ThreadedServer._shutdown_timer is not None:
                        ThreadedServer._shutdown_timer.cancel()
                    t = threading.Timer(IDLE_SECONDS, ThreadedServer._instance.shutdown)
                    t.daemon = True
                    ThreadedServer._shutdown_timer = t
                    t.start()
                    sys.stderr.write('Auto-shutdown in ' + str(IDLE_SECONDS) + 's\n')
                    sys.stderr.flush()
                return

            if parsed.path in ('/', '/index.html'):
                html_path = os.path.join(DIR, 'index.html')
                with open(html_path, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            self.send_error(404)

        except Exception as exc:
            import traceback
            sys.stderr.write('HANDLER ERROR: ' + str(exc) + '\n')
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            try:
                self.send_error(500, str(exc))
            except Exception:
                pass


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    _instance      = None   # set by launch.py / __main__
    _shutdown_timer = None  # pending auto-shutdown Timer


def free_port(port):
    """Kill any processes already listening on port (Windows only)."""
    if sys.platform != 'win32':
        return
    try:
        import subprocess
        out = subprocess.check_output('netstat -ano', shell=True).decode(errors='replace')
        pids = set()
        for line in out.splitlines():
            if ':' + str(port) in line and 'LISTEN' in line:
                parts = line.strip().split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            subprocess.run('taskkill /F /PID ' + pid, shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


if __name__ == '__main__':
    free_port(PORT)
    import time
    time.sleep(1)          # let TIME_WAIT sockets drain

    with ThreadedServer(('', PORT), Handler) as httpd:
        sys.stderr.write('SimReady Asset Browser -> http://localhost:' + str(PORT) + '\n')
        sys.stderr.write('Press Ctrl+C to stop.\n\n')
        sys.stderr.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            sys.stderr.write('\nStopped.\n')
            sys.exit(0)

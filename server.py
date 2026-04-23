# coding: utf-8
"""
SimReady Asset Browser - local server
Serves index.html and zips asset folders from S3 on demand.
Fetches live asset data from both S3 buckets on startup — no hardcoded counts.

Usage:
    python3 server.py
Then open: http://localhost:8081
"""
import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import zipfile
import io
import re
import os
import sys
import json
import threading

PORT = 8081
DIR  = os.path.dirname(os.path.abspath(__file__))

SKIP_PREFIXES = ('.thumbs/', 'textures/.thumbs/')
SKIP_SUFFIXES = ('.wrapp',)

ENVS = {
    'production': 'omniverse-content-production',
    'staging':    'omniverse-content-staging',
}

# In-memory asset cache populated at startup by init_assets()
_asset_cache      = {}
_asset_cache_lock = threading.Lock()


def fetch_assets(bucket_name):
    """Fetch and parse workspace_cache.json from an S3 bucket. Returns list of asset dicts."""
    base_url  = 'https://' + bucket_name + '.s3.amazonaws.com/Assets/Isaac/6.0/Isaac/'
    cache_url = base_url + 'SimReady/workspace_cache.json'
    sys.stderr.write('  Fetching ' + cache_url + ' ...\n')
    sys.stderr.flush()
    with urllib.request.urlopen(cache_url, timeout=30) as r:
        cache = json.load(r)

    assets = []
    for usd_path, versions in cache.items():
        inner         = versions.get('null') or next(iter(versions.values()), {})
        install_paths = inner.get('install_path_options') or []
        segs      = usd_path.split('/')
        usd_file  = segs[-1]
        folder    = '/'.join(segs[:-1])
        usd_stem  = usd_file[:-4]
        name      = segs[-2].replace('_', ' ') if len(segs) >= 2 else usd_file
        top_cat   = segs[1] if len(segs) > 1 else ''
        category  = ' > '.join(segs[1:-1])
        s3_prefix = 'Assets/Isaac/6.0/Isaac/' + folder + '/'

        assets.append({
            'name':     name,
            'topCat':   top_cat,
            'category': category,
            'usdFile':  usd_file,
            'usdUrl':   base_url + usd_path,
            'thumbUrl': base_url + folder + '/.thumbs/' + usd_stem + '_thumbnail.png',
            's3Uri':    's3://' + bucket_name + '/Assets/Isaac/6.0/Isaac/' + usd_path,
            'bucket':   bucket_name,
            'prefix':   s3_prefix,
            'search':   (usd_path + ' ' + ' '.join(install_paths)).lower().replace('_', ' '),
        })

    sys.stderr.write('  Parsed ' + str(len(assets)) + ' assets\n')
    sys.stderr.flush()
    return assets


def probe_thumbnail(asset):
    """HEAD-request a thumbnail URL and return the HTTP status (or error string)."""
    try:
        req = urllib.request.Request(asset['thumbUrl'], method='HEAD')
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)


def init_assets():
    """Fetch asset data from both S3 buckets and populate the in-memory cache.
    Called once at startup — always reflects the current state of S3.
    """
    global _asset_cache
    data = {}
    for env, bucket in ENVS.items():
        sys.stderr.write('\n[' + env.upper() + ']\n')
        sys.stderr.flush()
        try:
            data[env] = fetch_assets(bucket)
        except Exception as exc:
            sys.stderr.write('  ERROR fetching ' + env + ': ' + str(exc) + '\n')
            sys.stderr.flush()
            data[env] = []

        # Probe a sample thumbnail to verify the URL pattern
        if data[env]:
            sample = data[env][0]
            status = probe_thumbnail(sample)
            ok = 'OK' if status == 200 else 'FAIL (' + str(status) + ')'
            sys.stderr.write('  Thumbnail check [' + ok + ']: ' + sample['thumbUrl'] + '\n')
            sys.stderr.flush()

    with _asset_cache_lock:
        _asset_cache = data
    total = sum(len(v) for v in data.values())
    sys.stderr.write('\nAsset scan complete — ' + str(total) + ' total assets loaded.\n\n')
    sys.stderr.flush()


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

            # Live asset data endpoint — always returns whatever is in the in-memory cache
            # (populated at startup from S3; never hardcoded)
            if parsed.path == '/assets':
                with _asset_cache_lock:
                    payload = json.dumps(_asset_cache, separators=(',', ':')).encode('utf-8')
                self.send_response(200)
                self.send_cors()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
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

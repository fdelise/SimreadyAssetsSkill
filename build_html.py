"""
build_html.py — Generates a self-contained index.html with both production and
staging asset data baked in (for offline / standalone use).

For the live server workflow, run launch.py instead — it fetches fresh data
from S3 on every launch via the /assets endpoint, so counts are never stale.

Usage: python3 build_html.py
"""
import json, urllib.request, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

ENVS = {
    'production': 'omniverse-content-production',
    'staging':    'omniverse-content-staging',
}

def fetch_assets(bucket_name):
    base_url  = f'https://{bucket_name}.s3.amazonaws.com/Assets/Isaac/6.0/Isaac/'
    cache_url = base_url + 'SimReady/workspace_cache.json'
    print(f'  Fetching {cache_url} ...')
    with urllib.request.urlopen(cache_url, timeout=30) as r:
        cache = json.load(r)

    assets = []
    for usd_path, versions in cache.items():
        inner = versions.get('null') or next(iter(versions.values()), {})
        install_paths = inner.get('install_path_options') or []
        segs     = usd_path.split('/')
        usd_file = segs[-1]
        folder   = '/'.join(segs[:-1])
        usd_stem = usd_file[:-4]
        name     = segs[-2].replace('_', ' ')
        top_cat  = segs[1] if len(segs) > 1 else ''
        category = ' > '.join(segs[1:-1])
        # S3 prefix for the folder (used by the /zip download endpoint)
        s3_prefix = 'Assets/Isaac/6.0/Isaac/' + folder + '/'

        assets.append({
            'name':     name,
            'topCat':   top_cat,
            'category': category,
            'usdFile':  usd_file,
            'usdUrl':   base_url + usd_path,
            'thumbUrl': base_url + folder + '/.thumbs/' + usd_stem + '_thumbnail.png',
            's3Uri':    f's3://{bucket_name}/Assets/Isaac/6.0/Isaac/' + usd_path,
            'bucket':   bucket_name,
            'prefix':   s3_prefix,
            'search':   (usd_path + ' ' + ' '.join(install_paths)).lower().replace('_', ' '),
        })
    print(f'  Parsed {len(assets)} assets')
    return assets

print('Building SimReady Asset Browser...')
data = {}
for env, bucket in ENVS.items():
    print(f'\n[{env.upper()}]')
    data[env] = fetch_assets(bucket)

template_path = os.path.join(SCRIPT_DIR, 'index_template.html')
out_path      = os.path.join(SCRIPT_DIR, 'index.html')

html = open(template_path, encoding='utf-8').read()
html = html.replace('/*PRODUCTION_DATA*/', json.dumps(data['production'], separators=(',', ':')))
html = html.replace('/*STAGING_DATA*/',    json.dumps(data['staging'],    separators=(',', ':')))
html = html.replace('PRODUCTION_COUNT',    str(len(data['production'])))
html = html.replace('STAGING_COUNT',       str(len(data['staging'])))

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(out_path)
print(f'\nWritten {out_path}  ({size/1024:.1f} KB)')
print('\nOpen index.html in any browser.')
print('USD button  — direct download from S3.')
print('Folder button — saves a Python script; run it to download all asset files into a ZIP.')

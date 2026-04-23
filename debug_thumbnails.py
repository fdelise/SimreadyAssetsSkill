# coding: utf-8
"""
debug_thumbnails.py — diagnose staging thumbnail issues.
Run with: python3 debug_thumbnails.py
"""
import json, urllib.request, urllib.error

STAGING_BUCKET = 'omniverse-content-staging'
BASE_URL = f'https://{STAGING_BUCKET}.s3.amazonaws.com/Assets/Isaac/6.0/Isaac/'
CACHE_URL = BASE_URL + 'SimReady/workspace_cache.json'

print('Fetching staging workspace_cache.json...')
with urllib.request.urlopen(CACHE_URL, timeout=30) as r:
    cache = json.load(r)

print(f'Total entries: {len(cache)}\n')

# Show the raw structure of the first 3 entries
print('=== RAW CACHE STRUCTURE (first 3 entries) ===')
for i, (usd_path, versions) in enumerate(cache.items()):
    print(f'\n[{i}] usd_path: {usd_path}')
    for ver_key, ver_val in versions.items():
        print(f'  version key: {repr(ver_key)}')
        print(f'  version fields: {list(ver_val.keys())}')
        # Print all non-list fields
        for k, v in ver_val.items():
            if not isinstance(v, (list, dict)):
                print(f'    {k}: {repr(v)}')
            elif isinstance(v, list) and len(v) <= 3:
                print(f'    {k}: {v}')
            else:
                print(f'    {k}: [{len(v)} items]')
    if i >= 2:
        break

# Try HEADing the constructed thumbnail URLs for the first 5 assets
print('\n\n=== THUMBNAIL URL PROBE (first 5 assets) ===')
for i, (usd_path, versions) in enumerate(cache.items()):
    segs = usd_path.split('/')
    usd_file = segs[-1]
    folder   = '/'.join(segs[:-1])
    usd_stem = usd_file[:-4]
    thumb_url = BASE_URL + folder + '/.thumbs/' + usd_stem + '_thumbnail.png'

    try:
        req = urllib.request.Request(thumb_url, method='HEAD')
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status = str(e)

    ok = '✓' if status == 200 else '✗'
    print(f'  {ok} [{status}] {thumb_url}')
    if i >= 4:
        break

# Also check if there's an explicit thumbnail field in the cache entries
print('\n\n=== CHECKING FOR EXPLICIT THUMBNAIL FIELDS ===')
thumb_fields = set()
for usd_path, versions in cache.items():
    for ver_key, ver_val in versions.items():
        for k in ver_val.keys():
            if 'thumb' in k.lower() or 'icon' in k.lower() or 'preview' in k.lower() or 'image' in k.lower():
                thumb_fields.add(k)

if thumb_fields:
    print(f'Found thumbnail-related fields: {thumb_fields}')
    # Show values for first entry
    for usd_path, versions in list(cache.items())[:1]:
        for ver_key, ver_val in versions.items():
            for k in thumb_fields:
                if k in ver_val:
                    print(f'  Example {k}: {repr(ver_val[k])}')
else:
    print('No explicit thumbnail/icon/preview fields found in cache entries.')
    print('Thumbnail URLs must be constructed from the asset path.')

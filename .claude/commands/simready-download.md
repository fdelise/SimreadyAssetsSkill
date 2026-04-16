Download a SimReady asset folder from S3 and save it as a ZIP file (USD + payloads + textures + materials).

Arguments: $ARGUMENTS

Supported flags:
- `--staging` — use the staging bucket instead of production
- `--out <dir>` — output directory (default: current directory)

Argument can be:
- An asset name or search term (e.g. `cardboard box`) — will search and ask which one to download
- An S3 URI (e.g. `s3://omniverse-content-production/Assets/Isaac/6.0/Isaac/SimReady/.../asset.usd`)

## Instructions

### Step 1 — Parse arguments and resolve the asset

Run this Python script:

```bash
python3 -c "
import sys, json, urllib.request, re, urllib.parse

args = '''$ARGUMENTS'''.strip()

# Parse flags
env = 'staging' if '--staging' in args else 'production'
args = args.replace('--staging', '').replace('--production', '').strip()

out_dir = '.'
if '--out' in args:
    parts = args.split('--out', 1)
    args  = parts[0].strip()
    out_dir = parts[1].strip().split()[0]
    args  = ' '.join(parts[1].strip().split()[1:]) or args

bucket   = f'omniverse-content-{env}'
base_url = f'https://{bucket}.s3.amazonaws.com/Assets/Isaac/6.0/Isaac/'
cache_url = base_url + 'SimReady/workspace_cache.json'

# If args looks like an S3 URI, extract the prefix directly
if args.startswith('s3://'):
    # s3://bucket/Assets/.../folder/file.usd
    path = args.split('/', 3)[-1]        # Assets/Isaac/.../file.usd
    prefix = path.rsplit('/', 1)[0] + '/' # Assets/Isaac/.../folder/
    asset_name = prefix.rstrip('/').rsplit('/', 1)[-1]
    print(f'RESOLVED:{bucket}:{prefix}:{asset_name}')
    sys.exit(0)

# Otherwise search workspace_cache
query = args.lower().strip()
if not query:
    print('ERROR: Please provide an asset name or S3 URI.')
    sys.exit(1)

with urllib.request.urlopen(cache_url, timeout=30) as r:
    cache = json.load(r)

results = []
terms = query.split()
for usd_path, versions in cache.items():
    inner = versions.get('null') or next(iter(versions.values()), {})
    install_paths = inner.get('install_path_options') or []
    searchable = (usd_path + ' ' + ' '.join(install_paths)).lower().replace('_', ' ')
    score = sum(1 for t in terms if t in searchable)
    if score > 0:
        parts      = usd_path.rsplit('/', 1)
        prefix     = parts[0] + '/'           # includes 'SimReady/...'
        full_prefix = 'Assets/Isaac/6.0/Isaac/' + prefix
        asset_name  = parts[0].rsplit('/', 1)[-1].replace('_', ' ')
        results.append((score, full_prefix, asset_name))

results.sort(key=lambda x: -x[0])

if not results:
    print(f'ERROR: No assets found matching: {query}')
    sys.exit(1)

if len(results) == 1:
    _, prefix, name = results[0]
    print(f'RESOLVED:{bucket}:{prefix}:{name}')
else:
    print('MULTIPLE:')
    for i, (score, prefix, name) in enumerate(results[:8]):
        print(f'  {i+1}. {name}  ({prefix.split(\"/\")[-2]})')
"
```

- If the output starts with `RESOLVED:bucket:prefix:name`, proceed to Step 2.
- If it starts with `MULTIPLE:`, show the list and ask the user to pick one, then re-run with the exact asset name.
- If it starts with `ERROR:`, report the error.

### Step 2 — Download and zip

Once you have `bucket`, `prefix`, and `asset_name`, run:

```bash
python3 -c "
import urllib.request, urllib.parse, zipfile, re, os, sys

bucket     = 'BUCKET_PLACEHOLDER'
prefix     = 'PREFIX_PLACEHOLDER'
asset_name = 'ASSET_NAME_PLACEHOLDER'
out_dir    = 'OUT_DIR_PLACEHOLDER'

SKIP_PREFIXES = ('.thumbs/', 'textures/.thumbs/')
SKIP_SUFFIXES = ('.wrapp',)

base_url  = f'https://{bucket}.s3.amazonaws.com/'
list_url  = base_url + '?list-type=2&prefix=' + urllib.parse.quote(prefix, safe='') + '&max-keys=1000'

print(f'Listing  s3://{bucket}/{prefix}', flush=True)
with urllib.request.urlopen(list_url, timeout=30) as r:
    xml = r.read().decode()
keys = [k.replace('&amp;','&') for k in re.findall(r'<Key>([^<]+)</Key>', xml)]
keys = [k for k in keys if not k.endswith('/')]

# Filter
def skip(key):
    rel = key[len(prefix):]
    return any(rel.startswith(p) for p in SKIP_PREFIXES) or any(rel.endswith(s) for s in SKIP_SUFFIXES)

keys = [k for k in keys if not skip(k)]
print(f'Downloading {len(keys)} files...', flush=True)

os.makedirs(out_dir, exist_ok=True)
zip_path = os.path.join(out_dir, asset_name.replace(' ', '_') + '.zip')

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for key in keys:
        url = base_url + urllib.parse.quote(key, safe='/')
        rel = key[len(prefix):]
        print(f'  + {rel}', flush=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            zf.writestr(rel, r.read())

size_mb = os.path.getsize(zip_path) / 1024 / 1024
print(f'Saved: {zip_path}  ({size_mb:.1f} MB)')
print(f'ZIP_PATH:{zip_path}')
"
```

Replace `BUCKET_PLACEHOLDER`, `PREFIX_PLACEHOLDER`, `ASSET_NAME_PLACEHOLDER`, and `OUT_DIR_PLACEHOLDER` with the actual values from Step 1 before running.

### Step 3 — Report

Tell the user where the ZIP was saved and list the top-level contents (USD, payloads/, textures/, etc.).

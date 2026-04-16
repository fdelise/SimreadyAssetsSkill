Search for SimReady assets in the NVIDIA Omniverse Isaac content bucket and return matching results with thumbnails and USD asset links.

The user's arguments are: $ARGUMENTS

Supported flags:
- `--staging` — search the staging bucket instead of production (default)
- `--production` — explicitly use production (default if no flag given)

## Instructions

### Step 1 — Fetch the asset index and search

Run this Python command:

```bash
python3 -c "
import json, urllib.request, sys

args = '''$ARGUMENTS'''.strip()

# Parse --staging / --production flag
env = 'production'
if '--staging' in args:
    env = 'staging'
    args = args.replace('--staging', '').strip()
elif '--production' in args:
    args = args.replace('--production', '').strip()

query = args.lower().strip()
if not query:
    print('ERROR: Please provide a search query.')
    print('Usage: /simready-search [--staging] <query>')
    print('Example: /simready-search --staging cardboard box')
    sys.exit(1)

BUCKET = 'omniverse-content-' + env
BASE_URL = f'https://{BUCKET}.s3.amazonaws.com/Assets/Isaac/6.0/Isaac/'
S3_BASE  = f's3://{BUCKET}/Assets/Isaac/6.0/Isaac/'
CACHE_URL = BASE_URL + 'SimReady/workspace_cache.json'

print(f'Environment : {env.upper()}', flush=True)
print(f'Fetching index from {BUCKET}...', flush=True)
with urllib.request.urlopen(CACHE_URL, timeout=30) as r:
    cache = json.load(r)

results = []
query_terms = query.split()

for usd_path, versions in cache.items():
    inner = versions.get('null') or next(iter(versions.values()), {})
    install_paths = inner.get('install_path_options') or []
    searchable = (usd_path + ' ' + ' '.join(install_paths)).lower().replace('_', ' ').replace('/', ' ')
    score = sum(1 for term in query_terms if term in searchable)
    if score > 0:
        parts    = usd_path.rsplit('/', 1)
        folder   = parts[0]
        usd_file = parts[1]
        usd_stem = usd_file[:-4]
        asset_name = folder.rsplit('/', 1)[-1].replace('_', ' ')
        category   = '/'.join(folder.split('/')[1:-1])
        results.append({
            'score':     score,
            'name':      asset_name,
            'category':  category,
            'usd_url':   BASE_URL + usd_path,
            'thumb_url': BASE_URL + folder + '/.thumbs/' + usd_stem + '_thumbnail.png',
            's3_uri':    S3_BASE + usd_path,
            'usd_file':  usd_file,
            'env':       env,
        })

results.sort(key=lambda x: -x['score'])
top = results[:8]

if not top:
    print(f'No assets found matching: {query}')
    sys.exit(0)

print(f'FOUND:{len(top)}')
for r in top:
    print(json.dumps(r))
"
```

### Step 2 — Display results

Parse the output lines after `FOUND:N`. Render each JSON result in this format:

```
### {name}  ·  `{env}`
**Category:** {category}
**USD Asset:** [{usd_file}]({usd_url})
**S3 URI:** `{s3_uri}`

![]({thumb_url})

---
```

Show the environment label (`STAGING` or `PRODUCTION`) prominently next to the asset name so it's clear which bucket the results came from.

### Step 3 — Final note

After all results add:

> **Tip:** Use the S3 URI directly in Isaac Sim or copy the HTTPS URL into Omniverse to load the asset. Switch environments with `--staging` or `--production`.

If no results were found, suggest alternative search terms based on the available categories: Industrial (Warehouse, Hardware, Tools) and Residential (Furnishing).

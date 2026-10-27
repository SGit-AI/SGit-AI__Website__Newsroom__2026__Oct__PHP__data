#!/usr/bin/env python3
"""The data repository's gate. Exits non-zero on any failure; seconds, not minutes.

1. Every catalogue file is in files/, and every file is valid JSON.
2. Every top-level file fits its schema (schemas/): a change of shape is a decision, not an accident.
3. Provenance: every source a claim or a timeline event cites is in sources.json; every edge of the risk graph joins
   two of its nodes and says how it is known.
4. The version CI will publish builds from files/ as itself (tools/package.py; CI mints the tag after this gate, and a
   published version is its tag: immutable, served from git, never committed as a copy).
5. No credential shapes anywhere in what is published.
"""
import json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(__file__))
from common import FILES, ROOT, SCHEMAS, catalogue, load_json, published_names, sha256, validate, walk  # noqa: E402

fails, notes = [], []
CREDENTIAL = re.compile(r'sgit_private_(vault|read)_[0-9a-f]{12,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|\bsk-(or-v1-|proj-|ant-[a-z0-9]+-)?[A-Za-z0-9_]{32,}')

# 1. present and parseable
for c in catalogue():
    if not os.path.exists(os.path.join(FILES, c['name'].rstrip('/'))):
        fails.append(f'files/{c["name"]}: in the catalogue, not in files/')
docs = {}
for n in published_names():
    try:
        docs[n] = load_json(os.path.join(FILES, n))
    except (OSError, ValueError) as e:
        fails.append(f'files/{n}: not valid JSON ({e})')

# 2. schemas
for n, d in docs.items():
    if '/' in n:
        continue
    sp = os.path.join(SCHEMAS, n.replace('.json', '.schema.json'))
    if not os.path.exists(sp):
        fails.append(f'schemas/{os.path.basename(sp)}: missing (python3 tools/schema.py)'); continue
    errs = validate(d, load_json(sp))
    fails += [f'files/{n}: {e}' for e in errs[:5]]

# 3. provenance
slugs = {s['slug'] for s in docs.get('sources.json', [])}
for f in ('claims.json', 'vault-claims.json', 'timeline.json', 'vault-timeline.json'):
    for i, row in enumerate(docs.get(f, [])):
        for s in row.get('sources') or []:
            if s not in slugs:
                fails.append(f'files/{f}[{i}]: cites "{s}", which is not in sources.json')
g = docs.get('grc-graph.json')
if g:
    ids = {n['id'] for n in g['nodes']}
    for i, e in enumerate(g['edges']):
        if e['from'] not in ids or e['to'] not in ids:
            fails.append(f'files/grc-graph.json edges[{i}]: joins a node that is not in the graph')
        if (e.get('basis') or {}).get('kind') not in ('source', 'code', 'inferred', 'confirmed'):
            fails.append(f'files/grc-graph.json edges[{i}]: no basis')
    notes.append(f'risk graph: {len(ids)} nodes, {len(g["edges"])} edges')
notes.append(f'{len(slugs)} sources; claims and events cite only those')

# 4. what CI will publish: the version built from files/ now (tools/package.py, at the tag CI mints after this gate)
tmp = tempfile.mkdtemp()
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('package', os.path.join(ROOT, 'tools', 'package.py'))
    pkg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pkg)
    m = pkg.build_version(ROOT, os.path.join(tmp, 'v'), 'next')
    for f in m['files']:
        if sha256(os.path.join(tmp, 'v', f['name'])) != f['sha256']:
            fails.append(f'files/{f["name"]}: does not publish as itself')
    notes.append(f'the next version: {len(m["files"])} files (CI tags it after this gate, on the push to dev)')
finally:
    shutil.rmtree(tmp)

# 6. credential shapes
for top in ('files', 'schemas', 'tools'):
    for p in walk(os.path.join(ROOT, top)) if os.path.isdir(os.path.join(ROOT, top)) else []:
        with open(os.path.join(ROOT, top, p), encoding='utf-8', errors='replace') as f:
            if CREDENTIAL.search(f.read()):
                fails.append(f'{top}/{p}: a credential shape')

for n in notes:
    print('note:', n)
for f in fails:
    print('FAIL:', f)
if fails:
    sys.exit(f'{len(fails)} failure(s)')
print(f'gate passed: {len(docs)} files')

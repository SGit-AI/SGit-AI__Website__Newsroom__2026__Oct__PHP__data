#!/usr/bin/env python3
"""The data repository's gate. Exits non-zero on any failure; seconds, not minutes.

1. Every catalogue file is in files/, and every file is valid JSON.
2. Every top-level file fits its schema (schemas/): a change of shape is a decision, not an accident.
3. Provenance: every source a claim or a timeline event cites is in sources.json; every edge of the risk graph joins
   two of its nodes and says how it is known.
4. Every published version matches its manifest, and no version already committed has changed.
5. latest/ is the newest version, and publishing again gives the same bytes (determinism).
6. No credential shapes anywhere in what is published.
"""
import json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(__file__))
from common import FILES, LATEST, PUBLISHED, ROOT, SCHEMAS, catalogue, load_json, published_names, sha256, validate, versions, walk  # noqa: E402

fails, notes = [], []
CREDENTIAL = re.compile(r'sgit_private_(vault|read)_[0-9a-f]{12,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}')

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

# 4. versions match their manifests; committed versions unchanged
committed = set()
try:
    # against the last commit, not the index: a staged change is still a change, and a published file removed is one too
    out = subprocess.run(['git', '-C', ROOT, 'ls-tree', '-r', 'HEAD', '--', 'v'], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        mode, kind, blob, path = line.replace('\t', ' ').split(None, 3)
        committed.add(path)
        now = subprocess.run(['git', '-C', ROOT, 'hash-object', path], capture_output=True, text=True).stdout.strip() if os.path.exists(os.path.join(ROOT, path)) else ''
        if now != blob:
            fails.append(f'{path}: a published file changed or went; a version is immutable, publish a new one')
except (subprocess.CalledProcessError, FileNotFoundError):
    notes.append('git not available: the immutability check was skipped')
vs = versions()
for v in vs:
    m = load_json(os.path.join(PUBLISHED, v, 'manifest.json'))
    for f in m['files']:
        p = os.path.join(PUBLISHED, v, f['name'])
        if not os.path.exists(p) or sha256(p) != f['sha256']:
            fails.append(f'v/{v}/{f["name"]}: does not match the manifest')

# 5. latest and determinism
if vs:
    a = {p: sha256(os.path.join(LATEST, p)) for p in walk(LATEST)} if os.path.isdir(LATEST) else {}
    b = {p: sha256(os.path.join(PUBLISHED, vs[-1], p)) for p in walk(os.path.join(PUBLISHED, vs[-1]))}
    if a != b:
        fails.append(f'latest/: is not v{vs[-1]}')
    version = open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip()
    published = {f['name']: f['sha256'] for f in load_json(os.path.join(PUBLISHED, vs[-1], 'manifest.json'))['files']}
    working = {n: sha256(os.path.join(FILES, n)) for n in published_names() if os.path.exists(os.path.join(FILES, n))}
    if working != published:
        # files/ moved on since the newest version: that is what a release publishes, not a failure
        changed = sorted(n for n in set(working) | set(published) if working.get(n) != published.get(n))
        notes.append(f'files/ differs from v{vs[-1]} in {len(changed)} file(s) ({", ".join(changed[:5])}{"..." if len(changed) > 5 else ""}): release a new version')
    elif version in vs:
        tmp = tempfile.mkdtemp()
        try:
            subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'publish.py'), '--into', tmp], capture_output=True, text=True, check=True)
            # the same files publish the same version: its file list and sums; the manifest's 'from' (the v1 commit it was
            # imported from) and the pages written from it may name a later import of the same files, which is no change
            if sha256(os.path.join(tmp, 'versions.json')) != sha256(os.path.join(ROOT, 'versions.json')):
                fails.append(f'versions.json: publishing again gives other bytes')
            a, b = (load_json(os.path.join(d, 'v', version, 'manifest.json'))['files'] for d in (tmp, ROOT))
            if a != b:
                fails.append(f'v/{version}/manifest.json: publishing again gives other files (files/ changed since v{version}: release a new version)')
        finally:
            shutil.rmtree(tmp)

# 6. credential shapes
for top in ('files', 'v', 'latest', 'schemas', 'tools'):
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
print(f'gate passed: {len(docs)} files, {len(vs)} version(s) published, latest v{vs[-1] if vs else "none"}')

#!/usr/bin/env python3
"""The data, both ways between files/ and v1's data/, while v1 still builds the pages (step A of the split).

    python3 tools/sync_v1.py import --from ../sgit-ai__website__newsroom__2026__oct__php   # v1 -> files/, never over a change made here
    python3 tools/sync_v1.py export --into ../sgit-ai__website__newsroom__2026__oct__php   # files/ -> v1 data/, what changed here since the last import

The rule: **what is written here wins.** tools/imported.json keeps the sha256 of every file the last import wrote. A
file whose sha256 differs was written here since: the import leaves it alone and says so, and the export carries it into
v1's data/, where v1's gate, build and release take it to the pages. After v1 releases, the next import finds the same
bytes and records them. A file v1's build itself writes (admin/build/outputs.txt in v1: the graphs, the items, the history) is never
exported: v1 derives it, and the import brings the derived file back.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
from common import FILES, ROOT, catalogue, dump_json, load_json  # noqa: E402

RECORD = os.path.join(ROOT, 'tools', 'imported.json')


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def names():
    """Every file the catalogue publishes, as files/-relative paths (a folder entry expands to its files in v1 or here)."""
    out = {}
    for c in catalogue():
        n = c['name']
        out[n] = c
    return out


def walk_rel(top):
    res = []
    for d, dirs, fs in os.walk(top):
        dirs.sort()
        for f in sorted(fs):
            res.append(os.path.relpath(os.path.join(d, f), top).replace(os.sep, '/'))
    return res


def entries_of(root, cat):
    """(files/-relative path, catalogue entry) for every file under root that the catalogue covers."""
    out = []
    for n, c in cat.items():
        p = os.path.join(root, n.rstrip('/'))
        if n.endswith('/'):
            if os.path.isdir(p):
                out += [(n + r, c) for r in walk_rel(p)]
        elif os.path.exists(p):
            out.append((n, c))
    return out


def changed_here(record, cat):
    known = record.get('files', {})
    if not known:   # no record yet (the first import): nothing counts as written here
        return []
    return [p for p, c in entries_of(FILES, cat) if known.get(p) != sha(os.path.join(FILES, p))]


def do_import(v1):
    data = os.path.join(v1, 'data')
    if subprocess.run(['git', '-C', v1, 'status', '--porcelain', '--', 'data'], capture_output=True, text=True).stdout.strip():
        sys.exit('import: the v1 clone has uncommitted changes under data/; import from a released commit')
    cat = names()
    record = load_json(RECORD) if os.path.exists(RECORD) else {}
    keep = set(changed_here(record, cat))
    kept, wrote, missing = [], {}, []
    for n in cat:
        if not os.path.exists(os.path.join(data, n.rstrip('/'))):
            missing.append(n)
    if missing:
        sys.exit(f'import: not in v1 data/: {", ".join(missing)}')
    for p, c in entries_of(data, cat):
        dst = os.path.join(FILES, p)
        if p in keep:
            kept.append(p); wrote[p] = sha(dst); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(data, p), dst); wrote[p] = sha(dst)
    gone = 0
    for p, h in record.get('files', {}).items():   # a file the last import wrote, gone from v1, unchanged here: gone
        q = os.path.join(FILES, p)
        if p not in wrote and os.path.exists(q) and sha(q) == h:
            os.remove(q); gone += 1
    for p, c in entries_of(FILES, cat):             # written here, never imported: its own
        if p not in wrote:
            wrote[p] = sha(os.path.join(FILES, p))
    commit = subprocess.run(['git', '-C', v1, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    story = load_json(os.path.join(data, 'story.json')); vault = load_json(os.path.join(data, 'vault.json'))
    site_version = open(os.path.join(v1, 'VERSION'), encoding='utf-8').read().strip()
    dump_json(RECORD, {'from': {'repository': 'SGit-AI/sgit-ai__website__newsroom__2026__oct__php', 'commit': commit, 'site_version': site_version},
                       'data_as_of': story.get('data_as_of'), 'evidence_vault_head': (vault.get('head') or {}).get('commit'),
                       'kept': sorted(kept), 'files': dict(sorted(wrote.items()))})
    print(f'imported {len(cat)} catalogue entries from v1 at {commit[:12]} (site v{site_version}); '
          f'{len(kept)} file(s) written here since the last import kept (export them), {gone} gone')
    for p in kept[:20]:
        print(f'  kept: {p}')


def do_export(v1):
    cat = names()
    record = load_json(RECORD) if os.path.exists(RECORD) else {}
    if not record.get('files'):
        sys.exit('export: no import record with file sums yet; import first')
    built = set(open(os.path.join(v1, 'admin', 'build', 'outputs.txt'), encoding='utf-8').read().split())   # what v1's build writes
    out, derived = [], []
    for p in changed_here(record, cat):
        c = cat.get(p) or cat.get(p.split('/')[0] + '/')
        if (c and c.get('built_by_v1')) or ('data/' + p) in built:
            derived.append(p); continue
        dst = os.path.join(v1, 'data', p); os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(FILES, p), dst); out.append(p)
    print(f'exported to v1 data/: {len(out)} file(s); release v1, then import again')
    for p in out[:20]:
        print(f'  {p}')
    for p in derived:
        print(f'  not exported, v1 builds it: {p}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['import', 'export'])
    ap.add_argument('--from', dest='src'); ap.add_argument('--into', dest='dst')
    a = ap.parse_args()
    if a.what == 'import':
        if not a.src: sys.exit('import needs --from')
        do_import(os.path.abspath(a.src))
    else:
        if not a.dst: sys.exit('export needs --into')
        do_export(os.path.abspath(a.dst))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Copy the catalogue's files from the v1 repository (today's site, which is still where the writers write) into files/.

    python3 tools/import_v1.py --from ../sgit-ai__website__newsroom__2026__oct__php

Until the cutover, v1 is the source of truth: the agents write its data/ and this copies it here, recording the v1
commit it read, so every published version says exactly which state of v1 it is. After the cutover the writers write
files/ here directly and this tool is retired.
"""
import argparse, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
from common import FILES, ROOT, catalogue, dump_json, load_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='v1', required=True, help='a clone of the v1 repository')
    a = ap.parse_args()
    v1 = os.path.abspath(a.v1)
    data = os.path.join(v1, 'data')
    commit = subprocess.run(['git', '-C', v1, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', v1, 'status', '--porcelain', '--', 'data'], capture_output=True, text=True).stdout.strip()
    if dirty:
        sys.exit('import: the v1 clone has uncommitted changes under data/; import from a released commit')
    missing = []
    for c in catalogue():
        n = c['name']
        src, dst = os.path.join(data, n.rstrip('/')), os.path.join(FILES, n.rstrip('/'))
        if not os.path.exists(src):
            missing.append(n); continue
        if n.endswith('/'):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    if missing:
        sys.exit(f'import: not in v1 data/: {", ".join(missing)}')
    story = load_json(os.path.join(data, 'story.json'))
    vault = load_json(os.path.join(data, 'vault.json'))
    site_version = open(os.path.join(v1, 'VERSION'), encoding='utf-8').read().strip()
    dump_json(os.path.join(ROOT, 'tools', 'imported.json'), {
        'from': {'repository': 'SGit-AI/sgit-ai__website__newsroom__2026__oct__php', 'commit': commit, 'site_version': site_version},
        'data_as_of': story.get('data_as_of'),
        'evidence_vault_head': (vault.get('head') or {}).get('commit'),
    })
    print(f'imported {len(catalogue())} catalogue entries from v1 at {commit[:12]} (site v{site_version})')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Publish files/ as the version in VERSION: v/<version>/ (immutable), latest/ (a copy of it), versions.json, index.html.

    python3 tools/publish.py               publish into this repository
    python3 tools/publish.py --into DIR    publish into DIR instead (the gate uses this to prove the output is the same)

A version folder holds every published file, its schema and manifest.json, which lists each file with its sha256, its
size and its group, and says which state of the writers' work it is (the v1 commit it was imported from, until the
cutover). A version already published is never changed: publishing different content under the same version stops.
Nothing here reads a clock: the same files give the same bytes.
"""
import argparse, html, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (FILES, ROOT, SCHEMAS, dump_json, group_of, load_json, published_names, sha256, versions,  # noqa: E402
                    vkey, walk)

SITE = 'https://data.php.oct.2026.newsroom.sgit.ai'


def build_version(dst, version):
    """Write one version folder at dst; return its manifest."""
    if os.path.exists(dst):
        shutil.rmtree(dst)
    files = []
    for n in published_names():
        src = os.path.join(FILES, n)
        os.makedirs(os.path.dirname(os.path.join(dst, n)), exist_ok=True)
        shutil.copyfile(src, os.path.join(dst, n))
        sch = n.replace('.json', '.schema.json') if '/' not in n else None
        if sch and os.path.exists(os.path.join(SCHEMAS, sch)):
            os.makedirs(os.path.join(dst, 'schemas'), exist_ok=True)
            shutil.copyfile(os.path.join(SCHEMAS, sch), os.path.join(dst, 'schemas', sch))
        else:
            sch = None
        files.append({'name': n, 'group': group_of(n), 'bytes': os.path.getsize(src), 'sha256': sha256(src), 'schema': f'schemas/{sch}' if sch else None})
    imported = load_json(os.path.join(ROOT, 'tools', 'imported.json'))
    manifest = {'api': 'php.oct.2026 newsroom data', 'version': version, 'url': f'{SITE}/v/{version}/', **imported, 'files': files}
    dump_json(os.path.join(dst, 'manifest.json'), manifest)
    return manifest


def tree(top):
    return {p: sha256(os.path.join(top, p)) for p in walk(top)} if os.path.isdir(top) else {}


def history(root):
    """versions.json: every published version, newest first, with what changed against the one before."""
    out, prev = [], {}
    vs = sorted((d for d in os.listdir(os.path.join(root, 'v')) if os.path.isfile(os.path.join(root, 'v', d, 'manifest.json'))), key=vkey)
    for v in vs:
        m = load_json(os.path.join(root, 'v', v, 'manifest.json'))
        cur = {f['name']: f['sha256'] for f in m['files']}
        out.append({'version': v, 'from': m.get('from'), 'data_as_of': m.get('data_as_of'), 'evidence_vault_head': m.get('evidence_vault_head'),
                    'files': len(cur), 'changed': sorted(n for n in cur if prev.get(n) != cur[n]), 'removed': sorted(set(prev) - set(cur))})
        prev = cur
    return list(reversed(out))


def index_html(hist, manifest):
    E = lambda s: html.escape(str(s if s is not None else ''), quote=True)
    rows = ''.join(f'<tr><td><a href="v/{E(h["version"])}/manifest.json">v{E(h["version"])}</a></td><td><code>{E((h["from"] or {}).get("commit", "")[:12])}</code> (site v{E((h["from"] or {}).get("site_version"))})</td>'
                   f'<td>{E(h["data_as_of"])}</td><td>{len(h["changed"])} of {h["files"]}</td></tr>' for h in hist)
    files = ''.join(f'<tr><td><a href="latest/{E(f["name"])}">{E(f["name"])}</a></td><td>{E(f["group"])}</td><td>{f["bytes"]:,}</td><td><code>{E(f["sha256"][:12])}</code></td>'
                    f'<td>{"<a href=" + chr(34) + "latest/" + E(f["schema"]) + chr(34) + ">schema</a>" if f["schema"] else ""}</td></tr>' for f in manifest['files'] if '/' not in f['name'])
    folders = sorted({f['name'].split('/')[0] + '/' for f in manifest['files'] if '/' in f['name']})
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PHP October 2026: the data</title>
<style>:root{{color-scheme:light dark}}body{{font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:0 auto;padding:16px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #8884}}code{{font-size:13px}}.tw{{overflow-x:auto}}</style></head>
<body>
<h1>PHP October 2026: the data</h1>
<p>The data behind <a href="https://php.oct.2026.newsroom.sgit.ai/">php.oct.2026.newsroom.sgit.ai</a>: the evidence exported from the vaults, the claims, the timeline, the state of affairs, the risk graph and the ontology. Every version is immutable once published: <code>{E(SITE)}/v/&lt;version&gt;/&lt;file&gt;</code>. <code>/latest/</code> is the newest. Each version's <code>manifest.json</code> lists every file with its sha256; pin a version and check the sums.</p>
<p>Latest: <a href="v/{E(manifest["version"])}/manifest.json">v{E(manifest["version"])}</a>, data as of {E(manifest.get("data_as_of"))}, from the site's repository at <code>{E(manifest["from"]["commit"][:12])}</code>. The history is <a href="versions.json">versions.json</a>.</p>
<h2>Files</h2>
<div class="tw"><table><thead><tr><th>File</th><th>Group</th><th>Bytes</th><th>sha256</th><th></th></tr></thead><tbody>{files}</tbody></table></div>
<p>Folders, each file listed in the manifest: {", ".join(f'<code>{E(f)}</code>' for f in folders)}.</p>
<h2>Versions</h2>
<div class="tw"><table><thead><tr><th>Version</th><th>From</th><th>Data as of</th><th>Files changed</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Kept in the repository <a href="https://github.com/SGit-AI/sgit-ai__website__newsroom__2026__oct__php__data">sgit-ai__website__newsroom__2026__oct__php__data</a>. Everything here is public; captures stay in the evidence vault.</p>
</body></html>
'''


def publish(root):
    version = open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip()
    vdir = os.path.join(root, 'v', version)
    if root == ROOT and os.path.isdir(vdir):
        # immutable: the same version may be published again only with exactly the same content
        tmp = os.path.join(ROOT, '.publish-check')
        shutil.rmtree(tmp, ignore_errors=True)
        build_version(tmp, version)
        same = tree(tmp) == tree(vdir)
        shutil.rmtree(tmp)
        if not same:
            sys.exit(f'publish: v{version} is already published with other content; bump VERSION (tools/release.sh does)')
    if root != ROOT:
        # a scratch publish: start from this repository's published versions, so the history is the same
        if os.path.isdir(os.path.join(ROOT, 'v')):
            shutil.copytree(os.path.join(ROOT, 'v'), os.path.join(root, 'v'), dirs_exist_ok=True)
    manifest = build_version(vdir, version)
    latest = os.path.join(root, 'latest')
    shutil.rmtree(latest, ignore_errors=True)
    shutil.copytree(vdir, latest)
    hist = history(root)
    dump_json(os.path.join(root, 'versions.json'), {'api': 'php.oct.2026 newsroom data', 'latest': version, 'versions': hist})
    with open(os.path.join(root, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(index_html(hist, manifest))
    print(f'published v{version}: {len(manifest["files"])} files')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--into', default=ROOT)
    publish(os.path.abspath(ap.parse_args().into))

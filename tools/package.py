#!/usr/bin/env python3
"""The data API as served, built from git tags (run by the deploy workflow; nothing here is committed).

    python3 tools/package.py --into _site

Every tag v<a>.<b>.<c> is a published version. One published before versions were minted in CI is served from the
last commit that held v/ in the tree (found from the history), as it was; a newer one is built from its tag's files/,
schemas/ and tools/, the way a version has always been built. The served tree:

- /v/<version>/manifest.json   for every version: each file's name, group, size, sha256 and schema
- /blobs/<sha256>              each distinct file content once, across all versions (a version's file is the blob its
                               manifest names; nothing is ever stored twice)
- /v/<version>/<file>          plain copies, for the newest KEEP_PLAIN versions
- /latest/<file>               the newest version, plain
- /versions.json, /index.html  the history and the front page

A version is immutable because its tag is (a ruleset forbids moving or deleting tags) and because the build of a tag is
the same bytes every time. No clock: the same tags give the same tree.
"""
import argparse, hashlib, html, io, json, os, shutil, subprocess, sys, tarfile, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SITE = 'https://data.php.oct.2026.newsroom.sgit.ai'
KEEP_PLAIN = 5


def git(*a, binary=False):
    r = subprocess.run(['git', '-C', ROOT, *a], capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode()


def archive():
    """The last commit that held v/ in the tree: the parent of the commit that removed it (27 October 2026). Every
    version published before CI owned the version is read from there, as it was. None in a repository that never had v/."""
    try:
        gone = git('log', '-1', '--diff-filter=D', '--format=%H', 'HEAD', '--', 'v/').strip()
        return git('rev-parse', gone + '^').strip() if gone else None
    except subprocess.CalledProcessError:
        return None


def before_ci(ref):
    """The versions published as folders before CI owned the version."""
    if not ref: return []
    try: return [x for x in git('ls-tree', '--name-only', f'{ref}:v').split() if x[:1].isdigit()]
    except subprocess.CalledProcessError: return []


def vkey(v):
    return tuple(int(x) for x in v.split('.'))


def tags():
    out = [t[1:] for t in git('tag', '-l', 'v[0-9]*.[0-9]*.[0-9]*').split()]
    return sorted(out, key=vkey)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 16), b''):
            h.update(c)
    return h.hexdigest()


def walk(top):
    out = []
    for d, dirs, fs in os.walk(top):
        dirs.sort()
        for f in sorted(fs):
            out.append(os.path.relpath(os.path.join(d, f), top).replace(os.sep, '/'))
    return sorted(out)


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True); f.write('\n')


def extract(ref, paths, dst):
    """The paths at ref, unpacked into dst; False when ref or a path is not there."""
    try:
        data = git('archive', ref, *paths, binary=True)
    except subprocess.CalledProcessError:
        return False
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(dst, filter='data')
    return True


def build_version(src, dst, version):
    """A version folder at dst from a tree src (files/, schemas/, tools/catalogue.json, tools/imported.json)."""
    cat = json.load(open(os.path.join(src, 'tools', 'catalogue.json')))['files']
    def group_of(n):
        for c in cat:
            if n == c['name'] or (c['name'].endswith('/') and n.startswith(c['name'])):
                return c['group']
    names = []
    for c in cat:
        n = c['name']
        names += [n + p for p in walk(os.path.join(src, 'files', n.rstrip('/')))] if n.endswith('/') else [n]
    files = []
    for n in sorted(names):
        s = os.path.join(src, 'files', n)
        os.makedirs(os.path.dirname(os.path.join(dst, n)), exist_ok=True)
        shutil.copyfile(s, os.path.join(dst, n))
        sch = n.replace('.json', '.schema.json') if '/' not in n else None
        if sch and os.path.exists(os.path.join(src, 'schemas', sch)):
            os.makedirs(os.path.join(dst, 'schemas'), exist_ok=True)
            shutil.copyfile(os.path.join(src, 'schemas', sch), os.path.join(dst, 'schemas', sch))
        else:
            sch = None
        files.append({'name': n, 'group': group_of(n), 'bytes': os.path.getsize(s), 'sha256': sha(s), 'schema': f'schemas/{sch}' if sch else None})
    imp = os.path.join(src, 'tools', 'imported.json')
    imported = json.load(open(imp)) if os.path.exists(imp) else {}
    # as every version has been published: the import record spread in, then the version's own fields over it
    manifest = {'api': 'php.oct.2026 newsroom data', 'version': version, 'url': f'{SITE}/v/{version}/', **imported, 'files': files}
    dump(os.path.join(dst, 'manifest.json'), manifest)
    return manifest


def index_html(hist, manifest):
    E = lambda s: html.escape(str(s if s is not None else ''), quote=True)
    rows = ''.join(f'<tr><td><a href="v/{E(h["version"])}/manifest.json">v{E(h["version"])}</a></td><td>{E(h["data_as_of"])}</td>'
                   f'<td>{len(h["changed"])} of {h["files"]}</td></tr>' for h in hist)
    files = ''.join(f'<tr><td><a href="latest/{E(f["name"])}">{E(f["name"])}</a></td><td>{E(f["group"])}</td><td>{f["bytes"]:,}</td><td><code>{E(f["sha256"][:12])}</code></td>'
                    f'<td>{"<a href=" + chr(34) + "latest/" + E(f["schema"]) + chr(34) + ">schema</a>" if f["schema"] else ""}</td></tr>' for f in manifest['files'] if '/' not in f['name'])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>PHP October 2026: the data</title>
<style>:root{{color-scheme:light dark}}body{{font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:0 auto;padding:16px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #8884}}code{{font-size:13px}}.tw{{overflow-x:auto}}</style></head>
<body>
<h1>PHP October 2026: the data</h1>
<p>The data behind <a href="https://php.oct.2026.newsroom.sgit.ai/">php.oct.2026.newsroom.sgit.ai</a>. <code>/latest/&lt;file&gt;</code> is the newest version; every version's <code>/v/&lt;version&gt;/manifest.json</code> lists each file with its sha256, and <code>/blobs/&lt;sha256&gt;</code> serves that exact content for any version, so a pinned version can always be read and checked. The newest {KEEP_PLAIN} versions are also served plain, at <code>/v/&lt;version&gt;/&lt;file&gt;</code>.</p>
<p>Latest: <a href="v/{E(manifest["version"])}/manifest.json">v{E(manifest["version"])}</a>, data as of {E(manifest.get("data_as_of"))}. The history is <a href="versions.json">versions.json</a>.</p>
<h2>Files</h2>
<div class="tw"><table><thead><tr><th>File</th><th>Group</th><th>Bytes</th><th>sha256</th><th></th></tr></thead><tbody>{files}</tbody></table></div>
<h2>Versions</h2>
<div class="tw"><table><thead><tr><th>Version</th><th>Data as of</th><th>Files changed</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Kept in <a href="https://github.com/SGit-AI/SGit-AI__Website__Newsroom__2026__Oct__PHP__data">SGit-AI__Website__Newsroom__2026__Oct__PHP__data</a>; a version is a tag there.</p>
</body></html>
'''


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--into', required=True)
    out = os.path.abspath(ap.parse_args().into)
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    arch = archive()
    vs = sorted(set(tags()) | set(before_ci(arch)), key=vkey)   # every version: the folders published before CI, then CI's tags
    if not vs:
        sys.exit('package: no version tags yet')
    hist, prev, blobs, manifest = [], {}, 0, None
    before_ci_set = set(before_ci(arch))
    for i, v in enumerate(vs):
        tmp = tempfile.mkdtemp()
        try:
            vdir = os.path.join(tmp, '_v')
            if arch and v in before_ci_set and extract(arch, [f'v/{v}'], tmp):           # published before CI minted versions: from the archive, as it was
                os.rename(os.path.join(tmp, 'v', v), vdir)
                manifest = json.load(open(os.path.join(vdir, 'manifest.json'), encoding='utf-8'))
            else:                                          # minted by CI: built from the tag's files, schemas and tools
                extract(f'v{v}', ['files', 'schemas', 'tools'], tmp)
                manifest = build_version(tmp, vdir, v)
            for f in manifest['files']:                       # each content once
                b = os.path.join(out, 'blobs', f['sha256'])
                if not os.path.exists(b):
                    os.makedirs(os.path.dirname(b), exist_ok=True); shutil.copyfile(os.path.join(vdir, f['name']), b); blobs += 1
            plain = i >= len(vs) - KEEP_PLAIN
            if plain:
                shutil.copytree(vdir, os.path.join(out, 'v', v))
            else:
                dump(os.path.join(out, 'v', v, 'manifest.json'), manifest)
            if i == len(vs) - 1:
                shutil.copytree(vdir, os.path.join(out, 'latest'))
            cur = {f['name']: f['sha256'] for f in manifest['files']}
            hist.append({'version': v, 'from': manifest.get('from'), 'data_as_of': manifest.get('data_as_of'), 'evidence_vault_head': manifest.get('evidence_vault_head'),
                         'files': len(cur), 'changed': sorted(n for n in cur if prev.get(n) != cur[n]), 'removed': sorted(set(prev) - set(cur))})
            prev = cur
        finally:
            shutil.rmtree(tmp)
    hist.reverse()
    dump(os.path.join(out, 'versions.json'), {'api': 'php.oct.2026 newsroom data', 'latest': vs[-1], 'versions': hist})
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(index_html(hist, manifest))
    with open(os.path.join(out, '.nojekyll'), 'w') as f:
        pass
    if os.path.exists(os.path.join(ROOT, 'CNAME')):
        shutil.copyfile(os.path.join(ROOT, 'CNAME'), os.path.join(out, 'CNAME'))
    size = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(out) for x in fs)
    print(f'package: {len(vs)} versions (v{vs[0]} to v{vs[-1]}), {blobs} blobs, {min(KEEP_PLAIN, len(vs))} plain, {size / 1e6:.0f} MB')


if __name__ == '__main__':
    main()

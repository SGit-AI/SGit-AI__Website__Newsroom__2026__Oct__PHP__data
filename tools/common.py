"""Shared by the data repository's tools: paths, hashing, the catalogue, and a small JSON Schema subset.

The schema subset is what tools/schema.py writes and tools/gate.py checks: type (one or several), properties,
required and items. It is enough to say "this file is a list of objects that each have an id and sources", which is
the contract a consumer pins; it needs nothing installed, so every agent's session can run the gate.
"""
import hashlib, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FILES = os.path.join(ROOT, 'files')        # the working copy the writers edit
SCHEMAS = os.path.join(ROOT, 'schemas')    # one schema per top-level file
PUBLISHED = os.path.join(ROOT, 'v')        # v/<version>/: immutable once released
LATEST = os.path.join(ROOT, 'latest')      # a copy of the newest version


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def dump_json(path, data, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        else:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def catalogue():
    return load_json(os.path.join(ROOT, 'tools', 'catalogue.json'))['files']


def walk(top):
    """Every file under top, as a sorted list of paths relative to top, with forward slashes."""
    out = []
    for d, dirs, files in os.walk(top):
        dirs.sort()
        for f in sorted(files):
            out.append(os.path.relpath(os.path.join(d, f), top).replace(os.sep, '/'))
    return sorted(out)


def published_names():
    """The files a version publishes: every catalogue file, and every file inside a catalogue folder."""
    names = []
    for c in catalogue():
        n = c['name']
        if n.endswith('/'):
            names += [n + p for p in walk(os.path.join(FILES, n.rstrip('/')))]
        else:
            names.append(n)
    return sorted(names)


def group_of(name):
    for c in catalogue():
        n = c['name']
        if name == n or (n.endswith('/') and name.startswith(n)):
            return c['group']
    return None


def vkey(v):
    return tuple(int(x) for x in v.split('.'))


def versions():
    if not os.path.isdir(PUBLISHED):
        return []
    return sorted((d for d in os.listdir(PUBLISHED) if os.path.isfile(os.path.join(PUBLISHED, d, 'manifest.json'))), key=vkey)


# ----------------------------------------------------------------------------- the schema subset

def kind(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'boolean'
    if isinstance(v, (int, float)):
        return 'number'
    if isinstance(v, str):
        return 'string'
    if isinstance(v, list):
        return 'array'
    return 'object'


def validate(value, schema, path='$'):
    """Errors, as 'path: message' strings; [] when value fits schema."""
    errs = []
    want = schema.get('type')
    if want:
        allowed = want if isinstance(want, list) else [want]
        if kind(value) not in allowed:
            return [f'{path}: is {kind(value)}, expected {" or ".join(allowed)}']
    if isinstance(value, dict):
        for k in schema.get('required', []):
            if k not in value:
                errs.append(f'{path}: missing "{k}"')
        props = schema.get('properties', {})
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f'{path}.{k}')
    elif isinstance(value, list) and 'items' in schema:
        for i, v in enumerate(value):
            errs += validate(v, schema['items'], f'{path}[{i}]')
            if len(errs) > 20:
                break
    return errs

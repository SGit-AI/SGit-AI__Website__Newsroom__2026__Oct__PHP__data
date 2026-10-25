#!/usr/bin/env python3
"""Write a schema for every top-level file in files/, inferred from the file as it is now.

    python3 tools/schema.py           writes schemas/<name>.schema.json for every catalogue file that has none
    python3 tools/schema.py --again   rewrites every schema (after a deliberate change of shape, in its own release)

A schema says what a consumer may rely on: the type of the file, the keys every object has, and the type of each
value, three levels deep. It is inferred once and then kept: the gate fails when a file stops fitting its schema, so
a change of shape is a decision (rewrite the schema, in its own release, said in its message) and never an accident. Files inside a
catalogue folder (wikipedia/) are checked as JSON and by their sha256 only.
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from common import FILES, SCHEMAS, catalogue, dump_json, kind, load_json  # noqa: E402

DEPTH = 3


def merge(a, b):
    """One schema that fits whatever a and b fit: types joined, required keys intersected, properties merged."""
    ta = a.get('type') if isinstance(a.get('type'), list) else [a.get('type')]
    tb = b.get('type') if isinstance(b.get('type'), list) else [b.get('type')]
    types = sorted(set(t for t in ta + tb if t))
    out = {'type': types[0] if len(types) == 1 else types}
    if 'properties' in a or 'properties' in b:
        pa, pb = a.get('properties', {}), b.get('properties', {})
        out['properties'] = {k: merge(pa[k], pb[k]) if k in pa and k in pb else (pa.get(k) or pb.get(k)) for k in sorted(set(pa) | set(pb))}
        ra = set(a.get('required', [])) if 'object' in ta else None
        rb = set(b.get('required', [])) if 'object' in tb else None
        req = (ra & rb) if ra is not None and rb is not None else (ra if ra is not None else rb)
        if req:
            out['required'] = sorted(req)
    if 'items' in a or 'items' in b:
        out['items'] = merge(a['items'], b['items']) if 'items' in a and 'items' in b else (a.get('items') or b.get('items'))
    return out


def infer(v, depth=0):
    k = kind(v)
    if k == 'object':
        s = {'type': 'object'}
        if depth < DEPTH:
            s['properties'] = {key: infer(val, depth + 1) for key, val in sorted(v.items())}
            s['required'] = sorted(v)
        return s
    if k == 'array':
        s = {'type': 'array'}
        if v and depth < DEPTH:
            item = infer(v[0], depth + 1)
            for x in v[1:]:
                item = merge(item, infer(x, depth + 1))
            s['items'] = item
        return s
    return {'type': k}


def main(again=False):
    wrote = 0
    for c in catalogue():
        n = c['name']
        if n.endswith('/'):
            continue
        out = os.path.join(SCHEMAS, n.replace('.json', '.schema.json'))
        if os.path.exists(out) and not again:
            continue
        s = infer(load_json(os.path.join(FILES, n)))
        s = {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': n, **s}
        dump_json(out, s)
        wrote += 1
    print(f'schemas: {wrote} written')


if __name__ == '__main__':
    main(again='--again' in sys.argv[1:])

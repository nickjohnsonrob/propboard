#!/usr/bin/env python3
"""Build tennis-2026-09-25 page: inject tennis JSON into the template."""
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(ROOT, 'output', 'tennis-2026-09-25.json')))
blob = (json.dumps(data, ensure_ascii=True)
        .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))
tpl = open(os.path.join(ROOT, 'templates', 'tennis.html')).read()
out = os.path.join(ROOT, 'tennis.html')  # GH Pages serves repo root
html = tpl.replace('__DATA__', blob)
open(out, 'w').write(html)
print(f'wrote {out} ({len(html)} bytes)')

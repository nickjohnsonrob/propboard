#!/usr/bin/env python3
"""PropBoard build: inject board.json into the HTML template and write index.html.

Usage: python3 build.py [board.json] [out.html]
Called by the cron/GitHub Action after a fresh scrape updates board.json.
"""
import json, os, sys, html as _html

ROOT = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(ROOT, 'templates', 'index.html')
board_in = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'output', 'board.json')
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'output', 'index.html')

with open(board_in) as f:
    data = json.load(f)

# sanitize: embed as valid JSON, escape <, >, & as unicode escapes so the
# data can never break out of the <script> block (players/teams only carry
# such chars in edge cases, but stay safe)
blob = (json.dumps(data, ensure_ascii=True)
        .replace('<', '\u003c').replace('>', '\u003e').replace('&', '\u0026'))
with open(TPL) as f:
    tpl = f.read()
html = tpl.replace('__DATA__', blob)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w') as f:
    f.write(html)
print(f'wrote {out} ({len(html)} bytes, {len(data.get("rows", []))} props)')


#!/usr/bin/env python3
"""PropBoard updater v2 — multi-market NFL player props.

Stdlib only; runs headless in cron / GitHub Actions.
Covers all markets BetIQ exposes per game: passing (yds/TDs/comps/ATTs/INTs/
longest), rushing (yds/ATTs/longest), receiving (yds/receptions/longest),
TD scorers (anytime/first/2+), combos (Pass+Rush, Rush+Rec), kicking
(points/FG/XP), defensive (Tackles, Assists, Tackles+Assists).
NOTE: BetIQ does NOT carry Sacks or Targets — those need a separate feed (see README).

Pipeline:
  matchups page -> game slugs -> slug page -> game id -> per-game market pages
  -> rows (line, side, L10%, best-across-books + DK price, locked flag)
  -> output/board.json -> build.py -> index.html
"""
import urllib.request, re, json, os, sys, time
from collections import Counter
from datetime import datetime

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'output')

# one slug per market-group; each page returns that whole group
GROUP_SLUGS = ['passing-yards', 'rushing-yards', 'receiving-yards',
               'anytime-touchdown', 'tackles-assists']
# markets to include (skips weird extras if the page ever has any)
MARKET_ORDER = ['Passing Yards','Passing Touchdowns','Passing Completions','Passing Attempts',
                'Passing Interceptions','Longest Passing Completion','Rushing Yards','Rushing Attempts',
                'Longest Rush','Receiving Yards','Receptions','Longest Reception',
                'Anytime Touchdown Scorer','First Touchdown Scorer','To Score 2 or More TDs',
                'Passing + Rushing Yards','Rushing + Receiving Yards','Total Kicking Points',
                'Field Goals Made','Extra Points Made','Total Tackles','Total Assists','Tackles + Assists']

def fetch(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8', 'ignore')
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2)

def textify(html):
    txt = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    txt = re.sub(r'<style.*?</style>', ' ', txt, flags=re.S)
    txt = re.sub(r'<[^>]+>', '\n', txt)
    t = txt.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#039;', "'")
    return [l.strip() for l in t.split('\n') if l.strip()]

def implied(p):
    p = str(p).replace('+', '').replace('\u2212', '-')
    try:
        a = int(p)
    except Exception:
        return None
    return ((100 if a > 0 else -a) / (abs(a) + 100.0))

def enumerate_games():
    html = fetch('https://betiq.teamrankings.com/nfl/props/player/matchups/')
    slugs = re.findall(r'href="(/nfl/props/player/([a-z0-9\-]+-vs-[a-z0-9\-]+)/)"', html)
    out, seen = [], set()
    for _, slug in slugs:
        if slug in seen:
            continue
        seen.add(slug)
        out.append({'slug': slug, 'label': slug.replace('-vs-', ' @ ')})
    return out

def game_id(slug):
    html = fetch(f'https://betiq.teamrankings.com/nfl/props/player/{slug}/')
    ids = re.findall(r'\?game=(\d+)', html)
    return Counter(ids).most_common(1)[0][0] if ids else None

META_RE = re.compile(r'^#\d+ [^A-Z]{1,3} (.{1,6}) [^A-Z]{1,3} ([A-Z]{2,4})$')
# allow posizations like 'S' 'LB' 'CB' 'DE' 'DL' 'DT' 'WR/DB'? keep simple letter codes
POS_RE = re.compile(r'^[A-Z]{1,6}$')

def parse_market_page(html):
    """Parse ALL market sections on one BetIQ game page -> list of row dicts."""
    lines = textify(html)
    sections = {}   # market name -> [row dicts]
    closed = 'at close' in ' '.join(lines)
    for i, l in enumerate(lines):
        if i + 1 < len(lines) and re.match(r'^\d+ props?$', lines[i + 1]) and l in MARKET_ORDER:
            market = l
            _closed = closed
            j = i + 2
            while j < len(lines) and lines[j] != 'Sort:':
                j += 1
            j += 1
            while j < len(lines) and lines[j] in ('Over %', 'Kickoff time', 'Rising', 'Falling',
                                                 'Highest line', 'Lowest line', 'Over hit rate', 'Under hit rate', 'Highest'):
                j += 1
            blocks = []
            while j < len(lines):
                l2 = lines[j]
                if re.match(r'^View all \d+', l2) or (j + 1 < len(lines) and lines[j + 1].startswith('props') and lines[j] in MARKET_ORDER) or lines[j] in MARKET_ORDER or re.match(r'^(Best price|NFL Predictions|NFL Player Props)', l2):
                    break
                m = re.match(r'^#\d+ ', l2)
                if m:
                    meta = l2
                    name = lines[j - 1]
                    k = j + 1
                    prop = line = None
                    over = under = None
                    odds = []
                    while k < len(lines) and k < j + 50:
                        b = lines[k]
                        if re.match(r'^#\d+ ', b) or b in MARKET_ORDER or (k + 1 < len(lines) and lines[k + 1] == 'props' and b in MARKET_ORDER):
                            break
                        if prop is None and b not in ('Line', 'Price', 'Last 10', 'Over %'):
                            # first token after meta = prop label (e.g. "Pass Yds")
                            prop = b
                            line = lines[k + 1] if k + 1 < len(lines) else None
                        mm = re.match(r'^(\d+)% over$', b)
                        if mm and over is None:
                            over = int(mm.group(1))
                        mm = re.match(r'^(\d+)% under$', b)
                        if mm and under is None:
                            under = int(mm.group(1))
                        if b in ('Over', 'Under'):
                            odds.append({'side': b,
                                         'price': lines[k + 1] if k + 1 < len(lines) else '',
                                         'book': lines[k + 2] if k + 2 < len(lines) else ''})
                        k += 1
                    # meta is '#N · POS · TEAM' (jersey optional) -> team=last token, pos=2nd-to-last
                    parts = [p for p in meta.replace('#', '').replace('\u00b7', ' ').split(' ') if p and re.match(r'^[A-Z0-9]{1,4}$', p)]
                    team = parts[-1] if parts else None
                    pos = parts[-2] if len(parts) >= 2 else None
                    # sample = game logs between 'Last 10' and the first '% over'/'% under'
                    sample = 0
                    lt10 = next((z for z in range(j, k) if lines[z] == 'Last 10'), None)
                    if lt10 is not None:
                        for z in range(lt10 + 1, k):
                            if re.match(r'^\d+% (over|under)$', lines[z]):
                                break
                            if re.match(r'^@?[A-Z]{2,3} \d+ \(', lines[z]):
                                sample += 1
                    blocks.append({'name': name, 'prop': prop, 'line': line,
                                   'over_pct': over, 'under_pct': under, 'odds': odds,
                                   'pos': pos, 'team': team, 'sample': sample, 'locked': _closed})
                    nxt = j + 1
                    while nxt < len(lines) and not re.match(r'^#\d+ ', lines[nxt]) and not (lines[nxt] in MARKET_ORDER) and not re.match(r'^View all \d+', lines[nxt]):
                        nxt += 1
                    j = nxt
                    continue
                j += 1
            sections[market] = blocks
    return sections

def ok_row(r):
    return (r['over_pct'] is not None or r['under_pct'] is not None)

def best(odds, side):
    cands = [o for o in odds if o.get('side') == side]
    if not cands:
        return {}
    best = max(cands, key=lambda o: implied(o.get('price')) or 0)
    dk = next((o for o in cands if o.get('book') == 'DK'), None)
    return {'price': best.get('price'), 'book': best.get('book'), 'dk': dk.get('price') if dk else None}

def build_rows(games):
    rows = []
    for g in games:
        try:
            sections = {}
            for slug in GROUP_SLUGS:
                try:
                    page = parse_market_page(fetch(f'https://betiq.teamrankings.com/nfl/props/{slug}/?game={g["tid"]}'))
                    for mk, bl in page.items():
                        sections.setdefault(mk, [])
                        sections[mk] = bl  # sections repeat across slugs; keep last
                except Exception as e:
                    print(f"  ! {g['game']} {slug}: {e}")
            for mk in MARKET_ORDER:
                for r in sections.get(mk, []):
                    if not ok_row(r):
                        continue
                    best_o = best(r['odds'], 'Over')
                    best_u = best(r['odds'], 'Under')
                    cands = []
                    if r['over_pct'] and best_o:
                        cands.append(('O', r['over_pct'], best_o))
                    if r['under_pct'] and best_u:
                        cands.append(('U', r['under_pct'], best_u))
                    for side, pct, px in cands:
                        ip = implied(px['price'])
                        hist = pct / 100.0
                        rows.append({
                            'game': g['game'], 'name': r['name'], 'pos': r['pos'], 'team': r['team'],
                            'market': mk, 'prop': r['prop'], 'line': r['line'],
                            'side': side, 'pct': pct, 'sample': r.get('sample', 0), 'locked': r.get('locked', False),
                            'price': px['price'], 'book': px['book'], 'dk': px['dk'],
                            'mkt': round(ip * 100, 1) if ip is not None else None,
                            'hist': round(hist * 100, 1),
                            'edge': round((hist - (ip or 0)) * 100, 1),
                        })
        except Exception as e:
            print(f"  !! {g['game']}: {e}")
    return rows

def main():
    games = enumerate_games()
    print(f'games on slate: {len(games)}')
    gs = []
    for g in games:
        tid = game_id(g['slug'])
        if tid:
            gs.append({'game': g['label'], 'tid': tid})
            print(f"  {g['label']:16s} id={tid}")
        time.sleep(0.2)
    rows = build_rows(gs)
    rows.sort(key=lambda r: (-r['hist'], -r['edge']))
    now = datetime.now().astimezone()
    os.makedirs(OUT, exist_ok=True)
    try:
        mhtml = fetch('https://betiq.teamrankings.com/nfl/props/player/matchups/')
        wm = re.search(r'Week (\d+)', mhtml)
        week = f'Week {wm.group(1)}' if wm else ''
    except Exception:
        week = ''
    board = {'generated': now.strftime('%Y-%m-%d %H:%M %Z'),
             'sport': 'NFL', 'week': week, 'date_label': now.strftime('%a %b %d %Y'),
             'markets': MARKET_ORDER, 'rows': rows}
    json.dump(board, open(os.path.join(OUT, 'board.json'), 'w'), indent=1)
    print(f'wrote board.json: {len(rows)} props')

if __name__ == '__main__':
    main()

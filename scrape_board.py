#!/usr/bin/env python3
"""PropBoard daily updater — stdlib only, runs headless in cron / GitHub Actions.

Pipeline:
  1. Fetch BetIQ player-props matchups page -> enumerate today's game slugs
     (e.g. 'broncos-vs-jaguars'). Slugs leave the slate order to the site.
  2. Each slug's player page carries its numeric game id (?game=NNN).
  3. Scrape the per-game tackles-assists market page, parse T+A lines,
     L10 hit %, and best-across-books plus DK prices.
  4. Write output/board-<date>.json AND output/board.json + regenerate HTML.
"""
import urllib.request, re, json, os, sys, time
from collections import Counter
from datetime import datetime

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'output')

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

STAT_SKIP = ('Kickoff time', 'Rising', 'Falling', 'Highest line', 'Lowest line', 'Over hit rate', 'Under hit rate')

def implied(p):
    p = str(p).replace('+', '').replace('\u2212', '-')
    try:
        a = int(p)
    except Exception:
        return None
    return ((100 if a > 0 else -a) / (abs(a) + 100.0))

def enumerate_games():
    """Return [{'slug','label','teamA','teamB'}] for the current slate from the matchups page."""
    html = fetch('https://betiq.teamrankings.com/nfl/props/player/matchups/')
    slugs = re.findall(r'href="(/nfl/props/player/([a-z0-9\-]+-vs-[a-z0-9\-]+)/)"', html)
    games = []
    for _, slug in dict(slugs).items():
        label = slug.replace('-vs-', ' @ ')
        if label.lower() == slug.replace('-vs-', ' @ ').lower():
            pass
        g = {'slug': slug, 'label': label}
        games.append(g)
    # dedupe by slug, keep order
    seen = set(); out = []
    for g in games:
        if g['slug'] not in seen:
            seen.add(g['slug']); out.append(g)
    return out

def game_id(slug):
    html = fetch(f'https://betiq.teamrankings.com/nfl/props/player/{slug}/')
    ids = re.findall(r'\?game=(\d+)', html)
    return Counter(ids).most_common(1)[0][0] if ids else None

def implied_best(odds, side):
    cands = [o for o in odds if o.get('side') == side]
    if not cands:
        return {}
    best = max(cands, key=lambda o: implied(o.get('price')) or 0)
    dk = next((o for o in cands if o.get('book') == 'DK'), None)
    return {'price': best.get('price'), 'book': best.get('book'), 'dk': dk.get('price') if dk else None}

def scrape_game(gid):
    url = f'https://betiq.teamrankings.com/nfl/props/tackles-assists/?game={gid}&sort=over_hits'
    lines = textify(fetch(url))
    # lock detection: 'at close' prices appear on started/locked games
    locked = 'at close' in ' '.join(lines)
    rows = []
    for i, l in enumerate(lines):
        if l == 'Tackles + Assists' and i + 1 < len(lines) and re.match(r'^\d+ props?$', lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j] != 'Sort:':
                j += 1
            j += 1
            while j < len(lines) and lines[j] in STAT_SKIP or (j < len(lines) and lines[j] in ('Over %', 'Highest')):
                j += 1
            while j < len(lines):
                l2 = lines[j]
                if re.match(r'^View all \d+|^Total (Tackles|Assists)|^(Field Goals|Total Kicking|Extra Points|Passing|Rushing|Receiving)', l2):
                    break
                m = re.match(r'^#\d+ \S+ ([A-Z]{2,3} \S+ )?([A-Z]{2,3}) \S+ \S+ ([A-Z]{2,3})$', l2) or \
                    re.match(r'^#\d+ \S+ ([A-Z0-9/]{1,3}) \S+ ([A-Z]{2,3})$', l2)
                if re.match(r'^#\d+ ', l2):
                    meta = l2
                    name = lines[j - 1]
                    k = j + 1
                    line = price = None
                    over = under = None
                    odds = []
                    logs = []
                    while k < len(lines) and k < j + 60:
                        b = lines[k]
                        if re.match(r'^#\d+ |^View all \d+|^Total (Tackles|Assists)|^(Field Goals|Total Kicking|Extra Points|Passing|Rushing|Receiving)', b):
                            break
                        if line is None and b == 'Tack+Ast':
                            line = lines[k + 1] if k + 1 < len(lines) else None
                        if price is None and b == 'Price':
                            price = lines[k + 1] if k + 1 < len(lines) else None
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
                    # team from meta: last 2-3 letters usually; be defensive
                    parts = meta.replace('#', '').replace('\u00b7', ' ').split(' ')
                    parts = [p for p in parts if p]
                    pos = None
                    team = None
                    for cand in reversed(parts):
                        if re.match(r'^[A-Z]{1,4}$', cand):
                            if team is None:
                                team = cand
                            else:
                                pos = cand
                                break
                    rows.append({'name': name, 'line': line, 'price': price,
                                 'over_pct': over, 'under_pct': under, 'odds': odds,
                                 'meta': meta, 'pos': pos, 'team': team, 'locked': locked})
                    # advance past this block
                    nxt = j + 1
                    while nxt < len(lines) and not re.match(r'^#\d+ ', lines[nxt]) and not re.match(r'^View all \d+', lines[nxt]):
                        nxt += 1
                    j = nxt
                    continue
                j += 1
    return rows

def build_rows(games):
    """games: list of {'game', 'tid'} -> ranked prop rows for board.json."""
    recs = []
    for g in games:
        try:
            prows = scrape_game(g['tid'])
        except Exception as e:
            print(f"  ! {g['game']}: {e}")
            continue
        for r in prows:
            if r['over_pct'] is None and r['under_pct'] is None:
                continue
            rec = {'game': g['game'], 'name': r['name'], 'pos': None, 'team': r['team'],
                   'line': r['line'], 'price': r['price'],
                   'hist_pct': r['over_pct'] if r['over_pct'] is not None else 100 - (r['under_pct'] or 0)}
            # two candidates: over and under
            best_o = implied_best(r['odds'], 'Over')
            best_u = implied_best(r['odds'], 'Under')
            cands = []
            if r['over_pct'] is not None and best_o:
                cands.append({'side': 'O', 'pct': r['over_pct'], 'px': best_o})
            if r['under_pct'] is not None and best_u:
                cands.append({'side': 'U', 'pct': r['under_pct'], 'px': best_u})
            for c in cands:
                ip = implied(c['px']['price'])
                hist = c['pct'] / 100.0
                recs.append({
                    'game': g['game'], 'name': r['name'], 'pos': r['pos'], 'team': r['team'],
                    'line': r['line'], 'side': c['side'], 'pct': c['pct'],
                    'price': c['px']['price'], 'book': c['px']['book'],
                    'dk': c['px']['dk'], 'locked': r.get('locked', False),
                    'mkt': round(ip * 100, 1) if ip is not None else None,
                    'hist': round(hist * 100, 1),
                    'edge': round(hist - (ip or 0), 3) * 100,
                })
    return recs

def run():
    games = enumerate_games()
    print(f'games on slate: {len(games)}')
    gs = []
    for g in games:
        tid = game_id(g['slug'])
        if tid:
            gs.append({'game': g['label'], 'tid': tid})
            print(f"  {g['label']:14s} id={tid}")
        time.sleep(0.3)
    rows = build_rows(gs)
    rows.sort(key=lambda r: (-r['hist'], -r['edge']))
    now = datetime.now().astimezone()
    os.makedirs(OUT, exist_ok=True)
    # derive week label from the matchups page title if available
    try:
        mhtml = fetch('https://betiq.teamrankings.com/nfl/props/player/matchups/')
        wm = re.search(r'Week (\d+)', mhtml)
        week = f'Week {wm.group(1)}' if wm else ''
    except Exception:
        week = ''
    board = {'generated': now.strftime('%Y-%m-%d %H:%M %Z'),
             'sport': 'NFL', 'week': week, 'date_label': now.strftime('%a %b %d %Y'), 'rows': rows}
    json.dump(board, open(os.path.join(OUT, 'board.json'), 'w'), indent=1)
    print(f'wrote board.json with {len(rows)} props')

if __name__ == '__main__':
    run()

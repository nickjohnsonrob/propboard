# PropBoard

Auto-updating NFL player-prop board — all markets, ranked by L10 hit%.
Data scraped from BetIQ/TeamRankings per-game prop pages; static, filterable,
mobile-friendly page served by GitHub Pages.

## Markets covered (23)
Passing: Yards / TDs / Completions / Attempts / INTs / Longest Pass
Rushing: Yards / Attempts / Longest Rush
Receiving: Yards / Receptions / Longest Reception
TDs: Anytime / First / 2+ TDs
Combos: Pass+Rush Yds / Rush+Rec Yds
Kicking: Kicking Points / FG Made / XP Made
Defense: Total Tackles / Assists / Tackles+Assists

**Not covered by BetIQ: Sacks and Targets.** BetIQ exposes no sacks or targets
market on any page (verified vs game pages, market slugs, and player research
pages). If you want those + DK prices, options:
- DraftKings scrape (JS-heavy, state-gated; needs a headless browser + session)
- The Odds API (has NFL Sacks/Targets player props; free tier exists; add an
  API key and a small adapter — ask Kimi to wire it)
- FanDuel research articles (human-read; not auto-board compatible)

## Layout
- `scrape_board.py` — stdlib-only updater: enumerates slate, scrapes the 5
  BetIQ market-group pages per game, parses every market section (line, side,
  L10 over/under %, best-across-books + DK price, sample size, locked flag) ->
  `output/board.json`.
- `build.py` — injects `output/board.json` into `templates/index.html` ->
  `output/index.html`.
- `templates/index.html` — search box, market dropdown, Over/Under filter,
  "hide locked" toggle. Locked = game already started ("at close" prices).
  L10% column shows `(n)` = sample size; treat high % on n<8 as noise.
- `.github/workflows/update.yml` — GitHub Actions cron runs the pipeline and
  commits the fresh page + dated archive (`output/board-YYYY-MM-DD.json`).
  GitHub Pages serves the committed root `index.html`.

## Run locally
```
python3 scrape_board.py   # re-pull data for the current slate (~15-40s)
python3 build.py          # regenerate the page
open output/index.html
```

## Deploy (one-time)
1. git push origin main
2. Repo -> Settings -> Pages -> Deploy from branch: `main` / root.
3. The workflow auto-updates; Pages publishes after each commit.

## Notes
- Prices are snapshots at scrape time; "best across books" per BetIQ. The DK
  column is DraftKings price where quoted. Verify the live DK slip before
  betting — lines move (Bosa T+A moved +129->-112 during a single day).
- L10 = last 10 games (spans prior season, so team changes can mislead).
- BetIQ game IDs change per week; the scraper auto-discovers them from the
  matchups page each run.
- Research only, 21+, where legal.

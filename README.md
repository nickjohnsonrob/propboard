# PropBoard

Auto-updating NFL **Tackles + Assists** player-prop board (ranked by L10 hit%).
Data scraped from BetIQ/TeamRankings per-game prop pages; serves a static,
filterable, mobile-friendly page.

## Layout
- `scrape_board.py` — stdlib-only updater: enumerates the current slate's games,
  scrapes each game's tackles+assists market (line, L10 over/under %, best
  across-books price, DK price where quoted), writes `output/board.json`.
- `build.py` — injects `output/board.json` into `templates/index.html` ->
  `output/index.html`.
- `templates/index.html` — the page (search box, Over/Under filter, "hide locked"
  toggle; locked = game already started, prices are "at close").
- `.github/workflows/update.yml` — GitHub Actions cron runs the whole pipeline
  and commits the fresh page + a dated archive (`output/board-YYYY-MM-DD.json`).
  GitHub Pages then serves the committed root `index.html`.

## Run locally
```
python3 scrape_board.py   # re-pull data for the current slate
python3 build.py          # regenerate the page
open output/index.html
```

## Deploy (one-time)
Serve the `index.html` from anywhere static. Recommended: GitHub Pages /
Cloudflare Pages (both free). For GH Pages:
1. Push this repo to GitHub.
2. Repo -> Settings -> Pages -> Deploy from branch: `main` / root.
3. The workflow auto-updates; Pages publishes after each commit.

## Notes
- Prices are snapshots at scrape time and "best across books" per BetIQ —
  verify the actual DraftKings slip before betting, especially the DK column.
- L10 = last 10 games (spans prior season); small samples, no guarantee.
- Not financial advice; 21+; only where legal.

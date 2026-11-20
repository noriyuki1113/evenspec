# EvenSpec

AI API prices & specs, compared on one fair spec sheet. Static site, generated
with **Python standard library only** — no npm, no Astro, no dependencies to
maintain. Data comes primarily from the LiteLLM dataset (MIT); OpenRouter
prices are shown alongside, labeled and linked, as a reference.

## Local build

```bash
python3 scripts/fetch_data.py --offline   # normalize the cached data in data/raw/
python3 scripts/build_site.py             # writes dist/
# preview:
python3 -m http.server -d dist 8000       # http://localhost:8000
```

To refresh the raw data from the network:

```bash
python3 scripts/fetch_data.py             # fetches LiteLLM + OpenRouter, diffs prices
python3 scripts/build_site.py
```

`fetch_data.py` compares against the previous `data/models.json` and appends
price changes to `data/price_events.json` (the source of /price-drops/).
The first run is a baseline: no events.

## Layout

- `scripts/fetch_data.py` — fetch + normalize → `data/models.json`, `data/price_events.json`
- `scripts/build_site.py` — `data/models.json` → `dist/` (home, /models/, up to 400 model
  detail pages, ~20 /compare/ pages, /price-drops/, /calculators/coding-agent-cost/, /about/,
  sitemap.xml, robots.txt)
- `.github/workflows/update.yml` — daily cron: fetch → build → commit

## Publishing on Cloudflare Pages

1. Push this repository to GitHub.
2. Cloudflare Dashboard → Pages → Create → Connect to Git → select the repo.
3. Build settings:
   - **Build command:** `python3 scripts/fetch_data.py --offline && python3 scripts/build_site.py`
     (use `--offline` so the Pages build uses the committed data; the GitHub
     Actions workflow keeps that data fresh daily)
   - **Build output directory:** `dist`
   - Environment: Python is available on the Pages build image; no other setup.
4. Add the custom domain `evenspec.com` under the Pages project's Custom domains.
5. (Optional) Enable Cloudflare Web Analytics and submit `https://evenspec.com/sitemap.xml`
   in Google Search Console.

## Monthly check (the only routine maintenance)

Once a month, ~10 minutes:

1. GitHub → Actions → "Daily data update" — confirm recent runs are green.
   A red run means a data source changed shape; the live site keeps serving
   the last good build, so there is no urgency.
2. Open /price-drops/ and 2–3 popular model pages; spot-check one price against
   the provider's official pricing page.
3. Check `data/price_events.json` is growing and `data/models.json`
   `generated_at` is current.
4. Glance at Search Console for indexing errors.

## Data & licensing notes

- LiteLLM dataset: MIT License (© BerriAI) — attribution is on /about/ and in
  the site footer.
- OpenRouter prices are reproduced as a labeled reference with a link to the
  model page on openrouter.ai. If OpenRouter's terms change, remove the
  `openrouter` field usage in `scripts/build_site.py` — the site works fully
  on LiteLLM data alone.
- Always-verify disclaimer: prices change frequently; the site tells visitors
  to verify against official provider pricing.

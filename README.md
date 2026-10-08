# Houston Car Finder

Watches Craigslist and CarGurus within 50 miles of Rice every 10 minutes, prices every reliable Honda/Toyota against the local market, and pings your phone when one is underpriced, in budget, and doesn't look like it needs work.

Inspired by [carbuyer](https://github.com/Dropio12/used-car-deal-finder) from Hack the North. Same idea, rebuilt from scratch in Python for Houston, a sub-$6k budget, and "little to no work."

## How it works

```
GitHub Actions (every 10 min)
   │
   ├─ CarGurus ── dealer cars + CarGurus' own market value per car
   ├─ Craigslist ─ private + dealer ads, opens each new ad for year/miles/title/VIN
   │
   ▼
 filters.py ── reject: wrong model, >170k mi, <2005, branded title, <20 mpg,
   │           finance/down-payment ads, "mechanic special", keyword spam
   │           warn:   flood/water words, check engine, paint/body words
   ▼
 pricing.py ── per model, fits  log(value) = a + b·(year) + c·(miles/10k)
   │           on every CarGurus car it has seen (45 days of history),
   │           then predicts this exact car's value. Private sellers get
   │           an 8% discount on that value (private cars sell for less).
   ▼
 reliability.py ─ known problem years + NHTSA complaint spikes
   ▼
 vision.py ── Claude Haiku looks at up to 4 photos: paint, body, rust, flood signs
   ▼
 tiers:  Deal      ≤ $6,000 and ≥ 10% under market        → phone alert
         Stretch   ≤ $7,500, Tacoma/CR-V, ≥ 20% under      → phone alert
         Austin    ≤ $6,000, ≥ 25% under, ≤150k, no flags  → phone alert
         Under $6k / Stretch (everything else that passes) → dashboard only
   ▼
 data branch ── history + dashboard, served by GitHub Pages
```

Each car alerts once per price. If the price drops again, you get pinged again.

## Things it can't do for you

- **Flood history.** Houston's biggest used-car risk. The dashboard has a "Flood check" button that copies the VIN and opens NICB's free VINCheck (it has a captcha, so it can't be automated). Run it on any car before you drive out, and get a Carfax or AutoCheck on the finalist.
- **Facebook Marketplace.** It's where a lot of Houston private sales happen, but it requires a login and blocks bots. Check it by hand.

## Setup (one time)

1. **Phone alerts:** install the free **ntfy** app (iOS/Android), tap +, and subscribe to a topic name nobody would guess, like `daniel-cars-` plus random letters.
2. **GitHub secrets:** repo → Settings → Secrets and variables → Actions → New repository secret
   - `NTFY_TOPIC` = that same topic name
   - `ANTHROPIC_API_KEY` = a key from platform.claude.com/settings/keys (optional; enables photo checks. API credit is billed separately from a Claude Pro plan; $5 lasts months)
3. **Run it:** Actions tab → crawl → Run workflow. After that it runs itself every 10 minutes.

The first run records everything already listed without alerting, so you don't get 40 pings at once.

## Tweaking

Everything you'd change lives in `config.yml`: budget, models, mileage cap, radius, deal thresholds, Austin rules, photo-check cap.

Run locally (no alerts): `pip install -r requirements.txt && python -m carfinder.run --state state --quiet`, then open `state/data.json`.

Tests: `pip install pytest && python -m pytest -q`

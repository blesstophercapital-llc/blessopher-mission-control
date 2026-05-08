# Maintane Mission Control

Static Cloudflare Pages dashboard for Blessopher Capital / Maintane.

## Architecture

Maintane Mission Control uses a static frontend with a Python-generated data layer.

- `index.html` renders the dashboard UI.
- `mission-control.json` is the frontend data contract.
- `scripts/generate-mission-control.py` pulls, parses, normalizes, and calculates source data.
- Future API integrations should be added to the Python generator first, then exposed through the JSON contract.

This keeps the dashboard cheap and fast on Cloudflare Pages while preserving a clean path to live Shopify, Amazon, TikTok Shop, Klaviyo, and other API integrations later.

## V1 Pages

- Command Center
- Revenue Funnel
- Website Analytics
- SEO Opportunities
- Channel Ops
- Unit Economics
- Action Queue

## Data flow

`index.html` renders from `mission-control.json`.

`mission-control.json` is generated from TomMemory plus live Google metrics when `~/.hermes/google_token.json` is authorized:

- `/Users/christopherbless/TomMemory/Maintane/Maintane-brand-asset 4-19.md`
- `/Users/christopherbless/TomMemory/Tasks.md`
- `/Users/christopherbless/TomMemory/Content-Strategy/Maintane-Content-Strategy.md`
- GA4 property `532192988` / Maintane
- Search Console property `sc-domain:getmaintane.com`

Missing commerce metrics are intentionally labeled as pending/future API data. Do not fake sales, CAC, contribution profit, or order data.

## Update dashboard data

```bash
npm run generate
```

Validate without writing:

```bash
npm run generate:check
```

Override the vault path if needed:

```bash
TOMMEMORY_PATH=/path/to/TomMemory npm run generate
```

## Validation

Run:

```bash
npm run generate:check
python3 -m unittest discover -s tests -v
```

Then commit/push to `main`; Cloudflare Pages should deploy from GitHub if connected.

# Maintane Mission Control

Static Cloudflare Pages dashboard for Blessopher Capital / Maintane.

## Data flow

`index.html` renders from `mission-control.json`.

`mission-control.json` is generated from TomMemory:

- `/Users/christopherbless/TomMemory/Maintane/Maintane-brand-asset 4-19.md`
- `/Users/christopherbless/TomMemory/Tasks.md`
- `/Users/christopherbless/TomMemory/Content-Strategy/Maintane-Content-Strategy.md`

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

Then commit/push to `main`; Cloudflare Pages should deploy from GitHub if connected.

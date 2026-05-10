#!/usr/bin/env python3
"""Generate mission-control.json from TomMemory notes.

This keeps the dashboard data layer editable from the Obsidian vault instead of
hardcoding volatile operating facts into index.html.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path(os.environ.get("TOMMEMORY_PATH", "/Users/christopherbless/TomMemory")).expanduser()
DEFAULT_OUTPUT = REPO_ROOT / "mission-control.json"

TASK_RE = re.compile(
    r"^- \[ \] \[(?P<priority>CRITICAL|HIGH|MEDIUM|LOW)\] (?P<text>.*?)"
    r"(?: \| deadline: (?P<deadline>\d{4}-\d{2}-\d{2}))?"
    r"(?: \| time: (?P<time>[^|]+?))?"
    r"(?: \| owner: (?P<owner>.+?))?$",
    re.I,
)


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required TomMemory note missing: {path}")
    return path.read_text(encoding="utf-8")


def first(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else default


def normalize_status(status: str) -> str:
    status_l = status.lower()
    if any(word in status_l for word in ["live", "active", "approved"]):
        return "ok"
    if any(word in status_l for word in ["pending", "draft", "waiting", "needs"]):
        return "warn"
    if any(word in status_l for word in ["blocked", "deactivated", "reinstatement"]):
        return "block"
    return "info"


def parse_tasks(tasks_md: str) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    in_current = False
    for raw in tasks_md.splitlines():
        line = raw.strip()
        if line.startswith("## Current Active Tasks"):
            in_current = True
            continue
        if in_current and line.startswith("## "):
            break
        if not in_current or not line.startswith("- [ ]"):
            continue
        match = TASK_RE.match(line)
        if not match:
            continue
        priority = match.group("priority").upper()
        tone = {"CRITICAL": "red", "HIGH": "amber", "MEDIUM": "blue", "LOW": "green"}.get(priority, "blue")
        deadline = match.group("deadline") or ""
        time = (match.group("time") or "").strip()
        due = format_due(deadline, time)
        tasks.append({
            "priority": priority.title(),
            "tone": tone,
            "text": match.group("text").strip(),
            "due": due or "No deadline",
        })
    return tasks


def format_due(deadline: str, time: str) -> str:
    if not deadline:
        return time.strip()
    try:
        dt = datetime.strptime(deadline, "%Y-%m-%d")
        label = dt.strftime("%b %d").replace(" 0", " ")
    except ValueError:
        label = deadline
    return f"{label} · {time}" if time else label


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^### {re.escape(heading)}\n(?P<body>.*?)(?=\n### |\n## |\Z)"
    match = re.search(pattern, text, re.M | re.S)
    return match.group("body") if match else ""


def extract_bullets(section: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in re.findall(r"^- \*\*(.+?):\*\*\s*(.+)$", section, re.M):
        out[key.strip()] = value.strip()
    return out


def parse_brand_asset(asset_md: str) -> dict[str, Any]:
    website = extract_bullets(extract_section(asset_md, "Website"))
    shopify = extract_bullets(extract_section(asset_md, "Shopify Store"))
    amazon = extract_bullets(extract_section(asset_md, "Amazon FBA"))
    tiktok_shop = extract_bullets(extract_section(asset_md, "TikTok Shop"))
    inventory = extract_bullets(extract_section(asset_md, "Zoho Inventory"))
    tiktok = extract_bullets(extract_section(asset_md, "TikTok"))
    instagram = extract_bullets(extract_section(asset_md, "Instagram"))
    influencer = extract_bullets(re.search(r"## INFLUENCER PIPELINE\n(?P<body>.*?)(?=\n---\n\n## |\Z)", asset_md, re.S).group("body") if "## INFLUENCER PIPELINE" in asset_md else "")

    contacts = []
    for raw in re.findall(r"^- ([^\n]+)$", extract_section(asset_md, "Key Contacts"), re.M):
        name, _, meta = raw.partition(" — ")
        tone = "warn" if "wave 2" in raw.lower() or "paid" in raw.lower() else "ok"
        badge = "Wave 2" if tone == "warn" else ("Warm" if "applied" in raw.lower() or "responded" in raw.lower() else "Priority")
        contacts.append({"name": name.strip(), "meta": meta.strip(), "badge": badge, "tone": tone})

    price = shopify.get("Price", "$39.99 retail / $59.99 compare-at")
    launch_price = first(r"\$(\d+\.\d{2})", price, "39.99")
    cogs = first(r"\$([0-9.]+)/unit", asset_md, "6.49")
    total_vetted = first(r"\*\*Total vetted:\*\*\s*([0-9]+)", asset_md, "76")
    email_contacts = first(r"\*\*Email contacts:\*\*\s*([0-9]+)", asset_md, "57")
    dm_only = first(r"\*\*DM only:\*\*\s*([0-9]+)", asset_md, "34")
    seeding = first(r"\*\*Seeding units:\*\*\s*([0-9]+)", asset_md, "25")

    return {
        "website": website,
        "shopify": shopify,
        "amazon": amazon,
        "tiktok_shop": tiktok_shop,
        "inventory": inventory,
        "tiktok": tiktok,
        "instagram": instagram,
        "contacts": contacts[:4],
        "launch_price": f"${launch_price}",
        "cogs": f"${cogs}",
        "total_vetted": total_vetted,
        "email_contacts": email_contacts,
        "dm_only": dm_only,
        "seeding": seeding,
    }


def load_existing(output: Path) -> dict[str, Any]:
    return json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _zoho_credentials() -> dict[str, str]:
    return {
        "client_id": _first_env("ZOHO_CLIENT_ID", "ZOHO_INVENTORY_CLIENT_ID"),
        "client_secret": _first_env("ZOHO_CLIENT_SECRET", "ZOHO_INVENTORY_CLIENT_SECRET"),
        "refresh_token": _first_env("ZOHO_REFRESH_TOKEN", "ZOHO_INVENTORY_REFRESH_TOKEN"),
        "organization_id": _first_env("ZOHO_ORGANIZATION_ID", "ZOHO_INVENTORY_ORGANIZATION_ID", "ZOHO_ORG_ID"),
        "accounts_base": _first_env("ZOHO_ACCOUNTS_BASE", "ZOHO_ACCOUNTS_URL") or "https://accounts.zoho.com",
        "api_base": _first_env("ZOHO_INVENTORY_API_BASE", "ZOHO_API_BASE") or "https://www.zohoapis.com/inventory/v1",
    }


def _json_request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, data: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=encoded, method=method, headers=headers or {})
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _default_zoho_inventory(status: str = "missing_credentials", message: str = "Set Zoho OAuth env vars to enable live inventory data.") -> dict[str, Any]:
    return {
        "updatedLabel": "Zoho unavailable",
        "status": status,
        "message": message,
        "scorecards": [
            {"label": "Zoho stock on hand", "value": "—", "tone": "amber", "note": message, "source": "future:zoho"},
            {"label": "Zoho sales orders", "value": "—", "tone": "amber", "note": "Requires Zoho Inventory API.", "source": "future:zoho"},
            {"label": "Zoho invoices", "value": "—", "tone": "amber", "note": "Requires Zoho Inventory API.", "source": "future:zoho"},
        ],
        "inventoryItems": [],
        "inventoryTypeSummary": [],
        "lowStockItems": [],
        "recentSalesOrders": [],
        "recentInvoices": [],
    }


def fetch_zoho_inventory(existing: dict[str, Any]) -> dict[str, Any]:
    creds = _zoho_credentials()
    required = ["client_id", "client_secret", "refresh_token", "organization_id"]
    missing = [name for name in required if not creds.get(name)]
    if missing:
        fallback = existing.get("zohoInventory")
        if fallback and fallback.get("status") == "ok":
            return fallback
        return _default_zoho_inventory(message=f"Missing Zoho env vars: {', '.join(missing)}.")

    token_url = f"{creds['accounts_base'].rstrip('/')}/oauth/v2/token"
    try:
        token_response = _json_request(token_url, method="POST", data={
            "refresh_token": creds["refresh_token"],
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "grant_type": "refresh_token",
        })
        access_token = token_response["access_token"]
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        api_base = creds["api_base"].rstrip("/")
        org_qs = urllib.parse.urlencode({"organization_id": creds["organization_id"]})

        items = _json_request(f"{api_base}/items?{org_qs}&per_page=200", headers=headers).get("items", [])
        sales_orders = _json_request(f"{api_base}/salesorders?{org_qs}&per_page=20&sort_column=created_time&sort_order=D", headers=headers).get("salesorders", [])
        invoices = _json_request(f"{api_base}/invoices?{org_qs}&per_page=20&sort_column=created_time&sort_order=D", headers=headers).get("invoices", [])
    except (KeyError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        fallback = existing.get("zohoInventory")
        if fallback and fallback.get("status") == "ok":
            fallback["message"] = f"Zoho refresh failed; showing last successful pull. Error: {exc}"
            return fallback
        return _default_zoho_inventory(status="error", message=f"Zoho refresh failed: {exc}")

    def qty(item: dict[str, Any]) -> float:
        for key in ["available_stock", "actual_available_stock", "stock_on_hand", "quantity_available"]:
            try:
                return float(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0.0

    def reorder_level(item: dict[str, Any]) -> float:
        try:
            return float(item.get("reorder_level") or 0)
        except (TypeError, ValueError):
            return 0.0

    def item_type(item: dict[str, Any]) -> str:
        return str(item.get("category_name") or item.get("product_type") or item.get("item_type") or item.get("type") or "Uncategorized").strip() or "Uncategorized"

    total_stock = sum(qty(item) for item in items)
    inventory_items = sorted([
        {
            "name": item.get("name", "Unnamed item"),
            "sku": item.get("sku", ""),
            "type": item_type(item),
            "status": str(item.get("status") or item.get("item_status") or ""),
            "stock": fmt_int(qty(item)),
            "stockRaw": qty(item),
            "reorderLevel": fmt_int(reorder_level(item)),
            "unit": item.get("unit") or item.get("unit_name") or "units",
            "rate": f"${float(item.get('rate') or 0):,.2f}" if item.get("rate") else "",
        }
        for item in items
    ], key=lambda item: (-item["stockRaw"], item["name"]))
    inventory_summary_map: dict[str, dict[str, Any]] = {}
    for item in inventory_items:
        summary = inventory_summary_map.setdefault(item["type"], {"type": item["type"], "units": 0.0, "items": 0})
        summary["units"] += float(item["stockRaw"] or 0)
        summary["items"] += 1
    inventory_type_summary = [
        {"type": row["type"], "units": fmt_int(row["units"]), "items": fmt_int(row["items"])}
        for row in sorted(inventory_summary_map.values(), key=lambda row: (-row["units"], row["type"]))
    ]
    low_stock = [item for item in items if reorder_level(item) and qty(item) <= reorder_level(item)]
    open_orders = [order for order in sales_orders if str(order.get("status", "")).lower() not in {"closed", "void", "cancelled"}]
    unpaid_invoices = [invoice for invoice in invoices if str(invoice.get("status", "")).lower() not in {"paid", "void", "cancelled"}]
    paid_total = sum(float(invoice.get("total") or 0) for invoice in invoices if str(invoice.get("status", "")).lower() == "paid")

    now = datetime.now().astimezone().strftime("%a %b %-d · %-I:%M %p %Z")
    return {
        "updatedLabel": f"Zoho synced {now}",
        "status": "ok",
        "message": "Live read-only Zoho Inventory API pull.",
        "scorecards": [
            {"label": "Zoho stock on hand", "value": fmt_int(total_stock), "tone": "green", "note": f"Across {len(items)} item(s).", "source": "zoho_inventory"},
            {"label": "Zoho sales orders", "value": fmt_int(len(sales_orders)), "tone": "blue", "note": f"{len(open_orders)} open in recent pull.", "source": "zoho_inventory"},
            {"label": "Zoho invoices", "value": fmt_int(len(invoices)), "tone": "blue", "note": f"{len(unpaid_invoices)} unpaid in recent pull; paid total ${paid_total:,.2f}.", "source": "zoho_inventory"},
        ],
        "inventoryItems": [
            {key: value for key, value in item.items() if key != "stockRaw"}
            for item in inventory_items
        ],
        "inventoryTypeSummary": inventory_type_summary,
        "lowStockItems": [
            {"name": item.get("name", "Unnamed item"), "sku": item.get("sku", ""), "type": item_type(item), "stock": fmt_int(qty(item)), "reorderLevel": fmt_int(reorder_level(item))}
            for item in low_stock[:10]
        ],
        "recentSalesOrders": [
            {"number": order.get("salesorder_number", ""), "customer": order.get("customer_name", ""), "status": order.get("status", ""), "total": f"${float(order.get('total') or 0):,.2f}"}
            for order in sales_orders[:8]
        ],
        "recentInvoices": [
            {"number": invoice.get("invoice_number", ""), "customer": invoice.get("customer_name", ""), "status": invoice.get("status", ""), "total": f"${float(invoice.get('total') or 0):,.2f}"}
            for invoice in invoices[:8]
        ],
    }


def fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value or "0")


def fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def fmt_pos(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _metric_value(report: dict[str, Any], index: int, default: str = "0") -> str:
    rows = report.get("rows") or []
    if not rows:
        return default
    values = rows[0].get("metricValues") or []
    return values[index].get("value", default) if len(values) > index else default


def _analytics_rows(report: dict[str, Any], *metric_names: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in report.get("rows", []):
        label = " / ".join(v.get("value", "") for v in row.get("dimensionValues", []))
        metrics = [v.get("value", "0") for v in row.get("metricValues", [])]
        rows.append([label, *metrics[: len(metric_names)]])
    return rows


def _gsc_rows(report: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in report.get("rows", []):
        label = " / ".join(row.get("keys", []))
        rows.append([
            label,
            fmt_int(row.get("clicks", 0)),
            fmt_int(row.get("impressions", 0)),
            fmt_pct(row.get("ctr", 0)),
            fmt_pos(row.get("position", 0)),
        ])
    return rows


def _default_website_analytics() -> dict[str, Any]:
    return {
        "updatedLabel": "Analytics unavailable",
        "ga4": {"propertyId": "532192988", "propertyName": "Maintane", "period": "Last 30 days"},
        "searchConsole": {"siteUrl": "sc-domain:getmaintane.com", "period": "Last 30 days"},
        "scorecards": [
            {"label": "GA4 users", "value": "—", "tone": "blue", "note": "Connect Google token to refresh."},
            {"label": "GA4 sessions", "value": "—", "tone": "blue", "note": "Connect Google token to refresh."},
            {"label": "Search impressions", "value": "—", "tone": "amber", "note": "Connect Search Console to refresh."},
            {"label": "Search clicks", "value": "—", "tone": "red", "note": "Connect Search Console to refresh."},
        ],
        "diagnostics": [["Status", "Waiting for live analytics token", "warn"]],
        "actions": ["Reconnect Google Analytics/Search Console and rerun npm run generate."],
        "gaTopPages": [],
        "gaChannels": [],
        "gaEvents": [],
        "gscTopQueries": [],
        "gscTopPages": [],
        "devices": [],
    }


def fetch_website_analytics(existing: dict[str, Any]) -> dict[str, Any]:
    token_path = Path.home() / ".hermes" / "google_token.json"
    if not token_path.exists():
        return existing.get("websiteAnalytics") or _default_website_analytics()

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return existing.get("websiteAnalytics") or _default_website_analytics()

    ga_property_id = "532192988"
    gsc_site_url = "sc-domain:getmaintane.com"
    scopes = [
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/webmasters.readonly",
    ]
    today = datetime.now().date()
    start = today - timedelta(days=30)
    period = f"{start.isoformat()} → {today.isoformat()}"

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), scopes=scopes)
        ga = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)
        gsc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

        ga_summary = ga.properties().runReport(
            property=f"properties/{ga_property_id}",
            body={
                "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                "metrics": [
                    {"name": "activeUsers"},
                    {"name": "sessions"},
                    {"name": "screenPageViews"},
                    {"name": "eventCount"},
                ],
            },
        ).execute()
        ga_top_pages = ga.properties().runReport(
            property=f"properties/{ga_property_id}",
            body={
                "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "pagePath"}],
                "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
                "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
                "limit": 8,
            },
        ).execute()
        ga_channels = ga.properties().runReport(
            property=f"properties/{ga_property_id}",
            body={
                "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "sessionDefaultChannelGroup"}],
                "metrics": [{"name": "sessions"}, {"name": "activeUsers"}],
                "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
                "limit": 8,
            },
        ).execute()
        ga_events = ga.properties().runReport(
            property=f"properties/{ga_property_id}",
            body={
                "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "eventName"}],
                "metrics": [{"name": "eventCount"}],
                "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
                "limit": 8,
            },
        ).execute()
        ga_today = ga.properties().runReport(
            property=f"properties/{ga_property_id}",
            body={
                "dateRanges": [{"startDate": "today", "endDate": "today"}],
                "metrics": [
                    {"name": "activeUsers"},
                    {"name": "sessions"},
                    {"name": "screenPageViews"},
                    {"name": "eventCount"},
                ],
            },
        ).execute()

        gsc_base = {"startDate": start.isoformat(), "endDate": today.isoformat()}
        gsc_summary = gsc.searchanalytics().query(siteUrl=gsc_site_url, body={**gsc_base, "dimensions": [], "rowLimit": 1}).execute()
        gsc_queries = gsc.searchanalytics().query(siteUrl=gsc_site_url, body={**gsc_base, "dimensions": ["query"], "rowLimit": 12}).execute()
        gsc_pages = gsc.searchanalytics().query(siteUrl=gsc_site_url, body={**gsc_base, "dimensions": ["page"], "rowLimit": 10}).execute()
        gsc_devices = gsc.searchanalytics().query(siteUrl=gsc_site_url, body={**gsc_base, "dimensions": ["device"], "rowLimit": 5}).execute()

        users = _metric_value(ga_summary, 0)
        sessions = _metric_value(ga_summary, 1)
        pageviews = _metric_value(ga_summary, 2)
        events = _metric_value(ga_summary, 3)
        today_users = _metric_value(ga_today, 0)
        today_sessions = _metric_value(ga_today, 1)
        today_pageviews = _metric_value(ga_today, 2)
        today_events = _metric_value(ga_today, 3)
        gsc_row = (gsc_summary.get("rows") or [{}])[0]
        impressions = gsc_row.get("impressions", 0)
        clicks = gsc_row.get("clicks", 0)
        ctr = gsc_row.get("ctr", 0)
        position = gsc_row.get("position", 0)

        nonbrand_rows = [r for r in gsc_queries.get("rows", []) if "maintane" not in (r.get("keys") or [""])[0].lower()]
        best_nonbrand = nonbrand_rows[0] if nonbrand_rows else None
        best_nonbrand_label = (best_nonbrand.get("keys") or ["None yet"])[0] if best_nonbrand else "None yet"
        best_nonbrand_impressions = best_nonbrand.get("impressions", 0) if best_nonbrand else 0

        actions = [
            "Treat the homepage as the conversion hub: it has the only search click and the strongest branded rank.",
            "Refresh title/meta and add stronger internal links for septic tank cleaning cost, bacteria, and how-often treatment pages — they have impressions but weak rank.",
            "Turn high-impression/low-rank queries into content briefs: septic cleaning cost, septic bacteria, old-home treatment, and Rid-X alternative/comparison.",
            "Fix analytics hygiene: reduce Unassigned traffic by tagging influencer, TikTok, paid social, and email links with UTMs.",
        ]

        return {
            "updatedLabel": f"Pulled {datetime.now().astimezone().strftime('%a %b %-d · %-I:%M %p %Z')}",
            "ga4": {"propertyId": ga_property_id, "propertyName": "Maintane", "period": "Last 30 days"},
            "searchConsole": {"siteUrl": gsc_site_url, "period": period},
            "scorecards": [
                {"label": "GA4 active users", "value": fmt_int(users), "tone": "blue", "note": f"{fmt_int(sessions)} sessions · {fmt_int(pageviews)} page views"},
                {"label": "GA4 events", "value": fmt_int(events), "tone": "green", "note": "Includes CTA impressions, nav clicks, scrolls, engagement."},
                {"label": "Search impressions", "value": fmt_int(impressions), "tone": "amber", "note": f"Avg position {fmt_pos(position)} · CTR {fmt_pct(ctr)}"},
                {"label": "Search clicks", "value": fmt_int(clicks), "tone": "red", "note": "SEO is indexed but not converting clicks yet."},
            ],
            "diagnostics": [
                ["GA4 property", "Maintane · 532192988", "ok"],
                ["Today so far", f"{fmt_int(today_users)} active users / {fmt_int(today_sessions)} sessions / {fmt_int(today_pageviews)} page views / {fmt_int(today_events)} events", "ok"],
                ["Search property", gsc_site_url, "ok"],
                ["SEO readout", f"{fmt_int(impressions)} impressions / {fmt_int(clicks)} clicks / rank {fmt_pos(position)}", "warn"],
                ["Best non-brand query", f"{best_nonbrand_label} · {fmt_int(best_nonbrand_impressions)} impressions", "info"],
            ],
            "actions": actions,
            "gaTopPages": _analytics_rows(ga_top_pages, "Views", "Users"),
            "gaChannels": _analytics_rows(ga_channels, "Sessions", "Users"),
            "gaEvents": _analytics_rows(ga_events, "Events"),
            "gscTopQueries": _gsc_rows(gsc_queries),
            "gscTopPages": _gsc_rows(gsc_pages),
            "devices": _gsc_rows(gsc_devices),
        }
    except Exception:
        return existing.get("websiteAnalytics") or _default_website_analytics()


def _metric_from_scorecards(analytics: dict[str, Any], label_part: str, default: str = "—") -> str:
    for card in analytics.get("scorecards", []):
        if label_part.lower() in card.get("label", "").lower():
            return card.get("value", default)
    return default


def _sessions_from_analytics(analytics: dict[str, Any]) -> str:
    sessions = _metric_from_scorecards(analytics, "sessions")
    if sessions != "—":
        return sessions
    for card in analytics.get("scorecards", []):
        match = re.search(r"([0-9,]+)\s+sessions", card.get("note", ""), re.I)
        if match:
            return match.group(1)
    return "—"


def _parse_display_number(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def _seo_bucket(query: str, position: float, impressions: float) -> str:
    if "maintane" in query.lower():
        return "Brand Defense"
    if 4 <= position <= 15 and impressions > 0:
        return "Quick Win"
    if 16 <= position < 50 and impressions > 0:
        return "Build Authority"
    if position >= 50:
        return "Long Shot"
    return "Monitor"


def _ensure_base_sections(data: dict[str, Any]) -> dict[str, Any]:
    """Populate static dashboard sections needed when no output JSON exists yet.

    The generator refreshes volatile metrics from TomMemory, but the V1 UI also
    contains mostly-static cards/lists that historically lived in the checked-in
    JSON. Keep those sections present for fresh output paths while preserving any
    richer existing generated content when mission-control.json already exists.
    """
    data.setdefault("blockers", {})
    data["blockers"].setdefault("columns", [
        {"title": "Blocked", "cards": [
            {"title": "Amazon reinstatement", "body": "Pay supplier invoice, attach paid invoice, then resubmit the Amazon appeal."},
            {"title": "TikTok listing submission", "body": "Complete final product images before submitting the listing for review."},
        ]},
        {"title": "In motion", "cards": [
            {"title": "Invivo production", "body": "Keep production, invoice, and shipment-plan tasks moving."},
            {"title": "Influencer outreach", "body": "Prioritize warm creators and track UTMs before seeding."},
        ]},
        {"title": "Ready", "cards": [
            {"title": "Shopify DTC", "body": "Live storefront remains the initial conversion hub."},
            {"title": "Website + SEO base", "body": "GA4/Search Console data contract is ready when tokens are available."},
        ]},
    ])
    data.setdefault("influencers", {})
    data["influencers"].setdefault("priorityContacts", [])
    data["influencers"].setdefault("outreachRules", [
        "Ask whether the creator or audience has septic before offering product.",
        "Offer a free jar plus affiliate upside; tag every link with UTMs.",
        "Prioritize email first, then Instagram DM follow-up.",
    ])
    data.setdefault("content", {})
    data["content"].setdefault("pillars", [
        ["Mistakes", "40–50%"],
        ["Consequences", "20–25%"],
        ["Mechanism", "15–20%"],
        ["Awareness", "10–15%"],
        ["Prevention", "5–10%"],
    ])
    data["content"].setdefault("creativeRules", [
        "Lead with the mistake or financial consequence.",
        "Keep hooks direct and septic-homeowner specific.",
        "Use Maintane as the simple monthly maintenance step.",
    ])
    data.setdefault("finance", {})
    data["finance"].setdefault("priceLadder", [
        ["Launch", "$39.99 · first 50 units / 0–24 reviews"],
        ["Growth", "$49.99 · 25 reviews"],
        ["Upper end", "$59.99 · 75 reviews"],
        ["Premium", "$74.99 · 100 reviews"],
    ])
    data["finance"].setdefault("consumerAngle", [
        ["Monthly cost", "$6.67/month"],
        ["Core contrast", "$6.67/month vs $10k–$25k repair"],
        ["Positioning", "Premium wellness, kid & pet safe"],
        ["PPC", "No PPC weeks 1–2; test only after attribution exists"],
    ])
    data.setdefault("tom", {})
    data["tom"].setdefault("description", "Ask for Maintane launch decisions, appeal checklists, influencer scripts, content hooks, and channel priorities.")
    data["tom"].setdefault("statusPrompt", "Give me a concise Maintane status update: what is live, what is blocked, and the next 5 actions.")
    data["tom"].setdefault("dataSourceRows", [
        ["Vault", "~/TomMemory"],
        ["Core note", "Maintane-brand-asset 4-19.md"],
        ["Tasks", "Tasks.md"],
        ["Content rules", "Maintane-Content-Strategy.md"],
    ])
    return data


def build_command_center(data: dict[str, Any]) -> dict[str, Any]:
    analytics = data.get("websiteAnalytics", {})
    zoho = data.get("zohoInventory", {})
    zoho_cards = {card.get("label", ""): card for card in zoho.get("scorecards", [])}
    sessions = _sessions_from_analytics(analytics)
    impressions = _metric_from_scorecards(analytics, "Search impressions")
    orders_card = zoho_cards.get("Zoho sales orders", {}) if zoho.get("status") == "ok" else {}
    stock_card = zoho_cards.get("Zoho stock on hand", {}) if zoho.get("status") == "ok" else {}
    return {
        "diagnosis": "Maintane made concrete progress today: supplier payment completed, Amazon appeal work moved forward, influencer retouch outreach is running, and live GA4/Search Console access is restored.",
        "scorecards": [
            {"label": "Revenue", "value": "Pending Shopify API", "note": "Future source required for DTC revenue; Zoho invoices are tracked separately.", "tone": "warn", "source": "future:shopify"},
            {"label": "Orders", "value": orders_card.get("value", "Pending Zoho/Shopify API"), "note": orders_card.get("note", "Requires Zoho Inventory or Shopify order integration."), "tone": orders_card.get("tone", "warn"), "source": orders_card.get("source", "future:zoho")},
            {"label": "Sessions", "value": sessions, "note": "Last 30 days from GA4 when available.", "tone": "blue", "source": "ga4"},
            {"label": "Search Impressions", "value": impressions, "note": "Last 30 days from Search Console when available.", "tone": "amber", "source": "search_console"},
            {"label": "Inventory", "value": stock_card.get("value", "Pending Zoho API"), "note": stock_card.get("note", "Live stock requires Zoho Inventory API."), "tone": stock_card.get("tone", "warn"), "source": stock_card.get("source", "future:zoho")},
            {"label": "Channel Status", "value": "DTC live; Amazon/TikTok pending", "note": "Based on Maintane brand asset plus live integrations when available.", "tone": "amber", "source": "TomMemory/Zoho"},
        ],
        "primaryBottleneck": {
            "title": "Commerce data plus next growth decision",
            "status": "Today’s execution list is cleared; next bottleneck is live order/revenue visibility.",
            "nextAction": "Keep the dashboard honest until Shopify/Amazon/TikTok order sources are connected, then use the Jarvis home radar to route each system into its expanded page.",
            "tone": "warn",
        },
        "nextActions": [
            "Use the Jarvis home radar as the daily command layer: daily revenue in the center, system cards around it, Tom in the right rail.",
            "Click Tasks, Channels, Advertising, Marketing, Content, Customers, Finance, or Data Health to inspect the expanded page.",
            "Keep Branding, Product & Inventory, and Contacts out of the homepage so the cockpit stays focused.",
            "Connect Shopify orders/revenue API before treating the daily revenue metric as live.",
        ],
    }


def build_revenue_funnel(data: dict[str, Any]) -> dict[str, Any]:
    analytics = data.get("websiteAnalytics", {})
    zoho = data.get("zohoInventory", {})
    zoho_cards = {card.get("label", ""): card for card in zoho.get("scorecards", [])}
    orders_card = zoho_cards.get("Zoho sales orders", {}) if zoho.get("status") == "ok" else {}
    sessions = _sessions_from_analytics(analytics)
    page_views = "Pending GA4 event mapping"
    for card in analytics.get("scorecards", []):
        note = card.get("note", "")
        if "page views" in note:
            page_views = note.split("·")[-1].strip()
            break
    return {
        "diagnosis": "Top-of-funnel visibility is measurable; commerce conversion steps remain pending until Shopify and explicit GA4 events are wired.",
        "stages": [
            {"label": "Sessions", "value": sessions, "status": "active", "source": "ga4", "tone": "blue"},
            {"label": "Product / intent page views", "value": page_views, "status": "partial", "source": "ga4", "tone": "blue", "note": "Use explicit product/intent page grouping in future."},
            {"label": "CTA clicks", "value": "Pending GA4 event instrumentation", "status": "pending", "source": "future:ga4_event", "tone": "warn"},
            {"label": "Checkout starts", "value": "Pending Shopify API", "status": "pending", "source": "future:shopify", "tone": "warn"},
            {"label": "Orders", "value": orders_card.get("value", "Pending Zoho/Shopify API"), "status": "active" if zoho.get("status") == "ok" else "pending", "source": orders_card.get("source", "future:zoho"), "tone": orders_card.get("tone", "warn")},
            {"label": "Repeat/subscription intent", "value": "Pending Klaviyo/subscription source", "status": "pending", "source": "future:klaviyo", "tone": "warn"},
        ],
        "missingInstrumentation": [
            "CTA clicks require a named GA4 event on product and content CTAs.",
            "Checkout starts require Shopify API or GA4 checkout event instrumentation.",
            "Orders and revenue require Shopify API; do not infer from traffic.",
        ],
    }


def build_seo_opportunities(data: dict[str, Any]) -> dict[str, Any]:
    analytics = data.get("websiteAnalytics", {})
    opportunities: list[dict[str, Any]] = []
    buckets: dict[str, int] = {"Brand Defense": 0, "Quick Win": 0, "Build Authority": 0, "Long Shot": 0, "Monitor": 0}
    for row in analytics.get("gscTopQueries", []):
        query = row[0] if row else ""
        clicks = row[1] if len(row) > 1 else "0"
        impressions = row[2] if len(row) > 2 else "0"
        ctr = row[3] if len(row) > 3 else "0.00%"
        position = row[4] if len(row) > 4 else "—"
        impression_num = _parse_display_number(impressions)
        position_num = _parse_display_number(position)
        bucket = _seo_bucket(query, position_num, impression_num)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        if bucket != "Monitor":
            opportunities.append({
                "query": query,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "position": position,
                "bucket": bucket,
                "recommendedAction": "Defend branded title/snippet." if bucket == "Brand Defense" else "Refresh or build content targeting this query cluster.",
                "source": "search_console",
            })
    fallback_opportunities = [
        {"query": "septic tank cleaning cost", "impressions": "Pending Search Console", "clicks": "Pending Search Console", "ctr": "Pending Search Console", "position": "Pending Search Console", "bucket": "Build Authority", "recommendedAction": "Create or refresh a cost-focused SEO page with Maintane CTA.", "source": "future:search_console"},
        {"query": "septic bacteria treatment", "impressions": "Pending Search Console", "clicks": "Pending Search Console", "ctr": "Pending Search Console", "position": "Pending Search Console", "bucket": "Build Authority", "recommendedAction": "Build mechanism content around bacteria and monthly maintenance.", "source": "future:search_console"},
        {"query": "maintane", "impressions": "Pending Search Console", "clicks": "Pending Search Console", "ctr": "Pending Search Console", "position": "Pending Search Console", "bucket": "Brand Defense", "recommendedAction": "Keep homepage title/meta tightly branded and conversion-oriented.", "source": "future:search_console"},
    ]
    while len(opportunities) < 3:
        fallback = fallback_opportunities[len(opportunities)]
        opportunities.append(fallback)
        buckets[fallback["bucket"]] = buckets.get(fallback["bucket"], 0) + 1
    visible_opportunities = opportunities[:8]
    return {
        "scorecards": [
            {"label": "Search impressions", "value": _metric_from_scorecards(analytics, "Search impressions"), "tone": "amber", "source": "search_console"},
            {"label": "Search clicks", "value": _metric_from_scorecards(analytics, "Search clicks"), "tone": "red", "source": "search_console"},
            {"label": "Tracked opportunities", "value": str(len(visible_opportunities)), "tone": "blue", "source": "generated"},
        ],
        "opportunities": visible_opportunities,
        "queryBuckets": [{"bucket": key, "count": value} for key, value in buckets.items()],
        "actions": [
            "Prioritize position 4–15 queries first: title/meta refresh, FAQ block, and internal links.",
            "Turn position 16–50 queries into authority pages and comparison content.",
            "Protect branded search by making homepage snippets unmistakably Maintane and purchase-oriented.",
        ],
    }


def build_channel_ops(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "channels": [
            {"channel": "Shopify/DTC", "status": "Live storefront; sales metrics pending", "blocker": "Pending Shopify API for orders/revenue", "nextAction": "Wire Shopify API and purchase events before scaling spend.", "tone": "ok", "source": "future:shopify"},
            {"channel": "Amazon", "status": "Appeal submitted / awaiting review", "blocker": "Amazon Account Health response and official paid invoice document if requested", "nextAction": "Monitor Seller Central and keep paid-in-full invoice packet ready.", "tone": "warn", "source": "TomMemory/session"},
            {"channel": "TikTok Shop", "status": "Approved account; listing draft", "blocker": "Product images and future TikTok Shop API metrics", "nextAction": "Finish product images, submit listing, then connect TikTok metrics.", "tone": "warn", "source": "future:tiktok"},
            {"channel": "Influencers", "status": "Retouch sprint active", "blocker": "Remaining scheduled sends plus UTM/affiliate prep", "nextAction": "Finish the 10 retouch follow-ups, then contact 7 no-contact Tier 1 YouTube / homestead creators.", "tone": "blue", "source": "Gmail/cron"},
            {"channel": "Email/Klaviyo", "status": "App installed; performance pending", "blocker": "Pending Klaviyo flow and API source", "nextAction": "Create launch capture/abandon flows and connect Klaviyo metrics.", "tone": "warn", "source": "future:klaviyo"},
        ]
    }


def build_unit_economics(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "price": "$39.99",
        "cogs": "~$6.49",
        "channels": [
            {"channel": "Shopify/DTC", "net": "~$26.54", "breakEvenCac": "~$26.54", "targetCac": "≤ $13.25", "source": "known economics"},
            {"channel": "Amazon", "net": "~$23.50", "breakEvenCac": "~$23.50", "targetCac": "≤ $11.75", "source": "known economics; sales pending future:amazon"},
            {"channel": "TikTok Shop", "net": "~$25.50", "breakEvenCac": "~$25.50", "targetCac": "≤ $12.75", "source": "known economics; sales pending future:tiktok"},
        ],
        "breakEvenCac": "Use channel net as break-even CAC before overhead; live CAC pending ad/order integrations.",
        "targetCac": "Target roughly 50% of channel net until repeat purchase data exists.",
        "notes": [
            "Known Maintane economics only: price $39.99, COGS ~$6.49, Shopify net ~$26.54, Amazon net ~$23.50, TikTok net ~$25.50.",
            "No sales, conversion, CAC, or order volume is inferred without future Shopify/Amazon/TikTok sources.",
        ],
    }


def _action(title: str, kpi: str, impact: str, owner: str, status: str) -> dict[str, str]:
    return {"title": title, "kpi": kpi, "impact": impact, "owner": owner, "status": status}


def build_action_queue(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "now": [],
        "next": [
            _action("Connect Shopify orders/revenue API", "Revenue visibility", "High", "Mr. Bless / Dev", "Next"),
            _action("Connect Meta/Google ad spend and campaign attribution", "Paid acquisition", "High", "Tom / Dev", "Next"),
            _action("Turn the Jarvis home nodes into the default daily review flow", "Operating cadence", "Medium", "Tom", "Next"),
        ],
        "waiting": [
            _action("Pull Amazon order/ad metrics", "Marketplace profit", "High", "Future Amazon API", "Waiting"),
            _action("Pull TikTok Shop order metrics", "Creator commerce", "Medium", "Future TikTok source", "Waiting"),
            _action("Pull Klaviyo email revenue metrics", "Retention", "Medium", "Future Klaviyo source", "Waiting"),
        ],
        "done": [
            _action("Sent remaining Amit payment", "Supplier proof", "High", "Mr. Bless", "Done"),
            _action("Drafted official paid-in-full invoice/document request to Amit and Allen", "Amazon evidence", "High", "Tom", "Done"),
            _action("Submitted / moved forward Amazon appeal packet", "Amazon reactivation", "High", "Mr. Bless / Tom", "Done"),
            _action("Restored combined Google OAuth for Gmail, Workspace, GA4, and Search Console", "Operating data", "High", "Mr. Bless / Tom", "Done"),
            _action("Verified live GA4 today-so-far traffic pull", "Traffic visibility", "Medium", "Tom", "Done"),
            _action("Sent first Maintane retouch email and rescheduled remaining sends after script fix", "Creator pipeline", "High", "Tom", "Done"),
            _action("Monitored Amazon appeal / Account Health response", "Amazon channel activation", "High", "Mr. Bless / Tom", "Done"),
            _action("Completed scheduled Maintane retouch emails with reply-safety checks", "Creator pipeline", "High", "Tom", "Done"),
            _action("Prepared 7 new Tier 1 YouTube / homestead creator first-outreach emails", "Influencer pipeline", "High", "Tom", "Done"),
            _action("Finished Mother’s Day flowers for Amy and Mom", "Personal priority", "High", "Mr. Bless", "Done"),
            _action("Created UTM / affiliate tracking link plan for closed creators after packages ship", "Attribution", "High", "Mr. Bless / Tom", "Done"),
            _action("Instrumented CTA and checkout-start event plan", "Funnel attribution", "High", "Tom / Mr. Bless", "Done"),
            _action("Built SEO brief queue for high-impression septic queries", "Organic clicks", "Medium", "Tom", "Done"),
            _action("Confirmed supplier paid-in-full document request is drafted and ready", "Amazon evidence", "High", "Amit / Allen", "Done"),
            _action("Completed tracking + affiliate link handoff plan for closed green/address creators", "Creator handoff", "Medium", "Tom", "Done"),
        ],
    }


def build_data(vault: Path, output: Path) -> dict[str, Any]:
    asset_path = vault / "Maintane" / "Maintane-brand-asset 4-19.md"
    tasks_path = vault / "Tasks.md"
    content_path = vault / "Content-Strategy" / "Maintane-Content-Strategy.md"

    asset_md = read(asset_path)
    tasks_md = read(tasks_path)
    content_md = read(content_path)
    existing = load_existing(output)
    parsed = parse_brand_asset(asset_md)
    tasks = parse_tasks(tasks_md)

    now = datetime.now().astimezone().strftime("%a %b %-d · %-I:%M %p %Z")
    active_blockers = sum(1 for t in tasks if t["tone"] in {"red", "amber"})
    readiness = 62
    if parsed["shopify"].get("Status", "").lower().startswith("live"):
        readiness += 8
    if "pending" not in parsed["amazon"].get("Status", "").lower():
        readiness += 15
    if "needs" not in parsed["tiktok_shop"].get("Needs", "").lower():
        readiness += 8
    readiness = min(readiness, 95)

    data = _ensure_base_sections(existing or {})
    data["meta"] = {
        "title": "Maintane Mission Control",
        "subtitle": "Blesstopher Capital operating cockpit",
        "updatedLabel": f"Updated {now}",
        "source": "~/TomMemory",
        "siteUrl": "https://getmaintane.com",
        "cloudflareNote": "Cloudflare Pages deploys from GitHub main when connected.",
    }
    data["hero"] = {
        "headline": "Maintane launch cockpit.",
        "body": "Operating surface for getting Maintane live across Amazon, Shopify, TikTok Shop, influencers, and content — with today focused on marketplace proof, creator outreach, and traffic visibility.",
        "needleLabel": "Today’s needle mover",
        "needleValue": "Amazon appeal submitted; influencer retouch sprint running",
        "needleSupport": "Amit payment is complete, the paid-in-full document has been requested, Amazon appeal work moved forward, and Google analytics access is restored. Keep creator outreach moving while waiting on marketplace responses.",
    }
    data["zohoInventory"] = fetch_zoho_inventory(existing)
    zoho_cards = {card.get("label", ""): card for card in data["zohoInventory"].get("scorecards", [])}
    zoho_stock_card = zoho_cards.get("Zoho stock on hand", {})
    data["overviewMetrics"] = [
        {"label": "Launch readiness", "value": f"{min(readiness + 5, 95)}%", "tone": "amber", "note": "DTC live; Amazon appeal submitted; TikTok still gated by product images."},
        {"label": "Active blockers", "value": str(active_blockers), "tone": "red", "note": "Counted from current critical/high TomMemory tasks."},
        {"label": "Vetted creators", "value": parsed["total_vetted"], "tone": "blue", "note": f"{parsed['email_contacts']} email contacts; {parsed['dm_only']} DM-only; {parsed['seeding']} seeding units planned."},
        {"label": "Launch price", "value": parsed["launch_price"], "tone": "green", "note": "Review velocity first; margin still strong."},
    ]
    data["criticalTasks"] = [
        {"priority": "High", "tone": "amber", "text": "Monitor Amazon appeal / Account Health response after paid invoice packet work", "due": "May 8"},
        {"priority": "High", "tone": "amber", "text": "Keep Maintane retouch follow-up sprint running at 25 minute spacing with reply-safety checks", "due": "May 8 · 2:30–5:50 PM"},
        {"priority": "High", "tone": "amber", "text": "Prepare first outreach to 7 no-contact Tier 1 YouTube / homestead creators", "due": "May 8"},
        {"priority": "High", "tone": "amber", "text": "Mother’s Day flowers for Amy and Mom are being handled by Mr. Bless", "due": "May 8"},
    ]
    data["blockers"]["metrics"] = [
        {"label": "Amazon case", "value": "Submitted", "tone": "amber", "note": "Appeal packet work moved forward; awaiting Amazon response / paid invoice document if requested."},
        {"label": "Invoice", "value": "Paid", "tone": "green", "note": "Remaining Amit payment completed; official paid-in-full document requested from Amit and Allen."},
        {"label": "TikTok Shop", "value": "Draft" if "draft" in parsed["tiktok_shop"].get("Status", "").lower() else parsed["tiktok_shop"].get("Status", "Draft"), "tone": "amber", "note": parsed["tiktok_shop"].get("Needs", "Needs product images before review")},
        {"label": "Inventory", "value": zoho_stock_card.get("value", parsed["inventory"].get("On hand", "250 units").replace(" units", "")), "tone": zoho_stock_card.get("tone", "blue"), "note": zoho_stock_card.get("note", "On hand / production per TomMemory")},
    ]
    data["blockers"]["columns"] = [
        {"title": "Waiting", "cards": [
            {"title": "Amazon reinstatement", "body": "Appeal work submitted / moved forward; monitor Account Health and keep the official paid invoice ready."},
            {"title": "TikTok listing submission", "body": "Still needs final product images before clean review submission."},
        ]},
        {"title": "In motion", "cards": [
            {"title": "Influencer retouch sprint", "body": "First retouch sent; remaining creator follow-ups scheduled with reply checks and 25 minute spacing."},
            {"title": "Google data access", "body": "Combined OAuth restored Gmail, Workspace, GA4, and Search Console so live dashboard pulls work again."},
        ]},
        {"title": "Ready", "cards": [
            {"title": "Shopify DTC", "body": "Live storefront remains the initial conversion hub."},
            {"title": "Website + SEO base", "body": "getmaintane.com live with GA4, Search Console, and refreshed today-so-far analytics."},
        ]},
    ]
    data["channels"] = [
        {"title": "Shopify DTC", "rows": [["Store", parsed["shopify"].get("Store URL", "maintane-2.myshopify.com")], ["Custom domain", parsed["shopify"].get("Custom domain", "shop.getmaintane.com")], ["Status", parsed["shopify"].get("Status", "Live"), normalize_status(parsed["shopify"].get("Status", "Live"))], ["Price", parsed["shopify"].get("Price", "$39.99 retail / $59.99 compare-at")], ["Apps", parsed["shopify"].get("Apps installed", "Klaviyo · Judge.me · Collabs")]]},
        {"title": "Amazon FBA", "rows": [["Status", "Appeal submitted / awaiting Amazon response", "warn"], ["Case", first(r"Case #(\d+)", parsed["amazon"].get("Status", ""), "19511671511")], ["Seller ID", parsed["amazon"].get("Seller ID", "A3FXI24FIY5G9I")], ["Allocation", parsed["amazon"].get("Inventory allocation", "225 units")], ["Next", "Monitor Account Health and keep official paid invoice ready"]]},
        {"title": "TikTok Shop", "rows": [["Status", parsed["tiktok_shop"].get("Status", "Approved · draft"), "warn"], ["Category", parsed["tiktok_shop"].get("Category", "Home Supplies")], ["Affiliate", parsed["tiktok_shop"].get("Affiliate", "15% post-launch")], ["Stock", parsed["tiktok_shop"].get("Stock", "225 units, SKU: MTN-001")], ["Need", parsed["tiktok_shop"].get("Needs", "Product images")]]},
    ]
    data["influencers"]["metrics"] = [
        {"label": "Total vetted", "value": parsed["total_vetted"], "note": "Creator pipeline"},
        {"label": "Email contacts", "value": parsed["email_contacts"], "tone": "blue", "note": "Primary channel"},
        {"label": "DM only", "value": parsed["dm_only"], "tone": "amber", "note": "Secondary channel"},
        {"label": "Seeding units", "value": parsed["seeding"], "tone": "green", "note": "USPS from Miami"},
    ]
    if parsed["contacts"]:
        data["influencers"]["priorityContacts"] = parsed["contacts"]
    data["content"]["metrics"] = [
        {"label": "TikTok", "value": first(r"\*\*Total views \(28 days\):\*\*\s*([^\n]+)", asset_md, "5.4K"), "tone": "green", "note": f"28-day views · {parsed['tiktok'].get('Traffic source', 'For You')}"},
        {"label": "Instagram best post", "value": first(r"—\s*([0-9,]+) views", parsed["instagram"].get("Best post", "1,092 views"), "1,092"), "tone": "blue", "note": parsed["instagram"].get("Best post", "“4 Warning Signs”")},
        {"label": "Cadence", "value": first(r"Daily at ([^\n]+)", parsed["tiktok"].get("Posting cadence", "Daily at 3:00 PM EST"), "3:00 PM EST"), "note": "Daily TikTok + Instagram"},
    ]
    data["finance"]["metrics"] = [
        {"label": "COGS", "value": parsed["cogs"], "tone": "green", "note": "Material/unit"},
        {"label": "Amazon net", "value": "~$23.50", "tone": "green", "note": "At $39.99 after fees"},
        {"label": "Shopify net", "value": "~$26.54", "tone": "green", "note": "After Shopify + MCF"},
        {"label": "TikTok net", "value": "~$25.50", "tone": "green", "note": "After commission + shipping"},
    ]
    data["tom"]["sourceNote"] = f"Dashboard content is generated from TomMemory into mission-control.json as of {now}."
    data["websiteAnalytics"] = fetch_website_analytics(existing)
    data["commandCenter"] = build_command_center(data)
    data["revenueFunnel"] = build_revenue_funnel(data)
    data["seoOpportunities"] = build_seo_opportunities(data)
    data["channelOps"] = build_channel_ops(data)
    data["unitEconomics"] = build_unit_economics(data)
    data["actionQueue"] = build_action_queue(data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate mission-control.json from TomMemory")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT, help="Path to TomMemory vault")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to write mission-control.json")
    parser.add_argument("--check", action="store_true", help="Validate generation without writing")
    args = parser.parse_args()

    data = build_data(args.vault.expanduser(), args.output.expanduser())
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(encoded)  # validation
    if args.check:
        print(f"ok: generated {len(encoded)} bytes from {args.vault}")
        return 0
    args.output.write_text(encoded, encoding="utf-8")
    print(f"wrote {args.output} from {args.vault}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

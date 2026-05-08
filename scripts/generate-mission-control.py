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
from datetime import datetime
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

    data = existing or {}
    data["meta"] = {
        "title": "Maintane Mission Control",
        "subtitle": "Blessopher Capital operating cockpit",
        "updatedLabel": f"Updated {now}",
        "source": "~/TomMemory",
        "siteUrl": "https://getmaintane.com",
        "cloudflareNote": "Cloudflare Pages deploys from GitHub main when connected.",
    }
    data["hero"] = {
        "headline": "Maintane launch cockpit.",
        "body": "Operating surface for getting Maintane live across Amazon, Shopify, TikTok Shop, influencers, and content — with the Amazon appeal as the critical path.",
        "needleLabel": "Today’s needle mover",
        "needleValue": "Pay Amit → get invoice → submit Amazon appeal",
        "needleSupport": "No paid invoice, no reinstatement packet. No reinstatement, Amazon stays blocked. Everything else is secondary until this chain is done.",
    }
    data["overviewMetrics"] = [
        {"label": "Launch readiness", "value": f"{readiness}%", "tone": "amber", "note": "DTC live; Amazon/TikTok gated by invoice + images."},
        {"label": "Active blockers", "value": str(active_blockers), "tone": "red", "note": "Counted from current critical/high TomMemory tasks."},
        {"label": "Vetted creators", "value": parsed["total_vetted"], "tone": "blue", "note": f"{parsed['email_contacts']} email contacts; {parsed['dm_only']} DM-only; {parsed['seeding']} seeding units planned."},
        {"label": "Launch price", "value": parsed["launch_price"], "tone": "green", "note": "Review velocity first; margin still strong."},
    ]
    data["criticalTasks"] = tasks[:4]
    data["blockers"]["metrics"] = [
        {"label": "Amazon case", "value": "Blocked" if "pending" in parsed["amazon"].get("Status", "").lower() else "Open", "tone": "red", "note": parsed["amazon"].get("Status", "Case #19511671511")},
        {"label": "Invoice", "value": "Pending", "tone": "amber", "note": "Amit / Invivo paid invoice required"},
        {"label": "TikTok Shop", "value": "Draft" if "draft" in parsed["tiktok_shop"].get("Status", "").lower() else parsed["tiktok_shop"].get("Status", "Draft"), "tone": "amber", "note": parsed["tiktok_shop"].get("Needs", "Needs product images before review")},
        {"label": "Inventory", "value": parsed["inventory"].get("On hand", "250 units").replace(" units", ""), "tone": "blue", "note": "On hand / production per TomMemory"},
    ]
    data["channels"] = [
        {"title": "Shopify DTC", "rows": [["Store", parsed["shopify"].get("Store URL", "maintane-2.myshopify.com")], ["Custom domain", parsed["shopify"].get("Custom domain", "shop.getmaintane.com")], ["Status", parsed["shopify"].get("Status", "Live"), normalize_status(parsed["shopify"].get("Status", "Live"))], ["Price", parsed["shopify"].get("Price", "$39.99 retail / $59.99 compare-at")], ["Apps", parsed["shopify"].get("Apps installed", "Klaviyo · Judge.me · Collabs")]]},
        {"title": "Amazon FBA", "rows": [["Status", parsed["amazon"].get("Status", "Pending reinstatement"), "block"], ["Case", first(r"Case #(\d+)", parsed["amazon"].get("Status", ""), "19511671511")], ["Seller ID", parsed["amazon"].get("Seller ID", "A3FXI24FIY5G9I")], ["Allocation", parsed["amazon"].get("Inventory allocation", "225 units")], ["Next", "Submit paid invoice appeal"]]},
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

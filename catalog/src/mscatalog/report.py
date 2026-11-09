"""The human review sheet: every vetted record, grouped by main job, sorted by score, with an advisory recommendation.
The recommendation is a rule of thumb for the reviewer; only `mscatalog review` changes a record."""
import re
from datetime import datetime, timezone
from pathlib import Path

from . import store

SHORT = {"identity": "Id", "longevity": "Age", "data_handling": "Data", "pricing": "Price", "reviews": "Rev", "viability": "Viab"}
LINK = {"identity": "identity", "longevity": "age", "data_handling": "privacy", "pricing": "pricing", "reviews": "reviews", "viability": "news"}
SETUP_VENDOR = "chatling"  # docs/setup-vendor.md ranks Chatling first for agent setup


def _price(p: dict) -> str:
    parts = []
    if p["free_plan"]:
        parts.append("free plan")
    if p["from_usd_month"] is not None:
        parts.append(f"from ${p['from_usd_month']:g}/mo")
    return ", ".join(parts) or "not listed"


def recommend(t: dict) -> tuple[str, str]:
    s = t["trust"]["signals"]
    score = t["trust"]["score"]
    weak = [SHORT[k] for k, v in s.items() if v["points"] < v["max"] / 2]
    usd = t["price"]["from_usd_month"]
    if s["identity"]["points"] == 0:
        return "reject", "no company named on the site (Unknown builder)"
    if s["viability"]["points"] == 0:
        return "reject", f"shutdown or acquisition news; check the link ({s['viability']['value'][:70]})"
    if score < 50:
        return "reject", f"score {score} is under 50 (Unknown builder); weak: {', '.join(weak) or 'none'}"
    m = re.match(r"(\d\.\d) from (\d+) reviews", s["reviews"]["value"])
    if m and float(m.group(1)) < 3.5 and int(m.group(2)) >= 20:
        return "reject", f"poorly rated ({s['reviews']['value']})"
    if usd is not None and usd > 300:
        return "reject", f"priced for larger firms (from ${usd:g}/mo)"
    if score >= 75:
        return "approve", "strong evidence on every axis; Verified once approved"
    return "approve", f"Caution badge ({score}); weak: {', '.join(weak) or 'none'}"


def _row(t: dict) -> str:
    s = t["trust"]["signals"]
    pts = " ".join(f"{SHORT[k]} {s[k]['points']}/{s[k]['max']}" for k in SHORT)
    links = " ".join(f"[{LINK[k]}]({s[k]['evidence_url']})" for k in SHORT if s[k].get("evidence_url"))
    rec, why = recommend(t)
    sim = f"; simtest {t['sim_test']['score']}/10" if t.get("sim_test") else ""
    name = f"[{t['name']}]({t['url']})"
    return (f"| {t['id']} | {name} | {', '.join(t['business_types'])} | {_price(t['price'])} | "
            f"{t['trust']['score']} {t['trust']['badge']} | {pts} | {links} | {rec}: {why}{sim} |")


def write(out: str) -> str:
    needs = store.load_needs()
    tools = [r["tool"] for r in store.records() if r.get("tool")]
    titles = {n["id"]: n["title"] for n in needs["needs"]}
    approve = [t["id"] for t in tools if recommend(t)[0] == "approve" and t["status"] == "pending"]
    reject = [t["id"] for t in tools if recommend(t)[0] == "reject" and t["status"] == "pending"]
    lines = [
        "# Catalog review sheet",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `mscatalog report` from catalog/data/records.",
        f"{len(tools)} vetted records: {len(approve)} advised approve, {len(reject)} advised reject. "
        "Nothing here is approved yet. The recommendation column is a rule of thumb; the reviewer decides.",
        "",
        "Signals (points/max): Id = identity (company, people, address), Age = domain age or press, "
        "Data = privacy policy and model-training statement, Price = public prices, Rev = G2, Capterra or App Store "
        "rating, Viab = no shutdown or acquisition news in 12 months. Badges before review are at most caution; "
        "an approved record with 75 or more becomes verified.",
        "",
        "Rule of thumb: reject when identity is 0, there is shutdown news, the score is under 50, the app is rated "
        "under 3.5 from 20 or more reviews, or prices start above $300/month; otherwise approve. Simtest scores are simulated by Claude playing a persona.",
        "",
        "To apply decisions (edit the lists first):",
        "",
        "```",
        f'MS_REVIEWER="<name>" uv run --package mscatalog mscatalog review --approve {",".join(approve)} '
        f'--reject {",".join(reject)}' + (f" --agent-setup {SETUP_VENDOR}" if any(t["id"] == SETUP_VENDOR for t in tools) else ""),
        "```",
        "",
        f"`{SETUP_VENDOR}` is the Task 7 setup vendor (docs/setup-vendor.md); turn agent setup on for it only if approved.",
        "",
    ]
    for nid in titles:
        group = sorted([t for t in tools if t["need_ids"][0] == nid], key=lambda t: -t["trust"]["score"])
        lines += [f"## {titles[nid]} (`{nid}`), {len(group)} tools", ""]
        if not group:
            lines += ["No vetted tools with this as their main job.", ""]
            continue
        lines += ["| id | name | business types | price | score | signals | evidence | recommendation |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [_row(t) for t in group]
        also = [t["id"] for t in tools if nid in t["need_ids"][1:]]
        lines += ["", f"Also does this job: {', '.join(also)}" if also else "", ""]
    Path(out).write_text("\n".join(lines).rstrip() + "\n")
    return out

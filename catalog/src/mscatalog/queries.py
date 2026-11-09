"""The search query grid: business type x default job x 2 phrasings, plus one directory query per job."""


def query_grid(needs: dict) -> list[str]:
    jobs = {n["id"]: n for n in needs["needs"]}
    words = needs["type_words"]
    out: list[str] = []
    for btype, need_ids in needs["type_needs"].items():
        w = words[btype]
        for nid in need_ids:
            job = jobs[nid]
            out.append(f"AI {job['query']} for {w['plural']}")
            out.append(f"best AI tool to {job['verb']} small {w['singular']}")
    for job in needs["needs"]:
        out.append(f"site:theresanaiforthat.com {job['query']}")
    return out


def query_meta(needs: dict) -> dict[str, dict]:
    """Which job and business type each query stands for, so a hit can carry them."""
    jobs = {n["id"]: n for n in needs["needs"]}
    words = needs["type_words"]
    meta: dict[str, dict] = {}
    for btype, need_ids in needs["type_needs"].items():
        w = words[btype]
        for nid in need_ids:
            job = jobs[nid]
            for q in (f"AI {job['query']} for {w['plural']}", f"best AI tool to {job['verb']} small {w['singular']}"):
                meta[q] = {"need_id": nid, "business_type": btype}
    for job in needs["needs"]:
        meta[f"site:theresanaiforthat.com {job['query']}"] = {"need_id": job["id"], "business_type": None}
    return meta

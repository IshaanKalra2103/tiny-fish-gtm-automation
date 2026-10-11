"""Static dashboard: runs/<id>/index.html, rebuilt after every role (auto-refreshes while the run is live)."""

import json
from html import escape

from . import config
from .run import Run

PRIMS = [("search", "Search", "discover URLs"), ("fetch", "Fetch", "read pages"), ("agent", "Agent", "work YouTube filters"),
         ("browser", "Browser", "brand screenshots")]


def build(r: Run) -> str:
    ev = r.read("evidence.json", {})
    ins = r.read("insights.json")
    personas = r.read("personas.json")
    charts = r.read("charts.json", {})
    costs = r.read("costs.json", {"tinyfish_usd": 0, "calls": {}, "llm_tokens": 0})
    timings = r.read("timings.json", {})
    qa = r.read("qa.json")
    pub = r.read("publish.json")
    state = r.read("workflow.json", {})
    status = state.get("status") or (pub or {}).get("status") or ("qa done" if qa else "running")
    live = status not in ("complete", "blocked", "ready_to_publish", "awaiting_approval", "needs_human")
    b = r.brief
    bd = ev.get("brightdata", {})

    cards = "".join(
        f"<div class=card><b>TinyFish {name}</b><span>{why}</span><em>{costs['calls'].get(k, {}).get('calls', 0)} calls · "
        f"${costs['calls'].get(k, {}).get('usd', 0):.3f}</em></div>" for k, name, why in PRIMS)
    cards += (f"<div class='card bd'><b>Bright Data</b><span>TikTok + Reels engagement, persona comments</span><em>"
              + (" · ".join(f"{p}: {s.get('posts', 0)} posts/{s.get('comments', 0)} comments" if s.get("ok") else f"{p}: skipped"
                            for p, s in bd.items()) or "—") + "</em></div>")

    shots = "".join(f"<img src='{escape(s)}'>" for s in ev.get("shots", []))
    social = "".join(f"<tr><td>{escape(p['label'].split(':')[0])}</td><td><a href='{escape(p.get('url') or '#')}'>"
                     f"{escape(p['label'].split(': ', 1)[-1])}</a></td><td>{p['value']:,}</td><td>{p['likes']:,}</td></tr>"
                     for p in charts.get("social_top", []))
    threads = "".join(f"<li><a href='{escape(t['url'])}'>{escape(t['title'] or t['url'])}</a></li>" for t in ev.get("threads", []))
    yt = "".join(f"<li><a href='{escape(v.get('url') or '#')}'>{escape(v.get('title') or '')}</a> · {escape(str(v.get('views') or ''))}</li>"
                 for v in ev.get("youtube", {}).get("videos", []))

    template = ""
    if ins:
        t = ins["template"]
        template = (f"<h3>{escape(t['name'])}</h3><p><b>Hook:</b> {escape(t['hook_pattern'])}</p><ol>"
                    + "".join(f"<li>{escape(x)}</li>" for x in t["beats"]) + f"</ol><p><b>CTA:</b> {escape(t['cta_pattern'])}</p>"
                    f"<p class=muted>{escape(t['why'])}</p><h4>Themes</h4><ul>"
                    + "".join(f"<li><b>{escape(th['name'])}</b> — {escape(th['pain_point'])}</li>" for th in ins["themes"]) + "</ul>")
    pcards = ""
    if personas:
        pcards = f"<p class=muted>{escape(personas['label'])} Source: {escape(personas['source'])}.</p><div class=grid>" + "".join(
            f"<div class=card><b>{escape(p['name'])}</b><span>{escape(p['who'])}</span><small>Responds to: {escape('; '.join(p['responds_to']))}"
            f"<br>Drops off when: {escape('; '.join(p['drops_off_when']))}</small><blockquote>{escape(' / '.join(p['cited_comments'][:2]))}</blockquote></div>"
            for p in personas["personas"]) + "</div>"

    drafts = ""
    for v in range(1, config.MAX_VERSIONS + 1):
        if not r.exists(f"video_v{v}.mp4"):
            continue
        q = r.read(f"qa_v{v}.json")
        s = r.read(f"script_v{v}.json", {})
        verdict = "" if not q else (f"<span class={'pass' if q['passed'] else 'fail'}>{'PASS' if q['passed'] else 'FAIL'} · "
                                    f"{q['avg_score']}/10</span>")
        body = ""
        if q:
            body = ("<ul>" + "".join(f"<li class=fail>{escape(x)}</li>" for x in q["blocking"]) + "</ul>"
                    + "".join(f"<p><b>{escape(rv['persona'])}</b> {rv['score_1_10']}/10 — {escape(rv['top_fix'])}</p>" for rv in q["reviews"])
                    + "<p class=muted>" + " · ".join(f"{escape(c['check'])}: {'✓' if c['passed'] else '✗ ' + escape(c['note'][:80])}"
                                                     for c in q["compliance"]) + "</p>")
        drafts += (f"<div class=draft><h3>Draft v{v} {verdict}</h3><video controls src='video_v{v}.mp4'></video>"
                   f"<p><i>{escape(s.get('changes_from_previous', ''))}</i></p>{body}</div>")

    publish = ""
    if pub:
        c = pub["copy"]
        publish = (f"<p>Status: <b class={'pass' if pub['status'] == 'ready_to_publish' else ''}>{escape(pub['status'])}</b> "
                   f"(publishing is simulated)</p><p><b>TikTok:</b> {escape(c['tiktok_caption'])}</p>"
                   f"<p><b>Reels:</b> {escape(c['reels_caption'])}</p><p><b>Shorts:</b> {escape(c['shorts_title'])}</p>"
                   f"<p class=muted>{escape(' '.join(c['hashtags']))} · link: {escape(pub['link'])}</p>"
                   + ("" if pub["status"] != "awaiting_approval" else f"<p>Approve: <code>uv run gtm approve {escape(r.id)}</code> or on the Paperclip board</p>"))

    log = "".join(f"<tr><td>{escape(e['ts'][11:19])}</td><td>{escape(e['role'])}</td><td>{escape(e['msg'])}</td></tr>"
                  for e in r.activity()[-120:][::-1])

    html = f"""<!doctype html><html><head><meta charset=utf-8><title>GTM run {escape(r.id)}</title>
{'<meta http-equiv=refresh content=6>' if live else ''}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
body{{font-family:-apple-system,Inter,sans-serif;margin:0;background:#0f0f17;color:#eee}} main{{max-width:1200px;margin:auto;padding:24px}}
h1{{margin:0}} h1 span{{color:#ff6a00}} h2{{border-bottom:2px solid #ff6a00;padding-bottom:4px;margin-top:36px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.card{{background:#1b1b27;border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:6px}} .card span,.muted{{color:#aab}}
.card em{{color:#ff6a00;font-style:normal}} .bd{{border:1px dashed #556}} .shots img{{height:320px;border-radius:10px;margin-right:8px}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} canvas{{background:#1b1b27;border-radius:12px;padding:8px}}
table{{width:100%;border-collapse:collapse}} td{{padding:4px 8px;border-bottom:1px solid #2a2a38;font-size:14px}} a{{color:#8cf}}
.drafts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}} .draft{{background:#1b1b27;border-radius:12px;padding:14px}}
video{{width:100%;max-height:600px;border-radius:10px;background:#000}} .pass{{color:#3ddc84}} .fail{{color:#ff5c5c}}
blockquote{{margin:4px 0;color:#ccd;font-style:italic}} code{{background:#2a2a38;padding:2px 6px;border-radius:4px}}
</style></head><body><main>
<h1><span>{escape(b['brand'])}</span> growth loop · {escape(b['niche'])}</h1>
<p class=muted>Run {escape(r.id)} · status <b>{escape(status)}</b> · TinyFish spend ${costs['tinyfish_usd']:.3f} ·
LLM tokens {costs['llm_tokens']:,} · time {sum(timings.values()):.0f}s ({escape(', '.join(f'{k} {v:.0f}s' for k, v in timings.items()))})</p>
<p><b>Current stage:</b> {escape(state.get('current_stage', 'not started'))} · {escape(state.get('stages', {}).get(state.get('current_stage'), {}).get('summary', ''))}</p>
{_identity_block(r)}<h2>Who did what</h2><div class=grid>{cards}</div>
<h2>Trends</h2><div class=charts><canvas id=sources></canvas><canvas id=themes></canvas><canvas id=social></canvas><canvas id=yt></canvas></div>
<h2>Evidence</h2><div class=shots>{shots}</div>
<h3>Top TikToks + Reels (Bright Data, engagement-ranked)</h3><table><tr><td>platform</td><td>post</td><td>views</td><td>likes</td></tr>{social}</table>
<h3>YouTube Shorts this week (TinyFish Agent)</h3><ul>{yt}</ul><h3>Threads read (TinyFish Fetch)</h3><ul>{threads}</ul>
<h2>Template</h2>{template}<h2>Personas</h2>{pcards}
<h2>Drafts → QA → revise</h2><div class=drafts>{drafts}</div>
<h2>Publish</h2>{publish}
<h2>Activity</h2><table>{log}</table>
</main><script>
const C={json.dumps(charts)};
Chart.defaults.color='#ccd';
function bar(id,rows,label,type='bar'){{if(!rows||!rows.length)return;new Chart(document.getElementById(id),{{type,data:{{labels:rows.map(r=>r.label),datasets:[{{label,data:rows.map(r=>r.value),backgroundColor:['#ff6a00','#8cf','#3ddc84','#c8f','#fd4','#f6a']}}]}},options:{{indexAxis:type==='bar'?'y':undefined,plugins:{{title:{{display:true,text:label}}}}}}}})}}
if(C.sources)bar('sources',Object.entries(C.sources).map(([label,value])=>({{label,value}})),'Sources by primitive','doughnut');
bar('themes',C.themes,'Theme strength (evidence-weighted)');bar('social',C.social_top,'TikTok + Reels views');bar('yt',C.youtube,'YouTube Shorts views this week');
</script></body></html>"""
    path = r.path("index.html")
    path.write_text(html)
    index()
    return str(path)


def index() -> None:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runs = sorted((p for p in config.RUNS_DIR.iterdir() if (p / "index.html").exists()), key=lambda p: p.stat().st_mtime, reverse=True)
    items = "".join(f"<li><a href='{p.name}/index.html'>{p.name}</a></li>" for p in runs)
    (config.RUNS_DIR / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>GTM runs</title>"
                                                f"<body style='font-family:sans-serif'><h1>GTM runs</h1><ul>{items}</ul>")


def _identity_block(r: Run) -> str:
    pmf = r.read("identity/pmf.json") or {}
    mood = "<img src='identity/moodboard.png' style='max-width:100%;border-radius:12px'>" if r.exists("identity/moodboard.png") else ""
    if not (pmf or mood):
        return ""
    return (f"<h2>Product identity &amp; PMF (stage 0)</h2><p><b>Niche:</b> {escape(str(pmf.get('chosen_niche', '')))}</p>"
            f"<p><b>Hypothesis:</b> {escape(str(pmf.get('hypothesis', '')))} <span class=muted>(from public signals, not validated)</span></p>{mood}")

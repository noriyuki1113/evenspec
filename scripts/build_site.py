#!/usr/bin/env python3
"""Build the EvenSpec static site into dist/ from data/models.json.

Zero dependencies: Python standard library only.
    python3 scripts/build_site.py
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BASE = "https://evenspec.com"
TRACKING_START = "2026-11-21"
DETAIL_LIMIT = 400

CSS = """
:root{--ink:#1c2733;--muted:#5b6b7a;--line:#d9e1e8;--bg:#f7f9fb;--accent:#0b62b8;--good:#0a7a42;--bad:#b3362b}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff;line-height:1.55}
header{border-bottom:1px solid var(--line);background:var(--bg)}header .wrap{display:flex;gap:20px;align-items:center;padding:12px 16px}
.logo{font-weight:800;font-size:20px;color:var(--ink);text-decoration:none}.logo span{color:var(--accent)}
nav a{margin-right:14px;color:var(--ink);text-decoration:none;font-size:14px}nav a:hover{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}main .wrap{padding-top:20px;padding-bottom:40px}
h1{font-size:26px;margin:8px 0 6px}h2{font-size:19px;margin:26px 0 8px}.sub{color:var(--muted);margin-top:0}
table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0 18px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--bg);cursor:pointer;white-space:nowrap}td.num,th.num{text-align:right}
a{color:var(--accent)}input[type=search],input[type=number]{padding:8px 10px;border:1px solid var(--line);border-radius:6px;font-size:15px}
input[type=search]{width:100%;max-width:520px}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;background:var(--bg);margin:14px 0}
.drop{color:var(--good);font-weight:600}.inc{color:var(--bad);font-weight:600}
.verdict{border-left:4px solid var(--accent);background:var(--bg);padding:10px 14px;margin:14px 0}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px}footer .wrap{padding:16px}
label{display:block;font-size:14px;margin:10px 0 2px}.small{font-size:13px;color:var(--muted)}
"""

FILTER_JS = """
<script>
const q=document.getElementById('q');
if(q){q.addEventListener('input',()=>{const t=q.value.toLowerCase();
document.querySelectorAll('tbody tr').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(t)?'':'none';});});}
document.querySelectorAll('th[data-k]').forEach((th,i)=>{th.addEventListener('click',()=>{
const tb=th.closest('table').querySelector('tbody');const rows=[...tb.rows];
const num=th.dataset.k==='n';const idx=[...th.parentNode.children].indexOf(th);
rows.sort((a,b)=>{let x=a.cells[idx].textContent.replace(/[$,]/g,''),y=b.cells[idx].textContent.replace(/[$,]/g,'');
return num?(parseFloat(x)||0)-(parseFloat(y)||0):x.localeCompare(y);});
rows.forEach(r=>tb.appendChild(r));});});
</script>
"""

# Curated popular model ids (only those that actually exist in the data are used)
POPULAR_IDS = [
    "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini",
    "claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5", "claude-sonnet-4",
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    "deepseek-chat", "deepseek-reasoner", "xai/grok-4.20",
    "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "mistral/mistral-large-latest",
    "command-a-03-2025", "perplexity/sonar-pro",
]
COMPARE_PAIRS = [
    ("gpt-5", "claude-sonnet-4-5"), ("gpt-5", "gemini-2.5-pro"),
    ("gpt-5-mini", "claude-haiku-4-5"), ("gpt-5-mini", "gemini-2.5-flash"),
    ("claude-sonnet-4-5", "gemini-2.5-pro"), ("claude-opus-4-5", "gpt-5"),
    ("claude-sonnet-4-5", "claude-opus-4-5"), ("gpt-4o", "gpt-5"),
    ("gpt-4o-mini", "gpt-5-nano"), ("o3", "gpt-5"),
    ("o3", "claude-sonnet-4-5"), ("gemini-2.5-pro", "gemini-2.5-flash"),
    ("deepseek-chat", "gpt-4o-mini"), ("deepseek-reasoner", "o3"),
    ("deepseek-chat", "gemini-2.5-flash"), ("xai/grok-4.20", "gpt-5"),
    ("xai/grok-4.20", "claude-sonnet-4-5"), ("claude-haiku-4-5", "gemini-2.5-flash"),
    ("gpt-5", "deepseek-chat"), ("claude-opus-4-5", "gemini-2.5-pro"),
    ("gpt-4o", "claude-sonnet-4-5"), ("gpt-5-nano", "gemini-2.5-flash-lite"),
]
MAJOR_PROVIDERS = {
    "openai": 0, "anthropic": 0, "vertex_ai-language-models": 1, "gemini": 1,
    "azure": 2, "bedrock": 2, "bedrock_converse": 2, "openrouter": 2,
    "mistral": 3, "cohere": 3, "deepseek": 3, "xai": 3, "groq": 3,
    "together_ai": 3, "fireworks_ai": 3, "deepinfra": 3, "perplexity": 3,
    "databricks": 4, "snowflake": 4, "oci": 4, "cloudflare": 4, "vercel_ai_gateway": 4,
}
DATE_IN_ID = re.compile(r"(20\d{6}|20\d{2}-\d{2}|-preview|-\d{4}(-|$))")
REGION_PREFIX = re.compile(r"^(us|eu|apac|global|au|jp|in)\.")


def esc(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def fmt_price(v):
    if v is None:
        return "—"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return f"${s}"


def fmt_num(v):
    return f"{v:,}" if isinstance(v, int) else "—"


def layout(title, desc, body, extra=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | EvenSpec</title>
<meta name="description" content="{esc(desc)}">
<link rel="stylesheet" href="/assets/style.css">{extra}</head>
<body><header><div class="wrap"><a class="logo" href="/">Even<span>Spec</span></a>
<nav><a href="/models/">Models</a><a href="/compare/">Compare</a><a href="/price-drops/">Price drops</a><a href="/calculators/coding-agent-cost/">Coding-agent cost</a><a href="/about/">About</a></nav></div></header>
<main><div class="wrap">{body}</div></main>
<footer><div class="wrap">EvenSpec — AI API prices &amp; specs, compared on one fair sheet. Prices are compiled from public data (LiteLLM, MIT) and shown with sources; always verify against the provider's official pricing before purchasing. Tracking started {TRACKING_START}. <a href="/about/">About &amp; disclosures</a></div></footer>
</body></html>"""


def model_row(m, link=True):
    name = f'<a href="/models/{m["slug"]}/">{esc(m["name"])}</a>' if link else esc(m["name"])
    orp = fmt_price(m["openrouter"]["price_in_per_1m"]) if m.get("openrouter") else "—"
    return (f'<tr><td>{name}<br><span class="small">{esc(m["id"])}</span></td>'
            f'<td>{esc(m["provider"])}</td><td class="num">{fmt_num(m["context"])}</td>'
            f'<td class="num">{fmt_price(m["price_in_per_1m"])}</td>'
            f'<td class="num">{fmt_price(m["price_out_per_1m"])}</td>'
            f'<td class="num">{fmt_price(m["price_cache_read_per_1m"])}</td>'
            f'<td class="num">{orp}</td></tr>')


TABLE_HEAD = ('<table><thead><tr><th>Model</th><th>Provider</th><th class="num" data-k="n">Context</th>'
              '<th class="num" data-k="n">Input /1M</th><th class="num" data-k="n">Output /1M</th>'
              '<th class="num" data-k="n">Cached input /1M</th><th class="num" data-k="n">OpenRouter input /1M</th>'
              '</tr></thead><tbody>')


def detail_score(m):
    """Rank models for detail pages: major providers, canonical ids first."""
    prov_rank = MAJOR_PROVIDERS.get(m["provider"], 9)
    penalty = 0
    if DATE_IN_ID.search(m["id"]):
        penalty += 3
    if REGION_PREFIX.match(m["id"]):
        penalty += 2
    if ":" in m["id"] or "@" in m["id"]:
        penalty += 2
    canonical = 0 if "/" not in m["id"] or m["provider"] in ("gemini", "openrouter") else 1
    return (prov_rank, penalty, canonical, len(m["id"]), m["id"])


def main():
    data = json.loads((ROOT / "data" / "models.json").read_text())
    models = data["models"]
    gen = data.get("generated_at", TRACKING_START)
    events_path = ROOT / "data" / "price_events.json"
    events = json.loads(events_path.read_text()) if events_path.exists() else []
    by_id = {m["id"]: m for m in models}
    by_slug = {m["slug"]: m for m in models}

    if DIST.exists():
        import shutil
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    (DIST / "assets" / "style.css").write_text(CSS)
    urls = ["/"]

    def write(path, content):
        p = DIST / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    popular = [by_id[i] for i in POPULAR_IDS if i in by_id]
    detail_models = sorted(models, key=detail_score)[:DETAIL_LIMIT]
    detail_slugs = {m["slug"] for m in detail_models}

    # ---- home ----
    drops = [e for e in events if e["direction"] == "drop"][-10:]
    if drops:
        drop_html = "<ul>" + "".join(
            f'<li><a href="/models/{e["slug"]}/">{esc(e["model_id"])}</a>: {esc(e["field"])} '
            f'{fmt_price(e["old"])} → <span class="drop">{fmt_price(e["new"])}</span> ({esc(e["date"])})</li>'
            for e in reversed(drops)) + "</ul>"
    else:
        drop_html = (f'<p>No price changes recorded yet. Tracking started on {TRACKING_START}; '
                     "drops and increases will appear here as the daily data updates land.</p>")
    rows = "".join(model_row(m) for m in popular)
    write("index.html", layout(
        "AI API prices & specs, compared fairly",
        "Compare AI model API prices, context windows and specs across providers on one fair sheet. Daily-updated from public data.",
        f"""<h1>Every AI model. Every host. One fair spec sheet.</h1>
<p class="sub">API prices, context windows and specs for {len(models):,} priced models, updated {esc(gen)}. Data: LiteLLM (MIT), with OpenRouter prices shown alongside where available.</p>
<p><input type="search" id="q" placeholder="Search the popular models below, or browse all models…"></p>
<div class="card"><h2 style="margin-top:0">Latest price drops</h2>{drop_html}<p><a href="/price-drops/">All price changes →</a></p></div>
<h2>Popular models</h2>{TABLE_HEAD}{rows}</tbody></table>
<p><a href="/models/">Browse all {len(models):,} models →</a> · <a href="/calculators/coding-agent-cost/">What will a coding agent cost you per month? →</a></p>
{FILTER_JS}"""))
    urls += ["/models/", "/price-drops/", "/calculators/coding-agent-cost/", "/about/", "/compare/"]

    # ---- models index ----
    rows = "".join(model_row(m, link=m["slug"] in detail_slugs) for m in models)
    write("models/index.html", layout(
        "All AI models — prices & specs",
        f"Full list of {len(models):,} AI models with API prices per 1M tokens, context windows and cached-input prices.",
        f"""<h1>All models</h1><p class="sub">{len(models):,} models with published token pricing. Click a column header to sort. Models in bold links have a detail page.</p>
<p><input type="search" id="q" placeholder="Filter by model or provider…"></p>
{TABLE_HEAD}{rows}</tbody></table>{FILTER_JS}"""))

    # ---- model detail pages ----
    by_provider = {}
    for m in models:
        by_provider.setdefault(m["provider"], []).append(m)
    for m in detail_models:
        orow = ""
        if m.get("openrouter"):
            o = m["openrouter"]
            orow = (f'<tr><td>OpenRouter price (reference)</td><td class="num">{fmt_price(o["price_in_per_1m"])}</td>'
                    f'<td class="num">{fmt_price(o["price_out_per_1m"])}</td><td>—</td>'
                    f'<td><a href="{esc(o["url"])}" rel="nofollow">OpenRouter</a></td></tr>')
        src = f'<a href="{esc(m["source_url"])}" rel="nofollow">provider source via LiteLLM</a>' if m.get("source_url") else "LiteLLM dataset"
        alts = [a for a in by_provider.get(m["provider"], []) if a["id"] != m["id"]][:3]
        alt_html = "".join(f'<li><a href="/models/{a["slug"]}/">{esc(a["name"])}</a> — {fmt_price(a["price_in_per_1m"])} in / {fmt_price(a["price_out_per_1m"])} out per 1M</li>' if a["slug"] in detail_slugs else f'<li>{esc(a["name"])} — {fmt_price(a["price_in_per_1m"])} in / {fmt_price(a["price_out_per_1m"])} out per 1M</li>' for a in alts)
        body = f"""<h1>{esc(m["name"])}</h1>
<p class="sub">{esc(m["id"])} · provider: {esc(m["provider"])} · updated {esc(gen)}</p>
<h2>Spec sheet</h2>
<table><tbody>
<tr><th>Context window</th><td class="num">{fmt_num(m["context"])} tokens</td></tr>
<tr><th>Max output</th><td class="num">{fmt_num(m["max_output"])} tokens</td></tr>
<tr><th>Mode</th><td>{esc(m["mode"])}</td></tr>
</tbody></table>
<h2>Prices (per 1M tokens)</h2>
<table><thead><tr><th>Source</th><th class="num">Input</th><th class="num">Output</th><th class="num">Cached input</th><th>Reference</th></tr></thead><tbody>
<tr><td>Listed price (LiteLLM)</td><td class="num">{fmt_price(m["price_in_per_1m"])}</td><td class="num">{fmt_price(m["price_out_per_1m"])}</td><td class="num">{fmt_price(m["price_cache_read_per_1m"])}</td><td>{src}</td></tr>
{orow}</tbody></table>
<p class="small">Prices are compiled from public data and change frequently. Always verify against the provider's official pricing page before purchasing.</p>
<h2>Alternatives from the same provider</h2><ul>{alt_html or '<li>—</li>'}</ul>
<p><a href="/calculators/coding-agent-cost/">Estimate this model's monthly coding-agent cost →</a></p>"""
        write(f"models/{m['slug']}/index.html", layout(
            f"{m['name']} — price & specs", f"{m['name']} API price per 1M tokens, context window and specs.", body))
        urls.append(f"/models/{m['slug']}/")

    # ---- compare pages ----
    pairs = [(by_id[a], by_id[b]) for a, b in COMPARE_PAIRS if a in by_id and b in by_id]
    pair_links = []
    for a, b in pairs:
        slug = f"{a['slug']}-vs-{b['slug']}"
        def cell(m, key, money=False):
            v = m.get(key)
            return fmt_price(v) if money else fmt_num(v)
        def verdict(a, b):
            if a["price_out_per_1m"] and b["price_out_per_1m"]:
                cheap, dear = (a, b) if a["price_out_per_1m"] < b["price_out_per_1m"] else (b, a)
                if dear["price_out_per_1m"]:
                    pct = round((1 - cheap["price_out_per_1m"] / dear["price_out_per_1m"]) * 100)
                    return f"{cheap['name']} is {pct}% cheaper on output tokens ({fmt_price(cheap['price_out_per_1m'])} vs {fmt_price(dear['price_out_per_1m'])} per 1M). Check the context and cached-input rows before deciding on price alone."
            return "Prices are close or incomplete — compare context window and cached-input pricing."
        body = f"""<h1>{esc(a['name'])} vs {esc(b['name'])}</h1>
<p class="sub">Same spec sheet, same units: prices per 1M tokens, updated {esc(gen)}.</p>
<div class="verdict"><strong>Verdict:</strong> {esc(verdict(a, b))}</div>
<table><thead><tr><th></th><th>{esc(a['name'])}</th><th>{esc(b['name'])}</th></tr></thead><tbody>
<tr><td>Model ID</td><td>{esc(a['id'])}</td><td>{esc(b['id'])}</td></tr>
<tr><td>Provider</td><td>{esc(a['provider'])}</td><td>{esc(b['provider'])}</td></tr>
<tr><td>Input /1M</td><td class="num">{cell(a,'price_in_per_1m',True)}</td><td class="num">{cell(b,'price_in_per_1m',True)}</td></tr>
<tr><td>Output /1M</td><td class="num">{cell(a,'price_out_per_1m',True)}</td><td class="num">{cell(b,'price_out_per_1m',True)}</td></tr>
<tr><td>Cached input /1M</td><td class="num">{cell(a,'price_cache_read_per_1m',True)}</td><td class="num">{cell(b,'price_cache_read_per_1m',True)}</td></tr>
<tr><td>Context</td><td class="num">{cell(a,'context')}</td><td class="num">{cell(b,'context')}</td></tr>
<tr><td>Max output</td><td class="num">{cell(a,'max_output')}</td><td class="num">{cell(b,'max_output')}</td></tr>
</tbody></table>
<p><a href="/models/{a['slug']}/">{esc(a['name'])} details</a> · <a href="/models/{b['slug']}/">{esc(b['name'])} details</a></p>"""
        write(f"compare/{slug}/index.html", layout(
            f"{a['name']} vs {b['name']} — price & specs",
            f"Side-by-side price and spec comparison: {a['name']} vs {b['name']}.", body))
        urls.append(f"/compare/{slug}/")
        pair_links.append(f'<li><a href="/compare/{slug}/">{esc(a["name"])} vs {esc(b["name"])}</a></li>')
    write("compare/index.html", layout(
        "Model comparisons", "Side-by-side AI model price and spec comparisons.",
        f"<h1>Comparisons</h1><ul>{''.join(pair_links)}</ul>"))

    # ---- price drops ----
    if events:
        ev_rows = "".join(
            f'<tr><td>{esc(e["date"])}</td><td><a href="/models/{e["slug"]}/">{esc(e["model_id"])}</a></td>'
            f'<td>{esc(e["field"])}</td><td class="num">{fmt_price(e["old"])}</td>'
            f'<td class="num"><span class="{"drop" if e["direction"]=="drop" else "inc"}">{fmt_price(e["new"])}</span></td></tr>'
            for e in reversed(events[-200:]))
        ev_html = f"<table><thead><tr><th>Date</th><th>Model</th><th>Field</th><th class='num'>Was</th><th class='num'>Now</th></tr></thead><tbody>{ev_rows}</tbody></table>"
    else:
        ev_html = (f'<div class="card"><p><strong>Tracking started on {TRACKING_START}.</strong> '
                   "No price changes have been recorded yet. This page is rebuilt daily from the LiteLLM dataset; "
                   "every input/output price change will be logged here with the old and new price.</p></div>")
    write("price-drops/index.html", layout(
        "AI API price drops & increases",
        "Daily log of AI model API price changes: drops and increases, with old and new prices per 1M tokens.",
        f"<h1>Price drops &amp; changes</h1><p class='sub'>Logged automatically from daily data updates since {TRACKING_START}.</p>{ev_html}"))

    # ---- calculator ----
    calc_models = popular[:24]
    calc_json = json.dumps([{"name": m["name"], "slug": m["slug"],
                             "pin": m["price_in_per_1m"] or 0, "pout": m["price_out_per_1m"] or 0}
                            for m in calc_models])
    calc_rows = "".join(f'<tr><td><a href="/models/{m["slug"]}/">{esc(m["name"])}</a></td><td class="num" data-cost="{m["slug"]}"></td></tr>' for m in calc_models)
    calc_body = f"""<h1>Coding-agent cost calculator</h1>
<p class="sub">Estimate what an AI coding agent (Claude Code, Codex, Cursor-style usage) costs per month on each major model. Runs entirely in your browser; nothing is sent anywhere.</p>
<label>Hours of agent use per day <input type="number" id="hours" value="2" min="0" step="0.5"></label>
<label>Working days per month <input type="number" id="days" value="22" min="1" max="31"></label>
<label>Input tokens per hour (context-heavy; 50,000 is a typical heavy session) <input type="number" id="tin" value="50000" step="1000"></label>
<label>Output tokens per hour <input type="number" id="tout" value="8000" step="500"></label>
<p class="small">Monthly tokens: <span id="mtok"></span>. Formula: monthly cost = (input tokens/1M × input price) + (output tokens/1M × output price). Cached-input discounts are not applied, so treat this as an upper bound.</p>
<table><thead><tr><th>Model</th><th class="num">Estimated monthly cost</th></tr></thead><tbody>{calc_rows}</tbody></table>
<script>
const MODELS={calc_json};
function calc(){{const h=+document.getElementById('hours').value||0,d=+document.getElementById('days').value||0,
ti=+document.getElementById('tin').value||0,to=+document.getElementById('tout').value||0;
const mi=h*d*ti, mo=h*d*to;document.getElementById('mtok').textContent=(mi/1e6).toFixed(2)+'M input, '+(mo/1e6).toFixed(2)+'M output';
MODELS.forEach(m=>{{const c=mi/1e6*m.pin+mo/1e6*m.pout;const el=document.querySelector('[data-cost="'+m.slug+'"]');if(el)el.textContent='$'+c.toFixed(2);}});}}
document.querySelectorAll('input').forEach(i=>i.addEventListener('input',calc));calc();
</script>"""
    write("calculators/coding-agent-cost/index.html", layout(
        "Coding-agent cost calculator",
        "Estimate monthly AI coding-agent costs per model from your daily usage.", calc_body))

    # ---- about ----
    write("about/index.html", layout(
        "About EvenSpec — data sources & disclosures",
        "How EvenSpec compiles AI API prices: data sources, licenses, and affiliate disclosure.",
        f"""<h1>About EvenSpec</h1>
<p>EvenSpec puts AI model API prices and specs on one fair sheet: same units (USD per 1M tokens), same fields, updated daily from public data. Tracking started on {TRACKING_START}; the current dataset was generated on {esc(gen)} and covers {len(models):,} priced models.</p>
<h2>Data sources &amp; licenses</h2>
<ul>
<li><strong>Primary:</strong> the <a href="https://github.com/BerriAI/litellm" rel="nofollow">LiteLLM</a> model prices &amp; context window dataset, licensed under the <strong>MIT License</strong> (© BerriAI). Prices shown as "Listed price (LiteLLM)" come from this dataset, which itself cites each provider's official source.</li>
<li><strong>Secondary:</strong> <a href="https://openrouter.ai/models" rel="nofollow">OpenRouter</a>'s public model list. Where a matching model exists, its OpenRouter price is shown alongside, clearly labeled and linked, as a reference only.</li>
</ul>
<h2>Accuracy</h2>
<p>Prices change frequently and this site is compiled automatically. <strong>Always verify prices against the provider's official pricing page before purchasing.</strong> If you spot an error, the underlying LiteLLM dataset is open source and accepts corrections.</p>
<h2>Affiliate disclosure</h2>
<p>Some outbound links on this site may be affiliate links: if you sign up with a provider through one, EvenSpec may earn a commission at no extra cost to you. Affiliate relationships never change the prices or the order of the data shown — every model is listed from the same public dataset, whether or not a program exists. Core model providers (including OpenAI, Anthropic and Google) do not offer public affiliate programs, and no provider pays for placement in the tables.</p>
<h2>Contact</h2>
<p>EvenSpec is an independent project, not affiliated with any model provider.</p>"""))

    # ---- 404 ----
    write("404.html", layout("Page not found", "The page you requested does not exist on EvenSpec.",
        """<h1>Page not found</h1>
<p>The page you requested does not exist. It may have been moved as model names and pricing pages are regenerated daily.</p>
<p><a href="/models/">Browse all AI models</a> · <a href="/">EvenSpec home</a></p>"""))

    # ---- sitemap & robots ----
    sm = "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")

    n_pages = sum(1 for _ in DIST.rglob("index.html")) + 1  # + home index counted once via rglob already; keep simple below
    total_html = sum(1 for _ in DIST.rglob("*.html"))
    print(f"built {total_html} HTML pages ({len(detail_models)} model detail, {len(pairs)} compare), {len(models)} models listed, sitemap urls: {len(urls)}")


if __name__ == "__main__":
    main()

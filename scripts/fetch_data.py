#!/usr/bin/env python3
"""Fetch LiteLLM + OpenRouter data, normalize to data/models.json.

Zero dependencies: Python standard library only.
Primary source: LiteLLM (MIT). OpenRouter prices are stored as a secondary,
attributed field only (see README / About page).

Usage:
    python3 scripts/fetch_data.py            # try network, fall back to raw cache
    python3 scripts/fetch_data.py --offline  # use data/raw/ as-is

Price-change events: before overwriting data/models.json, the previous
version is compared field-by-field and changes are appended to
data/price_events.json. On the first run there is no previous version, so
price_events.json is created as an empty baseline.
"""
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MODELS_JSON = ROOT / "data" / "models.json"
EVENTS_JSON = ROOT / "data" / "price_events.json"

LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

TRACKED_FIELDS = ("price_in_per_1m", "price_out_per_1m", "price_cache_read_per_1m")


def fetch(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "evenspec-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        print(f"fetched {url} -> {dest.name}")
        return True
    except Exception as e:  # network down, etc. -> fall back to cache
        print(f"WARNING: fetch failed for {url}: {e}; using cached {dest.name}")
        return False


def per_1m(per_token):
    if per_token is None:
        return None
    return round(float(per_token) * 1_000_000, 6)


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:120]


def display_name(model_id: str) -> str:
    tail = model_id.split("/")[-1]
    tail = re.sub(r"(-v\d+(:\d+)?|@.*|:\d+)$", "", tail)
    return tail


# --- OpenRouter matching -------------------------------------------------
DATE_SUFFIX = re.compile(r"-(20\d{6}|20\d{2}-\d{2}-\d{2})(-v\d+(:\d+)?)?$")
DECOR_SUFFIX = re.compile(r"(-v\d+(:\d+)?|:\d+|@.*)$")


def norm_key(s: str) -> str:
    s = s.lower().strip()
    s = DECOR_SUFFIX.sub("", s)
    s = DATE_SUFFIX.sub("", s)
    s = DECOR_SUFFIX.sub("", s)
    return s


def build_openrouter_index(or_data):
    """Map normalized candidate keys -> {price_in, price_out, id}."""
    index = {}
    for m in or_data:
        oid = m.get("id", "")
        pricing = m.get("pricing") or {}
        try:
            pin = per_1m(float(pricing["prompt"])) if pricing.get("prompt") is not None else None
            pout = per_1m(float(pricing["completion"])) if pricing.get("completion") is not None else None
        except (TypeError, ValueError):
            continue
        if pin is None and pout is None:
            continue
        entry = {"id": oid, "price_in_per_1m": pin, "price_out_per_1m": pout,
                 "url": f"https://openrouter.ai/{oid}"}
        candidates = {norm_key(oid), norm_key(oid.split("/")[-1])}
        for c in candidates:
            index.setdefault(c, entry)
    return index


def openrouter_match(model_id: str, index):
    candidates = [norm_key(model_id), norm_key(model_id.split("/")[-1])]
    # also try stripping a leading provider segment like "gemini/" or "openai/"
    if "/" in model_id:
        candidates.append(norm_key("/".join(model_id.split("/")[1:])))
    for c in candidates:
        if c in index:
            return index[c]
    return None


def normalize(litellm: dict, or_index) -> list:
    models = []
    for mid, v in sorted(litellm.items()):
        if mid == "sample_spec":
            continue
        if v.get("mode") not in ("chat", "responses", "completion"):
            continue
        pin = per_1m(v.get("input_cost_per_token"))
        pout = per_1m(v.get("output_cost_per_token"))
        if pin is None and pout is None:
            continue
        provider = v.get("litellm_provider") or (mid.split("/")[0] if "/" in mid else "unknown")
        orm = openrouter_match(mid, or_index)
        models.append({
            "id": mid,
            "slug": slugify(mid),
            "name": display_name(mid),
            "provider": provider,
            "mode": v.get("mode"),
            "context": v.get("max_input_tokens"),
            "max_output": v.get("max_output_tokens"),
            "price_in_per_1m": pin,
            "price_out_per_1m": pout,
            "price_cache_read_per_1m": per_1m(v.get("cache_read_input_token_cost")),
            "price_cache_create_per_1m": per_1m(v.get("cache_creation_input_token_cost")),
            "source_url": v.get("source"),
            "openrouter": orm,
        })
    return models


def diff_events(old_models: list, new_models: list, today: str) -> list:
    old = {m["id"]: m for m in old_models}
    events = []
    for m in new_models:
        o = old.get(m["id"])
        if not o:
            continue
        for f in TRACKED_FIELDS:
            if o.get(f) != m.get(f) and o.get(f) is not None and m.get(f) is not None:
                direction = "drop" if m[f] < o[f] else "increase"
                events.append({
                    "date": today, "model_id": m["id"], "slug": m["slug"],
                    "field": f, "old": o[f], "new": m[f], "direction": direction,
                })
    return events


def main():
    offline = "--offline" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    if not offline:
        fetch(LITELLM_URL, RAW / "litellm.json")
        fetch(OPENROUTER_URL, RAW / "openrouter.json")

    litellm = json.loads((RAW / "litellm.json").read_text())
    or_raw = json.loads((RAW / "openrouter.json").read_text())
    or_data = or_raw.get("data", []) if isinstance(or_raw, dict) else or_raw

    or_index = build_openrouter_index(or_data)
    models = normalize(litellm, or_index)
    matched = sum(1 for m in models if m["openrouter"])

    today = date.today().isoformat()
    # price events vs previous snapshot
    if EVENTS_JSON.exists():
        events = json.loads(EVENTS_JSON.read_text())
    else:
        events = []
    if MODELS_JSON.exists():
        old_models = json.loads(MODELS_JSON.read_text()).get("models", [])
        new_events = diff_events(old_models, models, today)
        if new_events:
            events.extend(new_events)
            print(f"price events added: {len(new_events)}")
    else:
        print("no previous models.json -> baseline, price_events starts empty")

    MODELS_JSON.write_text(json.dumps(
        {"generated_at": today, "count": len(models), "models": models}, indent=1))
    EVENTS_JSON.write_text(json.dumps(events, indent=1))
    print(f"models: {len(models)} (openrouter matched: {matched}), events total: {len(events)}")


if __name__ == "__main__":
    main()

"""
Fetch themes from AskLivermore, compute weighted scores, and generate
an interactive HTML dashboard with sortable columns.
"""

import json
import requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
TMP = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)

SUPABASE_URL = "https://dwihwpjhzssmssdewzof.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3aWh3cGpoenNzbXNzZGV3em9mIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNjU4OTMsImV4cCI6MjA5Mjc0MTg5M30.1PrjsczV70qNSssx4gTM_SXYUw1s7IfmI3ZeR6l6jtM"
SITE_URL = "https://www.asklivermore.com"

WEIGHTS = {"1d": 0.10, "1w": 0.25, "1m": 0.40, "3m": 0.25}


def login(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, json={"email": email, "password": password}, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_themes(access_token: str) -> list:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {access_token}"})
    resp = session.get(f"{SITE_URL}/api/themes")
    if resp.status_code != 200:
        session.cookies.set("sb-access-token", access_token, domain="www.asklivermore.com")
        resp = session.get(f"{SITE_URL}/api/themes")
    resp.raise_for_status()
    data = resp.json()
    return data.get("mainstream", []) + data.get("tomorrow", [])


def build_records(themes: list) -> list:
    records = []
    for t in themes:
        perf = t.get("performance", {})
        p1d = perf.get("1d") or 0
        p1w = perf.get("1w") or 0
        p1m = perf.get("1m") or 0
        p3m = perf.get("3m") or 0
        score = round(
            WEIGHTS["1d"] * p1d + WEIGHTS["1w"] * p1w +
            WEIGHTS["1m"] * p1m + WEIGHTS["3m"] * p3m, 2
        )
        ratings = t.get("ratings", {})
        records.append({
            "name":        t.get("name", ""),
            "id":          t.get("id", ""),
            "category":    t.get("category", ""),
            "theme_type":  t.get("theme_type", ""),
            "crowding":    t.get("crowding", ""),
            "stock_count": t.get("stock_count", 0),
            "1d":  p1d, "1w": p1w, "1m": p1m, "3m": p3m,
            "score": score,
            "avg_ta":  ratings.get("avg_ta") or 0,
            "avg_fa":  ratings.get("avg_fa") or 0,
            "avg_ars": ratings.get("avg_ars") or 0,
            "as_of":   t.get("as_of", ""),
        })
    records.sort(key=lambda x: x["score"], reverse=True)
    return records


def generate_html(records: list, crossref: list, themes_full: list, scanners_raw: dict) -> Path:
    template_path = Path(__file__).parent / "dashboard_template.html"
    template = template_path.read_text(encoding="utf-8")
    html = template.replace("__THEMES_DATA__", json.dumps(records, ensure_ascii=False))
    html = html.replace("__CROSSREF_DATA__", json.dumps(crossref, ensure_ascii=False))
    html = html.replace("__THEMES_FULL_DATA__", json.dumps(themes_full, ensure_ascii=False))
    html = html.replace("__SCANNERS_RAW_DATA__", json.dumps(scanners_raw, ensure_ascii=False))
    out = ROOT / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


def main():
    from dotenv import load_dotenv
    import os
    load_dotenv(ROOT / ".env")

    email    = os.getenv("ASKLIVERMORE_EMAIL", "dodo.ebayer@gmail.com")
    password = os.getenv("ASKLIVERMORE_PASSWORD", "livermore123")

    print("Logging in...", flush=True)
    token = login(email, password)
    print("Fetching themes...", flush=True)
    themes = fetch_themes(token)
    print(f"Got {len(themes)} themes.", flush=True)

    records = build_records(themes)

    # Save JSON
    (TMP / "theme_ranking.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Cross-reference
    from cross_reference import login as cr_login, make_session, fetch_themes as cr_fetch, fetch_scanner, build_crossref, FAVORITE_SCANNERS
    print("Fetching scanner results for cross-reference...", flush=True)
    session = make_session(token)
    scanner_results = {}
    for sid, label in FAVORITE_SCANNERS.items():
        scanner_results[sid] = fetch_scanner(session, sid)
        print(f"  {label}: {len(scanner_results[sid])} results", flush=True)
    crossref = build_crossref(themes, scanner_results, top_n=30)
    print(f"Cross-reference: {len(crossref)} titoli in incrocio", flush=True)
    (TMP / "crossref.json").write_text(json.dumps(crossref, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build themes_full: all themes with stocks[] and score for JS dynamic crossref
    from cross_reference import score as cr_score
    themes_full = []
    for t in themes:
        themes_full.append({
            "id":    t.get("id", ""),
            "name":  t.get("name", ""),
            "score": round(cr_score(t), 2),
            "stocks": t.get("stocks", []),
        })
    themes_full.sort(key=lambda x: x["score"], reverse=True)

    # Build scanners_raw: {scanner_id: [{ticker, name, price, change_pct, ta_rating, fa_rating, rs_rating, sector, avg_vol_50, tv_symbol}]}
    scanners_raw = {}
    for sid, matches in scanner_results.items():
        scanners_raw[sid] = [{
            "ticker":     m.get("ticker", ""),
            "name":       m.get("name", ""),
            "price":      m.get("price", 0),
            "change_pct": m.get("change_pct", 0),
            "ta_rating":  m.get("ta_rating", 0),
            "fa_rating":  m.get("fa_rating", 0),
            "rs_rating":  m.get("rs_rating", 0),
            "sector":     m.get("sector", ""),
            "avg_vol_50": m.get("avg_vol_50", 0),
            "tv_symbol":  m.get("tv_symbol", ""),
        } for m in matches if m.get("ticker")]

    # Generate HTML dashboard
    out = generate_html(records, crossref, themes_full, scanners_raw)
    print(f"\nDashboard generata: {out}")
    return out


if __name__ == "__main__":
    main()

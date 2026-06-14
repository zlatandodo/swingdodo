"""
Cross-reference: stocks in top-N themes (by weighted score) vs favorite scanners.
Outputs .tmp/crossref.json
"""

import json
import requests
from pathlib import Path

ROOT = Path(__file__).parent.parent
TMP  = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)

SUPABASE_URL      = "https://dwihwpjhzssmssdewzof.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3aWh3cGpoenNzbXNzZGV3em9mIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNjU4OTMsImV4cCI6MjA5Mjc0MTg5M30.1PrjsczV70qNSssx4gTM_SXYUw1s7IfmI3ZeR6l6jtM"
SITE_URL          = "https://www.asklivermore.com"

WEIGHTS = {"1d": 0.10, "1w": 0.25, "1m": 0.40, "3m": 0.25}

FAVORITE_SCANNERS = {
    "bull-flag":              "Bull Flag",
    "golden-pocket":          "Golden Pocket",
    "vcp":                    "VCP | Minervini",
    "ascending-triangle":     "Ascending Triangle",
    "pocket-pivot":           "Pocket Pivot",
    "peg-flag":               "PEG Flag",
    "insider-buying":         "Insider Buying",
    "volume-surge":           "Volume Surge",
    "inverse-head-shoulders": "Inv. H&S",
    "rsi-oversold":           "RSI Oversold",
    "livermore-pivotal":      "Livermore Pivotal",
    "livermore-buy-the-dip":  "Buy the Dip",
}


def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def fetch_themes(session: requests.Session) -> list:
    resp = session.get(f"{SITE_URL}/api/themes")
    resp.raise_for_status()
    d = resp.json()
    return d.get("mainstream", []) + d.get("tomorrow", [])


def score(theme: dict) -> float:
    p = theme.get("performance", {})
    return sum(WEIGHTS[k] * (p.get(k) or 0.0) for k in WEIGHTS)


def fetch_scanner(session: requests.Session, scanner_id: str) -> list:
    resp = session.get(f"{SITE_URL}/api/scanners/{scanner_id}/results")
    if resp.status_code != 200:
        print(f"  WARNING: {scanner_id} -> {resp.status_code}")
        return []
    return resp.json().get("matches", [])


def build_crossref(themes: list, scanner_results: dict, top_n: int = 30) -> list:
    # Rank themes
    ranked = sorted(themes, key=score, reverse=True)[:top_n]

    # ticker -> list of themes
    ticker_themes: dict[str, list] = {}
    for idx, theme in enumerate(ranked):
        for ticker in theme.get("stocks", []):
            if ticker not in ticker_themes:
                ticker_themes[ticker] = []
            ticker_themes[ticker].append({
                "rank":  idx + 1,
                "theme": theme["name"],
                "score": round(score(theme), 1),
                "crowding":    theme.get("crowding", ""),
                "theme_type":  theme.get("theme_type", ""),
            })

    # ticker -> scanner appearances
    ticker_scanners: dict[str, list] = {}
    ticker_meta: dict[str, dict] = {}
    for sid, label in FAVORITE_SCANNERS.items():
        for match in scanner_results.get(sid, []):
            tk = match.get("ticker", "")
            if not tk:
                continue
            if tk not in ticker_scanners:
                ticker_scanners[tk] = []
                ticker_meta[tk] = {
                    "name":       match.get("name", ""),
                    "price":      match.get("price", 0),
                    "change_pct": match.get("change_pct", 0),
                    "ta_rating":  match.get("ta_rating", 0),
                    "fa_rating":  match.get("fa_rating", 0),
                    "rs_rating":  match.get("rs_rating", 0),
                    "sector":     match.get("sector", ""),
                    "avg_vol_50": match.get("avg_vol_50", 0),
                }
            ticker_scanners[tk].append(label)

    # Intersect
    results = []
    for ticker, t_themes in ticker_themes.items():
        if ticker not in ticker_scanners:
            continue
        meta = ticker_meta[ticker]
        results.append({
            "ticker":           ticker,
            "name":             meta["name"],
            "price":            meta["price"],
            "change_pct":       meta["change_pct"],
            "ta_rating":        meta["ta_rating"],
            "fa_rating":        meta["fa_rating"],
            "rs_rating":        meta["rs_rating"],
            "sector":           meta["sector"],
            "avg_vol_50":       meta["avg_vol_50"],
            "themes":           t_themes,
            "theme_count":      len(t_themes),
            "best_theme_rank":  min(t["rank"] for t in t_themes),
            "best_theme_score": max(t["score"] for t in t_themes),
            "scanners":         ticker_scanners[ticker],
            "scanner_count":    len(ticker_scanners[ticker]),
        })

    # Sort: scanner_count desc, then best_theme_rank asc
    results.sort(key=lambda x: (-x["scanner_count"], x["best_theme_rank"]))
    return results


def main():
    from dotenv import load_dotenv
    import os
    load_dotenv(ROOT / ".env")
    email    = os.getenv("ASKLIVERMORE_EMAIL", "dodo.ebayer@gmail.com")
    password = os.getenv("ASKLIVERMORE_PASSWORD", "livermore123")

    print("Logging in...", flush=True)
    token   = login(email, password)
    session = make_session(token)

    print("Fetching themes...", flush=True)
    themes = fetch_themes(session)
    print(f"  {len(themes)} themes", flush=True)

    print("Fetching scanner results...", flush=True)
    scanner_results = {}
    for sid, label in FAVORITE_SCANNERS.items():
        matches = fetch_scanner(session, sid)
        scanner_results[sid] = matches
        print(f"  {label}: {len(matches)} results", flush=True)

    print("Computing cross-reference (top 30 themes)...", flush=True)
    crossref = build_crossref(themes, scanner_results, top_n=30)
    print(f"  {len(crossref)} stocks at intersection", flush=True)

    out = TMP / "crossref.json"
    out.write_text(json.dumps(crossref, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out}")
    return crossref


if __name__ == "__main__":
    main()

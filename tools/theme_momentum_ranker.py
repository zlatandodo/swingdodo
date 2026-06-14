"""
Fetch all themes from AskLivermore and rank them by momentum score.

Weighted formula:
  score = 5% * perf_1d + 50% * perf_1w + 30% * perf_1m + 15% * perf_3m
"""

import json
import sys
import requests
from pathlib import Path

ROOT = Path(__file__).parent.parent
TMP = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)

SUPABASE_URL = "https://dwihwpjhzssmssdewzof.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3aWh3cGpoenNzbXNzZGV3em9mIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNjU4OTMsImV4cCI6MjA5Mjc0MTg5M30.1PrjsczV70qNSssx4gTM_SXYUw1s7IfmI3ZeR6l6jtM"
SITE_URL = "https://www.asklivermore.com"

WEIGHT_SCHEMES = {
    "tuo":    {"1d": 0.05, "1w": 0.50, "1m": 0.30, "3m": 0.15},
    "gemini": {"1d": 0.10, "1w": 0.20, "1m": 0.45, "3m": 0.25},
    "claude": {"1d": 0.10, "1w": 0.25, "1m": 0.40, "3m": 0.25},
}
WEIGHTS = WEIGHT_SCHEMES["tuo"]  # default

CROWDING_ORDER = ["very uncrowded", "uncrowded", "moderate", "crowded"]


def login(email: str, password: str) -> str:
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json={"email": email, "password": password}, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_themes(access_token: str) -> list:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Cookie": "",
    }
    session = requests.Session()
    session.headers.update(headers)

    # Supabase sets the session via cookie after login — try direct API call
    resp = session.get(f"{SITE_URL}/api/themes")
    if resp.status_code != 200:
        # Fallback: pass token as cookie (some Next.js/Supabase setups)
        session.cookies.set("sb-access-token", access_token, domain="www.asklivermore.com")
        resp = session.get(f"{SITE_URL}/api/themes")
    resp.raise_for_status()
    data = resp.json()
    return data.get("mainstream", []) + data.get("tomorrow", [])


def compute_score(perf: dict, weights: dict = None) -> float:
    w = weights or WEIGHTS
    return sum(w[k] * (perf.get(k) or 0.0) for k in w)


def rank_themes(themes: list, weights: dict = None) -> list:
    ranked = []
    for t in themes:
        perf = t.get("performance", {})
        score = compute_score(perf, weights)
        ranked.append({
            "rank": 0,
            "name": t["name"],
            "id": t["id"],
            "score": round(score, 3),
            "1d": perf.get("1d") or 0,
            "1w": perf.get("1w") or 0,
            "1m": perf.get("1m") or 0,
            "3m": perf.get("3m") or 0,
            "category": t.get("category", ""),
            "theme_type": t.get("theme_type", ""),
            "crowding": t.get("crowding", ""),
            "stock_count": t.get("stock_count", 0),
            "avg_ta": t.get("ratings", {}).get("avg_ta", 0),
            "avg_fa": t.get("ratings", {}).get("avg_fa", 0),
            "avg_ars": t.get("ratings", {}).get("avg_ars", 0),
            "as_of": t.get("as_of", ""),
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, t in enumerate(ranked):
        t["rank"] = i + 1
    return ranked


def print_comparison(themes: list, top_n: int = 15):
    """Rank with all three schemes and print side-by-side comparison."""
    results = {}
    for scheme, weights in WEIGHT_SCHEMES.items():
        ranked = rank_themes(themes, weights)
        results[scheme] = {t["id"]: t for t in ranked}

    # Build unified top-N: union of top_n from each scheme, sorted by claude score
    claude_ranked = rank_themes(themes, WEIGHT_SCHEMES["claude"])
    top_ids_ordered = [t["id"] for t in claude_ranked[:top_n]]

    # Header
    print(f"\n{'='*110}")
    print(f"  THEME MOMENTUM RANKING — confronto ponderazioni (Top {top_n})")
    print(f"  TUO:    1D=5%  1W=50% 1M=30% 3M=15%")
    print(f"  GEMINI: 1D=10% 1W=20% 1M=45% 3M=25%")
    print(f"  CLAUDE: 1D=10% 1W=25% 1M=40% 3M=25%")
    print(f"{'='*110}")

    hdr = (f"{'#C':>3}  {'Theme':<38}  "
           f"{'1D':>5} {'1W':>6} {'1M':>6} {'3M':>6}  "
           f"{'ScTuo':>6} {'ScGem':>6} {'ScCla':>6}  "
           f"{'Crowd':<14} {'Type':<11}")
    print(hdr)
    print("-" * 110)

    for theme_id in top_ids_ordered:
        c = results["claude"][theme_id]
        t_score = results["tuo"][theme_id]["score"]
        g_score = results["gemini"][theme_id]["score"]
        c_rank  = results["claude"][theme_id]["rank"]

        print(
            f"{c_rank:>3}  {c['name']:<38}  "
            f"{c['1d']:>5.1f} {c['1w']:>6.1f} {c['1m']:>6.1f} {c['3m']:>6.1f}  "
            f"{t_score:>6.1f} {g_score:>6.1f} {c['score']:>6.1f}  "
            f"{c['crowding']:<14} {c['theme_type']:<11}"
        )

    # Rank divergence analysis
    print(f"\n{'='*110}")
    print("  DIVERGENZE — temi che cambiano posizione significativamente tra i 3 metodi:")
    print(f"{'='*110}")
    print(f"  {'Theme':<38}  {'#Tuo':>5} {'#Gem':>5} {'#Cla':>5}  {'Delta max':>9}")
    print("-" * 80)

    divergences = []
    for theme_id, c in results["claude"].items():
        r_tuo = results["tuo"][theme_id]["rank"]
        r_gem = results["gemini"][theme_id]["rank"]
        r_cla = results["claude"][theme_id]["rank"]
        delta = max(r_tuo, r_gem, r_cla) - min(r_tuo, r_gem, r_cla)
        if delta >= 5:
            divergences.append((delta, theme_id, r_tuo, r_gem, r_cla))

    divergences.sort(reverse=True)
    for delta, theme_id, r_tuo, r_gem, r_cla in divergences[:10]:
        name = results["claude"][theme_id]["name"]
        print(f"  {name:<38}  {r_tuo:>5} {r_gem:>5} {r_cla:>5}  {delta:>9}")


def print_table(ranked: list):
    header = f"{'#':>3}  {'Theme':<40} {'Score':>6}  {'1D':>6}  {'1W':>6}  {'1M':>6}  {'3M':>6}  {'Crowding':<14}  {'Type':<12}  {'Stk':>4}"
    print(header)
    print("-" * len(header))
    for t in ranked:
        print(
            f"{t['rank']:>3}  {t['name']:<40} {t['score']:>6.2f}  "
            f"{t['1d']:>6.2f}  {t['1w']:>6.2f}  {t['1m']:>6.2f}  {t['3m']:>6.2f}  "
            f"{t['crowding']:<14}  {t['theme_type']:<12}  {t['stock_count']:>4}"
        )


def main():
    from dotenv import load_dotenv
    import os
    load_dotenv(ROOT / ".env")

    email = os.getenv("ASKLIVERMORE_EMAIL", "dodo.ebayer@gmail.com")
    password = os.getenv("ASKLIVERMORE_PASSWORD", "livermore123")

    print("Logging in...", flush=True)
    access_token = login(email, password)
    print("Fetching themes...", flush=True)
    themes = fetch_themes(access_token)
    print(f"Got {len(themes)} themes.\n", flush=True)

    # Comparison table (primary output)
    print_comparison(themes, top_n=15)

    # Save claude-weighted ranking as default output
    ranked = rank_themes(themes, WEIGHT_SCHEMES["claude"])
    out_path = TMP / "theme_ranking.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=2, ensure_ascii=False)
    print(f"\nSaved claude-weighted ranking to {out_path}")
    return ranked


if __name__ == "__main__":
    main()

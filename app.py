import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import streamlit.components.v1 as components
from scipy.stats import norm

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUPABASE_URL      = "https://dwihwpjhzssmssdewzof.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3aWh3cGpoenNzbXNzZGV3em9mIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNjU4OTMsImV4cCI6MjA5Mjc0MTg5M30.1PrjsczV70qNSssx4gTM_SXYUw1s7IfmI3ZeR6l6jtM"
SITE_URL          = "https://www.asklivermore.com"
WEIGHTS           = {"1d": 0.10, "1w": 0.25, "1m": 0.40, "3m": 0.25}

SCANNERS = {
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

CROWD_COLORS = {
    "very-uncrowded": "#22c55e",
    "uncrowded":      "#84cc16",
    "moderate":       "#eab308",
    "crowded":        "#ef4444",
}

# ── PAGE SETUP ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dodo Swing Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 1rem; padding-bottom: 2rem; }
  .metric-card {
    background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px;
    padding: 16px 20px; text-align: center;
  }
  .metric-card .val { font-size: 28px; font-weight: 800; color: #f97316; }
  .metric-card .lbl { font-size: 11px; color: #64748b; text-transform: uppercase;
                      letter-spacing: .08em; margin-top: 2px; }
  .ticker-badge {
    display: inline-block; background: #f97316; color: #000;
    font-weight: 800; font-size: 13px; padding: 2px 8px; border-radius: 5px;
  }
  div[data-testid="stDataFrame"] > div { border-radius: 8px; overflow: hidden; }
  .stTabs [data-baseweb="tab"] { font-size: 14px; font-weight: 600; }
  [data-testid="stSidebar"] { background: #1a1d27; }
</style>
""", unsafe_allow_html=True)

# ── API FUNCTIONS ──────────────────────────────────────────────────────────────
def login(email, password):
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def make_session(token):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s

def fetch_themes(session):
    resp = session.get(f"{SITE_URL}/api/themes", timeout=15)
    resp.raise_for_status()
    d = resp.json()
    return d.get("mainstream", []) + d.get("tomorrow", [])

def fetch_scanner(session, scanner_id):
    resp = session.get(f"{SITE_URL}/api/scanners/{scanner_id}/results", timeout=15)
    if resp.status_code != 200:
        return []
    return resp.json().get("matches", [])

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_company_info(tv_symbol: str) -> dict:
    import time
    ticker = tv_symbol.split(":")[-1] if ":" in tv_symbol else tv_symbol
    # --- try 1: yfinance (handles Yahoo auth internally) ---
    try:
        time.sleep(0.5)
        info = yf.Ticker(ticker).info
        if info and info.get("longName"):
            return {
                "name":        info.get("longName", ""),
                "sector":      info.get("sector", ""),
                "industry":    info.get("industry", ""),
                "country":     info.get("country", ""),
                "employees":   info.get("fullTimeEmployees"),
                "website":     info.get("website", ""),
                "description": info.get("longBusinessSummary", ""),
            }
    except Exception:
        pass
    # --- try 2: Yahoo Finance chart v8 (public, no crumb needed) ---
    try:
        time.sleep(0.5)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
        }
        resp = requests.get(url, headers=hdrs, timeout=10)
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
        name = meta.get("longName") or meta.get("shortName", "")
        if name:
            return {
                "name":        name,
                "sector":      "",
                "industry":    "",
                "country":     "",
                "employees":   None,
                "website":     "",
                "description": "",
            }
    except Exception:
        pass
    # --- try 3: FMP demo (no signup needed for popular tickers) ---
    try:
        url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey=demo"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and data[0].get("companyName"):
            d = data[0]
            return {
                "name":        d.get("companyName", ""),
                "sector":      d.get("sector", ""),
                "industry":    d.get("industry", ""),
                "country":     d.get("country", ""),
                "employees":   d.get("fullTimeEmployees"),
                "website":     d.get("website", ""),
                "description": d.get("description", ""),
            }
    except Exception as e:
        return {"_error": str(e)}
    return {"_error": "Nessuna fonte disponibile"}


def company_card(tv_symbol: str, nome: str):
    info = fetch_company_info(tv_symbol)
    if not info or "_error" in info:
        st.warning(f"Impossibile caricare le informazioni. Errore: {info.get('_error','')}")
        return

    tags = " · ".join(filter(None, [
        info.get("sector"), info.get("industry"), info.get("country")
    ]))
    emps = f" · 👥 {info['employees']:,}" if info.get("employees") else ""
    site = f" · [🔗 sito]({info['website']})" if info.get("website") else ""
    desc = info.get("description") or "Descrizione non disponibile."

    st.markdown(f"**{info.get('name') or nome}**  \n"
                f"<span style='color:#6b7280;font-size:12px'>{tags}{emps}{site}</span>",
                unsafe_allow_html=True)
    st.markdown(f"> {desc[:700]}{'…' if len(desc) > 700 else ''}")


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_expirations(symbol: str):
    """Return list of available expiration dates for a ticker."""
    try:
        ticker = symbol.split(":")[-1] if ":" in symbol else symbol
        return list(yf.Ticker(ticker).options)
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_gex(symbol: str, selected_exps: tuple) -> dict:
    """Calculate Gamma Exposure per strike using Black-Scholes on yfinance option chains."""
    import time

    def bs_gamma(S, K, T, sigma, r=0.05):
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.0
        try:
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
        except Exception:
            return 0.0

    try:
        ticker = symbol.split(":")[-1] if ":" in symbol else symbol
        t      = yf.Ticker(ticker)
        spot   = t.fast_info.get("last_price") or t.fast_info.get("lastPrice")
        if not spot:
            return {"_error": "Prezzo non disponibile"}
        if not selected_exps:
            return {"_error": "Nessuna scadenza selezionata"}

        gex_map   = {}
        call_oi   = {}
        put_oi    = {}
        used_exps = []
        today     = pd.Timestamp.now(tz="UTC").normalize()

        for exp in selected_exps:
            exp_ts = pd.Timestamp(exp, tz="UTC")
            T      = max((exp_ts - today).days / 365, 1 / 365)
            try:
                chain = t.option_chain(exp)
                time.sleep(0.1)
                used_exps.append(exp)
            except Exception:
                continue

            for _, row in chain.calls.iterrows():
                iv, oi, k = row.get("impliedVolatility") or 0, row.get("openInterest") or 0, row.get("strike") or 0
                if iv <= 0 or oi <= 0 or k <= 0:
                    continue
                g = bs_gamma(spot, k, T, iv)
                gex_map[k] = gex_map.get(k, 0) + g * oi * 100 * spot
                call_oi[k] = call_oi.get(k, 0) + oi

            for _, row in chain.puts.iterrows():
                iv, oi, k = row.get("impliedVolatility") or 0, row.get("openInterest") or 0, row.get("strike") or 0
                if iv <= 0 or oi <= 0 or k <= 0:
                    continue
                g = bs_gamma(spot, k, T, iv)
                gex_map[k] = gex_map.get(k, 0) - g * oi * 100 * spot
                put_oi[k]  = put_oi.get(k, 0) + oi

        if not gex_map:
            return {"_error": "Dati GEX insufficienti"}

        filtered = {k: v for k, v in gex_map.items() if abs(k - spot) / spot <= 0.30}
        if not filtered:
            filtered = gex_map

        net_gex      = sum(filtered.values())
        sorted_items = sorted(filtered.items())
        strikes      = [x[0] for x in sorted_items]
        gex_vals     = [x[1] for x in sorted_items]

        cumsum      = np.cumsum(gex_vals)
        flip_strike = None
        for i in range(len(cumsum) - 1):
            if cumsum[i] * cumsum[i + 1] < 0:
                flip_strike = strikes[i]
                break

        call_wall = max(filtered, key=lambda k: call_oi.get(k, 0)) if call_oi else None
        put_wall  = max(filtered, key=lambda k: put_oi.get(k, 0))  if put_oi  else None

        return {
            "spot": spot, "strikes": strikes, "gex_vals": gex_vals,
            "net_gex": net_gex, "flip_strike": flip_strike,
            "call_wall": call_wall, "put_wall": put_wall,
            "expirations": used_exps,
        }
    except Exception as e:
        return {"_error": str(e)}


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_market_pulse():
    results = {}
    for sym in ["SPY", "QQQ"]:
        try:
            df = yf.download(sym, period="120d", interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                continue
            close = df["Close"].squeeze()
            price = float(close.iloc[-1])
            e8  = float(close.ewm(span=8,  adjust=False).mean().iloc[-1])
            e21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
            e50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            results[sym] = {"price": price, "ema8": e8, "ema21": e21, "ema50": e50}
        except Exception:
            pass
    return results

def weighted_score(theme):
    p = theme.get("performance", {})
    return sum(WEIGHTS[k] * (p.get(k) or 0.0) for k in WEIGHTS)

# ── DATA LOADING ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)
def load_data(email, password):
    token   = login(email, password)
    session = make_session(token)
    themes  = fetch_themes(session)

    records = []
    for t in themes:
        p = t.get("performance", {})
        r = t.get("ratings", {})
        records.append({
            "id":       t.get("id", ""),
            "Tema":     t.get("name", ""),
            "Score":    round(weighted_score(t), 2),
            "1M %":     round(p.get("1m") or 0, 1),
            "3M %":     round(p.get("3m") or 0, 1),
            "1W %":     round(p.get("1w") or 0, 1),
            "1D %":     round(p.get("1d") or 0, 1),
            "Crowding": (t.get("crowding") or "").replace("_", "-"),
            "Tipo":     t.get("theme_type", ""),
            "TA":       round(r.get("avg_ta") or 0, 1),
            "FA":       round(r.get("avg_fa") or 0, 1),
            "ARS":      round(r.get("avg_ars") or 0, 0),
            "Titoli":   t.get("stock_count", 0),
            "stocks":   t.get("stocks", []),
            "as_of":    t.get("as_of", ""),
        })
    records.sort(key=lambda x: x["Score"], reverse=True)

    scanner_results = {}
    for sid in SCANNERS:
        scanner_results[sid] = fetch_scanner(session, sid)

    return records, scanner_results

# ── CROSSREF ───────────────────────────────────────────────────────────────────
def build_crossref(records, scanner_results, sel_theme_ids, sel_scanner_ids):
    ranked = sorted(
        [r for r in records if r["id"] in sel_theme_ids],
        key=lambda x: x["Score"], reverse=True
    )
    ticker_themes = {}
    for idx, t in enumerate(ranked):
        for tk in t["stocks"]:
            ticker_themes.setdefault(tk, []).append(
                {"rank": idx+1, "theme": t["Tema"], "score": t["Score"]}
            )

    ticker_scanners, ticker_meta = {}, {}
    for sid in sel_scanner_ids:
        for m in scanner_results.get(sid, []):
            tk = m.get("ticker", "")
            if not tk:
                continue
            ticker_scanners.setdefault(tk, []).append(SCANNERS[sid])
            if tk not in ticker_meta:
                ticker_meta[tk] = m

    rows = []
    for tk, themes in ticker_themes.items():
        if tk not in ticker_scanners:
            continue
        meta = ticker_meta[tk]
        tv   = meta.get("tv_symbol", "") or tk
        best = min(themes, key=lambda x: x["rank"])
        mktcap = meta.get("market_cap") or meta.get("mktcap") or 0
        volume = meta.get("volume") or meta.get("avg_vol_50") or 0
        rows.append({
            "Ticker":       f"https://www.tradingview.com/chart/?symbol={tv}",
            "Nome":         (meta.get("name") or "")[:28],
            "N.Scanner":    len(ticker_scanners[tk]),
            "Rank Tema":    best["rank"],
            "N.Temi":       len(themes),
            "TA":           round(meta.get("ta_rating") or 0, 1),
            "FA":           round(meta.get("fa_rating") or 0, 1),
            "RS":           meta.get("rs_rating") or 0,
            "Prezzo $":     round(meta.get("price") or 0, 2),
            "1D %":         round(meta.get("change_pct") or 0, 2),
            "Mkt Cap $M":   round(mktcap / 1e6, 0) if mktcap else 0,
            "Vol 50d":      round(volume / 1e6, 2) if volume else 0,
            "Scanner":      ", ".join(ticker_scanners[tk]),
            "Top Tema":     f"#{best['rank']} {best['theme'][:28]}",
            "_ticker":      tk,
        })

    rows.sort(key=lambda x: (-x["N.Scanner"], x["Rank Tema"]))
    return rows

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Dodo Swing Scanner")
    st.markdown("---")
    try:
        email    = st.secrets["ASKLIVERMORE_EMAIL"]
        password = st.secrets["ASKLIVERMORE_PASSWORD"]
        st.success("✓ Credenziali configurate")
    except Exception:
        email    = st.text_input("Email", value="dodo.ebayer@gmail.com")
        password = st.text_input("Password", type="password")

    st.markdown("---")
    if st.button("🔄 Aggiorna dati", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Dati cachati per 1 ora")

# ── LOAD ───────────────────────────────────────────────────────────────────────
with st.spinner("⏳ Caricamento dati da AskLivermore..."):
    try:
        records, scanner_results = load_data(email, password)
    except Exception as e:
        st.error(f"❌ Errore: {e}")
        st.stop()

as_of = records[0]["as_of"] if records else ""

# ── HEADER METRICS ─────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='margin-top:18px;margin-bottom:4px;display:flex;align-items:center;gap:14px'>"
    f"<span style='font-size:48px;line-height:1'>🦤</span>"
    f"<div>"
    f"<div style='font-size:26px;font-weight:800;color:#f1f5f9;letter-spacing:-0.5px'>Dodo Swing Scanner</div>"
    f"<div style='font-size:12px;color:#64748b;margin-top:2px'>Dati al {as_of}</div>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
top5 = records[:5]
avg_score_top5 = round(sum(r["Score"] for r in top5) / len(top5), 1) if top5 else 0
total_scan_results = sum(len(v) for v in scanner_results.values())

with c1:
    st.markdown(f'<div class="metric-card"><div class="val">{len(records)}</div><div class="lbl">Temi totali</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="metric-card"><div class="val">{avg_score_top5}</div><div class="lbl">Score medio top 5</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="metric-card"><div class="val">{len(SCANNERS)}</div><div class="lbl">Scanner attivi</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="metric-card"><div class="val">{total_scan_results}</div><div class="lbl">Segnali scanner totali</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── MARKET PULSE ───────────────────────────────────────────────────────────────
pulse = fetch_market_pulse()
if pulse:
    def _ema_badge(price, ema, label):
        above = price > ema
        col   = "#22c55e" if above else "#ef4444"
        icon  = "▲" if above else "▼"
        return (f"<span style='background:{col}22;border:1px solid {col};color:{col};"
                f"font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;margin:2px'>"
                f"{icon} {label}</span>")

    parts = []
    for sym, d in pulse.items():
        p = d["price"]
        badges = (
            _ema_badge(p, d["ema8"],  "EMA8")  +
            _ema_badge(p, d["ema21"], "EMA21") +
            _ema_badge(p, d["ema50"], "EMA50")
        )
        above_all = p > d["ema8"] and p > d["ema21"] and p > d["ema50"]
        env_label = "<span style='color:#22c55e;font-weight:800'>BULLISH</span>" if above_all else \
                    "<span style='color:#ef4444;font-weight:800'>BEARISH</span>"
        parts.append(
            f"<span style='font-weight:700;font-size:14px;margin-right:6px'>{sym}</span>"
            f"<span style='color:#94a3b8;font-size:12px'>${p:.2f}</span> &nbsp;"
            f"{badges} &nbsp; {env_label}"
        )

    st.markdown(
        "<div style='background:#1a1d27;border:1px solid #2a2d3a;border-radius:10px;"
        "padding:12px 20px;display:flex;gap:40px;align-items:center;flex-wrap:wrap'>"
        "<span style='color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin-right:4px'>🌍 Market Pulse</span>"
        + " &nbsp;&nbsp;│&nbsp;&nbsp; ".join(parts) +
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

# ── TABS ───────────────────────────────────────────────────────────────────────
tab_themes, tab_chart, tab_cross, tab_gex, tab_config = st.tabs([
    "📈 Theme Momentum",
    "📊 Grafico Temi",
    "🎯 Cross-Reference",
    "📐 GEX Map",
    "⚙️ Configura",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — THEME MOMENTUM TABLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_themes:
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        crowd_opts = ["Tutti"] + sorted({r["Crowding"] for r in records if r["Crowding"]})
        crowd_sel  = st.selectbox("Crowding", crowd_opts, key="crowd")
    with col_f2:
        tipo_opts = ["Tutti"] + sorted({r["Tipo"] for r in records if r["Tipo"]})
        tipo_sel  = st.selectbox("Tipo tema", tipo_opts, key="tipo")
    with col_f3:
        top_n_show = st.selectbox("Mostra", [10, 20, 30, 54], index=2, key="topn")

    df_t = pd.DataFrame([{k: v for k, v in r.items() if k not in ("id","stocks","as_of")} for r in records])
    if crowd_sel != "Tutti":
        df_t = df_t[df_t["Crowding"] == crowd_sel]
    if tipo_sel != "Tutti":
        df_t = df_t[df_t["Tipo"] == tipo_sel]
    df_t = df_t.head(top_n_show).reset_index(drop=True)
    df_t.index += 1

    def color_pct(val):
        if isinstance(val, float):
            if val > 0:   return "color: #22c55e; font-weight:600"
            elif val < 0: return "color: #ef4444; font-weight:600"
        return ""

    def color_score(val):
        if isinstance(val, float):
            if val >= 15: return "color: #22c55e; font-weight:800"
            elif val >= 5: return "color: #eab308; font-weight:700"
            elif val < 0:  return "color: #ef4444"
        return "font-weight:600"

    styled = (df_t.style
        .map(color_score, subset=["Score"])
        .map(color_pct,   subset=["1M %","3M %","1W %","1D %"])
        .format({"Score": "{:.2f}", "1M %": "{:+.1f}%", "3M %": "{:+.1f}%",
                 "1W %": "{:+.1f}%", "1D %": "{:+.1f}%",
                 "TA": "{:.1f}", "FA": "{:.1f}", "ARS": "{:.0f}"})
    )

    st.dataframe(styled, use_container_width=True, height=560)
    st.caption(f"{len(df_t)} temi · Ponderazione: 1M=40% | 3M=25% | 1W=25% | 1D=10%")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — GRAFICO TEMI
# ══════════════════════════════════════════════════════════════════════════════
with tab_chart:
    st.markdown(
        "<div style='background:#1a1d27;border:1px solid #2a2d3a;border-radius:8px;"
        "padding:10px 18px;margin-bottom:12px;font-size:13px;color:#94a3b8'>"
        "📐 <strong style='color:#e2e8f0'>Score ponderato</strong> &nbsp;=&nbsp; "
        "<span style='color:#f97316'>1D×10%</span> &nbsp;+&nbsp; "
        "<span style='color:#eab308'>1W×25%</span> &nbsp;+&nbsp; "
        "<span style='color:#22c55e'>1M×40%</span> &nbsp;+&nbsp; "
        "<span style='color:#3b82f6'>3M×25%</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("#### 🏆 Top 20 temi per Score ponderato")
        df_bar = pd.DataFrame(records[:20])
        colors = [CROWD_COLORS.get(r["Crowding"], "#64748b") for r in records[:20]]
        fig_bar = go.Figure(go.Bar(
            x=df_bar["Score"],
            y=df_bar["Tema"],
            orientation="h",
            marker_color=colors,
            text=df_bar["Score"].apply(lambda x: f"{x:.1f}"),
            textposition="outside",
        ))
        fig_bar.update_layout(
            paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
            font_color="#e2e8f0", font_size=11,
            yaxis=dict(autorange="reversed", gridcolor="#2a2d3a"),
            xaxis=dict(gridcolor="#2a2d3a"),
            margin=dict(l=10, r=60, t=10, b=10),
            height=520,
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
        st.markdown("#### 📉 Score vs Performance 1M (Top 40)")
        df_sc = pd.DataFrame(records[:40])
        fig_sc = px.scatter(
            df_sc, x="1M %", y="Score",
            size="Titoli", color="Crowding",
            hover_name="Tema",
            color_discrete_map=CROWD_COLORS,
            size_max=30,
        )
        fig_sc.update_layout(
            paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
            font_color="#e2e8f0", font_size=11,
            xaxis=dict(gridcolor="#2a2d3a", title="Performance 1 Mese (%)"),
            yaxis=dict(gridcolor="#2a2d3a", title="Score Ponderato"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=520,
            legend=dict(bgcolor="#1a1d27", bordercolor="#2a2d3a"),
        )
        st.plotly_chart(fig_sc, use_container_width=True)

    st.markdown("#### 🗓️ Performance per timeframe — Top 15 temi")
    df_hm = pd.DataFrame(records[:15])[["Tema","1D %","1W %","1M %","3M %"]].set_index("Tema")
    fig_hm = px.imshow(
        df_hm,
        color_continuous_scale=[[0,"#ef4444"],[0.5,"#1a1d27"],[1,"#22c55e"]],
        text_auto=".1f",
        aspect="auto",
    )
    fig_hm.update_layout(
        paper_bgcolor="#0f1117", font_color="#e2e8f0", font_size=11,
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
    )
    st.plotly_chart(fig_hm, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — GEX MAP
# ══════════════════════════════════════════════════════════════════════════════
with tab_gex:
    st.markdown(
        "<div style='background:#1a1d27;border:1px solid #2a2d3a;border-radius:8px;"
        "padding:10px 18px;margin-bottom:16px;font-size:13px;color:#94a3b8'>"
        "📐 <strong style='color:#e2e8f0'>Gamma Exposure (GEX)</strong> — calcolato da option chain Yahoo Finance via Black-Scholes. "
        "Barre verdi = dealer long gamma (mercato tende a stabilizzarsi). "
        "Barre rosse = dealer short gamma (mercato amplifica i movimenti). "
        "La <strong style='color:#f97316'>linea arancione</strong> è il Gamma Flip: sopra = regime bullish, sotto = bearish."
        "</div>",
        unsafe_allow_html=True,
    )

    gex_col1, gex_col2 = st.columns([1, 3])
    with gex_col1:
        # suggerisci ticker dal crossref se disponibile
        crossref_tickers = []
        _th_ids = {r["id"] for r in records[:30]}
        _sc_ids = set(SCANNERS.keys())
        _cr = build_crossref(records, scanner_results, _th_ids, _sc_ids)
        if _cr:
            crossref_tickers = [
                row["Ticker"].split("symbol=")[-1].split(":")[-1]
                for row in _cr[:40]
            ]
        gex_input = st.text_input(
            "Ticker (es. NVDA, AAPL, TSLA)",
            value=crossref_tickers[0] if crossref_tickers else "NVDA",
            key="gex_ticker",
        )
        if crossref_tickers:
            st.caption("Suggeriti dal cross-reference:")
            quick_picks = st.selectbox(
                "Scegli rapido",
                ["—"] + crossref_tickers[:20],
                key="gex_quick",
            )
            if quick_picks != "—":
                gex_input = quick_picks

        # carica scadenze disponibili appena cambia il ticker
        avail_exps = fetch_expirations(gex_input) if gex_input else []
        if avail_exps:
            default_exps = avail_exps[:6]
            sel_exps = st.multiselect(
                "Scadenze",
                options=avail_exps,
                default=default_exps,
                key="gex_exps",
            )
        else:
            sel_exps = []
            st.caption("Carica le scadenze premendo Calcola GEX")

        load_gex = st.button("📐 Calcola GEX", type="primary", use_container_width=True)

    with gex_col2:
        if load_gex or st.session_state.get("gex_last") == (gex_input, tuple(sel_exps)):
            st.session_state["gex_last"] = (gex_input, tuple(sel_exps))
            with st.spinner(f"Calcolo GEX per {gex_input} ({len(sel_exps)} scadenze)..."):
                gdata = fetch_gex(gex_input, tuple(sel_exps))

            if "_error" in gdata:
                st.error(f"Errore: {gdata['_error']}")
            else:
                spot        = gdata["spot"]
                strikes     = gdata["strikes"]
                gex_vals    = gdata["gex_vals"]
                net_gex     = gdata["net_gex"]
                flip_strike = gdata["flip_strike"]
                call_wall   = gdata["call_wall"]
                put_wall    = gdata["put_wall"]

                # metriche
                m1, m2, m3, m4 = st.columns(4)
                net_color = "#22c55e" if net_gex >= 0 else "#ef4444"
                net_label = "LONG γ (stabilizzante)" if net_gex >= 0 else "SHORT γ (volatile)"
                m1.markdown(
                    f"<div class='metric-card'>"
                    f"<div class='val' style='color:{net_color};font-size:16px'>{net_label}</div>"
                    f"<div class='lbl'>Net GEX regime</div></div>",
                    unsafe_allow_html=True,
                )
                m2.markdown(
                    f"<div class='metric-card'>"
                    f"<div class='val' style='font-size:20px'>${spot:.2f}</div>"
                    f"<div class='lbl'>Prezzo spot</div></div>",
                    unsafe_allow_html=True,
                )
                m3.markdown(
                    f"<div class='metric-card'>"
                    f"<div class='val' style='color:#22c55e;font-size:20px'>${call_wall or '—'}</div>"
                    f"<div class='lbl'>Call Wall (max OI call)</div></div>",
                    unsafe_allow_html=True,
                )
                m4.markdown(
                    f"<div class='metric-card'>"
                    f"<div class='val' style='color:#ef4444;font-size:20px'>${put_wall or '—'}</div>"
                    f"<div class='lbl'>Put Wall (max OI put)</div></div>",
                    unsafe_allow_html=True,
                )

                st.markdown("<br>", unsafe_allow_html=True)

                # ── GEX PROFILE CHART (stile Bullflow) ──────────────────────
                # strikes sull'asse Y (alto = strike alto), GEX sull'asse X
                s_arr = np.array(strikes)
                g_arr = np.array([v / 1e6 for v in gex_vals])

                # barre positive (verde) e negative (rosso) separate per colore pieno
                pos_mask = g_arr >= 0
                neg_mask = g_arr < 0

                fig_gex = go.Figure()

                # barre positive
                fig_gex.add_trace(go.Bar(
                    y=s_arr[pos_mask],
                    x=g_arr[pos_mask],
                    orientation="h",
                    marker=dict(
                        color="rgba(34,197,94,0.85)",
                        line=dict(color="rgba(34,197,94,0.3)", width=0.5),
                    ),
                    name="Long γ",
                    hovertemplate="$%{y:.0f} → GEX %{x:.2f}M<extra>Long γ</extra>",
                ))

                # barre negative
                fig_gex.add_trace(go.Bar(
                    y=s_arr[neg_mask],
                    x=g_arr[neg_mask],
                    orientation="h",
                    marker=dict(
                        color="rgba(239,68,68,0.85)",
                        line=dict(color="rgba(239,68,68,0.3)", width=0.5),
                    ),
                    name="Short γ",
                    hovertemplate="$%{y:.0f} → GEX %{x:.2f}M<extra>Short γ</extra>",
                ))

                def _hline(fig, y_val, color, width, dash, label):
                    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                                  y0=y_val, y1=y_val, yref="y",
                                  line=dict(color=color, width=width, dash=dash))
                    fig.add_annotation(x=1.01, y=y_val, xref="paper", yref="y",
                                       text=label, showarrow=False,
                                       font=dict(color=color, size=11),
                                       xanchor="left", align="left")

                _hline(fig_gex, spot,        "#ffffff", 2,   "solid", f"Spot ${spot:.2f}")
                if flip_strike:
                    _hline(fig_gex, flip_strike, "#f97316", 1.5, "dash",  f"Flip ${flip_strike:.0f}")
                if call_wall:
                    _hline(fig_gex, call_wall,   "#4ade80", 1,   "dot",   f"Call Wall ${call_wall:.0f}")
                if put_wall:
                    _hline(fig_gex, put_wall,    "#f87171", 1,   "dot",   f"Put Wall ${put_wall:.0f}")

                # shading zona sopra spot (bullish) vs sotto (bearish)
                fig_gex.add_hrect(
                    y0=spot, y1=max(strikes) * 1.02,
                    fillcolor="rgba(34,197,94,0.04)",
                    line_width=0,
                    layer="below",
                )
                fig_gex.add_hrect(
                    y0=min(strikes) * 0.98, y1=spot,
                    fillcolor="rgba(239,68,68,0.04)",
                    line_width=0,
                    layer="below",
                )

                net_color  = "#22c55e" if net_gex >= 0 else "#ef4444"
                net_label  = f"{'▲ LONG γ' if net_gex >= 0 else '▼ SHORT γ'}  ${net_gex/1e6:.1f}M"
                exps_used  = gdata.get("expirations", [])
                exps_label = "  ·  ".join(exps_used) if exps_used else "—"

                fig_gex.update_layout(
                    paper_bgcolor="#0f1117",
                    plot_bgcolor="#111827",
                    font=dict(color="#e2e8f0", size=11, family="sans-serif"),
                    barmode="overlay",
                    bargap=0.15,
                    xaxis=dict(
                        title="GEX ($M)",
                        gridcolor="#1f2937",
                        zeroline=True, zerolinecolor="#374151", zerolinewidth=2,
                        ticksuffix="M",
                    ),
                    yaxis=dict(
                        title="Strike",
                        gridcolor="#1f2937",
                        tickprefix="$",
                        dtick=None,
                    ),
                    margin=dict(l=10, r=120, t=50, b=10),
                    height=560,
                    showlegend=True,
                    legend=dict(
                        bgcolor="rgba(0,0,0,0)",
                        borderwidth=0,
                        x=0.01, y=0.99,
                        font=dict(size=11),
                    ),
                    title=dict(
                        text=(
                            f"<b>{gex_input.upper()}</b>  GEX Profile"
                            f"   <span style='color:{net_color}'>{net_label}</span>"
                            f"   <span style='color:#64748b;font-size:11px'>· 6 scadenze · Black-Scholes</span>"
                        ),
                        font=dict(size=14, color="#f1f5f9"),
                        x=0, xanchor="left",
                    ),
                )
                st.plotly_chart(fig_gex, use_container_width=True)
                st.caption(
                    f"📅 Scadenze incluse nel calcolo: **{exps_label}** &nbsp;·&nbsp; "
                    f"Dati Yahoo Finance · aggiornato ogni ora"
                )
        else:
            st.info("👈 Inserisci un ticker e clicca **Calcola GEX**")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — CONFIG
# ══════════════════════════════════════════════════════════════════════════════
with tab_config:
    st.markdown("### 📊 Selezione Temi")
    pc = st.columns(6)
    presets = [("Top 10",10),("Top 20",20),("Top 30",30),("Top 50",50),("Tutti",999),("Nessuno",0)]
    for i, (label, n) in enumerate(presets):
        if pc[i].button(label, use_container_width=True):
            st.session_state["top_n_preset"] = n
            st.rerun()

    top_n   = st.session_state.get("top_n_preset", 30)
    def_th  = [r["Tema"] for r in records[:top_n]]
    sel_th  = st.multiselect(
        f"Temi nel cross-reference ({len(records)} disponibili)",
        [r["Tema"] for r in records],
        default=def_th, key="sel_themes",
    )

    st.markdown("---")
    st.markdown("### 🔍 Selezione Scanner")
    sel_sc = st.multiselect(
        "Scanner attivi",
        list(SCANNERS.keys()),
        default=list(SCANNERS.keys()),
        format_func=lambda k: f"{SCANNERS[k]}  ({len(scanner_results.get(k,[]))} titoli)",
        key="sel_scanners",
    )

    st.markdown("---")
    st.info(f"**{len(sel_th)}** temi selezionati · **{len(sel_sc)}** scanner selezionati")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CROSS-REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cross:
    sel_theme_ids   = {r["id"] for r in records if r["Tema"] in st.session_state.get("sel_themes", [])}
    sel_scanner_ids = set(st.session_state.get("sel_scanners", list(SCANNERS.keys())))
    if not sel_theme_ids:
        sel_theme_ids = {r["id"] for r in records[:30]}
    if not sel_scanner_ids:
        sel_scanner_ids = set(SCANNERS.keys())

    crossref = build_crossref(records, scanner_results, sel_theme_ids, sel_scanner_ids)
    df_c = pd.DataFrame(crossref) if crossref else pd.DataFrame()

    if df_c.empty:
        st.warning("⚠️ Nessun titolo trovato. Modifica temi/scanner nella tab ⚙️ Configura.")
    else:
        # ── FILTRI ──
        MKTCAP_CATS = {
            "Tutti":          (0,       9_999_999),
            "> $500B":        (500_000, 9_999_999),
            "> $200B":        (200_000, 9_999_999),
            "> $100B":        (100_000, 9_999_999),
            "> $50B":         (50_000,  9_999_999),
            "> $10B":         (10_000,  9_999_999),
            "> $5B":          (5_000,   9_999_999),
            "> $2B":          (2_000,   9_999_999),
            "> $1B":          (1_000,   9_999_999),
            "> $500M":        (500,     9_999_999),
            "> $300M":        (300,     9_999_999),
            "< $300M":        (0,       300),
        }
        VOL_CATS = {
            "Tutti":          (0,     9_999),
            "> 50M":          (50,    9_999),
            "> 10M":          (10,    9_999),
            "> 5M":           (5,     9_999),
            "> 1M":           (1,     9_999),
            "> 500K":         (0.5,   9_999),
            "> 100K":         (0.1,   9_999),
            "< 100K":         (0,     0.1),
        }

        f1, f2, f3, f4, f5 = st.columns([1,1,1,1,1])
        with f1:
            min_scan = st.selectbox("Min scanner", [1,2,3,4,5], index=0, key="min_sc")
        with f2:
            mc_sel = st.selectbox("Market Cap", list(MKTCAP_CATS.keys()), key="mc_cat")
        with f3:
            vol_sel = st.selectbox("Volume medio 50d", list(VOL_CATS.keys()), key="vol_cat")
        with f4:
            rs_min = st.selectbox("Min RS Rating", [0, 50, 60, 70, 80, 90], index=0, key="rs_min")
        with f5:
            view_mode = st.radio("Vista", ["📋 Elenco", "📊 Grafici"], index=1, horizontal=True, key="view_mode")

        # Applica filtri
        df_c = df_c[df_c["N.Scanner"] >= min_scan]
        mc_lo, mc_hi = MKTCAP_CATS[mc_sel]
        df_c = df_c[(df_c["Mkt Cap $M"] == 0) | (df_c["Mkt Cap $M"].between(mc_lo, mc_hi))]
        v_lo, v_hi = VOL_CATS[vol_sel]
        df_c = df_c[(df_c["Vol 50d"] == 0) | (df_c["Vol 50d"].between(v_lo, v_hi))]
        df_c = df_c[df_c["RS"] >= rs_min]
        df_display = df_c.drop(columns=["_ticker"]).reset_index(drop=True)
        df_display.index += 1

        st.divider()

        # Metriche rapide
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Titoli trovati", len(df_display))
        m2.metric("Media N.Scanner", f"{df_display['N.Scanner'].mean():.1f}" if len(df_display) else "—")
        m3.metric("Media TA",        f"{df_display['TA'].mean():.1f}"        if len(df_display) else "—")
        m4.metric("Media RS",        f"{df_display['RS'].mean():.0f}"        if len(df_display) else "—")

        # ── VISTA ELENCO ──────────────────────────────────────────────────────
        if view_mode == "📋 Elenco":
            styled_c = (df_display.style
                .background_gradient(subset=["N.Scanner"], cmap="Oranges")
                .background_gradient(subset=["TA","FA","RS"], cmap="RdYlGn")
                .map(color_pct, subset=["1D %"])
                .format({
                    "N.Scanner":  "{:.0f} ●",
                    "Rank Tema":  "#{:.0f}",
                    "TA":         "{:.1f}",
                    "FA":         "{:.1f}",
                    "Prezzo $":   "${:.2f}",
                    "1D %":       "{:+.2f}%",
                    "Mkt Cap $M": "{:,.0f}M",
                    "Vol 50d":    "{:.2f}M",
                })
            )
            selected_rows_pre = st.session_state.get("cross_table", {}).get("selection", {}).get("rows", [])
            if selected_rows_pre:
                tbl_col, chart_col = st.columns([3, 2])
            else:
                tbl_col = st.container()
                chart_col = None

            with tbl_col:
                selection = st.dataframe(
                    styled_c,
                    use_container_width=True,
                    height=520,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="cross_table",
                    column_config={
                        "Ticker": st.column_config.LinkColumn(
                            "Ticker",
                            display_text=r"symbol=(?:\w+:)?(\w+(?:\.\w+)?)",
                            help="Clicca per aprire TradingView · seleziona riga per grafico inline →",
                        ),
                    },
                    column_order=["Ticker","Nome","N.Scanner","Rank Tema","N.Temi",
                                  "TA","FA","RS","Prezzo $","1D %","Mkt Cap $M","Vol 50d",
                                  "Scanner","Top Tema"],
                )
                st.caption(f"{len(df_display)} titoli · seleziona una riga per il grafico inline →")

            selected_rows = selection.selection.get("rows", []) if selection else []
            if selected_rows and chart_col:
                with chart_col:
                    row    = df_display.iloc[selected_rows[0]]
                    tv_url = row["Ticker"]
                    tv_sym = tv_url.split("symbol=")[-1] if "symbol=" in tv_url else ""
                    st.markdown(f"**{tv_sym}** &nbsp; {row['Nome']} &nbsp; `${row['Prezzo $']:.2f}` &nbsp; `{row['1D %']:+.2f}%`")
                    components.html(f"""
                    <div id="tv_main" style="height:360px"></div>
                    <script src="https://s3.tradingview.com/tv.js"></script>
                    <script>
                    new TradingView.widget({{
                      "container_id": "tv_main",
                      "autosize": true,
                      "symbol": "{tv_sym}",
                      "interval": "D",
                      "timezone": "Europe/Rome",
                      "theme": "light",
                      "style": "9",
                      "locale": "it",
                      "toolbar_bg": "#ffffff",
                      "hide_top_toolbar": false,
                      "hide_side_toolbar": true,
                      "save_image": false,
                      "studies": [
                        {{"id":"MAExp@tv-basicstudies","inputs":{{"length":21}},"override":{{"MA Plot.color":"#16a34a","MA Plot.linewidth":2}}}},
                        {{"id":"MAExp@tv-basicstudies","inputs":{{"length":50}},"override":{{"MA Plot.color":"#2563eb","MA Plot.linewidth":2}}}}
                      ]
                    }});
                    </script>""", height=375)

        # ── VISTA GRAFICI ─────────────────────────────────────────────────────
        else:
            gc1, gc2, gc3 = st.columns(3)
            with gc1:
                n_cols = st.select_slider("Grafici per riga", [1, 2, 3], value=2, key="n_cols")
            with gc2:
                interval = st.selectbox("Timeframe", ["D","W","M"], index=0,
                                        format_func=lambda x: {"D":"Giornaliero","W":"Settimanale","M":"Mensile"}[x],
                                        key="tv_interval")
            with gc3:
                chart_h = st.select_slider("Altezza grafici", [300, 380, 460], value=380, key="chart_h")

            rows_data = df_display.head(24).to_dict("records")
            st.caption(f"Mostrando i primi {min(len(rows_data),24)} titoli · candele + EMA 21/50 + Volume · passa sopra al ticker per info azienda")

            cols = st.columns(n_cols)
            for i, row in enumerate(rows_data):
                tv_url = row["Ticker"]
                tv_sym = tv_url.split("symbol=")[-1] if "symbol=" in tv_url else ""
                pct    = row["1D %"]
                color  = "#22c55e" if pct >= 0 else "#ef4444"
                cid    = f"tv_{i}_{tv_sym.replace(':','_').replace('.','_')}"

                # build hover tooltip
                cinfo = fetch_company_info(tv_sym)
                if cinfo and "_error" not in cinfo:
                    tip_name = cinfo.get("name", "") or tv_sym
                    tip_sec  = " | ".join(filter(None, [cinfo.get("sector",""), cinfo.get("industry",""), cinfo.get("country","")]))
                    tip_desc = (cinfo.get("description") or "")[:300]
                    tooltip  = f"{tip_name}\n{tip_sec}\n\n{tip_desc}".replace('"', "'")
                else:
                    tooltip = tv_sym

                with cols[i % n_cols]:
                    scanner_badges = "".join(
                        f"<span style='background:#f97316;color:#fff;font-size:11px;"
                        f"font-weight:700;padding:2px 7px;border-radius:4px;margin:1px;display:inline-block'>{s.strip()}</span>"
                        for s in row["Scanner"].split(",")
                    )
                    st.markdown(
                        f"<div style='padding:4px 0 2px'>"
                        f"<strong title=\"{tooltip}\" style='font-size:14px;cursor:help;text-decoration:underline dotted #64748b'>{tv_sym}</strong> &nbsp;"
                        f"<span style='color:{color};font-weight:700'>{pct:+.2f}%</span> &nbsp;"
                        f"<span style='color:#64748b;font-size:11px'>R#{row['Rank Tema']} · "
                        f"TA {row['TA']:.0f} · RS {row['RS']}</span>"
                        f"</div>"
                        f"<div style='margin-bottom:4px'>{scanner_badges}</div>",
                        unsafe_allow_html=True,
                    )
                    components.html(f"""
                    <div id="{cid}" style="height:{chart_h}px;"></div>
                    <script src="https://s3.tradingview.com/tv.js"></script>
                    <script>
                    new TradingView.widget({{
                      "container_id": "{cid}",
                      "autosize": true,
                      "symbol": "{tv_sym}",
                      "interval": "{interval}",
                      "timezone": "Europe/Rome",
                      "theme": "light",
                      "style": "9",
                      "locale": "it",
                      "toolbar_bg": "#ffffff",
                      "hide_top_toolbar": false,
                      "hide_legend": false,
                      "hide_side_toolbar": true,
                      "allow_symbol_change": true,
                      "save_image": false,
                      "hide_volume": false,
                      "studies": [
                        {{
                          "id": "MAExp@tv-basicstudies",
                          "inputs": {{"length": 21}},
                          "override": {{"MA Plot.color": "#16a34a", "MA Plot.linewidth": 2}}
                        }},
                        {{
                          "id": "MAExp@tv-basicstudies",
                          "inputs": {{"length": 50}},
                          "override": {{"MA Plot.color": "#2563eb", "MA Plot.linewidth": 2}}
                        }}
                      ]
                    }});
                    </script>""", height=chart_h + 10)


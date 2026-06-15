import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
    page_title="Dodo Weekly Scanner",
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
        rows.append({
            "📈":           f"https://www.tradingview.com/chart/?symbol={tv}",
            "Ticker":       tk,
            "Nome":         (meta.get("name") or "")[:28],
            "N.Scanner":    len(ticker_scanners[tk]),
            "Rank Tema":    best["rank"],
            "N.Temi":       len(themes),
            "TA":           round(meta.get("ta_rating") or 0, 1),
            "FA":           round(meta.get("fa_rating") or 0, 1),
            "RS":           meta.get("rs_rating") or 0,
            "Prezzo $":     round(meta.get("price") or 0, 2),
            "1D %":         round(meta.get("change_pct") or 0, 2),
            "Scanner":      ", ".join(ticker_scanners[tk]),
            "Top Tema":     f"#{best['rank']} {best['theme'][:28]}",
            "tv_symbol":    tv,
        })

    rows.sort(key=lambda x: (-x["N.Scanner"], x["Rank Tema"]))
    return rows

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Dodo Weekly Scanner")
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
st.markdown(f"### 📊 Dodo Weekly Scanner &nbsp; <span style='font-size:13px;color:#64748b'>Dati al {as_of}</span>", unsafe_allow_html=True)

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

# ── TABS ───────────────────────────────────────────────────────────────────────
tab_themes, tab_chart, tab_cross, tab_config = st.tabs([
    "📈 Theme Momentum",
    "📊 Grafico Temi",
    "🎯 Cross-Reference",
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
        .applymap(color_score, subset=["Score"])
        .applymap(color_pct,   subset=["1M %","3M %","1W %","1D %"])
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
# TAB 4 — CONFIG
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

    col_f1, col_f2 = st.columns([1, 4])
    with col_f1:
        min_scan = st.selectbox("Min scanner", [1,2,3,4,5], index=0, key="min_sc")

    df_c = pd.DataFrame(crossref) if crossref else pd.DataFrame()

    if df_c.empty:
        st.warning("⚠️ Nessun titolo trovato. Modifica temi/scanner nella tab ⚙️ Configura.")
    else:
        df_c = df_c[df_c["N.Scanner"] >= min_scan].drop(columns=["tv_symbol"]).reset_index(drop=True)
        df_c.index += 1

        # Metriche rapide
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Titoli trovati", len(df_c))
        m2.metric("Media N.Scanner", f"{df_c['N.Scanner'].mean():.1f}")
        m3.metric("Media TA", f"{df_c['TA'].mean():.1f}")
        m4.metric("Media RS", f"{df_c['RS'].mean():.0f}")

        styled_c = (df_c.style
            .background_gradient(subset=["N.Scanner"], cmap="Oranges")
            .background_gradient(subset=["TA","FA","RS"], cmap="RdYlGn")
            .applymap(color_pct, subset=["1D %"])
            .format({
                "N.Scanner": "{:.0f} ●",
                "Rank Tema": "#{:.0f}",
                "TA": "{:.1f}", "FA": "{:.1f}",
                "Prezzo $": "${:.2f}",
                "1D %": "{:+.2f}%",
            })
        )

        st.dataframe(
            styled_c,
            use_container_width=True,
            height=560,
            column_config={
                "📈": st.column_config.LinkColumn("📈", display_text="Chart", width="small"),
            },
            column_order=["📈","Ticker","Nome","N.Scanner","Rank Tema","N.Temi",
                          "TA","FA","RS","Prezzo $","1D %","Scanner","Top Tema"],
        )
        st.caption(f"{len(df_c)} titoli · {len(sel_theme_ids)} temi · {len(sel_scanner_ids)} scanner")

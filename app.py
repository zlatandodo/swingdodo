import streamlit as st
import requests
import pandas as pd

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

# ── PAGE SETUP ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dodo Weekly Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0f1117; }
  [data-testid="stHeader"] { background: #0f1117; }
  .block-container { padding-top: 1.5rem; }
  div[data-testid="stDataFrame"] { border-radius: 8px; }
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] { border-radius: 6px; padding: 6px 18px; }
</style>
""", unsafe_allow_html=True)

# ── API FUNCTIONS ──────────────────────────────────────────────────────────────
def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def fetch_themes(session: requests.Session) -> list:
    resp = session.get(f"{SITE_URL}/api/themes", timeout=15)
    resp.raise_for_status()
    d = resp.json()
    return d.get("mainstream", []) + d.get("tomorrow", [])


def fetch_scanner(session: requests.Session, scanner_id: str) -> list:
    resp = session.get(f"{SITE_URL}/api/scanners/{scanner_id}/results", timeout=15)
    if resp.status_code != 200:
        return []
    return resp.json().get("matches", [])


def weighted_score(theme: dict) -> float:
    p = theme.get("performance", {})
    return sum(WEIGHTS[k] * (p.get(k) or 0.0) for k in WEIGHTS)


# ── DATA LOADING (cached) ──────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)
def load_data(email: str, password: str):
    token   = login(email, password)
    session = make_session(token)
    themes  = fetch_themes(session)

    # Build theme records
    theme_records = []
    for t in themes:
        p = t.get("performance", {})
        r = t.get("ratings", {})
        theme_records.append({
            "id":          t.get("id", ""),
            "Tema":        t.get("name", ""),
            "Score ⭐":    round(weighted_score(t), 2),
            "1M %":        p.get("1m") or 0,
            "3M %":        p.get("3m") or 0,
            "1W %":        p.get("1w") or 0,
            "1D %":        p.get("1d") or 0,
            "Crowding":    (t.get("crowding") or "").replace("_", "-"),
            "Tipo":        t.get("theme_type", ""),
            "TA":          r.get("avg_ta") or 0,
            "FA":          r.get("avg_fa") or 0,
            "ARS":         r.get("avg_ars") or 0,
            "Titoli":      t.get("stock_count", 0),
            "stocks":      t.get("stocks", []),
            "as_of":       t.get("as_of", ""),
        })
    theme_records.sort(key=lambda x: x["Score ⭐"], reverse=True)

    # Fetch all scanner results
    scanner_results = {}
    for sid in SCANNERS:
        scanner_results[sid] = fetch_scanner(session, sid)

    return theme_records, scanner_results


# ── CROSSREF COMPUTATION ───────────────────────────────────────────────────────
def build_crossref(theme_records: list, scanner_results: dict,
                   selected_theme_ids: set, selected_scanner_ids: set) -> list:
    # Rank selected themes
    ranked = [t for t in theme_records if t["id"] in selected_theme_ids]
    ranked.sort(key=lambda x: x["Score ⭐"], reverse=True)

    # ticker → themes
    ticker_themes: dict[str, list] = {}
    for idx, t in enumerate(ranked):
        for ticker in t["stocks"]:
            if ticker not in ticker_themes:
                ticker_themes[ticker] = []
            ticker_themes[ticker].append({
                "rank":  idx + 1,
                "theme": t["Tema"],
                "score": t["Score ⭐"],
            })

    # ticker → scanners + meta
    ticker_scanners: dict[str, list] = {}
    ticker_meta: dict[str, dict] = {}
    for sid in selected_scanner_ids:
        label = SCANNERS[sid]
        for m in scanner_results.get(sid, []):
            tk = m.get("ticker", "")
            if not tk:
                continue
            if tk not in ticker_scanners:
                ticker_scanners[tk] = []
                ticker_meta[tk] = m
            ticker_scanners[tk].append(label)

    # Intersect
    rows = []
    for ticker, themes in ticker_themes.items():
        if ticker not in ticker_scanners:
            continue
        meta  = ticker_meta[ticker]
        tv    = meta.get("tv_symbol", "") or ticker
        best  = min(themes, key=lambda x: x["rank"])
        rows.append({
            "Chart":           f"https://www.tradingview.com/chart/?symbol={tv}",
            "Ticker":          ticker,
            "Nome":            (meta.get("name") or "")[:28],
            "Scanner":         len(ticker_scanners[ticker]),
            "Scanner List":    ", ".join(ticker_scanners[ticker]),
            "Rank Tema":       best["rank"],
            "N. Temi":         len(themes),
            "TA":              round(meta.get("ta_rating") or 0, 1),
            "FA":              round(meta.get("fa_rating") or 0, 1),
            "RS":              meta.get("rs_rating") or 0,
            "Prezzo $":        round(meta.get("price") or 0, 2),
            "1D %":            round(meta.get("change_pct") or 0, 2),
            "Top Tema":        f"#{best['rank']} {best['theme'][:30]}",
            "tv_symbol":       tv,
        })

    rows.sort(key=lambda x: (-x["Scanner"], x["Rank Tema"]))
    return rows


# ── SIDEBAR: CREDENTIALS ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Impostazioni")
    try:
        email    = st.secrets["ASKLIVERMORE_EMAIL"]
        password = st.secrets["ASKLIVERMORE_PASSWORD"]
        st.success("Credenziali da Secrets ✓")
    except Exception:
        email    = st.text_input("Email AskLivermore", value="dodo.ebayer@gmail.com")
        password = st.text_input("Password", type="password")

    if st.button("🔄 Aggiorna dati", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption("I dati vengono cachati per 1 ora. Clicca 'Aggiorna' per forzare il refresh.")

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
with st.spinner("Caricamento dati da AskLivermore..."):
    try:
        theme_records, scanner_results = load_data(email, password)
    except Exception as e:
        st.error(f"Errore caricamento dati: {e}")
        st.stop()

as_of = theme_records[0]["as_of"] if theme_records else ""

# ── HEADER ─────────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.title("📊 Dodo Weekly Scanner")
with col2:
    st.metric("Temi", len(theme_records))
with col3:
    st.caption(f"Dati al: **{as_of}**")

# ── TABS ───────────────────────────────────────────────────────────────────────
tab_themes, tab_cross, tab_config = st.tabs([
    "📈 Theme Momentum",
    "🎯 Cross-Reference Titoli",
    "⚙️ Configura Scanner & Temi",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — THEME MOMENTUM
# ══════════════════════════════════════════════════════════════════════════════
with tab_themes:
    st.markdown("""
    > **Ponderazione Claude Swing** — 1M=40% | 3M=25% | 1W=25% | 1D=10%
    """)

    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        crowd_opts = ["Tutti"] + sorted({r["Crowding"] for r in theme_records if r["Crowding"]})
        crowd_sel  = st.selectbox("Filtra Crowding", crowd_opts)
    with col_f2:
        tipo_opts = ["Tutti"] + sorted({r["Tipo"] for r in theme_records if r["Tipo"]})
        tipo_sel  = st.selectbox("Filtra Tipo", tipo_opts)

    df_t = pd.DataFrame([{k: v for k, v in r.items() if k not in ("id", "stocks", "as_of")}
                         for r in theme_records])
    if crowd_sel != "Tutti":
        df_t = df_t[df_t["Crowding"] == crowd_sel]
    if tipo_sel != "Tutti":
        df_t = df_t[df_t["Tipo"] == tipo_sel]

    st.dataframe(
        df_t.reset_index(drop=True),
        use_container_width=True,
        height=600,
        column_config={
            "Score ⭐": st.column_config.NumberColumn(format="%.2f"),
            "1M %":  st.column_config.NumberColumn(format="%.1f%%"),
            "3M %":  st.column_config.NumberColumn(format="%.1f%%"),
            "1W %":  st.column_config.NumberColumn(format="%.1f%%"),
            "1D %":  st.column_config.NumberColumn(format="%.1f%%"),
            "TA":    st.column_config.NumberColumn(format="%.1f"),
            "FA":    st.column_config.NumberColumn(format="%.1f"),
            "ARS":   st.column_config.NumberColumn(format="%.0f"),
        },
    )
    st.caption(f"{len(df_t)} temi visualizzati")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONFIG (build first so state is ready before Tab 2 render)
# ══════════════════════════════════════════════════════════════════════════════
with tab_config:
    st.subheader("📊 Temi da includere nel cross-reference")

    preset_col = st.columns(6)
    top_n_val  = st.session_state.get("top_n_preset", 30)

    with preset_col[0]:
        if st.button("Top 10"):
            st.session_state["top_n_preset"] = 10
            st.rerun()
    with preset_col[1]:
        if st.button("Top 20"):
            st.session_state["top_n_preset"] = 20
            st.rerun()
    with preset_col[2]:
        if st.button("Top 30"):
            st.session_state["top_n_preset"] = 30
            st.rerun()
    with preset_col[3]:
        if st.button("Top 50"):
            st.session_state["top_n_preset"] = 50
            st.rerun()
    with preset_col[4]:
        if st.button("Tutti"):
            st.session_state["top_n_preset"] = 999
            st.rerun()
    with preset_col[5]:
        if st.button("Nessuno"):
            st.session_state["top_n_preset"] = 0
            st.rerun()

    top_n = st.session_state.get("top_n_preset", 30)
    default_themes = [r["Tema"] for r in theme_records[:top_n]]

    selected_themes = st.multiselect(
        f"Temi selezionati ({len(theme_records)} totali, ordinati per score)",
        options=[r["Tema"] for r in theme_records],
        default=default_themes,
        key="sel_themes",
    )

    st.divider()
    st.subheader("🔍 Scanner da includere")

    selected_scanners = st.multiselect(
        "Scanner attivi",
        options=list(SCANNERS.keys()),
        default=list(SCANNERS.keys()),
        format_func=lambda k: f"{SCANNERS[k]}  ({len(scanner_results.get(k, []))} titoli)",
        key="sel_scanners",
    )

    st.info(f"Selezione attuale: **{len(selected_themes)}** temi · **{len(selected_scanners)}** scanner")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CROSS-REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cross:
    sel_theme_ids   = {r["id"] for r in theme_records if r["Tema"] in st.session_state.get("sel_themes", [])}
    sel_scanner_ids = set(st.session_state.get("sel_scanners", list(SCANNERS.keys())))

    # Fallback defaults if config tab not yet visited
    if not sel_theme_ids:
        sel_theme_ids = {r["id"] for r in theme_records[:30]}
    if not sel_scanner_ids:
        sel_scanner_ids = set(SCANNERS.keys())

    crossref = build_crossref(theme_records, scanner_results, sel_theme_ids, sel_scanner_ids)

    st.markdown(f"""
    > Titoli nei temi selezionati **∩** scanner selezionati &nbsp;—&nbsp;
    **{len(sel_theme_ids)}** temi · **{len(sel_scanner_ids)}** scanner · **{len(crossref)}** titoli trovati
    """)

    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        min_scan = st.selectbox("Min scanner", [1, 2, 3, 4, 5], index=0)

    df_c = pd.DataFrame(crossref)
    if df_c.empty:
        st.warning("Nessun titolo trovato con la selezione attuale. Modifica temi/scanner nella tab ⚙️ Configura.")
    else:
        df_c = df_c[df_c["Scanner"] >= min_scan].copy()
        df_c = df_c.drop(columns=["tv_symbol"])

        st.dataframe(
            df_c.reset_index(drop=True),
            use_container_width=True,
            height=600,
            column_config={
                "Chart": st.column_config.LinkColumn(
                    "📈 Chart",
                    display_text="TradingView",
                    help="Apri il grafico su TradingView",
                ),
                "Ticker":       st.column_config.TextColumn(width="small"),
                "Scanner":      st.column_config.NumberColumn("N.Scan", format="%d ●"),
                "Rank Tema":    st.column_config.NumberColumn("Rank #", format="#%d"),
                "TA":           st.column_config.NumberColumn(format="%.1f"),
                "FA":           st.column_config.NumberColumn(format="%.1f"),
                "1D %":         st.column_config.NumberColumn(format="%.2f%%"),
                "Prezzo $":     st.column_config.NumberColumn(format="$%.2f"),
            },
            column_order=["Chart", "Ticker", "Nome", "Scanner", "Scanner List",
                          "Rank Tema", "N. Temi", "TA", "FA", "RS",
                          "Prezzo $", "1D %", "Top Tema"],
        )
        st.caption(f"{len(df_c)} titoli visualizzati")

'''
Identity Trust Assessment — enterprise layout.

Navigation is via sidebar, organized by task:
  Overview
    - Dashboard
  Analyze
    - HL7 Stream           (real-time message input — the production path)
    - Batch Upload         (CSV — retrospective / pre-pilot path)
  Reports
    - Flagged Records
    - Coding Coherence
    - DRG Readiness
    - Data Governance
  Compliance
    - Audit Trail
    - Standardization
  Settings
    - Configuration
    - About

State is held in st.session_state so navigation between pages is instant.
'''
import io
from datetime import datetime
import os
import re
import streamlit as st
import pandas as pd
import altair as alt

from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard
from trust_layer.validators import CrossRecordValidator
from trust_layer.audit import log_batch, verify_chain
from trust_layer.coding_validators import assess_record, find_duplicate_episodes
from trust_layer.drg_validators import assess_drg_readiness
from trust_layer.mds_validators import check_mds_completeness
from trust_layer.consent_validators import validate_consent
from trust_layer.schema_mapper import map_columns, CANONICAL_FIELDS, detect_output_file
from trust_layer.sample_generator import generate_sample

try:
    from trust_layer.prior_auth_validators import validate_preauth
    PA_AVAILABLE = True
except ImportError:
    PA_AVAILABLE = False


# ============================================================
# UI theme (inlined so the app is a single file)
# ============================================================
import types
import html as _html
from datetime import datetime as _dt


# ---- palette ------------------------------------------------
TEAL_DEEP = '#082F33'
TEAL = '#0F6B6B'
MINT = '#8FD3C8'
SIGNAL = '#E8573D'      # coral accent (ECG pulse, active nav marker)
INK = '#13272B'
MUTED = '#5E6F70'
LINE = '#E4DED2'
PAPER = '#F6F3EC'
ACCENT = TEAL
NAVY = TEAL_DEEP

# triage-tag status colours
OK = '#2F9E6E'
WARN = '#E9A820'
BAD = '#D64541'
NEUTRAL = '#2F3B40'

DECISION_COLORS = {
    'AUTO_LINK': OK,
    'LINK_WITH_FLAG': WARN,
    'QUARANTINE': BAD,
    'INSUFFICIENT_DATA': NEUTRAL,
}
DECISION_LABELS = {
    'AUTO_LINK': 'Auto-linked',
    'LINK_WITH_FLAG': 'Linked with flag',
    'QUARANTINE': 'Quarantined',
    'INSUFFICIENT_DATA': 'Insufficient data',
}

_TOKENS = {
    '@TD@': TEAL_DEEP, '@T@': TEAL, '@MINT@': MINT, '@SIG@': SIGNAL, '@INK@': INK,
    '@MUTED@': MUTED, '@LINE@': LINE, '@PAPER@': PAPER,
}

_CSS_TMPL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"], .stApp { font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; color: @INK@; }
.stApp {
    background-color: @PAPER@;
    background-image: radial-gradient(#E3DCCC 1px, transparent 1px);
    background-size: 24px 24px;
}
code, pre, .stCode, [data-testid="stCode"] * { font-family: 'IBM Plex Mono', Consolas, monospace !important; }

#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; height: 2.5rem; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }

h2, h3 { font-family: 'Fraunces', Georgia, serif; color: @TD@; font-weight: 600 !important; letter-spacing: -0.005em; }
h3 { font-size: 1.1rem !important; }
[data-testid="stCaptionContainer"] { color: @MUTED@; font-size: .9rem; }
hr { border-color: @LINE@ !important; margin: 1.25rem 0 !important; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #082F33 0%, #06262A 100%); border-right: none; }
[data-testid="stSidebar"] * { color: #CFE5E1; }
[data-testid="stSidebar"] a, [data-testid="stSidebarNav"] a {
    border-radius: 8px; padding: .38rem .7rem; font-size: .9rem; font-weight: 500; border-left: 3px solid transparent;
}
[data-testid="stSidebar"] a:hover { background: rgba(143,211,200,.10); }
[data-testid="stSidebar"] a[aria-current="page"] {
    background: rgba(143,211,200,.14); color: #fff; font-weight: 600; border-left: 3px solid @SIG@;
}
[data-testid="stNavSectionHeader"], [data-testid="stSidebarNav"] header, [data-testid="stSidebarNav"] li > div > span {
    text-transform: uppercase; font-family: 'IBM Plex Mono', monospace; font-size: .66rem !important;
    letter-spacing: .14em; color: #6FA9A0 !important; font-weight: 500;
}
.brand { padding: .3rem .1rem 1rem; border-bottom: 1px solid rgba(143,211,200,.18); margin-bottom: .6rem; display:flex; gap:12px; align-items:center; }
.brand .t { color:#fff !important; font-family:'Fraunces',serif; font-weight:600; font-size:1.15rem; line-height:1.1; }
.brand .s { color:#7DB8AE !important; font-size:.72rem; margin-top:3px; }
.regionchip { display:inline-block; margin:.4rem 0 .2rem; padding:3px 11px; border-radius:999px; border:1px solid rgba(143,211,200,.4);
    color:#BDEDE3 !important; font:500 .72rem 'IBM Plex Mono', monospace; letter-spacing:.04em; }
.demo-note { margin-top:1.2rem; padding:9px 11px; border-radius:8px; background:rgba(232,87,61,.12); border:1px solid rgba(232,87,61,.35);
    font-size:.7rem; line-height:1.4; color:#F3C2B8 !important; }
.demo-note * { color:#F3C2B8 !important; }

/* ---------- Hero ---------- */
.hero { position:relative; overflow:hidden; border-radius:16px; padding:22px 30px 20px; margin:0 0 .9rem;
    background: linear-gradient(115deg, #082F33 0%, #0B4447 52%, #0F6B6B 100%);
    box-shadow: 0 8px 22px rgba(8,47,51,.20); }
.hero .kick { font:500 .66rem 'IBM Plex Mono', monospace; letter-spacing:.18em; text-transform:uppercase; color:@MINT@; }
.hero h1 { font-family:'Fraunces', Georgia, serif !important; font-weight:600 !important; font-size:2rem !important; margin:.3rem 0 0 !important;
    color:#fff !important; padding:0 !important; letter-spacing:-.01em; line-height:1.15; }
.hero svg { position:absolute; right:-6px; bottom:8px; }

/* ---------- KPI tiles (triage tags) ---------- */
.kpi { background:#fff; border:1px solid @LINE@; border-radius:14px; padding:16px 16px 13px; position:relative; overflow:hidden;
    box-shadow:0 2px 6px rgba(8,47,51,.05); }
.kpi::before { content:''; position:absolute; top:0; left:0; right:0; height:6px; background:var(--c); }
.kpi::after { content:''; position:absolute; top:15px; right:13px; width:10px; height:10px; border-radius:50%;
    background:@PAPER@; box-shadow: inset 0 0 0 2px var(--c); }
.kpi .k { font:500 .66rem 'IBM Plex Mono', monospace; letter-spacing:.1em; text-transform:uppercase; color:@MUTED@; margin-top:4px; }
.kpi .v { font:600 2rem 'IBM Plex Mono', monospace; color:@INK@; margin-top:6px; letter-spacing:-.02em; }
.kpi .s { font-size:.76rem; color:@MUTED@; margin-top:2px; }

/* st.metric on other pages */
[data-testid="stMetric"] { background:#fff; border:1px solid @LINE@; border-top:5px solid @T@; border-radius:14px; padding:12px 16px;
    box-shadow:0 2px 6px rgba(8,47,51,.05); }
[data-testid="stMetricLabel"] p { color:@MUTED@; font:500 .68rem 'IBM Plex Mono', monospace; text-transform:uppercase; letter-spacing:.08em; }
[data-testid="stMetricValue"] { color:@INK@; font-family:'IBM Plex Mono', monospace; font-weight:600; font-size:1.65rem; }

/* buttons & inputs */
.stButton > button, .stDownloadButton > button { border-radius:10px; font-weight:550; border:1.5px solid @T@; background:#fff; color:@T@; }
.stButton > button:hover, .stDownloadButton > button:hover { background:@T@; color:#fff; border-color:@T@; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { background:@SIG@; border-color:@SIG@; color:#fff; }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { background:#CF452C; border-color:#CF452C; }
[data-testid="stExpander"] { background:#fff; border:1px solid @LINE@ !important; border-radius:12px; }
[data-testid="stExpander"] summary { font-weight:550; }
[data-testid="stDataFrame"] { border:1px solid @LINE@; border-radius:12px; overflow:hidden; }
[data-testid="stFileUploader"] section { background:#fff; border:2px dashed @T@; border-radius:14px; }
[data-testid="stAlert"] { border-radius:12px; border:1px solid @LINE@; }
.stTextArea textarea { font-family:'IBM Plex Mono', Consolas, monospace; font-size:.84rem; background:#FFFEFA; }

/* components */
.badge { display:inline-flex; align-items:center; gap:7px; padding:3px 11px 3px 9px; border-radius:6px; font:600 .72rem 'IBM Plex Mono', monospace;
    letter-spacing:.04em; text-transform:uppercase; border:1px solid; }
.badge i { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dimrow { margin-bottom:12px; }
.dimrow .l { display:flex; justify-content:space-between; font-size:.85rem; margin-bottom:4px; }
.dimrow .l b { font-weight:600; }
.dimrow .l span { color:@MUTED@; font-family:'IBM Plex Mono', monospace; }
.track { background:#EDE8DC; border-radius:99px; height:9px; overflow:hidden; }
.fill { height:100%; border-radius:99px; }

/* batch header */
.bh { background:#fff; border:1px solid @LINE@; border-radius:16px; padding:14px 22px; display:flex; align-items:center; gap:28px;
    box-shadow:0 2px 6px rgba(8,47,51,.05); margin:0 0 1.2rem; flex-wrap:wrap; }
.bh .grow { flex:1; min-width:200px; }
.bh .k { font:500 .64rem 'IBM Plex Mono', monospace; letter-spacing:.12em; text-transform:uppercase; color:@MUTED@; }
.bh .v { font:600 1.02rem 'IBM Plex Mono', monospace; color:@INK@; margin-top:3px; word-break:break-all; }
.bh .m { font-size:.8rem; color:@MUTED@; margin-top:3px; }
.bh .pill { padding:9px 16px; border-radius:8px; font:600 .78rem 'IBM Plex Mono', monospace; letter-spacing:.08em; border:1.5px solid; }
.bh .ring { display:flex; align-items:center; gap:10px; }
/* callouts + steps */
.callout { background:#fff; border:1px solid @LINE@; border-radius:14px; padding:13px 18px; margin:.4rem 0 1rem; box-shadow:0 2px 6px rgba(8,47,51,.05); }
.callout .ct { font:600 .72rem 'IBM Plex Mono', monospace; letter-spacing:.1em; text-transform:uppercase; color:@INK@; display:flex; align-items:center; gap:8px; }
.callout .ct i { width:10px; height:10px; border-radius:50%; background:var(--c); display:inline-block; }
.callout .cb { margin-top:6px; font-size:.92rem; line-height:1.5; color:@INK@; }
.steps { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:.5rem 0 1.1rem; }
.step { background:#fff; border:1px solid @LINE@; border-radius:14px; padding:14px 16px; box-shadow:0 2px 6px rgba(8,47,51,.05); }
.step .n { width:26px; height:26px; border-radius:50%; background:@T@; color:#fff; font:600 .8rem 'IBM Plex Mono', monospace; display:flex; align-items:center; justify-content:center; }
.step .st { font-weight:600; margin-top:9px; color:@TD@; }
.step .sd { font-size:.84rem; color:@MUTED@; margin-top:3px; line-height:1.45; }
</style>
"""
_CSS = _CSS_TMPL
for _k, _v in _TOKENS.items():
    _CSS = _CSS.replace(_k, _v)


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


# ---- components -------------------------------------------------
_ECG = (
    '<svg width="440" height="64" viewBox="0 0 440 64" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#8FD3C8" stop-opacity="0"/>'
    '<stop offset="0.6" stop-color="#8FD3C8" stop-opacity="0.55"/><stop offset="1" stop-color="#E8573D"/></linearGradient></defs>'
    '<path d="M0 36 H120 L132 36 L140 12 L152 58 L160 28 L166 36 H250 L260 36 L268 24 L276 42 L282 36 H440" '
    'stroke="url(#g)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

_LOGO = (
    '<svg width="38" height="38" viewBox="0 0 38 38" fill="none"><rect width="38" height="38" rx="10" fill="#0F6B6B"/>'
    '<path d="M5 20h7l3-8 5 15 3-9 2 2h8" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="33" cy="20" r="2.2" fill="#E8573D"/></svg>'
)


def hero(title, kicker='Identity Trust Assessment'):
    st.markdown(
        f'<div class="hero"><div class="kick">{_html.escape(kicker)}</div>'
        f'<h1>{_html.escape(title)}</h1>{_ECG}</div>',
        unsafe_allow_html=True,
    )


def kpi(label, value, color=TEAL, sub=''):
    sub_html = f'<div class="s">{_html.escape(sub)}</div>' if sub else ''
    st.markdown(
        f'<div class="kpi" style="--c:{color};"><div class="k">{_html.escape(label)}</div>'
        f'<div class="v">{_html.escape(str(value))}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )



def callout(title, body, color=TEAL):
    st.markdown(
        f'<div class="callout" style="--c:{color};"><div class="ct"><i></i>{_html.escape(title)}</div>'
        f'<div class="cb">{_html.escape(body)}</div></div>',
        unsafe_allow_html=True,
    )


def steps(items):
    cells = ''.join(
        f'<div class="step"><div class="n">{i + 1}</div><div class="st">{_html.escape(a)}</div>'
        f'<div class="sd">{_html.escape(b)}</div></div>' for i, (a, b) in enumerate(items)
    )
    st.markdown(f'<div class="steps">{cells}</div>', unsafe_allow_html=True)


def sidebar_brand(region_name):
    st.markdown(
        f'<div class="brand">{_LOGO}<div><div class="t">Identity Trust</div>'
        f'<div class="s">Patient data quality gate</div></div></div>'
        f'<span class="regionchip">{_html.escape(region_name)}</span>',
        unsafe_allow_html=True,
    )


def sidebar_note():
    st.markdown(
        '<div class="demo-note"><b>Demonstration build.</b> Synthetic data only. '
        'Not validated for clinical or regulatory use.</div>',
        unsafe_allow_html=True,
    )


def badge(decision):
    color = DECISION_COLORS.get(decision, NEUTRAL)
    label = DECISION_LABELS.get(decision, decision)
    return (f'<span class="badge" style="color:{INK};border-color:{color}88;background:{color}1F;">'
            f'<i style="background:{color};"></i>{label}</span>')


def score_color(score):
    if score >= 0.85:
        return OK
    if score >= 0.5:
        return WARN
    return BAD


def dimension_bar(label, score):
    pct = int(round(score * 100))
    c = score_color(score)
    st.markdown(
        f'<div class="dimrow"><div class="l"><b>{label}</b><span>{score:.2f}</span></div>'
        f'<div class="track"><div class="fill" style="width:{pct}%;background:{c};"></div></div></div>',
        unsafe_allow_html=True,
    )


def page_title(title, subtitle):
    hero(title)
    st.caption(subtitle)


def batch_status(results_df):
    """Overall outcome for a batch. Any quarantined / insufficient record needs action."""
    n_act = int(results_df['decision'].isin(['QUARANTINE', 'INSUFFICIENT_DATA']).sum())
    n_rev = int((results_df['decision'] == 'LINK_WITH_FLAG').sum())
    if n_act:
        return 'ACTION REQUIRED', BAD
    if n_rev:
        return 'REVIEW RECOMMENDED', WARN
    return 'NO ISSUES FOUND', OK


def batch_header(info, region_name, results_df):
    label, color = batch_status(results_df)
    total = len(results_df)
    flagged = int(results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA']).sum())
    auto = int((results_df['decision'] == 'AUTO_LINK').sum())
    pct = (auto / total * 100) if total else 0.0
    circ = 163.36
    dash = pct / 100 * circ
    name = _html.escape(str((info or {}).get('name') or 'Unnamed batch'))
    when = _html.escape(str((info or {}).get('processed_at') or ''))
    ring = (
        '<svg width="64" height="64" viewBox="0 0 64 64"><circle cx="32" cy="32" r="26" fill="none" stroke="#EDE8DC" stroke-width="7"/>'
        f'<circle cx="32" cy="32" r="26" fill="none" stroke="{TEAL}" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{dash:.1f} {circ}" transform="rotate(-90 32 32)"/>'
        f'<text x="32" y="36.5" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="13" font-weight="600" fill="{INK}">{pct:.0f}%</text></svg>'
    )
    st.markdown(
        f'<div class="bh">'
        f'<div class="grow"><div class="k">Batch</div><div class="v">{name}</div>'
        f'<div class="m">{_html.escape(region_name)} &middot; processed {when}</div></div>'
        f'<div class="ring">{ring}<div><div class="k">Auto-linked</div>'
        f'<div class="m">{auto:,} of {total:,} records<br>{flagged:,} need review</div></div></div>'
        f'<div class="pill" style="color:{INK};border-color:{color};background:{color}22;">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


_AX = dict(labelColor=MUTED, titleColor=MUTED, labelFont='IBM Plex Sans', titleFont='IBM Plex Sans')


def bar_chart(df, x, y, color=TEAL, height=240, domain=None, x_title=None):
    xenc = alt.X(f'{x}:Q', title=x_title or x, scale=alt.Scale(domain=domain) if domain else alt.Undefined,
                 axis=alt.Axis(grid=True, gridColor='#E9E3D6', domain=False, tickColor='#E9E3D6'))
    return (
        alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=4, size=18)
        .encode(x=xenc, y=alt.Y(f'{y}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False, labelLimit=260)),
                tooltip=list(df.columns))
        .properties(height=height)
        .configure(background='transparent')
        .configure_view(strokeWidth=0)
        .configure_axis(**_AX)
    )


def decision_chart(df, decision_col='Decision', count_col='Count', height=240):
    domain = [DECISION_LABELS[k] for k in DECISION_LABELS]
    rng = [DECISION_COLORS[k] for k in DECISION_LABELS]
    return (
        alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=18)
        .encode(
            x=alt.X(f'{count_col}:Q', title='Records', axis=alt.Axis(grid=True, gridColor='#E9E3D6', domain=False)),
            y=alt.Y(f'{decision_col}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False)),
            color=alt.Color(f'{decision_col}:N', scale=alt.Scale(domain=domain, range=rng), legend=None),
            tooltip=[decision_col, count_col],
        )
        .properties(height=height)
        .configure(background='transparent')
        .configure_view(strokeWidth=0)
        .configure_axis(**_AX)
    )


# ============================================================
# Printable report
# ============================================================
def build_report_html(info, region_name, config, results_df, schema,
                      clinical_meta, drg_meta, gov_meta, version='v0.7.0-demo'):
    e = _html.escape
    total = len(results_df)
    label, color = batch_status(results_df)
    now = _dt.now().strftime('%d %b %Y, %H:%M')
    rid = _dt.now().strftime('ITA-%Y%m%d-%H%M')

    counts = results_df['decision'].value_counts().to_dict()
    rows = ''.join(
        f'<tr><td>{e(DECISION_LABELS[k])}</td><td class="n">{counts.get(k, 0):,}</td>'
        f'<td class="n">{(counts.get(k, 0) / total * 100 if total else 0):.1f}%</td></tr>'
        for k in DECISION_LABELS
    )

    flagged = results_df[results_df['decision'] != 'AUTO_LINK']
    issues = flagged['primary_issue'].value_counts()
    issue_rows = ''.join(f'<tr><td>{e(str(k))}</td><td class="n">{v:,}</td></tr>' for k, v in issues.items()) \
        or '<tr><td colspan="2">No issues recorded.</td></tr>'

    dims = [('Completeness', 'dim_completeness'), ('Temporal validity', 'dim_temporal'),
            ('Identity consistency', 'dim_identity'), ('Provenance', 'dim_provenance'),
            ('Cross-record consistency', 'dim_cross_record')]
    dim_rows = ''.join(f'<tr><td>{n}</td><td class="n">{results_df[c].mean():.2f}</td></tr>' for n, c in dims)

    mods = []
    if clinical_meta.get('available'):
        mods.append(('Coding coherence',
                     f"{clinical_meta['icd_issues']} ICD issues, {clinical_meta['icd_cpt_mismatches']} ICD-CPT mismatches, "
                     f"{clinical_meta['timeline_errors']} timeline errors, {clinical_meta['triage_anomalies']} triage-cost anomalies"))
    else:
        mods.append(('Coding coherence', 'Not run (no diagnosis or procedure codes in file)'))
    if drg_meta.get('available'):
        mods.append(('DRG readiness',
                     f"{drg_meta['inpatient_count']} inpatient records: {drg_meta['fully_ready']} ready, "
                     f"{drg_meta['partial']} partial, {drg_meta['not_ready']} not ready"))
    else:
        mods.append(('DRG readiness', 'Not run (no encounter type in file)'))
    mods.append(('Minimum data set',
                 f"Mean completeness {gov_meta['mean_mds']:.2f}; {gov_meta['below_80']} records below 0.80"))
    if gov_meta['consent_available']:
        mods.append(('Consent', f"{gov_meta['consent_blocked']} denied/withdrawn, {gov_meta['consent_missing']} missing"))
    else:
        mods.append(('Consent', 'Not run (no consent status in file)'))
    if gov_meta['pa_available']:
        mods.append(('Prior authorization', f"{gov_meta['pa_missing']} of {gov_meta['pa_required']} required are missing a reference"))
    else:
        mods.append(('Prior authorization', 'Not run (no pre-authorization fields in file)'))
    mod_rows = ''.join(f'<tr><td>{e(a)}</td><td>{e(b)}</td></tr>' for a, b in mods)

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Data Quality Report {rid}</title>
<style>
 body {{ font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color:#13272B; margin:0; padding:32px; background:#fff; font-size:13px; line-height:1.45; }}
 .wrap {{ max-width: 820px; margin: 0 auto; }}
 .top {{ border-bottom: 3px solid #082F33; padding-bottom:12px; margin-bottom:18px; display:flex; justify-content:space-between; align-items:flex-end; }}
 h1 {{ font-size:20px; margin:0; color:#082F33; }} .sub {{ color:#5E6F70; font-size:12px; }}
 h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.07em; color:#082F33; border-bottom:1px solid #DDD6C8; padding-bottom:4px; margin:22px 0 8px; }}
 table {{ width:100%; border-collapse:collapse; }} td, th {{ padding:6px 8px; border-bottom:1px solid #EFEADF; text-align:left; vertical-align:top; }}
 th {{ background:#F6F3EC; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#5E6F70; }}
 td.n {{ text-align:right; font-variant-numeric:tabular-nums; width:90px; }}
 .meta td:first-child {{ color:#5E6F70; width:170px; }}
 .status {{ display:inline-block; padding:4px 12px; border:1px solid {color}; color:{color}; font-weight:700; letter-spacing:.06em; border-radius:4px; }}
 .sign td {{ height:42px; border-bottom:1px solid #9AA8B9; }} .sign td:first-child {{ width:140px; color:#5E6F70; border-bottom:none; vertical-align:bottom; }}
 .foot {{ margin-top:26px; font-size:11px; color:#5E6F70; border-top:1px solid #DDD6C8; padding-top:8px; }}
 @media print {{ body {{ padding:0; }} }}
</style></head><body><div class="wrap">
<div class="top"><div><h1>Patient Identity &amp; Data Quality Report</h1><div class="sub">Identity Trust Assessment &middot; {e(version)}</div></div>
<div class="sub" style="text-align:right">Report {rid}<br>Generated {now}</div></div>

<table class="meta">
<tr><td>Source file</td><td>{e(str((info or {}).get('name') or '-'))}</td></tr>
<tr><td>Region profile</td><td>{e(region_name)} ({e(config['regulatory_body'])}; identifier: {e(config['id_label'])})</td></tr>
<tr><td>Records assessed</td><td>{total:,}</td></tr>
<tr><td>Overall outcome</td><td><span class="status">{label}</span></td></tr>
</table>

<h2>Routing outcomes</h2>
<table><tr><th>Outcome</th><th style="text-align:right">Records</th><th style="text-align:right">Share</th></tr>{rows}</table>

<h2>Primary issues in flagged records</h2>
<table><tr><th>Issue</th><th style="text-align:right">Records</th></tr>{issue_rows}</table>

<h2>Mean score by dimension (0-1)</h2>
<table><tr><th>Dimension</th><th style="text-align:right">Mean</th></tr>{dim_rows}</table>

<h2>Module checks</h2>
<table><tr><th>Check</th><th>Result</th></tr>{mod_rows}</table>

<h2>Review and sign-off</h2>
<table class="sign"><tr><td>Reviewed by</td><td></td></tr><tr><td>Role</td><td></td></tr><tr><td>Date</td><td></td></tr><tr><td>Signature</td><td></td></tr></table>

<div class="foot">Method: five-dimension identity trust score with routing thresholds (auto-link 0.75, quarantine 0.45).
These demonstration thresholds differ from the published validated configuration and must be re-derived before any hospital pilot.
This tool flags records for human review; it does not merge, correct or delete data.
Demonstration build using synthetic data; not validated for clinical or regulatory use.</div>
</div></body></html>"""

ui = types.SimpleNamespace(
    ACCENT=ACCENT,
    BAD=BAD,
    DECISION_COLORS=DECISION_COLORS,
    DECISION_LABELS=DECISION_LABELS,
    NEUTRAL=NEUTRAL,
    OK=OK,
    TEAL=TEAL,
    WARN=WARN,
    badge=badge,
    bar_chart=bar_chart,
    batch_header=batch_header,
    build_report_html=build_report_html,
    callout=callout,
    decision_chart=decision_chart,
    dimension_bar=dimension_bar,
    hero=hero,
    inject_css=inject_css,
    kpi=kpi,
    sidebar_brand=sidebar_brand,
    sidebar_note=sidebar_note,
    steps=steps,
)


# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title='Identity Trust Assessment',
    page_icon=':material/health_and_safety:',
    layout='wide',
    initial_sidebar_state='expanded',
)
ui.inject_css()


# ============================================================
# Constants
# ============================================================
AUDIT_LOG_PATH = '/tmp/audit_log.jsonl'

COLOR_OPTIONS = {
    'Blue': '#1E90FF', 'Pink': '#FF69B4', 'Red': '#FF0000',
    'Orange': '#FFA500', 'Purple': '#800080', 'Green': '#32CD32',
    'Teal': '#008080', 'Magenta': '#FF00FF', 'Indigo': '#4B0082',
    'Black': '#000000', 'Gray': '#808080', 'Gold': '#FFD700',
}
PREFIXES = ['mr.', 'mrs.', 'ms.', 'dr.', 'mr ', 'mrs ', 'ms ', 'dr ']
SMALL_WORDS = {'and', 'of', 'the', 'at', 'in', 'on', 'for'}

GENDER_CANON = {
    'm': 'M', 'male': 'M', 'man': 'M',
    'f': 'F', 'female': 'F', 'woman': 'F',
    'o': 'O', 'other': 'O',
    'u': 'U', 'unknown': 'U',
}

NATIONALITY_CANON = {
    'uae': 'UAE', 'unitedarabemirates': 'UAE', 'emirati': 'UAE',
    'india': 'India', 'indian': 'India', 'ind': 'India',
    'pakistan': 'Pakistan', 'pakistani': 'Pakistan',
    'philippines': 'Philippines', 'filipino': 'Philippines',
    'egypt': 'Egypt', 'egyptian': 'Egypt',
    'uk': 'UK', 'unitedkingdom': 'UK', 'british': 'UK',
    'usa': 'USA', 'unitedstates': 'USA', 'american': 'USA',
}

REGION_PROFILES = {
    'UAE (DOH)': {
        'id_label': 'Emirates ID',
        'id_pattern': r'^784\d{12}$',
        'id_example': '784-1985-1234567-1',
        'regulatory_body': 'DOH',
        'trusted_facilities': [
            'Cleveland Clinic Abu Dhabi', 'Ssmc', 'Al Noor Hospital',
            'Tawam Hospital', 'Sheikh Khalifa Medical City',
        ],
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
        'dob_min_year': 1900, 'dob_max_year': 2025,
    },
    'India (ABDM)': {
        'id_label': 'ABHA / Aadhaar',
        'id_pattern': r'^\d{12}$',
        'id_example': '123456789012',
        'regulatory_body': 'ABDM',
        'trusted_facilities': [
            'Manipal Hospital', 'Apollo Hospital', 'Fortis Healthcare',
            'Max Healthcare', 'Aiims', 'Aiims Delhi', 'Narayana Health',
        ],
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
        'dob_min_year': 1900, 'dob_max_year': 2025,
    },
}


# ============================================================
# Session state initialization
# ============================================================
if 'region_name' not in st.session_state:
    st.session_state['region_name'] = 'UAE (DOH)'
if 'bar_color_name' not in st.session_state:
    st.session_state['bar_color_name'] = 'Blue'
if 'assessment' not in st.session_state:
    st.session_state['assessment'] = None
if 'uploaded_name' not in st.session_state:
    st.session_state['uploaded_name'] = None
if 'hl7_history' not in st.session_state:
    st.session_state['hl7_history'] = []
if 'batch_info' not in st.session_state:
    st.session_state['batch_info'] = None
if 'hl7_validator' not in st.session_state:
    st.session_state['hl7_validator'] = None


def _get_config():
    return REGION_PROFILES[st.session_state['region_name']]


def _get_color():
    return COLOR_OPTIONS[st.session_state['bar_color_name']]


# ============================================================
# Normalization helpers
# ============================================================
DECISION_MEANING = {
    'AUTO_LINK': ('Safe to link', 'Identity checks passed. The record can be linked to the patient automatically.'),
    'LINK_WITH_FLAG': ('Link, but check first', 'Mostly trustworthy, but something looked off. A person should take a quick look before relying on it.'),
    'QUARANTINE': ('Hold back', 'A serious problem was found, for example an ID already used by someone else. Do not share this record until a person resolves it.'),
    'INSUFFICIENT_DATA': ('Not enough information', 'Too little identity data to judge. Get the missing details from the source first.'),
}

ISSUE_ACTION = {
    'Identifier Collision': 'Two different people appear to share one ID. Check the ID against the patient\'s physical document before linking either record.',
    'Potential Name/DOB Collision': 'Same name and birth date as an existing patient but a different ID. Confirm whether this is a duplicate of the same person or a different person.',
    'Missing Demographics': 'Fill in the missing fields from the source system, then re-submit.',
    'Untrusted Facility': 'The record came from a facility that is not on the trusted list. Confirm it with the sending facility.',
    'Temporal Validity Error': 'The date of birth is impossible or unreadable. Correct it at the source.',
    'Malformed Identifier': 'The ID does not follow the national format. Check it for typos or missing digits.',
    'Insufficient Data': 'Too few identity fields were supplied. Obtain at least name, ID and date of birth.',
}

SAMPLE_HL7_CLEAN = (
    'MSH|^~\\&|HIS|CLEVELAND CLINIC ABU DHABI|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r'
    'EVN|A04|20240110120000\r'
    'PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M\r'
    'PV1|1|O'
)
SAMPLE_HL7_COLLISION = (
    'MSH|^~\\&|HIS|TAWAM HOSPITAL|MALAFFI|DOH|20240110121500||ADT^A04|MSG0002|P|2.5\r'
    'EVN|A04|20240110121500\r'
    'PID|1||784-1985-1234567-1^^^DOH^MR||Hashimi^Fatima||19920722|F\r'
    'PV1|1|O'
)
SAMPLE_HL7_BAD = (
    'MSH|^~\\&|HIS|UNKNOWN CLINIC|MALAFFI|DOH|20240110123000||ADT^A04|MSG0003|P|2.5\r'
    'EVN|A04|20240110123000\r'
    'PID|1||123^^^DOH^MR||Khan^Sara||19990101|F\r'
    'PV1|1|O'
)


def load_demo_batch():
    """Generate a synthetic batch and run the full assessment on it in one click."""
    region = st.session_state['region_name']
    sample_df = generate_sample(region, n=100)
    data = sample_df.to_csv(index=False).encode('utf-8')
    st.session_state['assessment'] = run_assessment(data, region)
    st.session_state['batch_info'] = {
        'name': f'demo_sample_{region.split()[0].lower()}_100.csv',
        'processed_at': datetime.now().strftime('%d %b %Y, %H:%M'),
    }


def goto_flagged(decisions):
    st.session_state['flag_preset'] = decisions
    st.switch_page(PAGES['flagged'])


def smart_title(s):
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w.title())
    t = ' '.join(out)
    t = re.sub(r"'S\b", "'s", t)
    return t


def normalize_text(value):
    if pd.isna(value) or value is None:
        return ''
    s = str(value).strip()
    if s.lower() in ('nan', 'nat', 'none'):
        return ''
    lower = s.lower()
    for prefix in PREFIXES:
        if lower.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    s = ' '.join(s.split())
    if not s:
        return ''
    return smart_title(s)


def normalize_id(value):
    if pd.isna(value) or value is None:
        return None
    s = str(value).strip()
    if s == '' or s.lower() in ('nan', 'nat', 'none'):
        return None
    digits = ''.join(c for c in s if c.isdigit())
    return digits if digits else None


def normalize_date(value):
    if pd.isna(value) or value is None:
        return ''
    if isinstance(value, pd.Timestamp):
        return value.strftime('%Y-%m-%d')
    s = str(value).strip()
    if s == '' or s.lower() in ('nan', 'nat', 'none'):
        return ''
    if len(s) == 10 and s[4] == '-':
        return s
    try:
        parsed = pd.to_datetime(s, dayfirst=True, errors='coerce')
        if pd.isna(parsed):
            return s
        return parsed.strftime('%Y-%m-%d')
    except Exception:
        return s


def normalize_gender(value):
    if pd.isna(value) or value is None:
        return ''
    s = str(value).strip().lower()
    if s == '' or s in ('nan', 'nat', 'none'):
        return ''
    return GENDER_CANON.get(s, str(value).strip().upper()[:1])


def normalize_nationality(value):
    if pd.isna(value) or value is None:
        return ''
    s = str(value).strip()
    if s == '' or s.lower() in ('nan', 'nat', 'none'):
        return ''
    key = re.sub(r'[\s_\-\.]+', '', s.lower())
    return NATIONALITY_CANON.get(key, s.title())


def render_dimension_bar(label, score, color=None):
    ui.dimension_bar(label, score)


# ============================================================
# Validators (region-aware)
# ============================================================
def validate_completeness_region(rec, config):
    fields = {
        'emirates_id': rec.emirates_id,
        'given_name': rec.given_name,
        'family_name': rec.family_name,
        'date_of_birth': rec.date_of_birth,
    }
    req = config['required_fields']
    present = sum(1 for f in req if fields.get(f))
    return round(present / len(req), 2) if req else 1.0


def validate_temporal_region(rec, config):
    if not rec.date_of_birth:
        return 0.0
    try:
        year = int(rec.date_of_birth[:4])
        if config['dob_min_year'] <= year <= config['dob_max_year']:
            return 1.0
        return 0.3
    except (ValueError, TypeError):
        return 0.0


def validate_identity_region(rec, config):
    if not rec.emirates_id:
        return 0.0
    if re.match(config['id_pattern'], rec.emirates_id):
        return 1.0
    return 0.3


def validate_provenance_region(rec, config):
    if not rec.source_facility:
        return 0.0
    if rec.source_facility in config['trusted_facilities']:
        return 1.0
    return 0.7


class Record:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ============================================================
# Assessment pipeline (cached)
# ============================================================
@st.cache_data(show_spinner='Running trust assessment...')
def run_assessment(file_bytes, region_name):
    config = REGION_PROFILES[region_name]

    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [str(c).strip() for c in df.columns]

    if len(df.columns) == 0:
        return None, {'error': True, 'found': [], 'missing': ['any columns']}

    original_columns = list(df.columns)
    looks_like_output = detect_output_file(df)

    mapping, unresolved, inferred = map_columns(df)
    df = df.rename(columns=mapping)

    for field in CANONICAL_FIELDS:
        if field not in df.columns:
            df[field] = ''

    coding_available = ('diagnosis_code' in df.columns and (df['diagnosis_code'].astype(str).str.strip() != '').any()) or \
                       ('procedure_code' in df.columns and (df['procedure_code'].astype(str).str.strip() != '').any())
    drg_available = 'encounter_type' in df.columns and (df['encounter_type'].astype(str).str.strip() != '').any()
    consent_available = 'consent_status' in df.columns and (df['consent_status'].astype(str).str.strip() != '').any()
    pa_available_here = ('preauth_reference' in df.columns and (df['preauth_reference'].astype(str).str.strip() != '').any()) or \
                        ('preauth_valid_until' in df.columns and (df['preauth_valid_until'].astype(str).str.strip() != '').any())

    df['_orig_given'] = df['given_name'].astype(str).replace('nan', '')
    df['_orig_family'] = df['family_name'].astype(str).replace('nan', '')
    df['_orig_dob'] = df['date_of_birth'].astype(str).replace('nan', '')
    df['_orig_id'] = df['emirates_id'].astype(str).replace('nan', '')
    df['_orig_gender'] = df['gender'].astype(str).replace('nan', '')
    df['_orig_nationality'] = df['nationality'].astype(str).replace('nan', '')

    df['given_name'] = df['given_name'].apply(normalize_text)
    df['family_name'] = df['family_name'].apply(normalize_text)
    df['date_of_birth'] = df['date_of_birth'].apply(normalize_date)
    df['source_facility'] = df['source_facility'].apply(normalize_text)
    df['nationality'] = df['nationality'].apply(normalize_nationality)
    df['gender'] = df['gender'].apply(normalize_gender)
    df['emirates_id'] = df['emirates_id'].apply(normalize_id)

    df['_changed_name'] = (df['_orig_given'] != df['given_name'].astype(str)) | (df['_orig_family'] != df['family_name'].astype(str))
    df['_changed_dob'] = (df['_orig_dob'] != df['date_of_birth'].astype(str)) & (df['_orig_dob'] != '')
    df['_changed_id'] = (df['_orig_id'] != df['emirates_id'].astype(str)) & (df['_orig_id'] != '')
    df['_changed_gender'] = (df['_orig_gender'] != df['gender'].astype(str)) & (df['_orig_gender'] != '')
    df['_changed_nationality'] = (df['_orig_nationality'] != df['nationality'].astype(str)) & (df['_orig_nationality'] != '')

    total_raw = len(df)
    missing_ids = int(df['emirates_id'].isna().sum())
    missing_dob = int((df['date_of_birth'] == '').sum())
    dup_ids = int(df['emirates_id'].dropna().duplicated().sum())
    total_normalized = int((df['_changed_name'] | df['_changed_dob'] | df['_changed_id'] | df['_changed_gender'] | df['_changed_nationality']).sum())

    cv = CrossRecordValidator()
    results = []
    audit_entries = []

    for index, row in df.iterrows():
        rec = Record(
            emirates_id=row.get('emirates_id') if pd.notna(row.get('emirates_id')) else None,
            given_name=row.get('given_name', ''),
            family_name=row.get('family_name', ''),
            date_of_birth=row.get('date_of_birth', ''),
            nationality=row.get('nationality', ''),
            source_facility=row.get('source_facility', ''),
            registration_date=row.get('registration_date', ''),
            canonical_id=str(row.get('canonical_id', f'ROW_{index}')),
        )

        dims = {
            'completeness': validate_completeness_region(rec, config),
            'temporal': validate_temporal_region(rec, config),
            'identity': validate_identity_region(rec, config),
            'provenance': validate_provenance_region(rec, config),
            'cross_record': cv.validate(rec),
        }
        weighted_sum = compute_trust_score(**dims)
        min_dim = min(dims.values())
        composite = round(weighted_sum * (0.4 + 0.6 * min_dim), 4)

        id_label = config['id_label']
        reg = config['regulatory_body']

        critical_present = sum(1 for v in [rec.emirates_id, rec.given_name, rec.family_name, rec.date_of_birth] if v)

        if critical_present < 2:
            decision = 'INSUFFICIENT_DATA'
            composite = 0.0
            explanation = 'Record contains fewer than two of the four core identity fields (name, ID, DOB).'
            primary_issue = 'Insufficient Data'
            routing_reason = 'Insufficient identity fields'
        else:
            decision, routing_reason = route_decision_hard(composite, dims['cross_record'])
            explanation = 'Record is clean and trusted.'
            primary_issue = 'None'
            if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
                weakest = min(dims, key=dims.get)
                wv = dims[weakest]

                if weakest == 'cross_record':
                    if wv == 0.0:
                        owner = None
                        owners = cv.identifier_index.get(rec.emirates_id, set()) if rec.emirates_id else set()
                        for o in owners:
                            if o != rec.canonical_id:
                                owner = o
                                break
                        explanation = (f'FORENSIC COLLISION: {id_label} {rec.emirates_id} is already registered '
                                       f'to patient {owner or "another record"}. This record claims to be '
                                       f'{rec.given_name} {rec.family_name} (DOB: {rec.date_of_birth}), which is a different identity.')
                        primary_issue = 'Identifier Collision'
                    elif wv == 0.5:
                        explanation = (f'POTENTIAL COLLISION: Name ({rec.given_name} {rec.family_name}) and '
                                       f'DOB ({rec.date_of_birth}) match an existing patient, but the {id_label} differs.')
                        primary_issue = 'Potential Name/DOB Collision'
                elif weakest == 'completeness':
                    missing_fields = [f for f, v in [
                        (id_label, rec.emirates_id), ('Given Name', rec.given_name),
                        ('Family Name', rec.family_name), ('DOB', rec.date_of_birth),
                    ] if not v]
                    explanation = f'INCOMPLETE DATA: Missing required fields: {", ".join(missing_fields)}.'
                    primary_issue = 'Missing Demographics'
                elif weakest == 'provenance':
                    explanation = f'LOW-TRUST SOURCE: Facility {rec.source_facility or "(unset)"} is not in the {reg} trusted tier.'
                    primary_issue = 'Untrusted Facility'
                elif weakest == 'temporal':
                    explanation = f'TEMPORAL ERROR: The DOB {rec.date_of_birth or "(unset)"} could not be normalized to a valid ISO date.'
                    primary_issue = 'Temporal Validity Error'
                elif weakest == 'identity':
                    explanation = (f'IDENTITY INCONSISTENCY: The {id_label} {rec.emirates_id or "(unset)"} does not match the {reg} format '
                                   f'(expected e.g. {config["id_example"]}).')
                    primary_issue = 'Malformed Identifier'

        results.append({
            'canonical_id': rec.canonical_id, 'given_name': rec.given_name,
            'family_name': rec.family_name, 'source_facility': rec.source_facility,
            'trust_score': round(composite, 4), 'weighted_sum': round(weighted_sum, 4),
            'routing_reason': routing_reason, 'decision': decision,
            'explanation': explanation, 'primary_issue': primary_issue,
            'dim_completeness': dims['completeness'], 'dim_temporal': dims['temporal'],
            'dim_identity': dims['identity'], 'dim_provenance': dims['provenance'],
            'dim_cross_record': dims['cross_record'],
        })

        audit_entries.append((rec, dims, score, decision))
        cv.add_record(rec)

    log_batch(
        audit_entries,
        log_path=AUDIT_LOG_PATH,
        config_version='v0.7.0-demo',
        thresholds={'low': 0.75, 'medium': 0.45},
    )

    results_df = pd.DataFrame(results)

    clinical_df = None
    clinical_meta = {'available': False}
    if coding_available:
        clinical_rows = []
        for _, row in df.iterrows():
            checks = assess_record(row.to_dict())
            clinical_rows.append({
                'canonical_id': row.get('canonical_id', '?'),
                'given_name': row.get('given_name', ''),
                'family_name': row.get('family_name', ''),
                'diagnosis_code': row.get('diagnosis_code', ''),
                'procedure_code': row.get('procedure_code', ''),
                'admission_date': row.get('admission_date', ''),
                'discharge_date': row.get('discharge_date', ''),
                'triage_level': row.get('triage_level', ''),
                'total_cost_aed': row.get('total_cost_aed', ''),
                'icd_exists': checks['icd_exists'],
                'icd_cpt_match': checks['icd_cpt_match'],
                'episode_timeline': checks['episode_timeline'],
                'admission_after_dob': checks['admission_after_dob'],
                'triage_cost': checks['triage_cost'],
                'clinical_coherence_score': checks['clinical_coherence_score'],
            })
        clinical_df = pd.DataFrame(clinical_rows)
        clinical_meta = {
            'available': True,
            'icd_issues': int((clinical_df['icd_exists'] < 1.0).sum()),
            'icd_cpt_mismatches': int((clinical_df['icd_cpt_match'] == 0.0).sum()),
            'timeline_errors': int((clinical_df['episode_timeline'] == 0.0).sum()),
            'triage_anomalies': int((clinical_df['triage_cost'] == 0.0).sum()),
            'mean_coherence': float(clinical_df['clinical_coherence_score'].mean()),
            'duplicate_episodes': find_duplicate_episodes(df.to_dict('records')),
        }

    drg_rows = []
    for _, row in df.iterrows():
        r = assess_drg_readiness(row.to_dict())
        drg_rows.append({
            'canonical_id': row.get('canonical_id', '?'),
            'given_name': row.get('given_name', ''),
            'family_name': row.get('family_name', ''),
            'encounter_type': row.get('encounter_type', ''),
            'drg_readiness_score': r['drg_readiness_score'],
            'applicable': r['applicable'],
            'missing_inputs': ', '.join(r['missing_inputs']),
            'issues': ' | '.join(r['issues']),
        })
    drg_df = pd.DataFrame(drg_rows)
    drg_applicable = drg_df[drg_df['applicable'] == True]
    drg_meta = {
        'available': drg_available and len(drg_applicable) > 0,
        'inpatient_count': len(drg_applicable),
        'outpatient_count': int((drg_df['applicable'] == False).sum()),
        'fully_ready': int((drg_applicable['drg_readiness_score'] >= 0.95).sum()) if len(drg_applicable) else 0,
        'partial': int(((drg_applicable['drg_readiness_score'] >= 0.5) & (drg_applicable['drg_readiness_score'] < 0.95)).sum()) if len(drg_applicable) else 0,
        'not_ready': int((drg_applicable['drg_readiness_score'] < 0.5).sum()) if len(drg_applicable) else 0,
        'mean_readiness': float(drg_applicable['drg_readiness_score'].mean()) if len(drg_applicable) else 1.0,
    }

    gov_rows = []
    for _, row in df.iterrows():
        rec_dict = row.to_dict()
        mds = check_mds_completeness(rec_dict)
        consent = {'consent_score': 1.0, 'consent_state': 'granted', 'issues': []}
        if consent_available:
            consent = validate_consent(rec_dict)
        pa = {'pa_required': False, 'pa_present': False, 'pa_score': 1.0, 'issues': []}
        if PA_AVAILABLE and pa_available_here:
            pa = validate_preauth(rec_dict)
        mds_missing = mds['patient_demographics_missing'] + mds['encounter_missing'] + mds['clinical_missing']
        gov_rows.append({
            'canonical_id': row.get('canonical_id', '?'),
            'given_name': row.get('given_name', ''),
            'family_name': row.get('family_name', ''),
            'mds_score': mds['mds_score'],
            'mds_missing': ', '.join(mds_missing) if mds_missing else '',
            'consent_score': consent['consent_score'],
            'consent_state': consent['consent_state'] if consent_available else 'N/A',
            'consent_issues': ' | '.join(consent['issues']),
            'pa_score': pa['pa_score'],
            'pa_required': pa['pa_required'],
            'pa_present': pa['pa_present'],
            'pa_issues': ' | '.join(pa['issues']),
        })
    gov_df = pd.DataFrame(gov_rows)
    gov_meta = {
        'available': True,
        'consent_available': consent_available,
        'pa_available': pa_available_here and PA_AVAILABLE,
        'mean_mds': float(gov_df['mds_score'].mean()),
        'below_80': int((gov_df['mds_score'] < 0.80).sum()),
        'below_60': int((gov_df['mds_score'] < 0.60).sum()),
        'consent_granted': int((gov_df['consent_state'] == 'granted').sum()),
        'consent_restricted': int((gov_df['consent_state'] == 'restricted').sum()),
        'consent_blocked': int(gov_df['consent_state'].isin(['denied', 'withdrawn']).sum()),
        'consent_missing': int((gov_df['consent_state'] == 'missing').sum()),
        'mean_consent': float(gov_df['consent_score'].mean()),
        'pa_required': int(gov_df['pa_required'].sum()),
        'pa_missing': int(((gov_df['pa_required'] == True) & (gov_df['pa_present'] == False)).sum()),
        'pa_valid': int(((gov_df['pa_required'] == True) & (gov_df['pa_score'] >= 0.95)).sum()),
    }

    missing_canonical = [f for f in CANONICAL_FIELDS if f not in df.columns or (df[f].astype(str).str.strip() == '').all()]
    total_records = len(results_df)
    flagged_count = len(results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])])
    flag_rate = flagged_count / total_records if total_records else 0.0

    schema_report = {
        'input_columns': len(original_columns),
        'mapped': len(mapping),
        'unresolved': unresolved,
        'inferred': inferred,
        'missing_canonical': missing_canonical,
        'coding_available': coding_available,
        'drg_available': drg_available,
        'consent_available': consent_available,
        'pa_available': pa_available_here and PA_AVAILABLE,
        'looks_like_output': looks_like_output,
        'flag_rate': flag_rate,
        'flagged_count': flagged_count,
        'total_records': total_records,
        'original_names': mapping,
    }

    meta = {
        'total_raw': total_raw, 'missing_ids': missing_ids,
        'missing_dob': missing_dob, 'dup_ids': dup_ids,
        'total_normalized': total_normalized,
    }
    return results_df, meta, df, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema_report


# ============================================================
# Page header helper
# ============================================================
def page_header(title, subtitle):
    st.markdown(f'### {title}')
    st.caption(subtitle)
    st.divider()


# ============================================================
# Page: Dashboard
# ============================================================
def pg_dashboard():
    ui.hero('Dashboard')
    st.caption('Batch overview. Upload a CSV from the Batch Upload page to populate this view.')

    result = st.session_state.get('assessment')
    if result is None:
        ui.steps([
            ('Bring in patient records', 'Upload a CSV file, or paste live HL7 messages from your hospital system.'),
            ('Five identity checks run', 'Each record is scored on completeness, date validity, ID format, source trust and clashes with existing patients.'),
            ('Review what needs attention', 'Safe records link automatically. Risky ones are held for a person, with the reason spelled out.'),
        ])
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button('Run a demo batch (100 synthetic records)', type='primary', use_container_width=True):
                load_demo_batch()
                st.rerun()
        with b2:
            if st.button('Upload your own CSV  →', use_container_width=True):
                st.switch_page(PAGES['batch'])
        with b3:
            if st.button('Try an HL7 message  →', use_container_width=True):
                st.switch_page(PAGES['hl7'])
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

    ui.batch_header(st.session_state.get('batch_info'), st.session_state['region_name'], results_df)

    def _n(d):
        return int((results_df['decision'] == d).sum())

    urgent = [d for d in ('QUARANTINE', 'INSUFFICIENT_DATA') if _n(d) > 0]
    soft = [d for d in ('LINK_WITH_FLAG',) if _n(d) > 0]
    if urgent:
        n_urgent = sum(_n(d) for d in urgent)
        if st.button(f'Review the {n_urgent:,} record{"s" if n_urgent != 1 else ""} that need action  →', type='primary'):
            goto_flagged(urgent)
    elif soft:
        if st.button(f'Review the {_n("LINK_WITH_FLAG"):,} flagged records  →', type='primary'):
            goto_flagged(soft)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        ui.kpi('Total records', f'{len(results_df):,}', ui.TEAL, 'in this batch')
        if st.button('Summary report  →', key='go_report', use_container_width=True):
            st.switch_page(PAGES['report'])
    with c2:
        ui.kpi('Auto-linked', f"{_n('AUTO_LINK'):,}", ui.OK, 'trusted, no action')
        st.caption('Nothing to do here')
    with c3:
        ui.kpi('Flagged', f"{_n('LINK_WITH_FLAG'):,}", ui.WARN, 'review recommended')
        if st.button('Review  →', key='go_flag', use_container_width=True, disabled=_n('LINK_WITH_FLAG') == 0):
            goto_flagged(['LINK_WITH_FLAG'])
    with c4:
        ui.kpi('Quarantined', f"{_n('QUARANTINE'):,}", ui.BAD, 'hold from exchange')
        if st.button('Review  →', key='go_quar', use_container_width=True, disabled=_n('QUARANTINE') == 0):
            goto_flagged(['QUARANTINE'])
    with c5:
        ui.kpi('Insufficient data', f"{_n('INSUFFICIENT_DATA'):,}", ui.NEUTRAL, 'cannot be scored')
        if st.button('Review  →', key='go_insuf', use_container_width=True, disabled=_n('INSUFFICIENT_DATA') == 0):
            goto_flagged(['INSUFFICIENT_DATA'])

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('**Decision Breakdown**')
        dc = results_df['decision'].value_counts().reset_index()
        dc.columns = ['Decision', 'Count']
        dc['Decision'] = dc['Decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
        st.altair_chart(ui.decision_chart(dc, height=250), use_container_width=True)
    with col_b:
        st.markdown('**Facility Risk Profile**')
        fl = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])]
        if not fl.empty:
            fac = fl['source_facility'].replace('', '(unset)').value_counts().reset_index()
            fac.columns = ['Facility', 'Flagged Count']
            st.altair_chart(ui.bar_chart(fac, 'Flagged Count', 'Facility', color=ui.BAD, height=250,
                                         x_title='Flagged records'), use_container_width=True)
        else:
            st.info('No records were flagged.')

    st.markdown('**Dimension Scoring Averages**')
    dm = results_df[['dim_completeness', 'dim_temporal', 'dim_identity', 'dim_provenance', 'dim_cross_record']].mean().reset_index()
    dm.columns = ['Dimension', 'Average Score']
    dm['Dimension'] = ['Completeness', 'Temporal', 'Identity', 'Provenance', 'Cross-Record']
    st.altair_chart(ui.bar_chart(dm, 'Average Score', 'Dimension', color=ui.ACCENT, height=220,
                                 domain=[0, 1]), use_container_width=True)

    with st.expander('How to read this page'):
        st.markdown('**What each outcome means**')
        for key in ('AUTO_LINK', 'LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'):
            title, text = DECISION_MEANING[key]
            st.markdown(f'- **{ui.DECISION_LABELS[key]}** — {title}. {text}')
        st.markdown('**What the five scores mean** (1.00 is best)')
        st.markdown(
            '- **Completeness**: are name, ID and date of birth all present?\n'
            '- **Temporal**: is the date of birth believable?\n'
            '- **Identity**: does the ID follow the national format?\n'
            '- **Provenance**: did it come from a facility we trust?\n'
            '- **Cross-record**: does it clash with a patient already on file?'
        )


# ============================================================
# Page: HL7 Stream
# ============================================================
def _set_hl7(text, autorun=False, reset=False):
    st.session_state['hl7_text'] = text
    st.session_state['hl7_autorun'] = autorun
    if reset:
        st.session_state['hl7_history'] = []
        st.session_state['hl7_validator'] = None


def pg_hl7():
    ui.hero('HL7 Stream')
    st.caption('Paste one or more HL7 v2 ADT messages below. Each message is parsed, scored against the five identity dimensions, and routed. The session maintains a persistent validator, so a second message with the same identifier triggers a collision.')

    st.info('In production, messages arrive continuously from the hospital interface engine via the FastAPI endpoint (`/assess-hl7`). This page demonstrates the same parser and scoring logic on pasted input.')

    default_msg = (
        'MSH|^~\\&|HIS|CLEVELAND CLINIC ABU DHABI|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r'
        'EVN|A04|20240110120000\r'
        'PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M\r'
        'PV1|1|O'
    )

    if 'hl7_text' not in st.session_state:
        st.session_state['hl7_text'] = default_msg

    with st.expander('What is an HL7 message?'):
        st.markdown(
            'HL7 v2 is the format hospital systems use to tell each other about patient events such as registrations and admissions. '
            'Each line is a *segment*. The **PID** line carries who the patient is (ID, name, date of birth, gender) and the **MSH** line says '
            'which facility sent it. This tool reads those fields and scores them exactly like a CSV row.'
        )

    st.markdown('**Try a ready-made example**')
    d1, d2, d3, d4 = st.columns(4)
    d1.button('Clean message', use_container_width=True, on_click=_set_hl7, args=(SAMPLE_HL7_CLEAN, True, False))
    d2.button('ID collision', use_container_width=True, on_click=_set_hl7, args=(SAMPLE_HL7_CLEAN + '\n\n' + SAMPLE_HL7_COLLISION, True, True),
              help='Sends a patient, then a different person using the same ID.')
    d3.button('Bad ID, unknown clinic', use_container_width=True, on_click=_set_hl7, args=(SAMPLE_HL7_BAD, True, False))
    d4.button('Full demo (3 messages)', use_container_width=True, type='primary', on_click=_set_hl7,
              args=(SAMPLE_HL7_CLEAN + '\n\n' + SAMPLE_HL7_COLLISION + '\n\n' + SAMPLE_HL7_BAD, True, True))

    if st.button('Reset session (clears history and remembered patients)', use_container_width=False):
        st.session_state['hl7_history'] = []
        st.session_state['hl7_validator'] = None
        st.success('Session cleared.')

    hl7_input = st.text_area(
        'HL7 v2 message(s). Separate multiple messages with a blank line.',
        height=220,
        key='hl7_text',
    )

    auto_run = st.session_state.pop('hl7_autorun', False)
    run_clicked = st.button('Parse and assess', type='primary')
    if run_clicked or auto_run:
        # Split on blank lines to support multiple messages
        raw_msgs = [m.strip() for m in re.split(r'\n\s*\n', hl7_input) if m.strip()]
        if not raw_msgs:
            st.error('No message found.')
            return

        config = _get_config()
        color = _get_color()

        # Build a local validator per session if not present
        if st.session_state['hl7_validator'] is None:
            class _V:
                def __init__(self):
                    self.identifier_index = {}
                    self.name_dob_index = {}
                def add_record(self, r):
                    if getattr(r, 'emirates_id', None):
                        self.identifier_index.setdefault(r.emirates_id, set()).add(r.canonical_id)
                    key = (
                        (getattr(r, 'given_name', '') or '').strip().lower(),
                        (getattr(r, 'family_name', '') or '').strip().lower(),
                        getattr(r, 'date_of_birth', '') or '',
                    )
                    if key != ('', '', ''):
                        self.name_dob_index.setdefault(key, set()).add(r.canonical_id)
                def validate(self, r):
                    eid = getattr(r, 'emirates_id', None)
                    if eid and eid in self.identifier_index:
                        if r.canonical_id not in self.identifier_index[eid]:
                            return 0.0
                    key = (
                        (getattr(r, 'given_name', '') or '').strip().lower(),
                        (getattr(r, 'family_name', '') or '').strip().lower(),
                        getattr(r, 'date_of_birth', '') or '',
                    )
                    if key != ('', '', '') and key in self.name_dob_index:
                        if r.canonical_id not in self.name_dob_index[key]:
                            return 0.5
                    return 1.0
            st.session_state['hl7_validator'] = _V()

        validator = st.session_state['hl7_validator']

        from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure

        for i, msg in enumerate(raw_msgs):
            st.markdown(f'---')
            st.markdown(f'### Message {i + 1}')

            ok, issues = validate_hl7_structure(msg)
            if not ok:
                st.error(f'Invalid HL7 structure: {"; ".join(issues)}')
                continue

            parsed = parse_hl7_message(msg)

            with st.expander('Parsed fields', expanded=False):
                for label, value in [
                    ('Emirates ID', parsed.get('emirates_id')),
                    ('Given Name', parsed.get('given_name')),
                    ('Family Name', parsed.get('family_name')),
                    ('Gender', parsed.get('gender')),
                    ('Date of Birth', parsed.get('date_of_birth')),
                    ('Source Facility', parsed.get('source_facility')),
                    ('Canonical ID', parsed.get('canonical_id')),
                    ('Encounter Type', parsed.get('encounter_type')),
                ]:
                    st.markdown(f'- **{label}:** {value if value else "_(empty)_"}')

            rec = Record(
                emirates_id=normalize_id(parsed.get('emirates_id')),
                given_name=normalize_text(parsed.get('given_name')),
                family_name=normalize_text(parsed.get('family_name')),
                date_of_birth=str(parsed.get('date_of_birth', '')).strip()[:10],
                nationality=normalize_nationality(parsed.get('nationality')),
                source_facility=normalize_text(parsed.get('source_facility')),
                canonical_id=parsed.get('canonical_id') or f'MSG_{i+1}',
            )

            required = config['required_fields']
            present = sum(1 for f in required if getattr(rec, f, None))
            completeness = round(present / len(required), 2) if required else 1.0

            try:
                year = int(rec.date_of_birth[:4])
                temporal = 1.0 if 1900 <= year <= 2025 else 0.3
            except (ValueError, TypeError):
                temporal = 0.0

            if not rec.emirates_id:
                identity = 0.0
            elif re.match(config['id_pattern'], rec.emirates_id):
                identity = 1.0
            else:
                identity = 0.3

            if not rec.source_facility:
                provenance = 0.0
            elif rec.source_facility in config['trusted_facilities']:
                provenance = 1.0
            else:
                provenance = 0.7

            dims = {
                'completeness': completeness,
                'temporal': temporal,
                'identity': identity,
                'provenance': provenance,
                'cross_record': validator.validate(rec),
            }
            score = compute_trust_score(**dims)
            decision = route_decision_hard(score, dims['cross_record'])

            cc1, cc2 = st.columns(2)
            cc1.metric('Trust Score', f'{score:.3f}')
            cc2.metric('Decision', ui.DECISION_LABELS.get(decision, decision))
            m_title, m_text = DECISION_MEANING.get(decision, ('', ''))
            ui.callout(m_title, m_text, ui.DECISION_COLORS.get(decision, ui.TEAL))

            if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
                if dims['cross_record'] == 0.0:
                    st.error(f'Identifier collision: {config["id_label"]} is already registered to a different patient.')
                else:
                    st.warning(f'Routed for review. Weakest dimension: {min(dims, key=dims.get)}.')

            with st.expander('Dimension scores'):
                for label, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                                   ('Identity', 'identity'), ('Provenance', 'provenance'),
                                   ('Cross-Record', 'cross_record')]:
                    render_dimension_bar(label, dims[key], color)

            validator.add_record(rec)
            st.session_state['hl7_history'].append({
                'msg_index': i + 1,
                'canonical_id': rec.canonical_id,
                'emirates_id': rec.emirates_id,
                'name': f'{rec.given_name} {rec.family_name}',
                'decision': decision,
                'trust_score': round(score, 3),
            })

        if st.session_state['hl7_history']:
            st.divider()
            st.markdown('### Session History')
            st.dataframe(pd.DataFrame(st.session_state['hl7_history']), use_container_width=True)


# ============================================================
# Page: Batch Upload (CSV)
# ============================================================
def pg_batch():
    ui.hero('Batch Upload')
    st.caption('Upload a CSV of patient records. The schema mapper handles arbitrary column names, and the pipeline processes whatever identity, clinical, and governance fields are present.')

    st.markdown('**Quick start**')
    if st.button('Run a demo batch now (100 synthetic records)', type='primary'):
        load_demo_batch()
        st.switch_page(PAGES['dashboard'])

    st.divider()
    st.markdown('**Generate a sample**')
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button(f'Generate {st.session_state["region_name"]} Sample (100 records)'):
            sample_df = generate_sample(st.session_state['region_name'], n=100)
            st.download_button(
                label='Download Generated Sample',
                data=sample_df.to_csv(index=False).encode('utf-8'),
                file_name=f'sample_{st.session_state["region_name"].split()[0].lower()}_100.csv',
                mime='text/csv',
            )

    st.divider()
    st.markdown('**Upload your own**')
    uploaded_file = st.file_uploader('CSV file', type=['csv'])

    if uploaded_file is None:
        return

    if st.session_state['uploaded_name'] != uploaded_file.name:
        st.session_state['assessment'] = None
        st.session_state['uploaded_name'] = uploaded_file.name
        st.session_state['batch_info'] = {
            'name': uploaded_file.name,
            'processed_at': datetime.now().strftime('%d %b %Y, %H:%M'),
        }

    with st.spinner('Running trust assessment...'):
        result = run_assessment(uploaded_file.getvalue(), st.session_state['region_name'])

    if result[0] is None:
        st.error('The uploaded file has no columns.')
        return

    st.session_state['assessment'] = result
    st.success(f'Processed. Open **Dashboard** or **Reports** in the sidebar to view results.')

    schema = result[9]

    if schema['looks_like_output']:
        st.error('This file appears to be a scored export from another system, not raw patient records. It contains output fields (Decision, MDS_Score, etc.) but no name columns.')

    if schema['flag_rate'] >= 0.90 and schema['total_records'] > 20:
        st.warning(f'{schema["flag_rate"]*100:.0f}% of records were flagged ({schema["flagged_count"]} of {schema["total_records"]}). This usually means the file is missing critical identity columns.')

    with st.expander('Schema Analysis', expanded=True):
        st.markdown(f'**Input:** {schema["input_columns"]} columns · **Mapped:** {schema["mapped"]} columns')
        if schema['inferred']:
            st.markdown('**Auto-detected by content:**')
            for item in schema['inferred']:
                st.markdown(f"- `{item['column']}` → `{item['field']}`")
        if schema['unresolved']:
            st.markdown(f'**Unrecognized columns:** ' + ', '.join(f'`{c}`' for c in schema['unresolved']))
        if schema['missing_canonical']:
            core = [f for f in schema['missing_canonical'] if f in ('emirates_id', 'given_name', 'family_name', 'date_of_birth')]
            if core:
                st.markdown(f'**Core identity fields missing:** ' + ', '.join(f'`{f}`' for f in core))


# ============================================================
# Page: Flagged Records
# ============================================================
def pg_flagged():
    ui.hero('Flagged Records')
    st.caption('Records routed for manual review.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result
    color = _get_color()

    flagged = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])].copy()
    if flagged.empty:
        st.success('No flagged records.')
        return

    pri = {'INSUFFICIENT_DATA': 0, 'QUARANTINE': 1, 'LINK_WITH_FLAG': 2}
    flagged['_p'] = flagged['decision'].map(pri)
    flagged = flagged.sort_values(['_p', 'trust_score']).drop(columns='_p')

    io_opt = sorted(flagged['primary_issue'].unique().tolist())
    d_opt = sorted(flagged['decision'].unique().tolist())
    preset = st.session_state.pop('flag_preset', None)
    if preset is not None:
        st.session_state['flag_dec_sel'] = [d for d in preset if d in d_opt] or d_opt
        st.session_state['flag_issue_sel'] = io_opt
    st.session_state['flag_dec_sel'] = [d for d in st.session_state.get('flag_dec_sel', d_opt) if d in d_opt] or d_opt
    st.session_state['flag_issue_sel'] = [i for i in st.session_state.get('flag_issue_sel', io_opt) if i in io_opt] or io_opt

    fc1, fc2 = st.columns(2)
    with fc1:
        sel_issues = st.multiselect('Issue type', options=io_opt, key='flag_issue_sel')
    with fc2:
        sel_dec = st.multiselect('Outcome', options=d_opt, key='flag_dec_sel',
                                 format_func=lambda d: ui.DECISION_LABELS.get(d, d))

    filtered = flagged[flagged['primary_issue'].isin(sel_issues) & flagged['decision'].isin(sel_dec)]
    st.caption(f'Showing {len(filtered)} of {len(flagged)} records.')

    with st.expander('Bulk Actions'):
        st.code('\n'.join(filtered['canonical_id'].astype(str).tolist()), language=None)

    STEP = 100
    if 'show_count' not in st.session_state:
        st.session_state.show_count = STEP
    to_render = filtered.head(st.session_state.show_count)

    for _, row in to_render.iterrows():
        with st.expander(f'{row["canonical_id"]} · {row["given_name"] or "(no name)"} {row["family_name"]} · {ui.DECISION_LABELS.get(row["decision"], row["decision"])}'):
            st.markdown(ui.badge(row['decision']), unsafe_allow_html=True)
            st.code(row['canonical_id'], language=None)
            st.write(f'**Trust Score:** {row["trust_score"]}')
            st.write(f'**Primary Issue:** {row["primary_issue"]}')
            st.info(f'{row["explanation"]}')
            st.markdown(f'**What to do:** {ISSUE_ACTION.get(row["primary_issue"], "Review the record with the source facility.")}')
            for lbl, col in [('Completeness', 'dim_completeness'), ('Temporal', 'dim_temporal'),
                             ('Identity', 'dim_identity'), ('Provenance', 'dim_provenance'),
                             ('Cross-Record', 'dim_cross_record')]:
                render_dimension_bar(lbl, row[col], color)

    if len(filtered) > st.session_state.show_count:
        if st.button('Load more'):
            st.session_state.show_count += STEP
            st.rerun()

    st.download_button(
        label='Download Filtered Records (CSV)',
        data=filtered.to_csv(index=False).encode('utf-8'),
        file_name='flagged_records.csv', mime='text/csv',
    )


# ============================================================
# Page: Coding Coherence
# ============================================================
def pg_coding():
    ui.hero('Coding Coherence')
    st.caption('Rule-based checks on diagnosis codes, procedure codes, and episode timelines.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

    if not clinical_meta.get('available'):
        st.info('This check could not run — the uploaded file has no populated `diagnosis_code` or `procedure_code` column.')
        return

    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric('ICD Issues', clinical_meta['icd_issues'])
    cc2.metric('ICD-CPT Mismatches', clinical_meta['icd_cpt_mismatches'])
    cc3.metric('Timeline Errors', clinical_meta['timeline_errors'])
    cc4.metric('Triage-Cost Anomalies', clinical_meta['triage_anomalies'])

    issue_counts = pd.DataFrame({
        'Issue': ['ICD Issues', 'ICD-CPT Mismatches', 'Timeline Errors', 'Triage-Cost Anomalies', 'Duplicate Episodes'],
        'Count': [
            clinical_meta['icd_issues'], clinical_meta['icd_cpt_mismatches'],
            clinical_meta['timeline_errors'], clinical_meta['triage_anomalies'],
            len(clinical_meta['duplicate_episodes']),
        ],
    })
    st.altair_chart(ui.bar_chart(issue_counts, 'Count', 'Issue', color=ui.ACCENT, height=240),
                    use_container_width=True)

    problematic = clinical_df[
        (clinical_df['icd_exists'] < 1.0) | (clinical_df['icd_cpt_match'] == 0.0) |
        (clinical_df['episode_timeline'] == 0.0) | (clinical_df['triage_cost'] == 0.0) |
        (clinical_df['admission_after_dob'] == 0.0)
    ].copy()

    if problematic.empty:
        st.success('No coding issues detected.')
    else:
        st.dataframe(problematic, use_container_width=True)
        st.download_button(
            label='Download Coding Coherence Report (CSV)',
            data=problematic.to_csv(index=False).encode('utf-8'),
            file_name='coding_coherence_report.csv', mime='text/csv',
        )


# ============================================================
# Page: DRG Readiness
# ============================================================
def pg_drg():
    ui.hero('DRG Readiness')
    st.caption('Validates whether inpatient records have every input the IR-DRG grouper needs.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

    if not drg_meta.get('available'):
        st.info('This check could not run — the uploaded file has no populated `encounter_type` column.')
        return

    d1, d2, d3, d4 = st.columns(4)
    d1.metric('Inpatient Records', drg_meta['inpatient_count'])
    d2.metric('Fully Ready', drg_meta['fully_ready'])
    d3.metric('Partial', drg_meta['partial'])
    d4.metric('Not Ready', drg_meta['not_ready'])

    readiness_counts = pd.DataFrame({
        'Status': ['Fully Ready', 'Partial', 'Not Ready'],
        'Count': [drg_meta['fully_ready'], drg_meta['partial'], drg_meta['not_ready']],
    })
    st.altair_chart(ui.bar_chart(readiness_counts, 'Count', 'Status', color=ui.ACCENT, height=180),
                    use_container_width=True)

    missing_counter = {}
    for m in drg_df['missing_inputs']:
        if m:
            for field in m.split(', '):
                missing_counter[field] = missing_counter.get(field, 0) + 1
    if missing_counter:
        miss_df = pd.DataFrame([
            {'Field': k, 'Records Missing': v}
            for k, v in sorted(missing_counter.items(), key=lambda x: -x[1])
        ])
        st.markdown('**Most Common Missing Inputs**')
        st.altair_chart(ui.bar_chart(miss_df, 'Records Missing', 'Field', color=ui.WARN, height=240),
                        use_container_width=True)

    problematic_drg = drg_df[
        (drg_df['applicable'] == True) &
        ((drg_df['drg_readiness_score'] < 1.0) | (drg_df['issues'] != ''))
    ].copy()

    if not problematic_drg.empty:
        st.dataframe(problematic_drg, use_container_width=True)
        st.download_button(
            label='Download DRG Readiness Report (CSV)',
            data=problematic_drg.to_csv(index=False).encode('utf-8'),
            file_name='drg_readiness_report.csv', mime='text/csv',
        )


# ============================================================
# Page: Data Governance
# ============================================================
def pg_gov():
    ui.hero('Data Governance')
    st.caption('Minimum Data Set completeness, consent compliance, and prior-authorization.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

    g1, g2, g3, g4 = st.columns(4)
    g1.metric('Mean MDS Score', f'{gov_meta["mean_mds"]:.3f}')
    g2.metric('Below 80% MDS', gov_meta['below_80'])
    g3.metric('Consent Blocked', gov_meta['consent_blocked'] if gov_meta['consent_available'] else 'N/A')
    g4.metric('Consent Missing', gov_meta['consent_missing'] if gov_meta['consent_available'] else 'N/A')

    if gov_meta['consent_available'] and gov_meta['consent_blocked'] > 0:
        st.error(f'{gov_meta["consent_blocked"]} record(s) have denied or withdrawn consent — these must not be shared without further review.')

    if gov_meta['pa_available'] and gov_meta['pa_missing'] > 0:
        st.error(f'{gov_meta["pa_missing"]} claim(s) will be rejected: procedure requires pre-authorization but no PA reference is on file.')

    st.divider()

    mds_buckets = pd.DataFrame({
        'Bucket': ['Perfect (1.0)', 'Good (0.8-0.99)', 'Partial (0.6-0.79)', 'Poor (<0.6)'],
        'Count': [
            int((gov_df['mds_score'] >= 0.999).sum()),
            int(((gov_df['mds_score'] >= 0.80) & (gov_df['mds_score'] < 0.999)).sum()),
            int(((gov_df['mds_score'] >= 0.60) & (gov_df['mds_score'] < 0.80)).sum()),
            int((gov_df['mds_score'] < 0.60).sum()),
        ],
    })
    st.markdown('**MDS Completeness Distribution**')
    st.altair_chart(ui.bar_chart(mds_buckets, 'Count', 'Bucket', color=ui.ACCENT, height=200),
                    use_container_width=True)

    problematic_gov = gov_df[
        (gov_df['mds_score'] < 0.80) |
        (gov_df['consent_state'].isin(['denied', 'withdrawn', 'missing'])) |
        (gov_df['consent_issues'] != '') |
        ((gov_df['pa_required'] == True) & (gov_df['pa_present'] == False))
    ].copy()

    if not problematic_gov.empty:
        st.dataframe(problematic_gov, use_container_width=True)
        st.download_button(
            label='Download Governance Report (CSV)',
            data=problematic_gov.to_csv(index=False).encode('utf-8'),
            file_name='governance_report.csv', mime='text/csv',
        )


# ============================================================
# Page: Audit Trail
# ============================================================
def pg_audit():
    ui.hero('Audit Trail')
    st.caption('A permanent record of every decision this tool made: what was decided, why, and proof that nobody has changed it since.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Run the demo batch from the **Dashboard**, or go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

    log_exists = os.path.exists(AUDIT_LOG_PATH)
    n_entries = 0
    chain_ok, chain_msg = None, 'No log file found yet.'
    if log_exists:
        with open(AUDIT_LOG_PATH, 'rb') as f:
            n_entries = sum(1 for _ in f)
        try:
            chain_ok, chain_msg = verify_chain(AUDIT_LOG_PATH)
        except Exception as ex:
            chain_ok, chain_msg = False, str(ex)

    k1, k2, k3 = st.columns(3)
    with k1:
        ui.kpi('Decisions logged', f'{n_entries:,}', ui.TEAL, 'entries in the log')
    with k2:
        if chain_ok is None:
            ui.kpi('Integrity check', 'Not run', ui.NEUTRAL, 'no log yet')
        elif chain_ok:
            ui.kpi('Integrity check', 'Verified', ui.OK, 'no entry has been altered')
        else:
            ui.kpi('Integrity check', 'Broken', ui.BAD, 'the log was modified')
    with k3:
        ui.kpi('Scoring version', 'v0.7.0-demo', ui.TEAL, 'thresholds 0.75 / 0.45')
    if chain_msg:
        st.caption(f'Integrity check result: {chain_msg}')

    st.markdown('### How the tamper-evidence works')
    ui.steps([
        ('Every decision is written down', 'The score, the outcome and the reason are saved the moment a record is assessed.'),
        ('Each entry is linked to the one before', 'Every entry carries a digital fingerprint of the previous one, like numbered pages stitched into a book.'),
        ('Any edit breaks the chain', 'Change, remove or reorder a single entry and the fingerprints after it stop matching. The check above catches it.'),
    ])

    st.markdown('### Look up a record')
    q = st.text_input('Patient ID or name', placeholder='Type a record ID or part of a name', label_visibility='collapsed')
    if q.strip():
        hay = (results_df['canonical_id'].astype(str) + ' ' + results_df['given_name'].astype(str) + ' '
               + results_df['family_name'].astype(str)).str.lower()
        hits = results_df[hay.str.contains(q.strip().lower(), regex=False)]
        if hits.empty:
            st.warning('No matching record in this batch.')
        else:
            st.caption(f'{len(hits)} match{"es" if len(hits) != 1 else ""}, showing up to 10.')
            for _, r in hits.head(10).iterrows():
                with st.expander(f'{r["canonical_id"]} · {r["given_name"]} {r["family_name"]}'):
                    st.markdown(ui.badge(r['decision']), unsafe_allow_html=True)
                    st.write(f'**Trust score:** {r["trust_score"]:.3f}')
                    st.write('**What it means:** ' + DECISION_MEANING.get(r['decision'], ('', ''))[1])
                    st.info(r['explanation'])
                    if r['primary_issue'] != 'None':
                        st.write('**What to do:** ' + ISSUE_ACTION.get(r['primary_issue'], 'Review the record with the source facility.'))

    st.markdown('### Decision log')
    log_df = results_df.copy()
    log_df['Patient'] = (log_df['given_name'].astype(str) + ' ' + log_df['family_name'].astype(str)).str.strip()
    log_df['Outcome'] = log_df['decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
    all_outcomes = list(ui.DECISION_LABELS.values())
    sel = st.multiselect('Show outcomes', options=all_outcomes, default=all_outcomes)
    view = log_df[log_df['Outcome'].isin(sel)][['canonical_id', 'Patient', 'source_facility', 'Outcome', 'trust_score', 'primary_issue']].rename(
        columns={'canonical_id': 'Record ID', 'source_facility': 'Source facility', 'trust_score': 'Trust score', 'primary_issue': 'Main issue'})
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={'Trust score': st.column_config.ProgressColumn('Trust score', min_value=0.0, max_value=1.0, format='%.2f')},
    )
    st.download_button(
        label='Download decision log (CSV)',
        data=view.to_csv(index=False).encode('utf-8'),
        file_name='decision_log.csv', mime='text/csv',
    )

    if log_exists:
        with st.expander('Technical export (for auditors and IT)'):
            st.caption('The raw tamper-evident log, one JSON entry per line.')
            with open(AUDIT_LOG_PATH, 'rb') as f:
                st.download_button(label='Download raw audit log (JSONL)', data=f.read(),
                                   file_name='audit_log.jsonl', mime='application/jsonl')


# ============================================================
# Page: Standardization
# ============================================================
def pg_standardization():
    ui.hero('Standardization')
    st.caption('What was cleaned before scoring, and the export of the standardized file.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result
    region = _get_config()

    st.metric('Records Standardized', meta['total_normalized'])

    export_cols = ['canonical_id', 'emirates_id', 'given_name', 'family_name',
                   'date_of_birth', 'gender', 'nationality', 'source_facility', 'registration_date']
    export_cols = [c for c in export_cols if c in df_meta.columns]
    cleaned = df_meta[export_cols].copy()
    original_names = schema.get('original_names', {})
    cleaned = cleaned.rename(columns=original_names)

    st.download_button(
        label='Download Cleaned & Standardized CSV',
        data=cleaned.to_csv(index=False).encode('utf-8'),
        file_name=f'standardized_{st.session_state["region_name"].split()[0].lower()}.csv',
        mime='text/csv',
    )

    if meta['total_normalized'] > 0:
        rows = []
        for i, r in df_meta.iterrows():
            ch = []
            if r['_changed_name']:
                ch.append(f'Name: {r["_orig_given"]} {r["_orig_family"]} → {r["given_name"]} {r["family_name"]}')
            if r['_changed_dob']:
                ch.append(f'DOB: {r["_orig_dob"]} → {r["date_of_birth"]}')
            if r['_changed_id']:
                ch.append(f'ID: {r["_orig_id"]} → {r["emirates_id"]}')
            if r['_changed_gender']:
                ch.append(f'Gender: {r["_orig_gender"]} → {r["gender"]}')
            if r['_changed_nationality']:
                ch.append(f'Nationality: {r["_orig_nationality"]} → {r["nationality"]}')
            if ch:
                rows.append({'canonical_id': r.get('canonical_id', f'ROW_{i}'), 'Changes': ' | '.join(ch)})
        cdf = pd.DataFrame(rows)
        st.dataframe(cdf.head(200), use_container_width=True)
        st.download_button(
            label='Download Normalization Log (CSV)',
            data=cdf.to_csv(index=False).encode('utf-8'),
            file_name='normalization_log.csv', mime='text/csv',
        )


# ============================================================
# Page: Configuration
# ============================================================
def pg_config():
    ui.hero('Configuration')
    st.caption('Region profile. Changes apply immediately across the app.')

    selected_region = st.selectbox(
        'Region Profile',
        list(REGION_PROFILES.keys()),
        index=list(REGION_PROFILES.keys()).index(st.session_state['region_name']),
        help='Swaps the ID format, required fields, DOB range, and trusted facility list.',
    )
    if selected_region != st.session_state['region_name']:
        st.session_state['region_name'] = selected_region
        st.session_state['assessment'] = None
        st.session_state['uploaded_name'] = None
        st.success(f'Region switched to {selected_region}. Reload your file to re-score.')

    st.divider()
    st.markdown('**Current region rules**')
    region = _get_config()
    st.markdown(f'- Identifier field: **{region["id_label"]}**')
    st.markdown(f'- ID pattern: `{region["id_pattern"]}`')
    st.markdown(f'- Regulatory body: **{region["regulatory_body"]}**')
    st.markdown(f'- Trusted facilities: {len(region["trusted_facilities"])}')


# ============================================================
# Page: About
# ============================================================
def pg_about():
    ui.hero('About')

    st.markdown('''
### What this tool does

A pre-submission trust gate for patient records in a health information exchange.
Every incoming record is scored across five identity dimensions and routed to
one of four outcomes. It does not merge records, resolve collisions, or
auto-correct data. It identifies problems, explains them, and hands control
to a human.

### The five dimensions

| Dimension | Weight | Check |
|---|---|---|
| Completeness | 0.20 | Required identity fields present |
| Temporal Validity | 0.15 | Plausible date of birth |
| Identity Consistency | 0.20 | ID format matches region standard |
| Provenance | 0.15 | Trusted source facility |
| Cross-Record Consistency | 0.30 | Collision with existing patient |

### Module checks

- **Coding Coherence** — ICD validity, ICD-CPT match, episode timeline, triage-cost anomaly
- **DRG Readiness** — mandatory inputs for IR-DRG grouping
- **MDS Completeness** — NABIDH/Malaffi minimum data set
- **Consent Compliance** — granted / restricted / denied / withdrawn
- **Prior-Authorization** — DHA/DOH pre-auth presence

### Scoring configuration notice

This demo uses a revised scoring configuration, tuned separately from the
published paper's validated configuration.

- **Composite formula:** weighted sum × (0.4 + 0.6 × weakest dimension score)
- **Demo thresholds (Trust-Hard variant):** auto-link ≥ 0.75 · flag 0.45–0.75 · quarantine < 0.45 · collision override at cross-record = 0.0
- **Paper's validated thresholds (Trust-Soft, §3.7):** auto-link ≥ 0.85 · flag 0.50–0.85 · quarantine < 0.50 · no collision override

The demo values were tuned for realistic flag rates on messy data. A
hospital pilot should re-derive both using the paper's methodology.

### Deployment

- **Batch path:** CSV upload for retrospective analysis and pre-pilot proof of concept.
- **Real-time path:** FastAPI service (`app.py`) with `/assess-hl7` endpoint. Deployed as a Docker container inside hospital infrastructure. Reads HL7 v2 ADT messages directly from the interface engine.

No patient data leaves the hospital network in production.

### Privacy

This demo uses synthetic data only. Do not upload real patient health
information.
    ''')


# ============================================================
# Page: Summary Report (printable)
# ============================================================
def pg_report():
    ui.hero('Summary Report')
    st.caption('A one-page report for the current batch, for data quality review and sign-off. Download it and print to PDF from your browser.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to **Analyze → Batch Upload**.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result
    info = st.session_state.get('batch_info')
    report_html = ui.build_report_html(info, st.session_state['region_name'], _get_config(),
                                       results_df, schema, clinical_meta, drg_meta, gov_meta)

    st.download_button(
        label='Download report (HTML, print to PDF)',
        data=report_html.encode('utf-8'),
        file_name=f'data_quality_report_{datetime.now().strftime("%Y%m%d_%H%M")}.html',
        mime='text/html',
        type='primary',
    )
    import streamlit.components.v1 as components
    components.html(report_html, height=1100, scrolling=True)


# ============================================================
# Router
# ============================================================
PAGES = {
    'dashboard': st.Page(pg_dashboard, title='Dashboard', icon=':material/dashboard:', default=True),
    'hl7': st.Page(pg_hl7, title='HL7 Stream', icon=':material/sensors:'),
    'batch': st.Page(pg_batch, title='Batch Upload', icon=':material/upload_file:'),
    'report': st.Page(pg_report, title='Summary Report', icon=':material/description:'),
    'flagged': st.Page(pg_flagged, title='Flagged Records', icon=':material/flag:'),
    'coding': st.Page(pg_coding, title='Coding Coherence', icon=':material/stethoscope:'),
    'drg': st.Page(pg_drg, title='DRG Readiness', icon=':material/request_quote:'),
    'gov': st.Page(pg_gov, title='Data Governance', icon=':material/shield:'),
    'audit': st.Page(pg_audit, title='Audit Trail', icon=':material/receipt_long:'),
    'std': st.Page(pg_standardization, title='Standardization', icon=':material/cleaning_services:'),
    'config': st.Page(pg_config, title='Configuration', icon=':material/settings:'),
    'about': st.Page(pg_about, title='About', icon=':material/info:'),
}

pages = {
    'Overview': [PAGES['dashboard']],
    'Analyze': [PAGES['hl7'], PAGES['batch']],
    'Reports': [PAGES['report'], PAGES['flagged'], PAGES['coding'], PAGES['drg'], PAGES['gov']],
    'Compliance': [PAGES['audit'], PAGES['std']],
    'Settings': [PAGES['config'], PAGES['about']],
}

# Sidebar branding
with st.sidebar:
    ui.sidebar_brand(st.session_state['region_name'])
    ui.sidebar_note()

pg = st.navigation(pages)
pg.run()

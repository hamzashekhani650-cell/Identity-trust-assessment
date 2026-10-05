"""
UI theme for the Identity Trust Assessment app.
Clinical-grade look: light canvas, navy sidebar, white cards, one accent colour,
status colours used only where they carry meaning (pass / review / fail).
"""
import altair as alt
import streamlit as st

NAVY = '#0F2A43'
ACCENT = '#1F5FA8'
INK = '#1B2733'
MUTED = '#5B6B7F'
LINE = '#E3E8EF'
CANVAS = '#F4F6F9'

OK = '#2E7D5B'
WARN = '#C77700'
BAD = '#B3261E'
NEUTRAL = '#6B7A8C'

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

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {{
    font-family: 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif;
    color: {INK};
}}
.stApp {{ background: {CANVAS}; }}

/* Chrome */
#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}
.block-container {{ padding-top: 2rem; padding-bottom: 3rem; max-width: 1280px; }}

/* Headings */
h1 {{ font-size: 1.65rem !important; font-weight: 650 !important; color: {NAVY};
     letter-spacing: -0.01em; padding-bottom: 0.15rem !important; }}
h2, h3 {{ color: {NAVY}; font-weight: 600 !important; letter-spacing: -0.005em; }}
h3 {{ font-size: 1.05rem !important; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; font-size: 0.9rem; }}
hr {{ border-color: {LINE} !important; margin: 1.25rem 0 !important; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: {NAVY}; border-right: none; }}
[data-testid="stSidebar"] * {{ color: #D5DFEA; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {{ opacity: .25; }}
[data-testid="stSidebarNav"] span[data-testid="stSidebarNavLinkContainer"] {{ gap: .25rem; }}
[data-testid="stSidebarNav"] a {{
    border-radius: 6px; padding: .35rem .6rem; font-size: .92rem; font-weight: 500;
}}
[data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,.07); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: rgba(255,255,255,.14); color: #fff; font-weight: 600;
}}
[data-testid="stSidebarNav"] li > div > span,
[data-testid="stSidebarNav"] header {{
    text-transform: uppercase; font-size: .68rem !important; letter-spacing: .09em;
    color: #8CA3BD !important; font-weight: 600;
}}
.brand {{ padding: .4rem .2rem 1rem; border-bottom: 1px solid rgba(255,255,255,.12); margin-bottom: .5rem; }}
.brand .t {{ color: #fff; font-weight: 650; font-size: 1.05rem; letter-spacing: -0.01em; }}
.brand .s {{ color: #8CA3BD; font-size: .75rem; margin-top: 2px; }}
.regionchip {{ display:inline-block; margin-top:.6rem; padding:2px 10px; border-radius:999px;
    background: rgba(255,255,255,.1); color:#fff !important; font-size:.75rem; font-weight:500; }}

/* KPI cards */
[data-testid="stMetric"] {{
    background: #fff; border: 1px solid {LINE}; border-left: 4px solid {ACCENT};
    border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(15,42,67,.04);
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .78rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em; }}
[data-testid="stMetricValue"] {{ color: {NAVY}; font-weight: 650; font-size: 1.7rem; }}

/* Buttons */
.stButton > button, .stDownloadButton > button {{
    border-radius: 6px; font-weight: 550; border: 1px solid #C9D3DF; background: #fff; color: {NAVY};
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
.stButton > button[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; color: #fff; }}
.stButton > button[kind="primary"]:hover {{ background: #184C87; color: #fff; }}

/* Containers */
[data-testid="stExpander"] {{ background: #fff; border: 1px solid {LINE} !important; border-radius: 8px; }}
[data-testid="stExpander"] summary {{ font-weight: 550; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 8px; overflow: hidden; }}
[data-testid="stFileUploader"] section {{ background: #fff; border: 1.5px dashed #B8C4D2; border-radius: 8px; }}
[data-testid="stAlert"] {{ border-radius: 8px; border: 1px solid {LINE}; }}
.stTextArea textarea {{ font-family: 'JetBrains Mono', Consolas, monospace; font-size: .85rem; }}

/* Components */
.card {{ background:#fff; border:1px solid {LINE}; border-radius:8px; padding:16px 18px;
    box-shadow:0 1px 2px rgba(15,42,67,.04); margin-bottom:12px; }}
.badge {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem;
    font-weight:600; letter-spacing:.02em; border:1px solid; }}
.dimrow {{ margin-bottom: 12px; }}
.dimrow .l {{ display:flex; justify-content:space-between; font-size:.85rem; margin-bottom:4px; }}
.dimrow .l b {{ font-weight:600; color:{INK}; }}
.dimrow .l span {{ color:{MUTED}; font-variant-numeric: tabular-nums; }}
.track {{ background:#E8EDF3; border-radius:4px; height:8px; overflow:hidden; }}
.fill {{ height:100%; border-radius:4px; }}
.pghead {{ margin-bottom: .25rem; }}
</style>
"""


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def sidebar_brand(region_name):
    st.markdown(
        f'''<div class="brand">
              <div class="t">Identity Trust</div>
              <div class="s">Patient data quality gate</div>
              <span class="regionchip">{region_name}</span>
            </div>''',
        unsafe_allow_html=True,
    )


def badge(decision):
    color = DECISION_COLORS.get(decision, NEUTRAL)
    label = DECISION_LABELS.get(decision, decision)
    return (f'<span class="badge" style="color:{color};border-color:{color}33;'
            f'background:{color}14;">{label}</span>')


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
        f'''<div class="dimrow">
              <div class="l"><b>{label}</b><span>{score:.2f}</span></div>
              <div class="track"><div class="fill" style="width:{pct}%;background:{c};"></div></div>
            </div>''',
        unsafe_allow_html=True,
    )


def page_title(title, subtitle):
    st.title(title)
    st.caption(subtitle)


def bar_chart(df, x, y, color=ACCENT, height=240, domain=None, x_title=None):
    xenc = alt.X(f'{x}:Q', title=x_title or x, scale=alt.Scale(domain=domain) if domain else alt.Undefined,
                 axis=alt.Axis(grid=True, gridColor='#EDF1F6', domain=False, tickColor='#EDF1F6'))
    return (
        alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=3, size=18)
        .encode(x=xenc, y=alt.Y(f'{y}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False, labelLimit=260)),
                tooltip=list(df.columns))
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, labelFont='Inter', titleFont='Inter')
    )


def decision_chart(df, decision_col='Decision', count_col='Count', height=240):
    domain = list(DECISION_LABELS.keys())
    rng = [DECISION_COLORS[k] for k in domain]
    return (
        alt.Chart(df).mark_bar(cornerRadiusEnd=3, size=18)
        .encode(
            x=alt.X(f'{count_col}:Q', title='Records',
                    axis=alt.Axis(grid=True, gridColor='#EDF1F6', domain=False)),
            y=alt.Y(f'{decision_col}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False)),
            color=alt.Color(f'{decision_col}:N', scale=alt.Scale(domain=domain, range=rng), legend=None),
            tooltip=[decision_col, count_col],
        )
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, labelFont='Inter', titleFont='Inter')
    )


# ============================================================
# Batch header + printable report
# ============================================================
import html as _html
from datetime import datetime as _dt

_CSS_EXTRA = """
<style>
.bh { background:#fff; border:1px solid #E3E8EF; border-radius:8px; padding:16px 20px;
      display:flex; justify-content:space-between; align-items:center; gap:24px;
      box-shadow:0 1px 2px rgba(15,42,67,.04); margin:0 0 1.25rem; flex-wrap:wrap; }
.bh .k { font-size:.68rem; letter-spacing:.09em; text-transform:uppercase; color:#5B6B7F; font-weight:600; }
.bh .v { font-size:1.05rem; font-weight:600; color:#0F2A43; margin-top:2px; word-break:break-all; }
.bh .m { font-size:.82rem; color:#5B6B7F; margin-top:4px; }
.bh .pill { padding:8px 16px; border-radius:6px; font-weight:650; font-size:.82rem; letter-spacing:.06em; border:1px solid; }
.demo-note { margin-top:1.2rem; padding:8px 10px; border-radius:6px; background:rgba(255,255,255,.07);
      font-size:.7rem; line-height:1.35; color:#B7C5D6 !important; }
</style>
"""


def inject_css():  # noqa: F811  (extends the earlier definition)
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_CSS_EXTRA, unsafe_allow_html=True)


def sidebar_note():
    st.markdown(
        '<div class="demo-note"><b>Demonstration build.</b> Synthetic data only. '
        'Not validated for clinical or regulatory use.</div>',
        unsafe_allow_html=True,
    )


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
    rate = (flagged / total * 100) if total else 0.0
    name = _html.escape(str((info or {}).get('name') or 'Unnamed batch'))
    when = _html.escape(str((info or {}).get('processed_at') or ''))
    st.markdown(
        f'''<div class="bh">
              <div><div class="k">Batch</div><div class="v">{name}</div>
                   <div class="m">{_html.escape(region_name)} &middot; processed {when}</div></div>
              <div><div class="k">Records</div><div class="v">{total:,}</div>
                   <div class="m">{flagged:,} flagged ({rate:.1f}%)</div></div>
              <div class="pill" style="color:{color};border-color:{color}55;background:{color}12;">{label}</div>
            </div>''',
        unsafe_allow_html=True,
    )


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
 body {{ font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color:#1B2733; margin:0; padding:32px; background:#fff; font-size:13px; line-height:1.45; }}
 .wrap {{ max-width: 820px; margin: 0 auto; }}
 .top {{ border-bottom: 3px solid #0F2A43; padding-bottom:12px; margin-bottom:18px; display:flex; justify-content:space-between; align-items:flex-end; }}
 h1 {{ font-size:20px; margin:0; color:#0F2A43; }} .sub {{ color:#5B6B7F; font-size:12px; }}
 h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.07em; color:#0F2A43; border-bottom:1px solid #D5DCE6; padding-bottom:4px; margin:22px 0 8px; }}
 table {{ width:100%; border-collapse:collapse; }} td, th {{ padding:6px 8px; border-bottom:1px solid #E8EDF3; text-align:left; vertical-align:top; }}
 th {{ background:#F4F6F9; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#5B6B7F; }}
 td.n {{ text-align:right; font-variant-numeric:tabular-nums; width:90px; }}
 .meta td:first-child {{ color:#5B6B7F; width:170px; }}
 .status {{ display:inline-block; padding:4px 12px; border:1px solid {color}; color:{color}; font-weight:700; letter-spacing:.06em; border-radius:4px; }}
 .sign td {{ height:42px; border-bottom:1px solid #9AA8B9; }} .sign td:first-child {{ width:140px; color:#5B6B7F; border-bottom:none; vertical-align:bottom; }}
 .foot {{ margin-top:26px; font-size:11px; color:#5B6B7F; border-top:1px solid #D5DCE6; padding-top:8px; }}
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

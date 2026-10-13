# demo.py - Part 1: Foundation, UI, and Helpers
import io
import re
import os
import requests
import pandas as pd
import altair as alt
import streamlit as st
from datetime import datetime
st.set_page_config(
    page_title='Identity Trust Assessment',
    page_icon=':material/health_and_safety:',
    layout='wide',
    initial_sidebar_state='expanded',
)

# ============================================================
# Configuration
# ============================================================
API_BASE_URL = "http://localhost:8000" # Your FastAPI backend
API_KEY = "" # Leave blank if no key is set, otherwise put your key here

# ============================================================
# UI Theme (Inlined)
# ============================================================
TEAL_DEEP = '#082F33'
TEAL = '#0F6B6B'
MINT = '#8FD3C8'
SIGNAL = '#E8573D'
INK = '#13272B'
MUTED = '#5E6F70'
LINE = '#E4DED2'
PAPER = '#F6F3EC'
ACCENT = TEAL
NAVY = TEAL_DEEP
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

DECISION_MEANING = {
    'AUTO_LINK': ('Safe to link', 'Identity checks passed. The record can be linked to the patient automatically.'),
    'LINK_WITH_FLAG': ('Link, but check first', 'Mostly trustworthy, but something looked off. A person should take a quick look before relying on it.'),
    'QUARANTINE': ('Hold back', 'A serious problem was found, for example an ID already used by someone else. Do not share this record until a person resolves it.'),
    'INSUFFICIENT_DATA': ('Not enough information', 'Too little identity data to judge. Get the missing details from the source first.'),
}

REGION_PROFILES = {
    'UAE (DOH)': {'id_label': 'Emirates ID', 'regulatory_body': 'DOH'},
    'India (ABDM)': {'id_label': 'ABHA / Aadhaar', 'regulatory_body': 'ABDM'},
}

# CSS (Same as your original, just injected cleanly)
_CSS_TMPL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp { font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; color: @INK@; }
.stApp { background-color: @PAPER@; background-image: radial-gradient(#E3DCCC 1px, transparent 1px); background-size: 24px 24px; }
code, pre, .stCode, [data-testid="stCode"] * { font-family: 'IBM Plex Mono', Consolas, monospace !important; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; height: 2.5rem; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
h2, h3 { font-family: 'Fraunces', Georgia, serif; color: @TD@; font-weight: 600 !important; letter-spacing: -0.005em; }
h3 { font-size: 1.1rem !important; }
[data-testid="stCaptionContainer"] { color: @MUTED@; font-size: .9rem; }
hr { border-color: @LINE@ !important; margin: 1.25rem 0 !important; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #082F33 0%, #06262A 100%); border-right: none; }
[data-testid="stSidebar"] * { color: #CFE5E1; }
[data-testid="stSidebar"] a, [data-testid="stSidebarNav"] a { border-radius: 8px; padding: .38rem .7rem; font-size: .9rem; font-weight: 500; border-left: 3px solid transparent; }
[data-testid="stSidebar"] a:hover { background: rgba(143,211,200,.10); }
[data-testid="stSidebar"] a[aria-current="page"] { background: rgba(143,211,200,.14); color: #fff; font-weight: 600; border-left: 3px solid @SIG@; }
[data-testid="stNavSectionHeader"], [data-testid="stSidebarNav"] header, [data-testid="stSidebarNav"] li > div > span { text-transform: uppercase; font-family: 'IBM Plex Mono', monospace; font-size: .66rem !important; letter-spacing: .14em; color: #6FA9A0 !important; font-weight: 500; }
.brand { padding: .3rem .1rem 1rem; border-bottom: 1px solid rgba(143,211,200,.18); margin-bottom: .6rem; display:flex; gap:12px; align-items:center; }
.brand .t { color:#fff !important; font-family:'Fraunces',serif; font-weight:600; font-size:1.15rem; line-height:1.1; }
.brand .s { color:#7DB8AE !important; font-size:.72rem; margin-top:3px; }
.regionchip { display:inline-block; margin:.4rem 0 .2rem; padding:3px 11px; border-radius:999px; border:1px solid rgba(143,211,200,.4); color:#BDEDE3 !important; font:500 .72rem 'IBM Plex Mono', monospace; letter-spacing:.04em; }
.demo-note { margin-top:1.2rem; padding:9px 11px; border-radius:8px; background:rgba(232,87,61,.12); border:1px solid rgba(232,87,61,.35); font-size:.7rem; line-height:1.4; color:#F3C2B8 !important; }
.demo-note * { color:#F3C2B8 !important; }
.hero { position:relative; overflow:hidden; border-radius:16px; padding:22px 30px 20px; margin:0 0 .9rem; background: linear-gradient(115deg, #082F33 0%, #0B4447 52%, #0F6B6B 100%); box-shadow: 0 8px 22px rgba(8,47,51,.20); }
.hero .kick { font:500 .66rem 'IBM Plex Mono', monospace; letter-spacing:.18em; text-transform:uppercase; color:@MINT@; }
.hero h1 { font-family:'Fraunces', Georgia, serif !important; font-weight:600 !important; font-size:2rem !important; margin:.3rem 0 0 !important; color:#fff !important; padding:0 !important; letter-spacing:-.01em; line-height:1.15; }
.hero svg { position:absolute; right:-6px; bottom:8px; }
.kpi { background:#fff; border:1px solid @LINE@; border-radius:14px; padding:16px 16px 13px; position:relative; overflow:hidden; box-shadow:0 2px 6px rgba(8,47,51,.05); }
.kpi::before { content:''; position:absolute; top:0; left:0; right:0; height:6px; background:var(--c); }
.kpi::after { content:''; position:absolute; top:15px; right:13px; width:10px; height:10px; border-radius:50%; background:@PAPER@; box-shadow: inset 0 0 0 2px var(--c); }
.kpi .k { font:500 .66rem 'IBM Plex Mono', monospace; letter-spacing:.1em; text-transform:uppercase; color:@MUTED@; margin-top:4px; }
.kpi .v { font:600 2rem 'IBM Plex Mono', monospace; color:@INK@; margin-top:6px; letter-spacing:-.02em; }
.kpi .s { font-size:.76rem; color:@MUTED@; margin-top:2px; }
[data-testid="stMetric"] { background:#fff; border:1px solid @LINE@; border-top:5px solid @T@; border-radius:14px; padding:12px 16px; box-shadow:0 2px 6px rgba(8,47,51,.05); }
[data-testid="stMetricLabel"] p { color:@MUTED@; font:500 .68rem 'IBM Plex Mono', monospace; text-transform:uppercase; letter-spacing:.08em; }
[data-testid="stMetricValue"] { color:@INK@; font-family:'IBM Plex Mono', monospace; font-weight:600; font-size:1.65rem; }
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
.badge { display:inline-flex; align-items:center; gap:7px; padding:3px 11px 3px 9px; border-radius:6px; font:600 .72rem 'IBM Plex Mono', monospace; letter-spacing:.04em; text-transform:uppercase; border:1px solid; }
.badge i { width:8px; height:8px; border-radius:50%; display:inline-block; }
.dimrow { margin-bottom:12px; }
.dimrow .l { display:flex; justify-content:space-between; font-size:.85rem; margin-bottom:4px; }
.dimrow .l b { font-weight:600; }
.dimrow .l span { color:@MUTED@; font-family:'IBM Plex Mono', monospace; }
.track { background:#EDE8DC; border-radius:99px; height:9px; overflow:hidden; }
.fill { height:100%; border-radius:99px; }
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
for _k, _v in {'@TD@': TEAL_DEEP, '@T@': TEAL, '@MINT@': MINT, '@SIG@': SIGNAL, '@INK@': INK, '@MUTED@': MUTED, '@LINE@': LINE, '@PAPER@': PAPER}.items():
    _CSS = _CSS.replace(_k, _v)

_ECG = '<svg width="440" height="64" viewBox="0 0 440 64" fill="none" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#8FD3C8" stop-opacity="0"/><stop offset="0.6" stop-color="#8FD3C8" stop-opacity="0.55"/><stop offset="1" stop-color="#E8573D"/></linearGradient></defs><path d="M0 36 H120 L132 36 L140 12 L152 58 L160 28 L166 36 H250 L260 36 L268 24 L276 42 L282 36 H440" stroke="url(#g)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
_LOGO = '<svg width="38" height="38" viewBox="0 0 38 38" fill="none"><rect width="38" height="38" rx="10" fill="#0F6B6B"/><path d="M5 20h7l3-8 5 15 3-9 2 2h8" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="33" cy="20" r="2.2" fill="#E8573D"/></svg>'

import html as _html

def inject_css(): st.markdown(_CSS, unsafe_allow_html=True)
def hero(title, kicker='Identity Trust Assessment'):
    st.markdown(f'<div class="hero"><div class="kick">{_html.escape(kicker)}</div><h1>{_html.escape(title)}</h1>{_ECG}</div>', unsafe_allow_html=True)
def kpi(label, value, color=TEAL, sub=''):
    sub_html = f'<div class="s">{_html.escape(sub)}</div>' if sub else ''
    st.markdown(f'<div class="kpi" style="--c:{color};"><div class="k">{_html.escape(label)}</div><div class="v">{_html.escape(str(value))}</div>{sub_html}</div>', unsafe_allow_html=True)
def callout(title, body, color=TEAL):
    st.markdown(f'<div class="callout" style="--c:{color};"><div class="ct"><i></i>{_html.escape(title)}</div><div class="cb">{_html.escape(body)}</div></div>', unsafe_allow_html=True)
def steps(items):
    cells = ''.join(f'<div class="step"><div class="n">{i+1}</div><div class="st">{_html.escape(a)}</div><div class="sd">{_html.escape(b)}</div></div>' for i, (a, b) in enumerate(items))
    st.markdown(f'<div class="steps">{cells}</div>', unsafe_allow_html=True)
def sidebar_brand(region_name):
    st.markdown(f'<div class="brand">{_LOGO}<div><div class="t">Identity Trust</div><div class="s">Patient data quality gate</div></div></div><span class="regionchip">{_html.escape(region_name)}</span>', unsafe_allow_html=True)
def sidebar_note():
    st.markdown('<div class="demo-note"><b>Demonstration build.</b> Synthetic data only. Not validated for clinical or regulatory use.</div>', unsafe_allow_html=True)
def badge(decision):
    color = DECISION_COLORS.get(decision, NEUTRAL)
    label = DECISION_LABELS.get(decision, decision)
    return f'<span class="badge" style="color:{INK};border-color:{color}88;background:{color}1F;"><i style="background:{color};"></i>{label}</span>'
def score_color(score):
    if score >= 0.85: return OK
    if score >= 0.5: return WARN
    return BAD
def dimension_bar(label, score):
    pct = int(round(score * 100))
    c = score_color(score)
    st.markdown(f'<div class="dimrow"><div class="l"><b>{label}</b><span>{score:.2f}</span></div><div class="track"><div class="fill" style="width:{pct}%;background:{c};"></div></div></div>', unsafe_allow_html=True)

# Altair Chart Helpers
_AX = dict(labelColor=MUTED, titleColor=MUTED, labelFont='IBM Plex Sans', titleFont='IBM Plex Sans')
def bar_chart(df, x, y, color=TEAL, height=240, domain=None, x_title=None):
    xenc = alt.X(f'{x}:Q', title=x_title or x, scale=alt.Scale(domain=domain) if domain else alt.Undefined, axis=alt.Axis(grid=True, gridColor='#E9E3D6', domain=False, tickColor='#E9E3D6'))
    return alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=4, size=18).encode(x=xenc, y=alt.Y(f'{y}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False, labelLimit=260)), tooltip=list(df.columns)).properties(height=height).configure(background='transparent').configure_view(strokeWidth=0).configure_axis(**_AX)
def decision_chart(df, decision_col='Decision', count_col='Count', height=240):
    domain = [DECISION_LABELS[k] for k in DECISION_LABELS]
    rng = [DECISION_COLORS[k] for k in DECISION_LABELS]
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=18).encode(x=alt.X(f'{count_col}:Q', title='Records', axis=alt.Axis(grid=True, gridColor='#E9E3D6', domain=False)), y=alt.Y(f'{decision_col}:N', sort='-x', title='', axis=alt.Axis(domain=False, ticks=False)), color=alt.Color(f'{decision_col}:N', scale=alt.Scale(domain=domain, range=rng), legend=None), tooltip=[decision_col, count_col]).properties(height=height).configure(background='transparent').configure_view(strokeWidth=0).configure_axis(**_AX)
    # ============================================================
import types

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
# Part 2: Dashboard & HL7 Stream (API-First)
# ============================================================
import sqlite3

def get_recent_decisions(limit=200):
    """Fetch recent decisions from the SQLite database to populate the dashboard."""
    try:
        conn = sqlite3.connect('audit_log.db')
        df = pd.read_sql_query(f"SELECT * FROM decisions ORDER BY id DESC LIMIT {limit}", conn)
        conn.close()
        return df
    except Exception as e:
        st.warning(f"Could not load database. Is the API running and creating records? Error: {e}")
        return pd.DataFrame()

def pg_dashboard():
    ui.hero('Dashboard')
    st.caption('Live overview of patient records processed by the Trust Gate API, MLLP Listener, and SFTP Poller.')

    # 1. Fetch live data from the database
    db_df = get_recent_decisions(limit=500)

    if db_df.empty:
        st.info("No records processed yet. Send an HL7 message or run the SFTP batch poller to populate the database.")
        
        # Still show the quick start guides
        st.markdown("### How to populate this dashboard")
        ui.steps([
            ('Send an HL7 message', 'Go to the HL7 Stream tab and paste a message to send it to the API.'),
            ('Run a batch process', 'Place a CSV in the sftp_input folder to trigger the poller.'),
            ('Check the audit log', 'Every decision is permanently saved to audit_log.db.'),
        ])
        return

    # 2. Calculate KPIs from the database
    total = len(db_df)
    auto = len(db_df[db_df['decision'] == 'AUTO_LINK'])
    flagged = len(db_df[db_df['decision'] == 'LINK_WITH_FLAG'])
    quarantined = len(db_df[db_df['decision'] == 'QUARANTINE'])
    insufficient = len(db_df[db_df['decision'] == 'INSUFFICIENT_DATA'])
    flagged_count = flagged + quarantined + insufficient
    flag_rate = (flagged_count / total) * 100 if total else 0

    # 3. Display KPIs
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        ui.kpi('Total Records', f'{total:,}', ui.TEAL, 'in this view')
    with c2:
        ui.kpi('Auto-linked', f'{auto:,}', ui.OK, 'trusted, no action')
    with c3:
        ui.kpi('Flagged', f'{flagged:,}', ui.WARN, 'review recommended')
    with c4:
        ui.kpi('Quarantined', f'{quarantined:,}', ui.BAD, 'hold from exchange')
    with c5:
        ui.kpi('Insufficient data', f'{insufficient:,}', ui.NEUTRAL, 'cannot be scored')

    st.divider()

    # 4. Charts
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Decision Breakdown**")
        dc = db_df['decision'].value_counts().reset_index()
        dc.columns = ['Decision', 'Count']
        dc['Decision'] = dc['Decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
        st.altair_chart(ui.decision_chart(dc, height=250), use_container_width=True)

    with col_b:
        st.markdown("**Top Primary Issues**")
        issues = db_df[db_df['primary_issue'] != 'None']['primary_issue'].value_counts().reset_index()
        issues.columns = ['Issue', 'Count']
        if not issues.empty:
            st.altair_chart(ui.bar_chart(issues, 'Count', 'Issue', color=ui.BAD, height=250), use_container_width=True)
        else:
            st.success("No issues detected in recent records.")

    # 5. Recent Records Table
    st.markdown("### Recent Decisions")
    display_df = db_df[['timestamp', 'canonical_id', 'trust_score', 'decision', 'primary_issue']].copy()
    display_df['decision'] = display_df['decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
    display_df.columns = ['Timestamp', 'Record ID', 'Trust Score', 'Outcome', 'Main Issue']
    
    st.dataframe(
        display_df, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            'Trust Score': st.column_config.ProgressColumn('Trust Score', min_value=0.0, max_value=1.0, format='%.2f')
        }
    )

    if st.button('Refresh Dashboard Data'):
        st.rerun()


def pg_hl7():
    ui.hero('HL7 Stream')
    st.caption('Paste one or more HL7 v2 ADT messages below. Each message is sent to the FastAPI backend, scored against the five identity dimensions, and routed in real-time.')

    st.info('In production, messages arrive continuously from the hospital interface engine via MLLP (port 6661). This page simulates that incoming flow.')

    default_msg = (
        'MSH|^~\\&|HIS|CLEVELAND CLINIC ABU DHABI|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r'
        'EVN|A04|20240110120000\r'
        'PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M\r'
        'PV1|1|O'
    )

    if 'hl7_text' not in st.session_state:
        st.session_state['hl7_text'] = default_msg

    with st.expander('What is an HL7 message?'):
        st.markdown('HL7 v2 is the format hospital systems use to tell each other about patient events such as registrations and admissions. The **PID** line carries who the patient is, and the **MSH** line says which facility sent it. This tool reads those fields and scores them exactly like a CSV row.')

    st.markdown("**Try a ready-made example**")
    d1, d2, d3, d4 = st.columns(4)
    
    sample_clean = default_msg
    sample_collision = (
        'MSH|^~\\&|HIS|TAWAM HOSPITAL|MALAFFI|DOH|20240110121500||ADT^A04|MSG0002|P|2.5\r'
        'EVN|A04|20240110121500\r'
        'PID|1||784-1985-1234567-1^^^DOH^MR||Hashimi^Fatima||19920722|F\r'
        'PV1|1|O'
    )
    sample_bad = (
        'MSH|^~\\&|HIS|UNKNOWN CLINIC|MALAFFI|DOH|20240110123000||ADT^A04|MSG0003|P|2.5\r'
        'EVN|A04|20240110123000\r'
        'PID|1||123^^^DOH^MR||Khan^Sara||19990101|F\r'
        'PV1|1|O'
    )

    d1.button('Clean message', use_container_width=True, on_click=lambda: st.session_state.update({'hl7_text': sample_clean}))
    d2.button('ID collision', use_container_width=True, on_click=lambda: st.session_state.update({'hl7_text': sample_clean + '\n\n' + sample_collision}), help='Sends a patient, then a different person using the same ID.')
    d3.button('Bad ID, unknown clinic', use_container_width=True, on_click=lambda: st.session_state.update({'hl7_text': sample_bad}))
    d4.button('Full demo (3 messages)', use_container_width=True, type='primary', on_click=lambda: st.session_state.update({'hl7_text': sample_clean + '\n\n' + sample_collision + '\n\n' + sample_bad}))

    if st.button('Reset session history'):
        st.session_state['hl7_history'] = []
        st.success('Session history cleared.')

    hl7_input = st.text_area(
        'HL7 v2 message(s). Separate multiple messages with a blank line.',
        height=220,
        key='hl7_text',
    )

    run_clicked = st.button('Send to Trust Gate API', type='primary')

    if run_clicked:
        raw_msgs = [m.strip() for m in re.split(r'\n\s*\n', hl7_input) if m.strip()]

        if not raw_msgs:
            st.error('No message found.')
            return

        if 'hl7_history' not in st.session_state:
            st.session_state['hl7_history'] = []

        for i, msg in enumerate(raw_msgs):
            st.markdown(f'---')
            st.markdown(f'### Message {i + 1}')
            
            try:
                # Send to FastAPI backend instead of processing locally
                response = requests.post(
                    f"{API_BASE_URL}/assess-hl7",
                    json={"message": msg},
                    headers={"X-API-Key": API_KEY} if API_KEY else {}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    decision = result['decision']
                    
                    cc1, cc2 = st.columns(2)
                    cc1.metric('Composite Trust Score', f"{result['trust_score']:.3f}")
                    cc2.metric('Decision', ui.DECISION_LABELS.get(decision, decision))
                    
                    m_title, m_text = DECISION_MEANING.get(decision, ('', ''))
                    ui.callout(m_title, m_text, ui.DECISION_COLORS.get(decision, ui.TEAL))
                    
                    if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
                        if result['dimensions']['cross_record'] == 0.0:
                            st.error(f"Identifier collision: ID is already registered to a different patient.")
                        else:
                            weakest = min(result['dimensions'], key=result['dimensions'].get)
                            st.warning(f"Routed for review. Weakest dimension: {weakest}.")
                            
                    with st.expander('Dimension scores'):
                        for label, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                                           ('Identity', 'identity'), ('Provenance', 'provenance'),
                                           ('Cross-Record', 'cross_record')]:
                            ui.dimension_bar(label, result['dimensions'][key])
                            
                    st.session_state['hl7_history'].append({
                        'msg_index': i + 1,
                        'canonical_id': result['canonical_id'],
                        'decision': decision,
                        'trust_score': round(result['trust_score'], 4),
                        'primary_issue': result['primary_issue']
                    })
                else:
                    st.error(f"API Error ({response.status_code}): {response.text}")

            except Exception as e:
                st.error(f"Failed to connect to the Trust Gate API: {e}. Is Uvicorn running on port 8000?")

        if st.session_state['hl7_history']:
            st.divider()
            st.markdown('### Session History')
            hist_df = pd.DataFrame(st.session_state['hl7_history'])
            hist_df['decision'] = hist_df['decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
            hist_df.columns = ['Message #', 'Record ID', 'Outcome', 'Trust Score', 'Main Issue']
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
            # ============================================================
# Part 3: Batch Upload, Flagged Records, Audit Trail, Router
# ============================================================

def pg_batch():
    ui.hero('Batch Upload')
    st.caption('Upload a CSV of patient records. The file is sent to the FastAPI backend for scoring.')

    st.info('In production, this is handled automatically by the SFTP Poller. This tab is for manual pre-pilot testing.')

    uploaded_file = st.file_uploader('CSV file', type=['csv'])

    if uploaded_file is None:
        if st.button('Run a demo batch (100 synthetic records)', type='primary'):
            # Since the demo generator is local, we'll generate it and send to API
            from trust_layer.sample_generator import generate_sample
            region = st.session_state.get('region_name', 'UAE (DOH)')
            sample_df = generate_sample(region, n=100)
            
            with st.spinner('Sending 100 records to the Trust Gate API...'):
                try:
                    # Convert DataFrame to list of dicts
                    records = sample_df.to_dict(orient='records')
                    response = requests.post(
                        f"{API_BASE_URL}/assess-batch",
                        json=records,
                        headers={"X-API-Key": API_KEY} if API_KEY else {}
                    )
                    if response.status_code == 200:
                        st.session_state['batch_results'] = response.json()
                        st.success(f"Successfully processed 100 records!")
                        st.switch_page(PAGES['flagged'])
                    else:
                        st.error(f"API Error: {response.text}")
                except Exception as e:
                    st.error(f"Failed to connect to API: {e}")
        return

    if st.button('Send to Trust Gate API', type='primary'):
        with st.spinner('Sending records to API for scoring...'):
            try:
                df = pd.read_csv(uploaded_file)
                records = df.to_dict(orient='records')
                
                response = requests.post(
                    f"{API_BASE_URL}/assess-batch",
                    json=records,
                    headers={"X-API-Key": API_KEY} if API_KEY else {}
                )
                
                if response.status_code == 200:
                    st.session_state['batch_results'] = response.json()
                    st.success(f"Successfully processed {len(records)} records!")
                    st.switch_page(PAGES['flagged'])
                else:
                    st.error(f"API Error: {response.text}")
            except Exception as e:
                st.error(f"Failed to process file: {e}")


def pg_flagged():
    ui.hero('Flagged Records')
    st.caption('Records routed for manual review by the Trust Gate API.')

    batch_results = st.session_state.get('batch_results')
    
    if not batch_results:
        st.info("No batch loaded in this session. Upload a CSV or run the demo batch to view flagged records.")
        return

    df = pd.DataFrame(batch_results)
    
    # Filter for records that need review
    flagged = df[df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])].copy()
    
    if flagged.empty:
        st.success("No flagged records in this batch. All records passed identity checks.")
        return

    # Sort by severity (Quarantine first, then Insufficient, then Flagged)
    pri = {'QUARANTINE': 0, 'INSUFFICIENT_DATA': 1, 'LINK_WITH_FLAG': 2}
    flagged['_priority'] = flagged['decision'].map(pri)
    flagged = flagged.sort_values(['_priority', 'trust_score'])

    st.caption(f"Showing {len(flagged)} of {len(df)} records.")

    for _, row in flagged.iterrows():
        with st.expander(f"{row['canonical_id']} · {row.get('given_name', '')} {row.get('family_name', '')} · {ui.DECISION_LABELS.get(row['decision'], row['decision'])}"):
            st.markdown(ui.badge(row['decision']), unsafe_allow_html=True)
            st.write(f"**Composite Trust Score:** {row['trust_score']:.3f}")
            st.write(f"**Primary Issue:** {row['primary_issue']}")
            st.info(f"{row['explanation']}")
            
            # Show dimensions
            dims = row.get('dimensions', {})
            if dims:
                st.markdown("**Dimension Scores:**")
                for label, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                                   ('Identity', 'identity'), ('Provenance', 'provenance'),
                                   ('Cross-Record', 'cross_record')]:
                    if key in dims:
                        ui.dimension_bar(label, dims[key])
    
    st.download_button(
        label='Download Flagged Records (CSV)',
        data=flagged.drop(columns=['_priority', 'dimensions']).to_csv(index=False).encode('utf-8'),
        file_name='flagged_records.csv',
        mime='text/csv'
    )


def pg_audit():
    ui.hero('Audit Trail')
    st.caption('A permanent record of every decision made by the Trust Gate API, MLLP Listener, and SFTP Poller.')

    try:
        conn = sqlite3.connect('audit_log.db')
        log_df = pd.read_sql_query("SELECT * FROM decisions ORDER BY id DESC", conn)
        conn.close()
    except Exception as e:
        st.error(f"Could not connect to audit_log.db. Is the API running? Error: {e}")
        return

    if log_df.empty:
        st.info("The audit log is currently empty. Send HL7 messages or run the batch poller to populate it.")
        return

    k1, k2, k3 = st.columns(3)
    with k1:
        ui.kpi('Total Decisions Logged', f'{len(log_df):,}', ui.TEAL, 'entries in the database')
    with k2:
        quarantined = len(log_df[log_df['decision'] == 'QUARANTINE'])
        ui.kpi('Total Quarantined', f'{quarantined:,}', ui.BAD, 'held from exchange')
    with k3:
        last_entry = log_df.iloc[0]['timestamp'] if not log_df.empty else 'N/A'
        ui.kpi('Last Entry', last_entry[:16] if last_entry != 'N/A' else 'N/A', ui.TEAL, 'most recent decision')

    st.markdown("### Raw Audit Log")
    display_df = log_df[['timestamp', 'canonical_id', 'trust_score', 'decision', 'primary_issue']].copy()
    display_df['decision'] = display_df['decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
    display_df.columns = ['Timestamp', 'Record ID', 'Trust Score', 'Outcome', 'Main Issue']

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        label='Download Raw Audit Log (CSV)',
        data=log_df.to_csv(index=False).encode('utf-8'),
        file_name='audit_log_export.csv',
        mime='text/csv'
    )


def pg_about():
    ui.hero('About')
    st.markdown('''
    ### What this tool does
    A pre-submission trust gate for patient records in a health information exchange. 
    Every incoming record is scored across five identity dimensions and routed to one of four outcomes.

    ### The five dimensions
    | Dimension | Weight | Check |
    |---|---|---|
    | Completeness | 0.20 | Required identity fields present |
    | Temporal Validity | 0.15 | Plausible date of birth |
    | Identity Consistency | 0.20 | ID format matches region standard |
    | Provenance | 0.15 | Trusted source facility |
    | Cross-Record Consistency | 0.30 | Collision with existing patient |

    ### Deployment
    - **Batch path:** FastAPI `/assess-batch` endpoint for retrospective analysis.
    - **Real-time path:** MLLP Listener (`mllp_listener.py`) for continuous HL7 streams.
    - **Production integration:** Deployed as a Docker container inside hospital infrastructure. 
    No patient data leaves the hospital network.
    ''')

# ============================================================
# Router & Navigation
# ============================================================
PAGES = {
    'dashboard': st.Page(pg_dashboard, title='Dashboard', icon=':material/dashboard:', default=True),
    'hl7': st.Page(pg_hl7, title='HL7 Stream', icon=':material/sensors:'),
    'batch': st.Page(pg_batch, title='Batch Upload', icon=':material/upload_file:'),
    'flagged': st.Page(pg_flagged, title='Flagged Records', icon=':material/flag:'),
    'audit': st.Page(pg_audit, title='Audit Trail', icon=':material/receipt_long:'),
    'about': st.Page(pg_about, title='About', icon=':material/info:'),
}

pages = {
    'Overview': [PAGES['dashboard']],
    'Analyze': [PAGES['hl7'], PAGES['batch']],
    'Reports': [PAGES['flagged']],
    'Compliance': [PAGES['audit']],
    'Settings': [PAGES['about']],
}

with st.sidebar:
    ui.sidebar_brand(st.session_state.get('region_name', 'UAE (DOH)'))
    ui.sidebar_note()

pg = st.navigation(pages)
pg.run()

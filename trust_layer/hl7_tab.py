'''
HL7 message input tab for the Streamlit demo.

Renders a text area for a raw HL7 v2 ADT message, parses it, scores it
across the same five identity dimensions, and routes it. Maintains a
session-scoped cross-record validator so pasting two messages with the
same identifier triggers a collision.
'''
import re
import streamlit as st

from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard


DEFAULT_HL7 = (
    'MSH|^~\\&|HIS|CLEVELAND CLINIC ABU DHABI|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r'
    'EVN|A04|20240110120000\r'
    'PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M\r'
    'PV1|1|O'
)


class _Rec:
    pass


class _Validator:
    def __init__(self):
        self.identifier_index = {}
        self.name_dob_index = {}

    def add_record(self, record):
        if getattr(record, 'emirates_id', None):
            self.identifier_index.setdefault(record.emirates_id, set()).add(record.canonical_id)
        key = (
            (getattr(record, 'given_name', '') or '').strip().lower(),
            (getattr(record, 'family_name', '') or '').strip().lower(),
            getattr(record, 'date_of_birth', '') or '',
        )
        if key != ('', '', ''):
            self.name_dob_index.setdefault(key, set()).add(record.canonical_id)

    def validate(self, record):
        eid = getattr(record, 'emirates_id', None)
        if eid and eid in self.identifier_index:
            if record.canonical_id not in self.identifier_index[eid]:
                return 0.0
        key = (
            (getattr(record, 'given_name', '') or '').strip().lower(),
            (getattr(record, 'family_name', '') or '').strip().lower(),
            getattr(record, 'date_of_birth', '') or '',
        )
        if key != ('', '', '') and key in self.name_dob_index:
            if record.canonical_id not in self.name_dob_index[key]:
                return 0.5
        return 1.0


def _normalize_text(value):
    if not value:
        return ''
    s = str(value).strip()
    if s.lower() in ('nan', 'nat', 'none'):
        return ''
    return ' '.join(s.split()).title()


def _normalize_id(value):
    if not value:
        return None
    digits = ''.join(c for c in str(value) if c.isdigit())
    return digits if digits else None


def _render_bar(label, score, color):
    pct = int(score * 100)
    html = f'''
    <div style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; font-family: Helvetica, sans-serif; font-size: 14px; margin-bottom: 4px;">
            <span style="font-weight: 600; color: #374151;">{label}</span>
            <span style="color: #6B7280;">{score:.2f}</span>
        </div>
        <div style="background-color: #E5E7EB; border-radius: 6px; height: 12px; width: 100%; overflow: hidden;">
            <div style="background-color: {color}; width: {pct}%; height: 100%; border-radius: 6px;"></div>
        </div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_hl7_tab(region_config, selected_color):
    st.subheader('HL7 Message Input')
    st.markdown('Paste a raw HL7 v2 ADT message. It will be parsed, scored against the same five identity dimensions used in the CSV pipeline, and routed. The session maintains a stateful validator, so pasting a second message with the same identifier triggers a collision.')

    if 'hl7_validator' not in st.session_state:
        st.session_state['hl7_validator'] = _Validator()

    hl7_input = st.text_area('HL7 v2 message', value=DEFAULT_HL7, height=220, key='hl7_text')

    col_a, col_b = st.columns([2, 1])
    with col_a:
        run = st.button('Parse and assess', key='hl7_run')
    with col_b:
        if st.button('Reset session validator', key='hl7_reset'):
            st.session_state['hl7_validator'] = _Validator()
            st.success('Session validator cleared.')

    if not run:
        return

    ok, issues = validate_hl7_structure(hl7_input)
    if not ok:
        st.error(f'Invalid HL7 message: {"; ".join(issues)}')
        return

    parsed = parse_hl7_message(hl7_input)

    st.markdown('### Parsed Fields')
    for label, value in [
        ('Emirates ID', parsed.get('emirates_id')),
        ('Given Name', parsed.get('given_name')),
        ('Family Name', parsed.get('family_name')),
        ('Gender', parsed.get('gender')),
        ('Date of Birth', parsed.get('date_of_birth')),
        ('Source Facility', parsed.get('source_facility')),
        ('Registration Date', parsed.get('registration_date')),
        ('Canonical ID', parsed.get('canonical_id')),
        ('Encounter Type', parsed.get('encounter_type')),
        ('Admission Date', parsed.get('admission_date')),
        ('Discharge Date', parsed.get('discharge_date')),
    ]:
        st.markdown(f'- **{label}:** {value if value else "_(empty)_"}')

    rec = _Rec()
    rec.emirates_id = _normalize_id(parsed.get('emirates_id'))
    rec.given_name = _normalize_text(parsed.get('given_name'))
    rec.family_name = _normalize_text(parsed.get('family_name'))
    rec.date_of_birth = str(parsed.get('date_of_birth', '')).strip()[:10]
    rec.nationality = _normalize_text(parsed.get('nationality'))
    rec.source_facility = _normalize_text(parsed.get('source_facility'))
    rec.registration_date = str(parsed.get('registration_date', '')).strip()[:10]
    rec.canonical_id = parsed.get('canonical_id') or 'HL7_MSG'

    required = region_config['required_fields']
    present = sum(1 for f in required if getattr(rec, f, None))
    completeness = round(present / len(required), 2) if required else 1.0

    try:
        year = int(rec.date_of_birth[:4])
        temporal = 1.0 if 1900 <= year <= 2025 else 0.3
    except (ValueError, TypeError):
        temporal = 0.0

    if not rec.emirates_id:
        identity = 0.0
    elif re.match(region_config['id_pattern'], rec.emirates_id):
        identity = 1.0
    else:
        identity = 0.3

    if not rec.source_facility:
        provenance = 0.0
    elif rec.source_facility in region_config['trusted_facilities']:
        provenance = 1.0
    else:
        provenance = 0.7

    dims = {
        'completeness': completeness,
        'temporal': temporal,
        'identity': identity,
        'provenance': provenance,
        'cross_record': st.session_state['hl7_validator'].validate(rec),
    }
    score = compute_trust_score(**dims)
    decision = route_decision_hard(score, dims['cross_record'])

    st.markdown('### Decision')
    d1, d2 = st.columns(2)
    d1.metric('Trust Score', f'{score:.3f}')
    d2.metric('Decision', decision)

    st.markdown('**Dimension Scores:**')
    for label, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                       ('Identity', 'identity'), ('Provenance', 'provenance'),
                       ('Cross-Record', 'cross_record')]:
        _render_bar(label, dims[key], selected_color)

    if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
        if dims['cross_record'] == 0.0:
            st.error(f'Identifier collision: {region_config["id_label"]} is already registered to a different patient.')
        else:
            weakest = min(dims, key=dims.get)
            st.warning(f'Routed to manual review. Weakest dimension: {weakest}.')

    st.session_state['hl7_validator'].add_record(rec)
    st.caption('Record added to session validator. Paste another message with the same Emirates ID to trigger a collision.')

'''
HL7 message input tab. Session-persistent validator catches collisions
across pasted messages.
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
    '\n\n'
    'MSH|^~\\&|HIS|TAWAM HOSPITAL|MALAFFI|DOH|20240110121500||ADT^A04|MSG0002|P|2.5\r'
    'EVN|A04|20240110121500\r'
    'PID|1||784-1985-1234567-1^^^DOH^MR||Hashimi^Fatima||19920722|F\r'
    'PV1|1|O'
    '\n\n'
    'MSH|^~\\&|HIS|UNKNOWN CLINIC|MALAFFI|DOH|20240110123000||ADT^A04|MSG0003|P|2.5\r'
    'EVN|A04|20240110123000\r'
    'PID|1||123^^^DOH^MR||Khan^Sara||19990101|F\r'
    'PV1|1|O'
)


# ============================================================
# Session-persistent cross-record validator
# ============================================================
class _Validator:
    def __init__(self):
        self.identifier_index = {}
        self.name_dob_index = {}

    def add_record(self, rec):
        if getattr(rec, 'emirates_id', None):
            self.identifier_index.setdefault(rec.emirates_id, set()).add(rec.canonical_id)
        key = (
            (getattr(rec, 'given_name', '') or '').strip().lower(),
            (getattr(rec, 'family_name', '') or '').strip().lower(),
            getattr(rec, 'date_of_birth', '') or '',
        )
        if key != ('', '', ''):
            self.name_dob_index.setdefault(key, set()).add(rec.canonical_id)

    def validate(self, rec):
        eid = getattr(rec, 'emirates_id', None)
        if eid and eid in self.identifier_index:
            if rec.canonical_id not in self.identifier_index[eid]:
                return 0.0
        key = (
            (getattr(rec, 'given_name', '') or '').strip().lower(),
            (getattr(rec, 'family_name', '') or '').strip().lower(),
            getattr(rec, 'date_of_birth', '') or '',
        )
        if key != ('', '', '') and key in self.name_dob_index:
            if rec.canonical_id not in self.name_dob_index[key]:
                return 0.5
        return 1.0


class _Rec:
    pass


def _norm_text(v):
    if not v:
        return ''
    s = str(v).strip()
    if s.lower() in ('nan', 'nat', 'none'):
        return ''
    return ' '.join(s.split()).title()


def _norm_id(v):
    if not v:
        return None
    digits = ''.join(c for c in str(v) if c.isdigit())
    return digits if digits else None


def _bar(label, score, color):
    pct = int(round(score * 100))
    st.markdown(
        f'''<div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px;">
                <span style="font-weight:600;">{label}</span><span>{score:.2f}</span>
              </div>
              <div style="background:#E5E7EB;border-radius:4px;height:8px;overflow:hidden;">
                <div style="background:{color};width:{pct}%;height:100%;border-radius:4px;"></div>
              </div>
            </div>''',
        unsafe_allow_html=True,
    )


def render_hl7_tab(region_config, selected_color=None):
    st.subheader('HL7 Message Input')
    st.markdown(
        'Paste one or more HL7 v2 ADT messages, separated by a blank line. '
        'Each is parsed and scored against the five identity dimensions. '
        'The session validator remembers every identifier it sees, so a second '
        'message with the same Emirates ID attached to a different patient triggers a collision.'
    )

    if 'hl7_validator' not in st.session_state:
        st.session_state['hl7_validator'] = _Validator()
    if 'hl7_history' not in st.session_state:
        st.session_state['hl7_history'] = []

    col_a, col_b = st.columns([2, 1])
    with col_b:
        if st.button('Reset session validator', key='hl7_reset', use_container_width=True):
            st.session_state['hl7_validator'] = _Validator()
            st.session_state['hl7_history'] = []
            st.success('Session cleared. Every message will be treated as new.')

    hl7_input = st.text_area('HL7 v2 message(s)', value=DEFAULT_HL7, height=260, key='hl7_text')

    if not st.button('Parse and assess', key='hl7_run', type='primary'):
        return

    raw_msgs = [m.strip() for m in re.split(r'\n\s*\n', hl7_input) if m.strip()]
    if not raw_msgs:
        st.error('No message found.')
        return

    validator = st.session_state['hl7_validator']

    for i, msg in enumerate(raw_msgs):
        st.markdown(f'---\n### Message {i + 1}')

        ok, issues = validate_hl7_structure(msg)
        if not ok:
            st.error(f'Invalid HL7 structure: {"; ".join(issues)}')
            continue

        parsed = parse_hl7_message(msg)

        with st.expander('Parsed fields', expanded=False):
            for label, value in [
                ('Emirates ID', parsed.get('emirates_id')),
                ('Given name', parsed.get('given_name')),
                ('Family name', parsed.get('family_name')),
                ('Gender', parsed.get('gender')),
                ('Date of birth', parsed.get('date_of_birth')),
                ('Source facility', parsed.get('source_facility')),
                ('Canonical ID', parsed.get('canonical_id')),
            ]:
                st.markdown(f'- **{label}:** {value if value else "_(empty)_"}')

        rec = _Rec()
        rec.emirates_id = _norm_id(parsed.get('emirates_id'))
        rec.given_name = _norm_text(parsed.get('given_name'))
        rec.family_name = _norm_text(parsed.get('family_name'))
        rec.date_of_birth = str(parsed.get('date_of_birth', '')).strip()[:10]
        rec.nationality = _norm_text(parsed.get('nationality'))
        rec.source_facility = _norm_text(parsed.get('source_facility'))
        rec.registration_date = str(parsed.get('registration_date', '')).strip()[:10]
        rec.canonical_id = parsed.get('canonical_id') or f'MSG_{i + 1}'

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

        cross_record = validator.validate(rec)

        dims = {
            'completeness': completeness,
            'temporal': temporal,
            'identity': identity,
            'provenance': provenance,
            'cross_record': cross_record,
        }
        score = compute_trust_score(**dims)
        decision = route_decision_hard(score, cross_record)

        c1, c2 = st.columns(2)
        c1.metric('Trust Score', f'{score:.3f}')
        c2.metric('Decision', decision.replace('_', ' ').title())

        if decision == 'QUARANTINE':
            if cross_record == 0.0:
                st.error(
                    f'Identifier collision. {region_config["id_label"]} {rec.emirates_id} '
                    f'is already registered to a different patient. This record claims to be '
                    f'{rec.given_name} {rec.family_name}.'
                )
            else:
                st.error(f'Record quarantined. Weakest dimension: {min(dims, key=dims.get)}.')
        elif decision == 'LINK_WITH_FLAG':
            st.warning(f'Routed for review. Weakest dimension: {min(dims, key=dims.get)}.')
        else:
            st.success('Clean record. Identity checks passed.')

        with st.expander('Dimension scores'):
            for lbl, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                             ('Identity', 'identity'), ('Provenance', 'provenance'),
                             ('Cross-record', 'cross_record')]:
                _bar(lbl, dims[key], '#1F5FA8')

        validator.add_record(rec)
        st.session_state['hl7_history'].append({
            'msg': i + 1,
            'id': rec.canonical_id,
            'emirates_id': rec.emirates_id,
            'name': f'{rec.given_name} {rec.family_name}',
            'decision': decision,
            'trust_score': round(score, 3),
        })

    if st.session_state['hl7_history']:
        st.divider()
        st.markdown('### Session history')
        st.dataframe(st.session_state['hl7_history'], use_container_width=True)

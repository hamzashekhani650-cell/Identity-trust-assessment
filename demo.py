import io
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
from trust_layer.schema_mapper import map_columns, CANONICAL_FIELDS
from trust_layer.sample_generator import generate_sample

try:
    from trust_layer.prior_auth_validators import validate_preauth
    PA_AVAILABLE = True
except ImportError:
    PA_AVAILABLE = False

st.set_page_config(page_title='Identity Trust Assessment', layout='wide')
st.title('Identity Trust Assessment')
st.caption('Pre-submission record trust gate for patient identity resolution and claim readiness in HIEs')

with st.expander('About this demo'):
    st.markdown('''
**Scoring configuration notice:**

This demo uses a revised scoring configuration, tuned separately from the published paper's validated configuration.

- **Composite formula:** weighted sum x (0.4 + 0.6 x weakest dimension score) — a continuous blend
- **Auto-link threshold:** 0.75 (paper: 0.952)
- **Quarantine threshold:** 0.45 (paper: 0.571)

The revised formula and thresholds were tuned for realistic flag rates on messy real-world hospital data. A hospital pilot should re-derive both using the paper's methodology before production deployment.

All checks are rule-based and deterministic. No AI-driven resolution, merging, or auto-correction is performed.

This tool accepts any CSV. It maps incoming column names to a canonical schema, normalizes formatting differences, and processes whatever identity, clinical, and governance fields are present. Missing fields are treated as blank, and any check that cannot run is marked "not available" without stopping the rest of the pipeline.
    ''')

AUDIT_LOG_PATH = '/tmp/audit_log.jsonl'

COLOR_OPTIONS = {
    'Blue': '#1E90FF', 'Pink': '#FF69B4', 'Red': '#FF0000',
    'Orange': '#FFA500', 'Purple': '#800080', 'Green': '#32CD32',
    'Teal': '#008080', 'Magenta': '#FF00FF', 'Indigo': '#4B0082',
    'Black': '#000000', 'Gray': '#808080', 'Gold': '#FFD700',
}
PREFIXES = ['mr.', 'mrs.', 'ms.', 'dr.', 'mr ', 'mrs ', 'ms ', 'dr ']
SMALL_WORDS = {'and', 'of', 'the', 'at', 'in', 'on', 'for'}

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
        'dob_min_year': 1900,
        'dob_max_year': 2025,
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
        'dob_min_year': 1900,
        'dob_max_year': 2025,
    },
}

def render_dimension_bar(label, score, color):
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

@st.cache_data(show_spinner='Running trust assessment...')
def run_assessment(file_bytes, region_name):
    config = REGION_PROFILES[region_name]

    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [str(c).strip() for c in df.columns]

    if len(df.columns) == 0:
        return None, {'error': True, 'found': [], 'missing': ['any columns']}

    original_columns = set(df.columns)

    mapping, unresolved, inferred = map_columns(df)
    df = df.rename(columns=mapping)

    for field in CANONICAL_FIELDS:
        if field not in df.columns:
            df[field] = ''

    coding_available = ('diagnosis_code' in original_columns) or ('procedure_code' in original_columns)
    drg_available = 'encounter_type' in original_columns
    consent_available = 'consent_status' in original_columns
    pa_available_here = 'preauth_reference' in original_columns or 'preauth_valid_until' in original_columns

    df['_orig_given'] = df['given_name'].astype(str).replace('nan', '')
    df['_orig_family'] = df['family_name'].astype(str).replace('nan', '')
    df['_orig_dob'] = df['date_of_birth'].astype(str).replace('nan', '')
    df['_orig_id'] = df['emirates_id'].astype(str).replace('nan', '')

    df['given_name'] = df['given_name'].apply(normalize_text)
    df['family_name'] = df['family_name'].apply(normalize_text)
    df['date_of_birth'] = df['date_of_birth'].apply(normalize_date)
    df['source_facility'] = df['source_facility'].apply(normalize_text)
    df['nationality'] = df['nationality'].apply(normalize_text)
    df['emirates_id'] = df['emirates_id'].apply(normalize_id)

    df['_changed_name'] = (df['_orig_given'] != df['given_name'].astype(str)) | (df['_orig_family'] != df['family_name'].astype(str))
    df['_changed_dob'] = (df['_orig_dob'] != df['date_of_birth'].astype(str)) & (df['_orig_dob'] != '')
    df['_changed_id'] = (df['_orig_id'] != df['emirates_id'].astype(str)) & (df['_orig_id'] != '')

    total_raw = len(df)
    missing_ids = int(df['emirates_id'].isna().sum())
    missing_dob = int((df['date_of_birth'] == '').sum())
    dup_ids = int(df['emirates_id'].dropna().duplicated().sum())
    total_normalized = int((df['_changed_name'] | df['_changed_dob'] | df['_changed_id']).sum())

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
        score = compute_trust_score(**dims)

        id_label = config['id_label']
        reg = config['regulatory_body']

        critical_present = sum(1 for v in [rec.emirates_id, rec.given_name, rec.family_name, rec.date_of_birth] if v)

        if critical_present == 0:
            decision = 'INSUFFICIENT_DATA'
            score = 0.0
            explanation = 'Record contains no name, identifier, or date of birth. Identity trust cannot be assessed on this record.'
            primary_issue = 'Insufficient Data'
        else:
            decision = route_decision_hard(score, dims['cross_record'])
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
            'trust_score': round(score, 3), 'decision': decision,
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
        config_version='v0.5.0-demo',
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

    schema_report = {
        'input_columns': len(original_columns),
        'mapped': len(mapping),
        'unresolved': unresolved,
        'inferred': inferred,
        'missing_canonical': [f for f in CANONICAL_FIELDS if f not in original_columns],
        'coding_available': coding_available,
        'drg_available': drg_available,
        'consent_available': consent_available,
        'pa_available': pa_available_here and PA_AVAILABLE,
    }

    meta = {
        'total_raw': total_raw, 'missing_ids': missing_ids,
        'missing_dob': missing_dob, 'dup_ids': dup_ids,
        'total_normalized': total_normalized,
    }
    return results_df, meta, df, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema_report

with st.sidebar:
    st.subheader('Configuration')
    selected_region = st.selectbox(
        'Region Profile',
        list(REGION_PROFILES.keys()),
        help='Swaps the ID format, required fields, DOB range, trusted facilities, and regulatory references.',
    )
    region = REGION_PROFILES[selected_region]

    selected_color_name = st.selectbox('Bar Color', list(COLOR_OPTIONS.keys()))
    selected_color = COLOR_OPTIONS[selected_color_name]

    st.warning('Privacy Notice: This demo uses synthetic data only. Do not upload real patient health information (PHI).')

    st.markdown('**Generate a sample**')
    if st.button(f'Generate {selected_region} Sample (100 records)', use_container_width=True):
        st.session_state['sample_df'] = generate_sample(selected_region, n=100)

    if 'sample_df' in st.session_state:
        st.download_button(
            label='📥 Download Generated Sample',
            data=st.session_state['sample_df'].to_csv(index=False).encode('utf-8'),
            file_name=f'sample_{selected_region.split()[0].lower()}_100.csv',
            mime='text/csv',
            use_container_width=True,
        )

    uploaded_file = st.file_uploader('Upload patient records (CSV)', type=['csv'])

if uploaded_file is None:
    st.info(f'Selected region: {selected_region}. Generate a sample or upload your own CSV to begin. Any CSV with patient records will work — column names and formatting are handled automatically.')
    st.stop()

result = run_assessment(uploaded_file.getvalue(), selected_region)

if result[0] is None:
    st.error('The uploaded file has no columns. Please check the CSV and try again.')
    st.stop()

results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result

with st.expander('📋 Schema Analysis', expanded=(schema['mapped'] < schema['input_columns'])):
    st.markdown(f'**Input:** {schema["input_columns"]} columns · **Mapped to canonical schema:** {schema["mapped"]} columns')
    if schema['inferred']:
        st.markdown('**Auto-detected by content:**')
        for item in schema['inferred']:
            st.markdown(f"- `{item['column']}` → `{item['field']}` (confidence {item['confidence']:.2f})")
    if schema['unresolved']:
        st.markdown(f'**Unrecognized columns ({len(schema["unresolved"])}):** ' + ', '.join(f'`{c}`' for c in schema['unresolved']))
    if schema['missing_canonical']:
        core = [f for f in schema['missing_canonical'] if f in ('emirates_id', 'given_name', 'family_name', 'date_of_birth')]
        if core:
            st.markdown(f'**Core identity fields not present in this file:** ' + ', '.join(f'`{f}`' for f in core))
        other = [f for f in schema['missing_canonical'] if f not in ('emirates_id', 'given_name', 'family_name', 'date_of_birth')]
        if other:
            st.caption(f'Other canonical fields not present: ' + ', '.join(f'`{f}`' for f in other))
    st.markdown('---')
    st.markdown('**Module availability for this file:**')
    st.markdown(f"- Identity Trust: **available**")
    st.markdown(f"- Coding Coherence: **{'available' if schema['coding_available'] else 'not available — no diagnosis_code or procedure_code column'}**")
    st.markdown(f"- DRG Readiness: **{'available' if schema['drg_available'] else 'not available — no encounter_type column'}**")
    st.markdown(f"- Consent Compliance: **{'available' if schema['consent_available'] else 'not available — no consent_status column'}**")
    st.markdown(f"- Prior-Authorization: **{'available' if schema['pa_available'] else 'not available — no preauth_reference column'}**")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    'Executive Dashboard', 'Flagged Records',
    'Batch Results', 'Coding Coherence',
    'DRG Readiness', 'Data Governance',
    'Audit Trail & Normalization',
])

with tab1:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Total Records', len(results_df))
    c2.metric('Auto-Linked', len(results_df[results_df['decision'] == 'AUTO_LINK']))
    c3.metric('Flagged', len(results_df[results_df['decision'] == 'LINK_WITH_FLAG']))
    c4.metric('Quarantined', len(results_df[results_df['decision'] == 'QUARANTINE']))
    c5.metric('Insufficient Data', len(results_df[results_df['decision'] == 'INSUFFICIENT_DATA']))
    st.divider()

    st.subheader('Decision Breakdown')
    dc = results_df['decision'].value_counts().reset_index()
    dc.columns = ['Decision', 'Count']
    st.altair_chart(
        alt.Chart(dc).mark_bar(color='#4A6FA5').encode(
            x=alt.X('Count:Q', title='Records'),
            y=alt.Y('Decision:N', sort='-x', title=''),
            tooltip=['Decision', 'Count'],
        ).properties(height=250),
        use_container_width=True,
    )

    st.subheader('Facility Risk Profile')
    fl = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])]
    if not fl.empty:
        fac = fl['source_facility'].replace('', '(unset)').value_counts().reset_index()
        fac.columns = ['Facility', 'Flagged Count']
        st.altair_chart(
            alt.Chart(fac).mark_bar(color='#C62828').encode(
                x=alt.X('Flagged Count:Q', title='Flagged Records'),
                y=alt.Y('Facility:N', sort='-x', title=''),
                tooltip=['Facility', 'Flagged Count'],
            ).properties(height=300),
            use_container_width=True,
        )
    else:
        st.info('No records were flagged in this batch.')

    st.subheader('Dimension Scoring Averages')
    dm = results_df[['dim_completeness', 'dim_temporal', 'dim_identity', 'dim_provenance', 'dim_cross_record']].mean().reset_index()
    dm.columns = ['Dimension', 'Average Score']
    dm['Dimension'] = ['Completeness', 'Temporal', 'Identity', 'Provenance', 'Cross-Record']
    st.altair_chart(
        alt.Chart(dm).mark_bar(color='#2E7D32').encode(
            x=alt.X('Average Score:Q', scale=alt.Scale(domain=[0, 1])),
            y=alt.Y('Dimension:N', sort='-x', title=''),
            tooltip=['Dimension', 'Average Score'],
        ).properties(height=250),
        use_container_width=True,
    )

with tab2:
    flagged = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])].copy()
    if flagged.empty:
        st.success('All records processed cleanly. No flags raised.')
    else:
        pri = {'INSUFFICIENT_DATA': 0, 'QUARANTINE': 1, 'LINK_WITH_FLAG': 2}
        flagged['_p'] = flagged['decision'].map(pri)
        flagged = flagged.sort_values(['_p', 'trust_score']).drop(columns='_p')

        st.subheader('Flagged Records for Manual Review')
        st.warning(f'{len(flagged)} record(s) require manual review.')

        fc1, fc2 = st.columns(2)
        with fc1:
            io_opt = sorted(flagged['primary_issue'].unique().tolist())
            sel_issues = st.multiselect('Filter by issue type', options=io_opt, default=io_opt)
        with fc2:
            d_opt = sorted(flagged['decision'].unique().tolist())
            sel_dec = st.multiselect('Filter by decision', options=d_opt, default=d_opt)

        filtered = flagged[flagged['primary_issue'].isin(sel_issues) & flagged['decision'].isin(sel_dec)]
        st.caption(f'Showing {len(filtered)} of {len(flagged)} flagged records.')

        with st.expander('Bulk Actions'):
            st.markdown('**Copy all filtered record IDs:**')
            st.code('\n'.join(filtered['canonical_id'].astype(str).tolist()), language=None)

        st.divider()

        STEP = 100
        if 'show_count' not in st.session_state:
            st.session_state.show_count = STEP

        to_render = filtered.head(st.session_state.show_count)
        st.caption(f'Rendering {len(to_render)} of {len(filtered)} filtered records.')

        for _, row in to_render.iterrows():
            with st.expander(f'{row["canonical_id"]} - {row["given_name"] or "(no name)"} {row["family_name"]} ({row["decision"]})'):
                st.markdown('**Record ID (click the copy icon):**')
                st.code(row['canonical_id'], language=None)
                st.write(f'**Trust Score:** {row["trust_score"]}')
                st.write(f'**Primary Issue:** {row["primary_issue"]}')
                st.info(f'**Forensic Detail:** {row["explanation"]}')
                st.write('**Dimension Scores:**')
                for lbl, col in [('Completeness', 'dim_completeness'), ('Temporal', 'dim_temporal'),
                                 ('Identity', 'dim_identity'), ('Provenance', 'dim_provenance'),
                                 ('Cross-Record', 'dim_cross_record')]:
                    render_dimension_bar(lbl, row[col], selected_color)

        if len(filtered) > st.session_state.show_count:
            if st.button('Load more records'):
                st.session_state.show_count += STEP
                st.rerun()

        st.download_button(
            label='Download Filtered Flagged Records (CSV)',
            data=filtered.to_csv(index=False).encode('utf-8'),
            file_name='flagged_identity_records.csv', mime='text/csv',
        )

with tab3:
    st.subheader('Batch Results')
    if len(results_df) > 500:
        st.caption(f'Showing first 500 of {len(results_df)} records.')
        st.markdown(results_df.head(500)[['canonical_id', 'given_name', 'family_name', 'trust_score', 'decision', 'primary_issue']].to_markdown(index=False))
    else:
        st.markdown(results_df[['canonical_id', 'given_name', 'family_name', 'trust_score', 'decision', 'primary_issue']].to_markdown(index=False))
    st.download_button(
        label='Download Full Scored Batch (CSV)',
        data=results_df.to_csv(index=False).encode('utf-8'),
        file_name='full_scored_batch.csv', mime='text/csv',
    )

with tab4:
    st.subheader('Coding & Episode Coherence')
    if not clinical_meta.get('available'):
        st.info('This check could not run because the uploaded file has no `diagnosis_code` or `procedure_code` column. The rest of the demo works normally.')
    else:
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric('ICD Issues', clinical_meta['icd_issues'])
        cc2.metric('ICD-CPT Mismatches', clinical_meta['icd_cpt_mismatches'])
        cc3.metric('Timeline Errors', clinical_meta['timeline_errors'])
        cc4.metric('Triage-Cost Anomalies', clinical_meta['triage_anomalies'])
        st.divider()
        issue_counts = pd.DataFrame({
            'Issue': ['ICD Issues', 'ICD-CPT Mismatches', 'Timeline Errors', 'Triage-Cost Anomalies', 'Duplicate Episodes'],
            'Count': [
                clinical_meta['icd_issues'], clinical_meta['icd_cpt_mismatches'],
                clinical_meta['timeline_errors'], clinical_meta['triage_anomalies'],
                len(clinical_meta['duplicate_episodes']),
            ],
        })
        st.altair_chart(
            alt.Chart(issue_counts).mark_bar(color='#7E57C2').encode(
                x=alt.X('Count:Q', title='Number of Records'),
                y=alt.Y('Issue:N', sort='-x', title=''),
                tooltip=['Issue', 'Count'],
            ).properties(height=280),
            use_container_width=True,
        )
        st.metric('Mean Clinical Coherence Score', f'{clinical_meta["mean_coherence"]:.3f}')
        st.divider()
        st.subheader('Records with Coding Issues')
        problematic = clinical_df[
            (clinical_df['icd_exists'] < 1.0) | (clinical_df['icd_cpt_match'] == 0.0) |
            (clinical_df['episode_timeline'] == 0.0) | (clinical_df['triage_cost'] == 0.0) |
            (clinical_df['admission_after_dob'] == 0.0)
        ].copy()
        if problematic.empty:
            st.success('No coding or episode coherence issues detected.')
        else:
            st.caption(f'{len(problematic)} record(s) with at least one coding coherence issue.')
            display_cols = ['canonical_id', 'given_name', 'family_name', 'diagnosis_code',
                            'procedure_code', 'admission_date', 'discharge_date',
                            'triage_level', 'total_cost_aed', 'clinical_coherence_score']
            display_cols = [c for c in display_cols if c in problematic.columns]
            st.dataframe(problematic[display_cols], use_container_width=True)
            st.download_button(
                label='Download Coding Coherence Report (CSV)',
                data=problematic.to_csv(index=False).encode('utf-8'),
                file_name='coding_coherence_report.csv', mime='text/csv',
            )
        if clinical_meta['duplicate_episodes']:
            st.divider()
            st.subheader('Duplicate Episodes')
            dup_rows = [{'episode_id': ep, 'claimed_by': ', '.join(ids)} for ep, ids in clinical_meta['duplicate_episodes'].items()]
            st.dataframe(pd.DataFrame(dup_rows), use_container_width=True)

with tab5:
    st.subheader('DRG Readiness')
    if not drg_meta.get('available'):
        st.info('This check could not run because the uploaded file has no `encounter_type` column (or no inpatient records). The rest of the demo works normally.')
    else:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric('Inpatient Records', drg_meta['inpatient_count'])
        d2.metric('Fully Ready', drg_meta['fully_ready'])
        d3.metric('Partial', drg_meta['partial'])
        d4.metric('Not Ready', drg_meta['not_ready'])
        st.divider()
        st.metric('Mean DRG Readiness', f'{drg_meta["mean_readiness"]:.3f}')
        readiness_counts = pd.DataFrame({
            'Status': ['Fully Ready', 'Partial', 'Not Ready'],
            'Count': [drg_meta['fully_ready'], drg_meta['partial'], drg_meta['not_ready']],
        })
        st.altair_chart(
            alt.Chart(readiness_counts).mark_bar(color='#00897B').encode(
                x=alt.X('Count:Q', title='Records'),
                y=alt.Y('Status:N', sort='-x', title=''),
                tooltip=['Status', 'Count'],
            ).properties(height=220),
            use_container_width=True,
        )
        st.divider()
        st.subheader('Most Common Missing Inputs')
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
            st.altair_chart(
                alt.Chart(miss_df).mark_bar(color='#C62828').encode(
                    x=alt.X('Records Missing:Q'),
                    y=alt.Y('Field:N', sort='-x', title=''),
                    tooltip=['Field', 'Records Missing'],
                ).properties(height=250),
                use_container_width=True,
            )
        st.divider()
        st.subheader('Inpatient Records with DRG Issues')
        problematic_drg = drg_df[
            (drg_df['applicable'] == True) &
            ((drg_df['drg_readiness_score'] < 1.0) | (drg_df['issues'] != ''))
        ].copy()
        if problematic_drg.empty:
            st.success('All inpatient records are fully DRG-ready.')
        else:
            st.caption(f'{len(problematic_drg)} inpatient record(s) with at least one issue.')
            display_cols = ['canonical_id', 'given_name', 'family_name', 'encounter_type',
                            'drg_readiness_score', 'missing_inputs', 'issues']
            display_cols = [c for c in display_cols if c in problematic_drg.columns]
            st.dataframe(problematic_drg[display_cols], use_container_width=True)
            st.download_button(
                label='Download DRG Readiness Report (CSV)',
                data=problematic_drg.to_csv(index=False).encode('utf-8'),
                file_name='drg_readiness_report.csv', mime='text/csv',
            )

with tab6:
    st.subheader('Data Governance')
    g1, g2, g3, g4 = st.columns(4)
    g1.metric('Mean MDS Score', f'{gov_meta["mean_mds"]:.3f}')
    g2.metric('Below 80% MDS', gov_meta['below_80'])
    g3.metric('Consent Blocked', gov_meta['consent_blocked'] if gov_meta['consent_available'] else 'N/A')
    g4.metric('Consent Missing', gov_meta['consent_missing'] if gov_meta['consent_available'] else 'N/A')

    st.divider()
    st.subheader('MDS Completeness Distribution')
    mds_buckets = pd.DataFrame({
        'Bucket': ['Perfect (1.0)', 'Good (0.8-0.99)', 'Partial (0.6-0.79)', 'Poor (<0.6)'],
        'Count': [
            int((gov_df['mds_score'] >= 0.999).sum()),
            int(((gov_df['mds_score'] >= 0.80) & (gov_df['mds_score'] < 0.999)).sum()),
            int(((gov_df['mds_score'] >= 0.60) & (gov_df['mds_score'] < 0.80)).sum()),
            int((gov_df['mds_score'] < 0.60).sum()),
        ],
    })
    st.altair_chart(
        alt.Chart(mds_buckets).mark_bar(color='#5E35B1').encode(
            x=alt.X('Count:Q', title='Records'),
            y=alt.Y('Bucket:N', sort='-x', title=''),
            tooltip=['Bucket', 'Count'],
        ).properties(height=220),
        use_container_width=True,
    )

    st.subheader('Most Common Missing MDS Fields')
    mds_missing_counter = {}
    for m in gov_df['mds_missing']:
        if m:
            for field in m.split(', '):
                mds_missing_counter[field] = mds_missing_counter.get(field, 0) + 1
    if mds_missing_counter:
        mds_miss_df = pd.DataFrame([
            {'Field': k, 'Records Missing': v}
            for k, v in sorted(mds_missing_counter.items(), key=lambda x: -x[1])
        ])
        st.altair_chart(
            alt.Chart(mds_miss_df).mark_bar(color='#E64A19').encode(
                x=alt.X('Records Missing:Q'),
                y=alt.Y('Field:N', sort='-x', title=''),
                tooltip=['Field', 'Records Missing'],
            ).properties(height=250),
            use_container_width=True,
        )

    if gov_meta['consent_available']:
        st.divider()
        st.subheader('Consent Status Breakdown')
        consent_counts = gov_df['consent_state'].value_counts().reset_index()
        consent_counts.columns = ['Status', 'Count']
        st.altair_chart(
            alt.Chart(consent_counts).mark_bar(color='#00838F').encode(
                x=alt.X('Count:Q', title='Records'),
                y=alt.Y('Status:N', sort='-x', title=''),
                tooltip=['Status', 'Count'],
            ).properties(height=220),
            use_container_width=True,
        )
        cns1, cns2, cns3, cns4 = st.columns(4)
        cns1.metric('Granted', gov_meta['consent_granted'])
        cns2.metric('Restricted', gov_meta['consent_restricted'])
        cns3.metric('Denied / Withdrawn', gov_meta['consent_blocked'])
        cns4.metric('Missing', gov_meta['consent_missing'])
        if gov_meta['consent_blocked'] > 0:
            st.error(f'{gov_meta["consent_blocked"]} record(s) have denied or withdrawn consent — these must not be shared without further review.')
    else:
        st.divider()
        st.info('Consent compliance check is not available for this file (no `consent_status` column).')

    if gov_meta['pa_available']:
        st.divider()
        st.subheader('Prior-Authorization Status')
        pa1, pa2, pa3 = st.columns(3)
        pa1.metric('PA-Required Procedures', gov_meta['pa_required'])
        pa2.metric('Missing PA Reference', gov_meta['pa_missing'])
        pa3.metric('Valid PA on File', gov_meta['pa_valid'])
        if gov_meta['pa_missing'] > 0:
            st.error(f'{gov_meta["pa_missing"]} claim(s) will be rejected: procedure requires pre-authorization but no PA reference is on file.')
    else:
        st.divider()
        st.info('Prior-authorization check is not available for this file (no `preauth_reference` column).')

    st.divider()
    st.subheader('Records with Governance Issues')
    problematic_gov = gov_df[
        (gov_df['mds_score'] < 0.80) |
        (gov_df['consent_state'].isin(['denied', 'withdrawn', 'missing'])) |
        (gov_df['consent_issues'] != '') |
        ((gov_df['pa_required'] == True) & (gov_df['pa_present'] == False))
    ].copy()
    if problematic_gov.empty:
        st.success('No governance issues detected.')
    else:
        st.caption(f'{len(problematic_gov)} record(s) with at least one governance issue.')
        display_cols = ['canonical_id', 'given_name', 'family_name',
                        'mds_score', 'mds_missing', 'consent_state', 'consent_issues',
                        'pa_score', 'pa_issues']
        display_cols = [c for c in display_cols if c in problematic_gov.columns]
        st.dataframe(problematic_gov[display_cols], use_container_width=True)
        st.download_button(
            label='Download Governance Report (CSV)',
            data=problematic_gov.to_csv(index=False).encode('utf-8'),
            file_name='governance_report.csv', mime='text/csv',
        )

with tab7:
    st.subheader('Tamper-Evident Audit Trail')
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button('Verify audit chain'):
            ok, msg = verify_chain(AUDIT_LOG_PATH)
            if ok:
                st.success(f'Chain verified: {msg}')
            else:
                st.error(f'Chain broken: {msg}')
    with ac2:
        if os.path.exists(AUDIT_LOG_PATH):
            with open(AUDIT_LOG_PATH, 'rb') as f:
                st.download_button(
                    label='Download Audit Log (JSONL)',
                    data=f.read(),
                    file_name='audit_log.jsonl',
                    mime='application/jsonl',
                )
    st.divider()
    st.subheader('Data Normalization Log')
    st.metric('Records Normalized', meta['total_normalized'])
    st.divider()
    st.subheader('Export Standardized Data')
    export_cols = ['canonical_id', 'emirates_id', 'given_name', 'family_name',
                   'date_of_birth', 'gender', 'nationality', 'source_facility', 'registration_date']
    export_cols = [c for c in export_cols if c in df_meta.columns]
    cleaned = df_meta[export_cols].rename(columns={'emirates_id': region['id_label'].replace(' ', '_').lower()})
    st.download_button(
        label='Download Cleaned & Standardized CSV',
        data=cleaned.to_csv(index=False).encode('utf-8'),
        file_name=f'standardized_{selected_region.split()[0].lower()}.csv',
        mime='text/csv',
        use_container_width=True,
    )
    st.divider()
    if meta['total_normalized'] > 0:
        rows = []
        for i, r in df_meta.iterrows():
            ch = []
            if r['_changed_name']:
                ch.append(f'Name: {r["_orig_given"]} {r["_orig_family"]} -> {r["given_name"]} {r["family_name"]}')
            if r['_changed_dob']:
                ch.append(f'DOB: {r["_orig_dob"]} -> {r["date_of_birth"]}')
            if r['_changed_id']:
                ch.append(f'ID: {r["_orig_id"]} -> {r["emirates_id"]}')
            if ch:
                rows.append({'canonical_id': r.get('canonical_id', f'ROW_{i}'), 'Changes': ' | '.join(ch)})
        cdf = pd.DataFrame(rows)
        st.dataframe(cdf.head(200), use_container_width=True)
        st.download_button(
            label='Download Normalization Log (CSV)',
            data=cdf.to_csv(index=False).encode('utf-8'),
            file_name='normalization_log.csv', mime='text/csv',
        )
    st.divider()
    st.subheader('Source Data Quality Snapshot')
    c1, c2, c3 = st.columns(3)
    c1.metric('Total Records', meta['total_raw'])
    c2.metric(f'Missing {region["id_label"]}', meta['missing_ids'])
    c3.metric(f'Duplicate {region["id_label"]}', meta['dup_ids'])

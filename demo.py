'''
Identity Trust Assessment — application entry point.

Navigation is organised by task in the sidebar. Assessment state is held
in st.session_state so navigating between pages is instant.
'''
import io
import os
import re
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

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
import sys
from pathlib import Path

# Add the current file's directory to the system path
# This ensures the 'ui_theme' module can be found
sys.path.append(str(Path(__file__).resolve().parent))

import ui_theme as ui
import ui_theme as ui

try:
    from trust_layer.prior_auth_validators import validate_preauth
    PA_AVAILABLE = True
except ImportError:
    PA_AVAILABLE = False


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

PREFIXES = ['mr.', 'mrs.', 'ms.', 'dr.', 'mr ', 'mrs ', 'ms ', 'dr ']
SMALL_WORDS = {'and', 'of', 'the', 'at', 'in', 'on', 'for'}

GENDER_CANON = {'m': 'M', 'male': 'M', 'man': 'M',
                'f': 'F', 'female': 'F', 'woman': 'F',
                'o': 'O', 'other': 'O',
                'u': 'U', 'unknown': 'U'}

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
        'trusted_facilities': ['Cleveland Clinic Abu Dhabi', 'Ssmc', 'Al Noor Hospital',
                               'Tawam Hospital', 'Sheikh Khalifa Medical City'],
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
        'dob_min_year': 1900, 'dob_max_year': 2025,
    },
    'India (ABDM)': {
        'id_label': 'ABHA / Aadhaar',
        'id_pattern': r'^\d{12}$',
        'id_example': '123456789012',
        'regulatory_body': 'ABDM',
        'trusted_facilities': ['Manipal Hospital', 'Apollo Hospital', 'Fortis Healthcare',
                               'Max Healthcare', 'Aiims', 'Aiims Delhi', 'Narayana Health'],
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
        'dob_min_year': 1900, 'dob_max_year': 2025,
    },
}


# ============================================================
# Session state
# ============================================================
for _k, _v in {
    'region_name': 'UAE (DOH)',
    'assessment': None,
    'uploaded_name': None,
    'hl7_history': [],
    'batch_info': None,
    'hl7_validator': None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _get_config():
    return REGION_PROFILES[st.session_state['region_name']]


# ============================================================
# Normalization helpers
# ============================================================
def smart_title(s):
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w.title())
    t = ' '.join(out)
    return re.sub(r"'S\b", "'s", t)


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
    return smart_title(s) if s else ''


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


# ============================================================
# Region-aware validators
# ============================================================
def validate_completeness_region(rec, config):
    fields = {'emirates_id': rec.emirates_id, 'given_name': rec.given_name,
              'family_name': rec.family_name, 'date_of_birth': rec.date_of_birth}
    req = config['required_fields']
    present = sum(1 for f in req if fields.get(f))
    return round(present / len(req), 2) if req else 1.0


def validate_temporal_region(rec, config):
    if not rec.date_of_birth:
        return 0.0
    try:
        year = int(rec.date_of_birth[:4])
        return 1.0 if config['dob_min_year'] <= year <= config['dob_max_year'] else 0.3
    except (ValueError, TypeError):
        return 0.0


def validate_identity_region(rec, config):
    if not rec.emirates_id:
        return 0.0
    return 1.0 if re.match(config['id_pattern'], rec.emirates_id) else 0.3


def validate_provenance_region(rec, config):
    if not rec.source_facility:
        return 0.0
    return 1.0 if rec.source_facility in config['trusted_facilities'] else 0.7


class Record:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ============================================================
# Assessment pipeline
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
    total_normalized = int((df['_changed_name'] | df['_changed_dob'] | df['_changed_id'] |
                            df['_changed_gender'] | df['_changed_nationality']).sum())

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

        if critical_present < 2:
            decision = 'INSUFFICIENT_DATA'
            score = 0.0
            explanation = 'Record contains fewer than two of the four core identity fields (name, ID, DOB). Identity trust cannot be assessed reliably.'
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
                    missing_fields = [f for f, v in [(id_label, rec.emirates_id), ('Given Name', rec.given_name),
                                                     ('Family Name', rec.family_name), ('DOB', rec.date_of_birth)] if not v]
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

    log_batch(audit_entries, log_path=AUDIT_LOG_PATH, config_version='v0.7.0-demo',
              thresholds={'low': 0.75, 'medium': 0.45})

    results_df = pd.DataFrame(results)

    clinical_df = None
    clinical_meta = {'available': False}
    if coding_available:
        clinical_rows = []
        for _, row in df.iterrows():
            checks = assess_record(row.to_dict())
            clinical_rows.append({
                'canonical_id': row.get('canonical_id', '?'),
                'given_name': row.get('given_name', ''), 'family_name': row.get('family_name', ''),
                'diagnosis_code': row.get('diagnosis_code', ''), 'procedure_code': row.get('procedure_code', ''),
                'admission_date': row.get('admission_date', ''), 'discharge_date': row.get('discharge_date', ''),
                'triage_level': row.get('triage_level', ''), 'total_cost_aed': row.get('total_cost_aed', ''),
                'icd_exists': checks['icd_exists'], 'icd_cpt_match': checks['icd_cpt_match'],
                'episode_timeline': checks['episode_timeline'], 'admission_after_dob': checks['admission_after_dob'],
                'triage_cost': checks['triage_cost'], 'clinical_coherence_score': checks['clinical_coherence_score'],
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
            'given_name': row.get('given_name', ''), 'family_name': row.get('family_name', ''),
            'encounter_type': row.get('encounter_type', ''),
            'drg_readiness_score': r['drg_readiness_score'], 'applicable': r['applicable'],
            'missing_inputs': ', '.join(r['missing_inputs']), 'issues': ' | '.join(r['issues']),
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
            'given_name': row.get('given_name', ''), 'family_name': row.get('family_name', ''),
            'mds_score': mds['mds_score'], 'mds_missing': ', '.join(mds_missing) if mds_missing else '',
            'consent_score': consent['consent_score'],
            'consent_state': consent['consent_state'] if consent_available else 'N/A',
            'consent_issues': ' | '.join(consent['issues']),
            'pa_score': pa['pa_score'], 'pa_required': pa['pa_required'],
            'pa_present': pa['pa_present'], 'pa_issues': ' | '.join(pa['issues']),
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
        'input_columns': len(original_columns), 'mapped': len(mapping),
        'unresolved': unresolved, 'inferred': inferred, 'missing_canonical': missing_canonical,
        'coding_available': coding_available, 'drg_available': drg_available,
        'consent_available': consent_available, 'pa_available': pa_available_here and PA_AVAILABLE,
        'looks_like_output': looks_like_output, 'flag_rate': flag_rate,
        'flagged_count': flagged_count, 'total_records': total_records,
        'original_names': mapping,
    }

    meta = {'total_raw': total_raw, 'missing_ids': missing_ids,
            'missing_dob': missing_dob, 'dup_ids': dup_ids,
            'total_normalized': total_normalized}

    return results_df, meta, df, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema_report


# ============================================================
# Pages
# ============================================================
def pg_dashboard():
    st.title('Dashboard')
    st.caption('Batch overview. Load a file from Batch Upload, or paste messages in HL7 Stream.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded yet. Go to **Analyze → Batch Upload** to load a CSV.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result
    ui.batch_header(st.session_state.get('batch_info'), st.session_state['region_name'], results_df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Total Records', len(results_df))
    c2.metric('Auto-Linked', len(results_df[results_df['decision'] == 'AUTO_LINK']))
    c3.metric('Flagged', len(results_df[results_df['decision'] == 'LINK_WITH_FLAG']))
    c4.metric('Quarantined', len(results_df[results_df['decision'] == 'QUARANTINE']))
    c5.metric('Insufficient Data', len(results_df[results_df['decision'] == 'INSUFFICIENT_DATA']))

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('**Decision breakdown**')
        dc = results_df['decision'].value_counts().reset_index()
        dc.columns = ['Decision', 'Count']
        dc['Decision'] = dc['Decision'].map(lambda d: ui.DECISION_LABELS.get(d, d))
        st.altair_chart(ui.decision_chart(dc, height=250), use_container_width=True)

    with col_b:
        st.markdown('**Facility risk profile**')
        fl = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])]
        if not fl.empty:
            fac = fl['source_facility'].replace('', '(unset)').value_counts().reset_index()
            fac.columns = ['Facility', 'Flagged Count']
            st.altair_chart(ui.bar_chart(fac, 'Flagged Count', 'Facility', color=ui.BAD, height=250,
                                         x_title='Flagged records'), use_container_width=True)
        else:
            st.info('No records were flagged.')

    st.markdown('**Dimension scoring averages**')
    dm = results_df[['dim_completeness', 'dim_temporal', 'dim_identity', 'dim_provenance', 'dim_cross_record']].mean().reset_index()
    dm.columns = ['Dimension', 'Average Score']
    dm['Dimension'] = ['Completeness', 'Temporal', 'Identity', 'Provenance', 'Cross-Record']
    st.altair_chart(ui.bar_chart(dm, 'Average Score', 'Dimension', color=ui.ACCENT, height=220, domain=[0, 1]),
                    use_container_width=True)


def pg_hl7():
    st.title('HL7 Stream')
    st.caption('Paste one or more HL7 v2 ADT messages. Each is parsed, scored against the five identity dimensions, and routed. The session validator remembers past messages, so a second message with the same identifier triggers a collision.')

    st.info('In production, messages arrive continuously from the hospital interface engine via the FastAPI endpoint (`/assess-hl7`). This page demonstrates the same parser and scoring logic on pasted input.')

    default_msg = (
        'MSH|^~\\&|HIS|CLEVELAND CLINIC ABU DHABI|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r'
        'EVN|A04|20240110120000\r'
        'PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M\r'
        'PV1|1|O'
    )

    _, col_b = st.columns([3, 1])
    with col_b:
        if st.button('Reset session validator', use_container_width=True):
            st.session_state['hl7_history'] = []
            st.session_state['hl7_validator'] = None
            st.success('Session cleared.')

    hl7_input = st.text_area('HL7 v2 message(s). Separate multiple messages with a blank line.',
                             value=default_msg, height=220)

    if st.button('Parse and assess', type='primary'):
        raw_msgs = [m.strip() for m in re.split(r'\n\s*\n', hl7_input) if m.strip()]
        if not raw_msgs:
            st.error('No message found.')
            return

        config = _get_config()

        if st.session_state['hl7_validator'] is None:
            class _V:
                def __init__(self):
                    self.identifier_index = {}
                    self.name_dob_index = {}
                def add_record(self, r):
                    if getattr(r, 'emirates_id', None):
                        self.identifier_index.setdefault(r.emirates_id, set()).add(r.canonical_id)
                    key = ((getattr(r, 'given_name', '') or '').strip().lower(),
                           (getattr(r, 'family_name', '') or '').strip().lower(),
                           getattr(r, 'date_of_birth', '') or '')
                    if key != ('', '', ''):
                        self.name_dob_index.setdefault(key, set()).add(r.canonical_id)
                def validate(self, r):
                    eid = getattr(r, 'emirates_id', None)
                    if eid and eid in self.identifier_index:
                        if r.canonical_id not in self.identifier_index[eid]:
                            return 0.0
                    key = ((getattr(r, 'given_name', '') or '').strip().lower(),
                           (getattr(r, 'family_name', '') or '').strip().lower(),
                           getattr(r, 'date_of_birth', '') or '')
                    if key != ('', '', '') and key in self.name_dob_index:
                        if r.canonical_id not in self.name_dob_index[key]:
                            return 0.5
                    return 1.0
            st.session_state['hl7_validator'] = _V()

        validator = st.session_state['hl7_validator']
        from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure

        for i, msg in enumerate(raw_msgs):
            st.markdown(f'---\n### Message {i + 1}')

            ok, issues = validate_hl7_structure(msg)
            if not ok:
                st.error(f'Invalid HL7 structure: {"; ".join(issues)}')
                continue

            parsed = parse_hl7_message(msg)

            with st.expander('Parsed fields', expanded=False):
                for label, value in [('Emirates ID', parsed.get('emirates_id')),
                                     ('Given name', parsed.get('given_name')),
                                     ('Family name', parsed.get('family_name')),
                                     ('Gender', parsed.get('gender')),
                                     ('Date of birth', parsed.get('date_of_birth')),
                                     ('Source facility', parsed.get('source_facility')),
                                     ('Canonical ID', parsed.get('canonical_id')),
                                     ('Encounter type', parsed.get('encounter_type'))]:
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

            dims = {'completeness': completeness, 'temporal': temporal, 'identity': identity,
                    'provenance': provenance, 'cross_record': validator.validate(rec)}
            score = compute_trust_score(**dims)
            decision = route_decision_hard(score, dims['cross_record'])

            cc1, cc2 = st.columns(2)
            cc1.metric('Trust Score', f'{score:.3f}')
            cc2.metric('Decision', ui.DECISION_LABELS.get(decision, decision))

            if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
                if dims['cross_record'] == 0.0:
                    st.error(f'Identifier collision: {config["id_label"]} is already registered to a different patient.')
                else:
                    st.warning(f'Routed for review. Weakest dimension: {min(dims, key=dims.get)}.')

            with st.expander('Dimension scores'):
                for label, key in [('Completeness', 'completeness'), ('Temporal', 'temporal'),
                                   ('Identity', 'identity'), ('Provenance', 'provenance'),
                                   ('Cross-record', 'cross_record')]:
                    ui.dimension_bar(label, dims[key])

            validator.add_record(rec)
            st.session_state['hl7_history'].append({
                'msg_index': i + 1, 'canonical_id': rec.canonical_id,
                'emirates_id': rec.emirates_id,
                'name': f'{rec.given_name} {rec.family_name}',
                'decision': ui.DECISION_LABELS.get(decision, decision),
                'trust_score': round(score, 3),
            })

        if st.session_state['hl7_history']:
            st.divider()
            st.markdown('### Session history')
            st.dataframe(pd.DataFrame(st.session_state['hl7_history']), use_container_width=True)


def pg_batch():
    st.title('Batch Upload')
    st.caption('Upload a CSV of patient records. The schema mapper handles arbitrary column names. The pipeline processes whatever identity, clinical, and governance fields are present.')

    st.markdown('**Generate a sample**')
    if st.button(f'Generate {st.session_state["region_name"]} sample (100 records)'):
        sample_df = generate_sample(st.session_state['region_name'], n=100)
        st.download_button(
            label='Download generated sample',
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
    st.success('Processed. Open Dashboard or Reports in the sidebar to view results.')

    schema = result[9]
    if schema['looks_like_output']:
        st.error('This file appears to be a scored export from another system, not raw patient records.')
    if schema['flag_rate'] >= 0.90 and schema['total_records'] > 20:
        st.warning(f'{schema["flag_rate"]*100:.0f}% of records were flagged ({schema["flagged_count"]} of {schema["total_records"]}). This usually means the file is missing critical identity columns.')

    with st.expander('Schema analysis', expanded=True):
        st.markdown(f'**Input:** {schema["input_columns"]} columns · **Mapped:** {schema["mapped"]} columns')
        if schema['inferred']:
            st.markdown('**Auto-detected by content:**')
            for item in schema['inferred']:
                st.markdown(f"- `{item['column']}` → `{item['field']}`")
        if schema['unresolved']:
            st.markdown(f'**Unrecognised columns:** ' + ', '.join(f'`{c}`' for c in schema['unresolved']))
        if schema['missing_canonical']:
            core = [f for f in schema['missing_canonical'] if f in ('emirates_id', 'given_name', 'family_name', 'date_of_birth')]
            if core:
                st.markdown(f'**Core identity fields missing:** ' + ', '.join(f'`{f}`' for f in core))


def pg_report():
    st.title('Summary Report')
    st.caption('A one-page report for the current batch. Download as HTML and print to PDF from your browser.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    results_df, meta, df_meta, clinical_df, clinical_meta, drg_df, drg_meta, gov_df, gov_meta, schema = result
    report_html = ui.build_report_html(
        st.session_state.get('batch_info'), st.session_state['region_name'], _get_config(),
        results_df, schema, clinical_meta, drg_meta, gov_meta,
    )

    st.download_button(
        label='Download report (HTML, print to PDF)',
        data=report_html.encode('utf-8'),
        file_name=f'data_quality_report_{datetime.now().strftime("%Y%m%d_%H%M")}.html',
        mime='text/html',
        type='primary',
    )
    import streamlit.components.v1 as components
    components.html(report_html, height=1100, scrolling=True)


def pg_flagged():
    st.title('Flagged Records')
    st.caption('Records routed for manual review.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    results_df = result[0]
    flagged = results_df[results_df['decision'].isin(['LINK_WITH_FLAG', 'QUARANTINE', 'INSUFFICIENT_DATA'])].copy()
    if flagged.empty:
        st.success('No flagged records.')
        return

    pri = {'INSUFFICIENT_DATA': 0, 'QUARANTINE': 1, 'LINK_WITH_FLAG': 2}
    flagged['_p'] = flagged['decision'].map(pri)
    flagged = flagged.sort_values(['_p', 'trust_score']).drop(columns='_p')

    fc1, fc2 = st.columns(2)
    with fc1:
        io_opt = sorted(flagged['primary_issue'].unique().tolist())
        sel_issues = st.multiselect('Issue type', options=io_opt, default=io_opt)
    with fc2:
        d_opt = sorted(flagged['decision'].unique().tolist())
        sel_dec = st.multiselect('Decision', options=d_opt, default=d_opt)

    filtered = flagged[flagged['primary_issue'].isin(sel_issues) & flagged['decision'].isin(sel_dec)]
    st.caption(f'Showing {len(filtered)} of {len(flagged)} records.')

    with st.expander('Bulk actions'):
        st.code('\n'.join(filtered['canonical_id'].astype(str).tolist()), language=None)

    STEP = 100
    if 'show_count' not in st.session_state:
        st.session_state.show_count = STEP
    to_render = filtered.head(st.session_state.show_count)

    for _, row in to_render.iterrows():
        label = ui.DECISION_LABELS.get(row['decision'], row['decision'])
        with st.expander(f'{row["canonical_id"]} · {row["given_name"] or "(no name)"} {row["family_name"]} · {label}'):
            st.markdown(ui.badge(row['decision']), unsafe_allow_html=True)
            st.code(row['canonical_id'], language=None)
            st.write(f'**Trust score:** {row["trust_score"]}')
            st.write(f'**Primary issue:** {row["primary_issue"]}')
            st.info(row['explanation'])
            for lbl, col in [('Completeness', 'dim_completeness'), ('Temporal', 'dim_temporal'),
                             ('Identity', 'dim_identity'), ('Provenance', 'dim_provenance'),
                             ('Cross-record', 'dim_cross_record')]:
                ui.dimension_bar(lbl, row[col])

    if len(filtered) > st.session_state.show_count:
        if st.button('Load more'):
            st.session_state.show_count += STEP
            st.rerun()

    st.download_button(
        label='Download filtered records (CSV)',
        data=filtered.to_csv(index=False).encode('utf-8'),
        file_name='flagged_records.csv', mime='text/csv',
    )


def pg_coding():
    st.title('Coding Coherence')
    st.caption('Rule-based checks on diagnosis codes, procedure codes, and episode timelines.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    clinical_df, clinical_meta = result[3], result[4]
    if not clinical_meta.get('available'):
        st.info('This check could not run — the uploaded file has no populated diagnosis_code or procedure_code column.')
        return

    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric('ICD issues', clinical_meta['icd_issues'])
    cc2.metric('ICD-CPT mismatches', clinical_meta['icd_cpt_mismatches'])
    cc3.metric('Timeline errors', clinical_meta['timeline_errors'])
    cc4.metric('Triage-cost anomalies', clinical_meta['triage_anomalies'])

    issue_counts = pd.DataFrame({
        'Issue': ['ICD issues', 'ICD-CPT mismatches', 'Timeline errors', 'Triage-cost anomalies', 'Duplicate episodes'],
        'Count': [clinical_meta['icd_issues'], clinical_meta['icd_cpt_mismatches'],
                  clinical_meta['timeline_errors'], clinical_meta['triage_anomalies'],
                  len(clinical_meta['duplicate_episodes'])],
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
            label='Download coding coherence report (CSV)',
            data=problematic.to_csv(index=False).encode('utf-8'),
            file_name='coding_coherence_report.csv', mime='text/csv',
        )


def pg_drg():
    st.title('DRG Readiness')
    st.caption('Whether inpatient records have every input the IR-DRG grouper needs.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    drg_df, drg_meta = result[5], result[6]
    if not drg_meta.get('available'):
        st.info('This check could not run — the uploaded file has no populated encounter_type column.')
        return

    d1, d2, d3, d4 = st.columns(4)
    d1.metric('Inpatient records', drg_meta['inpatient_count'])
    d2.metric('Fully ready', drg_meta['fully_ready'])
    d3.metric('Partial', drg_meta['partial'])
    d4.metric('Not ready', drg_meta['not_ready'])

    readiness_counts = pd.DataFrame({
        'Status': ['Fully ready', 'Partial', 'Not ready'],
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
        miss_df = pd.DataFrame([{'Field': k, 'Records Missing': v}
                                for k, v in sorted(missing_counter.items(), key=lambda x: -x[1])])
        st.markdown('**Most common missing inputs**')
        st.altair_chart(ui.bar_chart(miss_df, 'Records Missing', 'Field', color=ui.WARN, height=240),
                        use_container_width=True)

    problematic_drg = drg_df[(drg_df['applicable'] == True) &
                             ((drg_df['drg_readiness_score'] < 1.0) | (drg_df['issues'] != ''))].copy()

    if not problematic_drg.empty:
        st.dataframe(problematic_drg, use_container_width=True)
        st.download_button(
            label='Download DRG readiness report (CSV)',
            data=problematic_drg.to_csv(index=False).encode('utf-8'),
            file_name='drg_readiness_report.csv', mime='text/csv',
        )


def pg_gov():
    st.title('Data Governance')
    st.caption('Minimum Data Set completeness, consent compliance, and prior-authorization.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    gov_df, gov_meta = result[7], result[8]

    g1, g2, g3, g4 = st.columns(4)
    g1.metric('Mean MDS score', f'{gov_meta["mean_mds"]:.3f}')
    g2.metric('Below 80% MDS', gov_meta['below_80'])
    g3.metric('Consent blocked', gov_meta['consent_blocked'] if gov_meta['consent_available'] else 'N/A')
    g4.metric('Consent missing', gov_meta['consent_missing'] if gov_meta['consent_available'] else 'N/A')

    if gov_meta['consent_available'] and gov_meta['consent_blocked'] > 0:
        st.error(f'{gov_meta["consent_blocked"]} record(s) have denied or withdrawn consent — these must not be shared without further review.')
    if gov_meta['pa_available'] and gov_meta['pa_missing'] > 0:
        st.error(f'{gov_meta["pa_missing"]} claim(s) will be rejected: procedure requires pre-authorization but no PA reference is on file.')

    st.divider()

    mds_buckets = pd.DataFrame({
        'Bucket': ['Perfect (1.0)', 'Good (0.80-0.99)', 'Partial (0.60-0.79)', 'Poor (<0.60)'],
        'Count': [int((gov_df['mds_score'] >= 0.999).sum()),
                  int(((gov_df['mds_score'] >= 0.80) & (gov_df['mds_score'] < 0.999)).sum()),
                  int(((gov_df['mds_score'] >= 0.60) & (gov_df['mds_score'] < 0.80)).sum()),
                  int((gov_df['mds_score'] < 0.60).sum())],
    })
    st.markdown('**MDS completeness distribution**')
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
            label='Download governance report (CSV)',
            data=problematic_gov.to_csv(index=False).encode('utf-8'),
            file_name='governance_report.csv', mime='text/csv',
        )


def pg_audit():
    st.title('Audit Trail')
    st.caption('Tamper-evident log of every decision in the current session.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

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
                st.download_button('Download audit log (JSONL)', data=f.read(),
                                   file_name='audit_log.jsonl', mime='application/jsonl')


def pg_standardization():
    st.title('Standardization')
    st.caption('What was cleaned before scoring, and the export of the standardized file.')

    result = st.session_state.get('assessment')
    if result is None:
        st.info('No batch loaded. Go to Analyze → Batch Upload.')
        return

    meta, df_meta, schema = result[1], result[2], result[9]
    st.metric('Records standardized', meta['total_normalized'])

    export_cols = ['canonical_id', 'emirates_id', 'given_name', 'family_name',
                   'date_of_birth', 'gender', 'nationality', 'source_facility', 'registration_date']
    export_cols = [c for c in export_cols if c in df_meta.columns]
    cleaned = df_meta[export_cols].copy()
    cleaned = cleaned.rename(columns=schema.get('original_names', {}))

    st.download_button(
        label='Download cleaned & standardized CSV',
        data=cleaned.to_csv(index=False).encode('utf-8'),
        file_name=f'standardized_{st.session_state["region_name"].split()[0].lower()}.csv',
        mime='text/csv',
    )

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
            if r['_changed_gender']:
                ch.append(f'Gender: {r["_orig_gender"]} -> {r["gender"]}')
            if r['_changed_nationality']:
                ch.append(f'Nationality: {r["_orig_nationality"]} -> {r["nationality"]}')
            if ch:
                rows.append({'canonical_id': r.get('canonical_id', f'ROW_{i}'), 'Changes': ' | '.join(ch)})
        cdf = pd.DataFrame(rows)
        st.dataframe(cdf.head(200), use_container_width=True)
        st.download_button('Download normalization log (CSV)',
                           data=cdf.to_csv(index=False).encode('utf-8'),
                           file_name='normalization_log.csv', mime='text/csv')


def pg_config():
    st.title('Configuration')
    st.caption('Region profile. Changes apply immediately across the app.')

    selected_region = st.selectbox(
        'Region profile',
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


def pg_about():
    st.title('About')

    st.markdown('''
### What this tool does

A pre-submission trust gate for patient records in a health information exchange. Every incoming record is scored across five identity dimensions and routed to one of four outcomes. It does not merge records, resolve collisions, or auto-correct data. It identifies problems, explains them, and hands control to a human.

### The five dimensions

| Dimension | Weight | Check |
|---|---|---|
| Completeness | 0.20 | Required identity fields present |
| Temporal validity | 0.15 | Plausible date of birth |
| Identity consistency | 0.20 | ID format matches region standard |
| Provenance | 0.15 | Trusted source facility |
| Cross-record consistency | 0.30 | Collision with existing patient |

### Module checks

- **Coding coherence** — ICD validity, ICD-CPT match, episode timeline, triage-cost anomaly
- **DRG readiness** — mandatory inputs for IR-DRG grouping
- **MDS completeness** — NABIDH/Malaffi minimum data set
- **Consent compliance** — granted / restricted / denied / withdrawn
- **Prior authorization** — DHA/DOH pre-auth presence

### Scoring configuration notice

This demo uses a revised scoring configuration, tuned separately from the published paper's validated configuration.

- **Composite formula:** weighted sum × (0.4 + 0.6 × weakest dimension score)
- **Auto-link threshold:** 0.75 (paper: 0.952)
- **Quarantine threshold:** 0.45 (paper: 0.571)

The revised values were tuned for realistic flag rates on messy data. A hospital pilot should re-derive both using the paper's methodology.

### Deployment

- **Batch path:** CSV upload for retrospective analysis and pre-pilot proof of concept.
- **Real-time path:** FastAPI service (`app.py`) with a `/assess-hl7` endpoint. Deployed as a Docker container inside hospital infrastructure. Reads HL7 v2 ADT messages directly from the interface engine.

No patient data leaves the hospital network in production.

### Privacy

This demo uses synthetic data only. Do not upload real patient health information.
    ''')


# ============================================================
# Router
# ============================================================
pages = {
    'Overview': [
        st.Page(pg_dashboard, title='Dashboard', icon=':material/dashboard:', default=True),
    ],
    'Analyze': [
        st.Page(pg_hl7, title='HL7 Stream', icon=':material/sensors:'),
        st.Page(pg_batch, title='Batch Upload', icon=':material/upload_file:'),
    ],
    'Reports': [
        st.Page(pg_report, title='Summary Report', icon=':material/description:'),
        st.Page(pg_flagged, title='Flagged Records', icon=':material/flag:'),
        st.Page(pg_coding, title='Coding Coherence', icon=':material/stethoscope:'),
        st.Page(pg_drg, title='DRG Readiness', icon=':material/request_quote:'),
        st.Page(pg_gov, title='Data Governance', icon=':material/shield:'),
    ],
    'Compliance': [
        st.Page(pg_audit, title='Audit Trail', icon=':material/receipt_long:'),
        st.Page(pg_standardization, title='Standardization', icon=':material/cleaning_services:'),
    ],
    'Settings': [
        st.Page(pg_config, title='Configuration', icon=':material/settings:'),
        st.Page(pg_about, title='About', icon=':material/info:'),
    ],
}

with st.sidebar:
    ui.sidebar_brand(st.session_state['region_name'])
    ui.sidebar_note()

pg = st.navigation(pages)
pg.run()

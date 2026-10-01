'''
Coding and episode coherence checks for UAE healthcare data.
Standalone module — no dependencies on the Streamlit demo.

Design principle: only deterministic, rule-based checks. No clinical judgment.
Every flag traces to a specific, verifiable condition.
'''
import re
from datetime import datetime


# ============================================================
# ICD-10 EXISTENCE CHECK
# Curated subset for the demo. Replace with the full WHO ICD-10
# catalogue (~70k codes) before production.
# ============================================================
VALID_ICD10_PREFIXES = {
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
    'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
    'V', 'W', 'X', 'Y', 'Z',
}

VALID_ICD10_CODES = {
    'E11', 'E11.9', 'I10', 'J45', 'J45.9', 'K21', 'K21.0', 'K21.9',
    'M54', 'M54.5', 'F41', 'F41.1', 'F41.9', 'J06', 'J06.9',
    'N39', 'N39.0', 'I25', 'I25.9', 'E78', 'E78.5',
}


def validate_icd_code(code):
    '''Returns 1.0 if valid and known, 0.3 if structurally valid but
    not in our curated list, 0.0 if malformed.'''
    if not code or str(code).strip() == '':
        return 0.0
    code = str(code).strip().upper()

    if not re.match(r'^[A-Z]\d{2}(\.\d{1,2})?$', code):
        return 0.0

    if code[0] not in VALID_ICD10_PREFIXES:
        return 0.0

    if code in VALID_ICD10_CODES:
        return 1.0

    return 0.3


# ============================================================
# ICD-CPT COHERENCE
# Curated crosswalk for the demo. Real version needs a proper
# ICD-10-CM to CPT crosswalk table.
# ============================================================
PLAUSIBLE_CPT_FOR_ICD = {
    'E11':   {'83036', '82947', '99213', '99214'},
    'E11.9': {'83036', '82947', '99213', '99214'},
    'I10':   {'99213', '99214', '93000'},
    'J45':   {'94010', '99214', '99213'},
    'J45.9': {'94010', '99214', '99213'},
    'K21':   {'43239', '99213'},
    'K21.0': {'43239', '99213'},
    'K21.9': {'43239', '99213'},
    'M54':   {'97110', '99213'},
    'M54.5': {'97110', '99213'},
    'F41':   {'90834', '99214'},
    'F41.1': {'90834', '99214'},
    'F41.9': {'90834', '99214'},
    'J06':   {'99213', '87880'},
    'J06.9': {'99213', '87880'},
    'N39':   {'81002', '99213'},
    'N39.0': {'81002', '99213'},
    'I25':   {'93000', '93306'},
    'I25.9': {'93000', '93306'},
    'E78':   {'80061', '99214'},
    'E78.5': {'80061', '99214'},
}


def validate_icd_cpt_match(icd_code, cpt_code):
    '''Returns 1.0 if the procedure is plausible for the diagnosis,
    0.3 if we do not have a mapping, 0.0 if clearly mismatched.'''
    if not icd_code or not cpt_code:
        return 0.0
    icd = str(icd_code).strip().upper()
    cpt = str(cpt_code).strip()

    if icd in PLAUSIBLE_CPT_FOR_ICD:
        if cpt in PLAUSIBLE_CPT_FOR_ICD[icd]:
            return 1.0
        return 0.0

    return 0.3


# ============================================================
# EPISODE TIMELINE COHERENCE
# ============================================================
def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip()[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def validate_episode_timeline(admission_date, discharge_date):
    '''Returns 1.0 coherent, 0.3 suspicious (long stay), 0.0 inverted/missing.'''
    adm = _parse_date(admission_date)
    dis = _parse_date(discharge_date)
    if adm is None or dis is None:
        return 0.0
    if dis < adm:
        return 0.0
    if (dis - adm).days > 365:
        return 0.3
    return 1.0


def validate_admission_after_dob(admission_date, date_of_birth):
    '''Admission cannot be before the patient was born.'''
    adm = _parse_date(admission_date)
    dob = _parse_date(date_of_birth)
    if adm is None or dob is None:
        return 0.0
    if adm < dob:
        return 0.0
    return 1.0


# ============================================================
# DUPLICATE EPISODE DETECTION
# ============================================================
def find_duplicate_episodes(records):
    '''records: list of dicts with episode_id and canonical_id.
    Returns dict mapping duplicated episode_id -> list of canonical_ids.'''
    idx = {}
    for r in records:
        ep = r.get('episode_id')
        if not ep:
            continue
        idx.setdefault(ep, []).append(r.get('canonical_id', '?'))
    return {ep: ids for ep, ids in idx.items() if len(ids) > 1}


# ============================================================
# TRIAGE-COST ANOMALY (DOH-specific pattern)
# High cost with low triage, or low cost with high triage.
# ============================================================
def validate_triage_cost(triage_level, total_cost_aed):
    '''Returns 1.0 normal, 0.3 missing, 0.0 anomalous.'''
    if triage_level is None or total_cost_aed is None:
        return 0.3
    try:
        t = int(triage_level)
        c = float(total_cost_aed)
    except (ValueError, TypeError):
        return 0.3

    if not (1 <= t <= 5):
        return 0.0

    if t >= 3 and c > 10000:
        return 0.0
    if t <= 2 and c < 500:
        return 0.0

    return 1.0


# ============================================================
# RUN ALL CHECKS ON A SINGLE RECORD
# ============================================================
def assess_record(rec):
    '''rec: dict-like row. Returns individual check scores and an
    aggregate clinical coherence score.'''
    icd = rec.get('diagnosis_code')
    cpt = rec.get('procedure_code')
    adm = rec.get('admission_date')
    dis = rec.get('discharge_date')
    dob = rec.get('date_of_birth')
    tri = rec.get('triage_level')
    cost = rec.get('total_cost_aed')

    checks = {
        'icd_exists': validate_icd_code(icd),
        'icd_cpt_match': validate_icd_cpt_match(icd, cpt),
        'episode_timeline': validate_episode_timeline(adm, dis),
        'admission_after_dob': validate_admission_after_dob(adm, dob),
        'triage_cost': validate_triage_cost(tri, cost),
    }

    valid = list(checks.values())
    checks['clinical_coherence_score'] = round(sum(valid) / len(valid), 3) if valid else 0.0
    return checks

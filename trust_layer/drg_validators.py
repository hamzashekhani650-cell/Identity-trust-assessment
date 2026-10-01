'''
IR-DRG grouper readiness validation for UAE inpatient encounters.

SCOPE: This module validates whether a record has every input the 3M
IR-DRG grouper needs to succeed. It does NOT perform actual DRG grouping
— the 3M rule tables are proprietary. This is a pre-submission check that
catches missing or malformed inputs before the grouper runs.

Aligned with DOH Abu Dhabi Claims & Adjudication Rules V2025.1 and
Addendum 06 (inpatient payment requires a valid IR-DRG code).
'''
import re
from datetime import datetime


INPATIENT_ENCOUNTER_TYPES = {'3', '4', 'I', 'INPATIENT', 'IP', 'INPATIENT_STAY'}

# Format for a valid IR-DRG code — e.g. G70A, F62B, I01Z.
# The structure is: one letter (MDC), two digits (DRG number), one letter
# (severity/complication split A/B/C/D/Z).
IR_DRG_PATTERN = r'^[A-Z]\d{2}[A-Z]$'

# DOH procedure categories that typically require laterality specification
LATERALITY_REQUIRED_PROCEDURE_PREFIXES = {
    '0SB', '0SC', '0SD',  # knee replacements
    '0SR', '0SQ',          # hip replacements
    '0PB', '0PC',          # shoulder
    '0TC', '0TD',          # foot/ankle
    '0LB', '0LC',          # eye/ear
}

VALID_SEVERITY_SPLITS = {'A', 'B', 'C', 'D', 'Z'}


def _is_present(v):
    if v is None:
        return False
    s = str(v).strip().upper()
    return s != '' and s not in ('NAN', 'NAT', 'NONE')


def _is_inpatient(rec):
    et = str(rec.get('encounter_type', '')).strip().upper()
    return et in INPATIENT_ENCOUNTER_TYPES


def _is_valid_iso_date(v):
    if not _is_present(v):
        return False
    try:
        datetime.strptime(str(v).strip()[:10], '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def validate_drg_inputs(rec):
    '''
    Checks whether every required input for DRG grouping is present.
    Only applies to inpatient encounters. Outpatient records return a
    neutral score.

    Returns dict with readiness_score (0-1), missing_inputs (list),
    issues (list).
    '''
    if not _is_inpatient(rec):
        return {
            'readiness_score': 1.0,
            'applicable': False,
            'missing_inputs': [],
            'issues': [],
        }

    missing = []
    issues = []

    # Required for every inpatient DRG assignment
    if not _is_present(rec.get('diagnosis_code')):
        missing.append('principal diagnosis (ICD-10 code)')

    if not _is_present(rec.get('gender')):
        missing.append('administrative sex')

    if not _is_valid_iso_date(rec.get('date_of_birth')):
        missing.append('date of birth (for age derivation)')

    # At least one secondary diagnosis is required to justify severity
    # splits (CC/MCC in 3M terminology). We accept a simple presence check
    # on either an explicit count or a delimited list.
    secondary = rec.get('secondary_diagnoses') or rec.get('secondary_diagnosis_count')
    if not _is_present(secondary):
        missing.append('secondary diagnoses (required for severity assignment)')

    # Discharge summary required for documentation of inpatient stay
    if not _is_present(rec.get('discharge_summary')):
        missing.append('discharge summary')

    # Procedures are needed only for surgical DRGs — we cannot know from
    # the code alone whether it's surgical. We flag the absence rather
    # than fail the record.
    if not _is_present(rec.get('procedure_code')):
        issues.append('DRG-1: no procedure code present — if surgical DRG applies, grouping will fail')

    # Compute score
    total_expected = 5  # the five checks above that append to `missing`
    score = max(0.0, (total_expected - len(missing)) / total_expected)

    return {
        'readiness_score': round(score, 3),
        'applicable': True,
        'missing_inputs': missing,
        'issues': issues,
    }


def validate_drg_code_format(rec):
    '''
    If a DRG code is present on the record, validate its format.
    Absence is not an error here — that's caught by validate_drg_inputs.
    '''
    code = rec.get('drg_code')
    if not _is_present(code):
        return {'drg_code_valid': None, 'issues': []}

    c = str(code).strip().upper()

    if not re.match(IR_DRG_PATTERN, c):
        return {
            'drg_code_valid': False,
            'issues': [f'DRG-2: drg_code {c!r} does not match IR-DRG format (example: G70A)'],
        }

    severity = c[-1]
    if severity not in VALID_SEVERITY_SPLITS:
        return {
            'drg_code_valid': False,
            'issues': [f'DRG-3: drg_code {c!r} has unrecognised severity split {severity!r}'],
        }

    return {'drg_code_valid': True, 'issues': []}


def validate_laterality(rec):
    '''
    Procedures known to require laterality specification. If the
    procedure code starts with a laterality-sensitive prefix and no
    laterality field is populated, flag it.
    '''
    proc = rec.get('procedure_code')
    if not _is_present(proc):
        return {'laterality_ok': None, 'issues': []}

    p = str(proc).strip().upper().replace('.', '')
    prefix3 = p[:3]

    if prefix3 in LATERALITY_REQUIRED_PROCEDURE_PREFIXES:
        lat = rec.get('laterality')
        if not _is_present(lat):
            return {
                'laterality_ok': False,
                'issues': [f'DRG-4: procedure {p!r} requires laterality (L/R/B) but none is recorded'],
            }
        if str(lat).strip().upper() not in {'L', 'R', 'B', 'LEFT', 'RIGHT', 'BILATERAL'}:
            return {
                'laterality_ok': False,
                'issues': [f'DRG-5: laterality {lat!r} is not a recognised value'],
            }

    return {'laterality_ok': True, 'issues': []}


def assess_drg_readiness(rec):
    '''
    Aggregate all DRG-readiness checks for one record. Returns a dict
    with the composite readiness score and all accumulated issues.
    '''
    inputs = validate_drg_inputs(rec)
    code = validate_drg_code_format(rec)
    laterality = validate_laterality(rec)

    all_issues = inputs['issues'] + code['issues'] + laterality['issues']

    # Composite score: weighted average of the three sub-checks.
    # If not applicable (outpatient), skip the check entirely.
    if not inputs['applicable']:
        composite = 1.0
    else:
        subscores = [inputs['readiness_score']]
        if code['drg_code_valid'] is not None:
            subscores.append(1.0 if code['drg_code_valid'] else 0.0)
        if laterality['laterality_ok'] is not None:
            subscores.append(1.0 if laterality['laterality_ok'] else 0.0)
        composite = sum(subscores) / len(subscores)

    return {
        'drg_readiness_score': round(composite, 3),
        'applicable': inputs['applicable'],
        'missing_inputs': inputs['missing_inputs'],
        'issues': all_issues,
    }


def drg_readiness_batch(records):
    '''
    Aggregate over a list of records. Returns counts of records that are
    fully ready, partially ready, and not ready for grouping.
    '''
    results = [assess_drg_readiness(r) for r in records]
    applicable = [r for r in results if r['applicable']]

    if not applicable:
        return {
            'total': len(records), 'applicable': 0,
            'ready': 0, 'partial': 0, 'not_ready': 0,
            'mean_readiness': 1.0,
        }

    ready = sum(1 for r in applicable if r['drg_readiness_score'] >= 0.95)
    partial = sum(1 for r in applicable if 0.5 <= r['drg_readiness_score'] < 0.95)
    not_ready = sum(1 for r in applicable if r['drg_readiness_score'] < 0.5)
    mean = sum(r['drg_readiness_score'] for r in applicable) / len(applicable)

    return {
        'total': len(records),
        'applicable': len(applicable),
        'ready': ready,
        'partial': partial,
        'not_ready': not_ready,
        'mean_readiness': round(mean, 3),
    }

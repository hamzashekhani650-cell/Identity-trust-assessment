import re
from datetime import datetime


INPATIENT_ENCOUNTER_TYPES = {'3', '4', 'I', 'INPATIENT', 'IP', 'INPATIENT_STAY'}

IR_DRG_PATTERN = r'^[A-Z]\d{2}[A-Z]$'

LATERALITY_REQUIRED_PROCEDURE_PREFIXES = {
    '0SB', '0SC', '0SD', '0SR', '0SQ', '0PB', '0PC',
    '0TC', '0TD', '0LB', '0LC',
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
    if not _is_inpatient(rec):
        return {
            'readiness_score': 1.0,
            'applicable': False,
            'missing_inputs': [],
            'issues': [],
        }

    missing = []
    issues = []

    if not _is_present(rec.get('diagnosis_code')):
        missing.append('principal diagnosis (ICD-10 code)')

    if not _is_present(rec.get('gender')):
        missing.append('administrative sex')

    if not _is_valid_iso_date(rec.get('date_of_birth')):
        missing.append('date of birth (for age derivation)')

    secondary = rec.get('secondary_diagnoses') or rec.get('secondary_diagnosis_count')
    if not _is_present(secondary):
        missing.append('secondary diagnoses (required for severity assignment)')

    if not _is_present(rec.get('discharge_summary')):
        missing.append('discharge summary')

    if not _is_present(rec.get('procedure_code')):
        issues.append('DRG-1: no procedure code present — surgical DRG will fail')

    total_expected = 5
    score = max(0.0, (total_expected - len(missing)) / total_expected)

    return {
        'readiness_score': round(score, 3),
        'applicable': True,
        'missing_inputs': missing,
        'issues': issues,
    }


def validate_drg_code_format(rec):
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
    inputs = validate_drg_inputs(rec)
    code = validate_drg_code_format(rec)
    laterality = validate_laterality(rec)

    all_issues = inputs['issues'] + code['issues'] + laterality['issues']

    if not inputs['applicable']:
        return {
            'drg_readiness_score': 1.0,
            'applicable': False,
            'missing_inputs': [],
            'issues': [],
        }

    if code['drg_code_valid'] is False:
        composite = 0.3
    elif len(inputs['missing_inputs']) >= 3:
        composite = 0.4
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

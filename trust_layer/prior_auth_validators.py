'''
Prior-authorization validation for UAE inpatient and specified outpatient claims.

DHA and DOH require pre-authorization for specified procedure categories before
claim submission. A claim for a PA-required procedure with no PA reference on
file is a documented rejection cause.

SCOPE: Deterministic rule-based checks. This module does not query any payer
system. It validates presence and structural validity of the PA reference on
the record. Live PA verification requires eClaimLink integration.
'''
import re
from datetime import datetime


PA_REQUIRED_PROCEDURE_PREFIXES = {
    '0S', '0P', '0T', '0L',
    '0B', '0C', '0D',
    '0F', '0G',
}

PA_REQUIRED_PROCEDURE_CODES = {
    '27447', '27446', '27445',
    '47562', '47563', '47564',
    '43239', '43235', '43236',
    '93000', '93306',
}

PA_REFERENCE_PATTERN = r'^[A-Z0-9\-]{6,20}$'


def _is_present(v):
    if v is None:
        return False
    s = str(v).strip().upper()
    return s != '' and s not in ('NAN', 'NAT', 'NONE')


def _parse_date(v):
    if not _is_present(v):
        return None
    try:
        return datetime.strptime(str(v).strip()[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def _requires_preauth(procedure_code):
    if not _is_present(procedure_code):
        return False
    code = str(procedure_code).strip().upper().replace('.', '')
    if code in PA_REQUIRED_PROCEDURE_CODES:
        return True
    if len(code) >= 2 and code[:2] in PA_REQUIRED_PROCEDURE_PREFIXES:
        return True
    return False


def validate_preauth(rec):
    issues = []
    procedure_code = rec.get('procedure_code')
    required = _requires_preauth(procedure_code)

    if not required:
        return {
            'pa_required': False,
            'pa_present': False,
            'pa_score': 1.0,
            'issues': [],
        }

    pa_ref = rec.get('preauth_reference')
    pa_valid_until = rec.get('preauth_valid_until')
    enc_date = rec.get('admission_date') or rec.get('registration_date')

    if not _is_present(pa_ref):
        return {
            'pa_required': True,
            'pa_present': False,
            'pa_score': 0.0,
            'issues': [f'PREAUTH-1: procedure {procedure_code} requires pre-authorization but no PA reference is recorded'],
        }

    score = 1.0

    if not re.match(PA_REFERENCE_PATTERN, str(pa_ref).strip().upper()):
        issues.append(f'PREAUTH-2: PA reference {pa_ref!r} does not match expected format')
        score = min(score, 0.5)

    pa_until = _parse_date(pa_valid_until)
    enc = _parse_date(enc_date)
    if pa_until is None:
        issues.append('PREAUTH-3: PA validity date missing or malformed')
        score = min(score, 0.6)
    elif enc is not None and pa_until < enc:
        issues.append(f'PREAUTH-4: PA expired on {pa_valid_until} but encounter was on {enc_date}')
        score = 0.0

    return {
        'pa_required': True,
        'pa_present': True,
        'pa_score': score,
        'issues': issues,
    }


def validate_preauth_batch(records):
    results = [validate_preauth(r) for r in records]
    total = len(results)
    required = sum(1 for r in results if r['pa_required'])
    if required == 0:
        return {
            'total': total, 'pa_required': 0, 'pa_missing': 0,
            'pa_expired': 0, 'pa_valid': 0, 'mean_score': 1.0,
        }
    missing = sum(1 for r in results if r['pa_required'] and not r['pa_present'])
    expired = sum(1 for r in results if any('PREAUTH-4' in i for i in r['issues']))
    valid = sum(1 for r in results if r['pa_required'] and r['pa_score'] >= 0.95)
    mean = sum(r['pa_score'] for r in results if r['pa_required']) / required
    return {
        'total': total,
        'pa_required': required,
        'pa_missing': missing,
        'pa_expired': expired,
        'pa_valid': valid,
        'mean_score': round(mean, 3),
    }

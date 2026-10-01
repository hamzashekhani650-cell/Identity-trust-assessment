'''
Consent flag validation for UAE HIE submissions.
Standalone module. Checks that consent metadata is present, valid, and
coherent with the record's submission state.

Rule-based, deterministic. No clinical judgment.
'''
from datetime import datetime


VALID_CONSENT_STATES = {'granted', 'denied', 'restricted', 'withdrawn', 'unknown'}

# Consent states that should block record sharing
BLOCKING_STATES = {'denied', 'withdrawn'}

# Consent states that allow sharing but with scope restrictions
SCOPED_STATES = {'restricted'}


def _is_present(value):
    if value is None:
        return False
    s = str(value).strip().lower()
    return s != '' and s not in ('nan', 'nat', 'none', 'null')


def _parse_iso_date(value):
    if not _is_present(value):
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def validate_consent(rec):
    '''
    rec: dict with optional fields:
      - consent_status: granted | denied | restricted | withdrawn | unknown
      - consent_date: ISO date the consent was captured
      - consent_scope: description of permitted uses (required if restricted)

    Returns dict with consent_score, consent_state, issues.
    '''
    issues = []
    state = str(rec.get('consent_status', '')).strip().lower()
    date_val = rec.get('consent_date')
    scope = rec.get('consent_scope')

    # Rule 1: consent_status must be present
    if not _is_present(state):
        issues.append('CONSENT-1: consent_status missing')
        return {
            'consent_score': 0.0,
            'consent_state': 'missing',
            'issues': issues,
        }

    # Rule 2: consent_status must be a recognised value
    if state not in VALID_CONSENT_STATES:
        issues.append(f'CONSENT-2: consent_status {state!r} not in {sorted(VALID_CONSENT_STATES)}')
        return {
            'consent_score': 0.3,
            'consent_state': state,
            'issues': issues,
        }

    score = 1.0

    # Rule 3: blocked states are a hard failure for sharing
    if state in BLOCKING_STATES:
        issues.append(f'CONSENT-3: consent_status is {state!r} — record must not be shared')
        score = 0.0

    # Rule 4: restricted consent requires a scope description
    if state in SCOPED_STATES and not _is_present(scope):
        issues.append('CONSENT-4: consent_status is restricted but consent_scope is missing')
        score = min(score, 0.4)

    # Rule 5: consent_date should be present and not in the future
    parsed = _parse_iso_date(date_val)
    if parsed is None:
        issues.append('CONSENT-5: consent_date missing or malformed')
        score = min(score, 0.5)
    else:
        if parsed > datetime.today():
            issues.append('CONSENT-6: consent_date is in the future')
            score = min(score, 0.4)

    return {
        'consent_score': round(score, 3),
        'consent_state': state,
        'issues': issues,
    }


def validate_consent_batch(records):
    '''Aggregate over a list of dicts. Returns summary stats and results.'''
    results = [validate_consent(r) for r in records]
    total = len(results)
    if total == 0:
        return {'count': 0, 'blocked': 0, 'restricted': 0, 'missing': 0, 'mean_score': 0.0}

    blocked = sum(1 for r in results if r['consent_state'] in BLOCKING_STATES)
    restricted = sum(1 for r in results if r['consent_state'] in SCOPED_STATES)
    missing = sum(1 for r in results if r['consent_state'] == 'missing')
    mean = sum(r['consent_score'] for r in results) / total

    return {
        'count': total,
        'blocked': blocked,
        'restricted': restricted,
        'missing': missing,
        'mean_score': round(mean, 3),
    }

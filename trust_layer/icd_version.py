'''
ICD-10-AM vs ICD-10-CM detection demonstrator.

HONEST SCOPE: This is a demonstrator. It detects structural patterns
that distinguish ICD-10-AM from ICD-10-CM codes, plus checks a small
curated list of known-divergent codes. It does NOT contain the full AM
or CM catalogues. Real deployment requires the official crosswalk
tables from AIHW (Australia, for AM) and CMS (USA, for CM).
'''
import re


CM_LATERALITY_7TH = {'A', 'D', 'S'}

CM_ONLY_EXAMPLES = {
    'S72.001A', 'S72.001D', 'S72.001S',
    'S06.0X0A', 'S06.0X0D',
    'M17.11', 'M17.12', 'M17.111', 'M17.112',
    'I50.21', 'I50.22',
}

AM_ONLY_EXAMPLES = {'U07.1', 'U08.9', 'U09.9', 'U10.9', 'Z11.52', 'Z11.59'}


def _is_present(v):
    if v is None:
        return False
    s = str(v).strip().upper()
    return s != '' and s not in ('NAN', 'NAT', 'NONE', '')


def detect_code_format(code):
    if not _is_present(code):
        return 'missing'
    c = str(code).strip().upper()

    if not re.match(r'^[A-Z]\d{2}(\.\d{1,4}[A-Z]?)?$', c):
        return 'malformed'

    if c in CM_ONLY_EXAMPLES:
        return 'curated-cm'
    if c in AM_ONLY_EXAMPLES:
        return 'curated-am'

    flat = c.replace('.', '')
    n = len(flat)

    if n <= 5:
        return 'shared'
    if n == 6:
        return 'am-leaning'
    if n == 7:
        if flat[-1] in CM_LATERALITY_7TH:
            return 'cm-specific'
        return 'ambiguous'
    return 'ambiguous'


def classify_code_set(codes):
    valid = [c for c in codes if _is_present(c)]
    if not valid:
        return {'dominant': 'unknown', 'counts': {}, 'confidence': 0.0, 'total_classified': 0}

    counts = {}
    for c in valid:
        f = detect_code_format(c)
        counts[f] = counts.get(f, 0) + 1

    total = sum(counts.values())
    cm_s = counts.get('cm-specific', 0) + counts.get('curated-cm', 0)
    am_s = counts.get('am-leaning', 0) + counts.get('curated-am', 0)
    shared = counts.get('shared', 0)

    if cm_s > 0 and am_s > 0:
        return {'dominant': 'mixed', 'counts': counts,
                'confidence': round(max(cm_s, am_s) / total, 3), 'total_classified': total}
    if cm_s > 0 and cm_s >= am_s:
        return {'dominant': 'CM', 'counts': counts,
                'confidence': round(cm_s / total, 3), 'total_classified': total}
    if am_s > 0 and am_s > cm_s:
        return {'dominant': 'AM', 'counts': counts,
                'confidence': round(am_s / total, 3), 'total_classified': total}
    if shared == total:
        return {'dominant': 'shared', 'counts': counts,
                'confidence': 1.0, 'total_classified': total}
    return {'dominant': 'unknown', 'counts': counts,
            'confidence': 0.0, 'total_classified': total}


def validate_icd_version_consistency(records, declared_system=None):
    codes = [r.get('diagnosis_code') for r in records]
    classification = classify_code_set(codes)
    dominant = classification['dominant']

    issues = []
    if dominant == 'mixed':
        issues.append('ICD-VERSION-1: file contains a mixture of AM-style and CM-style codes')
    if dominant == 'unknown':
        issues.append('ICD-VERSION-2: could not determine a dominant code system')
    if declared_system and dominant in ('AM', 'CM') and dominant != declared_system:
        issues.append(f'ICD-VERSION-3: declared system {declared_system!r} but codes look {dominant!r}')

    record_flags = []
    if dominant == 'CM':
        for r in records:
            if detect_code_format(r.get('diagnosis_code')) == 'am-leaning':
                record_flags.append({
                    'canonical_id': r.get('canonical_id', '?'),
                    'diagnosis_code': r.get('diagnosis_code'),
                    'issue': 'AM-style code in a CM-dominant file',
                })
    elif dominant == 'AM':
        for r in records:
            if detect_code_format(r.get('diagnosis_code')) == 'cm-specific':
                record_flags.append({
                    'canonical_id': r.get('canonical_id', '?'),
                    'diagnosis_code': r.get('diagnosis_code'),
                    'issue': 'CM-style code in an AM-dominant file',
                })

    return {
        'classification': classification,
        'issues': issues,
        'record_flags': record_flags,
    }

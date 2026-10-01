'''
ICD-10-AM vs ICD-10-CM detection demonstrator.

HONEST SCOPE: This is a demonstrator. It detects structural patterns
that distinguish ICD-10-AM from ICD-10-CM codes, plus checks a small
curated list of known-divergent codes. It does NOT contain the full AM
or CM catalogues. Real deployment requires the official crosswalk
tables from AIHW (Australia, for AM) and CMS (USA, for CM).

Structural signals:
  - ICD-10-CM uses 7th-character extensions for laterality
    (A = initial encounter, D = subsequent, S = sequela).
  - ICD-10-AM typically uses 5-character codes with optional 6th/7th
    for local extension, but does NOT use the A/D/S laterality set
    for the same purpose.
  - Codes with 3-5 characters are usually identical in both sets.
'''
import re


# 7th-character values specific to ICD-10-CM laterality
CM_LATERALITY_7TH = {'A', 'D', 'S'}

# A small curated list of codes that exist in ICD-10-CM and are
# structurally AM-incompatible. Demonstrator only — not exhaustive.
CM_ONLY_EXAMPLES = {
    'S72.001A', 'S72.001D', 'S72.001S',  # femur fracture, encounter-specific
    'S06.0X0A', 'S06.0X0D',              # concussion, encounter-specific
    'M17.11',   'M17.12',                # osteoarthritis, laterality explicit
    'M17.111',  'M17.112',
    'I50.21',   'I50.22',                # heart failure with laterality in CM
}

# A small curated list of AM-heavy codes. AM tends toward 5-char codes
# without the A/D/S encounter suffixes.
AM_ONLY_EXAMPLES = {
    'U07.1',   # COVID-19 — AM uses U07.1 as a special code
    'U08.9', 'U09.9', 'U10.9',
    'Z11.52', 'Z11.59',
}


def _is_present(v):
    if v is None:
        return False
    s = str(v).strip().upper()
    return s != '' and s not in ('NAN', 'NAT', 'NONE', '')


def detect_code_format(code):
    '''Classify a single code by structural pattern.

    Returns one of:
      'shared'       — 3-5 char, same in both systems
      'cm-specific'  — 7-char with A/D/S laterality, CM-style
      'am-leaning'   — 6-char extension typical of AM
      'curated-cm'   — in the curated CM-only list
      'curated-am'   — in the curated AM-only list
      'malformed'    — not recognisable as ICD-10 at all
      'ambiguous'    — long enough to be either, no distinguishing signal
    '''
    if not _is_present(code):
        return 'missing'
    c = str(code).strip().upper()

    # Structural check
    if not re.match(r'^[A-Z]\d{2}(\.\d{1,4})?$', c):
        return 'malformed'

    # Curated lists first
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
    '''Given a list of codes, estimate which system the file uses.

    Returns dict with:
      - dominant: 'AM', 'CM', 'shared', 'mixed', or 'unknown'
      - counts: per-category counts
      - confidence: fraction of codes matching the dominant system
    '''
    valid_codes = [c for c in codes if _is_present(c)]
    if not valid_codes:
        return {
            'dominant': 'unknown', 'counts': {}, 'confidence': 0.0,
            'total_classified': 0,
        }

    counts = {}
    for c in valid_codes:
        fmt = detect_code_format(c)
        counts[fmt] = counts.get(fmt, 0) + 1

    total = sum(counts.values())
    cm_signals = counts.get('cm-specific', 0) + counts.get('curated-cm', 0)
    am_signals = counts.get('am-leaning', 0) + counts.get('curated-am', 0)
    shared = counts.get('shared', 0)

    # Decide
    if cm_signals > 0 and am_signals > 0:
        dominant = 'mixed'
        confidence = round(max(cm_signals, am_signals) / total, 3)
    elif cm_signals > 0 and cm_signals >= am_signals:
        dominant = 'CM'
        confidence = round(cm_signals / total, 3)
    elif am_signals > 0 and am_signals > cm_signals:
        dominant = 'AM'
        confidence = round(am_signals / total, 3)
    elif shared == total:
        dominant = 'shared'
        confidence = 1.0
    else:
        dominant = 'unknown'
        confidence = 0.0

    return {
        'dominant': dominant,
        'counts': counts,
        'confidence': confidence,
        'total_classified': total,
    }


def validate_icd_version_consistency(records, declared_system=None):
    '''Given a list of records (dicts with 'diagnosis_code'), determine
    whether the code style is internally consistent.

    If declared_system is provided ('AM' or 'CM'), check for mismatch.

    Returns dict with classification + per-record issues.
    '''
    codes = [r.get('diagnosis_code') for r in records]
    classification = classify_code_set(codes)
    dominant = classification['dominant']

    issues = []

    if dominant == 'mixed':
        issues.append(
            'ICD-VERSION-1: file contains a mixture of AM-style and CM-style codes'
        )
    if dominant == 'unknown':
        issues.append(
            'ICD-VERSION-2: could not determine a dominant code system'
        )
    if declared_system and dominant in ('AM', 'CM') and dominant != declared_system:
        issues.append(
            f'ICD-VERSION-3: declared system {declared_system!r} but codes look {dominant!r}'
        )

    # Per-record outlier flags
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

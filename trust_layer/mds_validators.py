'''
Minimum Data Set (MDS) validation for UAE HIEs.
Checks that records carry the mandatory fields required by NABIDH
and Malaffi before submission. Rule-based, deterministic.

Mapping intent (citations to be filled in once institutional access
to the DOH/Nabidh specification is confirmed):
  - Patient demographics
  - Encounter
  - Clinical coding
'''
import re
from datetime import datetime


# ============================================================
# MDS SCHEMA
# ============================================================
MDS_REQUIRED_FIELDS = {
    'patient_demographics': {
        'emirates_id':   {'label': 'Emirates ID / National Identifier', 'weight': 1.5},
        'given_name':    {'label': 'Given Name',                        'weight': 1.0},
        'family_name':   {'label': 'Family Name',                       'weight': 1.0},
        'date_of_birth': {'label': 'Date of Birth',                     'weight': 1.5},
        'gender':        {'label': 'Gender',                            'weight': 1.0},
        'nationality':   {'label': 'Nationality',                       'weight': 0.7},
    },
    'encounter': {
        'episode_id':       {'label': 'Episode Identifier',             'weight': 1.0},
        'admission_date':   {'label': 'Admission Date',                 'weight': 1.5},
        'discharge_date':   {'label': 'Discharge Date',                 'weight': 1.0},
        'source_facility':  {'label': 'Source Facility',                'weight': 1.0},
    },
    'clinical': {
        'diagnosis_code':   {'label': 'Primary Diagnosis Code',         'weight': 2.0},
        'procedure_code':   {'label': 'Primary Procedure Code',         'weight': 1.0},
    },
}


# ============================================================
# VALUE-LEVEL CHECKS
# ============================================================
VALID_GENDERS = {'M', 'F', 'MALE', 'FEMALE', 'OTHER', 'UNKNOWN', 'O', 'U'}


def _is_present(value):
    if value is None:
        return False
    s = str(value).strip()
    return s != '' and s.lower() not in ('nan', 'nat', 'none')


def _is_valid_iso_date(value):
    if not _is_present(value):
        return False
    try:
        datetime.strptime(str(value).strip()[:10], '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def check_field_presence(rec, category):
    '''Returns (present_count, total_count, missing_labels) for a category.'''
    schema = MDS_REQUIRED_FIELDS.get(category, {})
    missing_labels = []
    present = 0
    total = 0
    for field, meta in schema.items():
        total += 1
        if _is_present(rec.get(field)):
            present += 1
        else:
            missing_labels.append(meta['label'])
    return present, total, missing_labels


def check_gender_validity(gender_value):
    '''Returns 1.0 if valid, 0.0 if missing, 0.3 if not in allowed set.'''
    if not _is_present(gender_value):
        return 0.0
    if str(gender_value).strip().upper() in VALID_GENDERS:
        return 1.0
    return 0.3


def check_mds_completeness(rec):
    '''Returns a dict with per-category presence ratios and overall MDS score.'''
    out = {}
    total_weight_present = 0.0
    total_weight = 0.0

    for category, schema in MDS_REQUIRED_FIELDS.items():
        cat_present = 0
        cat_total = 0
        cat_missing = []
        for field, meta in schema.items():
            w = meta['weight']
            total_weight += w
            cat_total += 1
            if _is_present(rec.get(field)):
                cat_present += 1
                total_weight_present += w
            else:
                cat_missing.append(meta['label'])

        out[f'{category}_present'] = cat_present
        out[f'{category}_total'] = cat_total
        out[f'{category}_missing'] = cat_missing
        out[f'{category}_score'] = round(cat_present / cat_total, 2) if cat_total else 1.0

    # Weighted overall MDS score
    out['mds_score'] = round(total_weight_present / total_weight, 3) if total_weight else 0.0

    # Gender sanity check (separate from presence)
    out['gender_validity'] = check_gender_validity(rec.get('gender'))

    return out


def find_mds_gaps(records):
    '''Returns a summary dict of the most common missing MDS fields across
    a batch of records. Useful for showing hospitals where their data is
    weakest.'''
    from collections import Counter
    missing_counter = Counter()
    for r in records:
        for category, schema in MDS_REQUIRED_FIELDS.items():
            for field, meta in schema.items():
                if not _is_present(r.get(field)):
                    missing_counter[meta['label']] += 1
    return dict(missing_counter.most_common())

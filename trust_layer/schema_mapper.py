'''
Smart schema mapper for hospital CSV exports.

Real hospitals do not use consistent column names. One file has
"Date_of_Birth", another has "DOB", another has "birth date". This module
resolves incoming column names to canonical field names using three
strategies in order:

  1. Exact normalized match against a synonym dictionary
  2. Fuzzy string match against the same dictionary
  3. Content-based inference (e.g. a column of 15-digit numbers beginning
     with 784 is almost certainly an Emirates ID)

Only strategy 1 is exact. Strategies 2 and 3 are returned as "inferred"
so the UI can flag them to the user.
'''
import re
from difflib import SequenceMatcher


CANONICAL_FIELDS = [
    'emirates_id', 'given_name', 'family_name', 'date_of_birth',
    'gender', 'nationality', 'source_facility', 'registration_date',
    'canonical_id', 'episode_id', 'encounter_type', 'admission_date',
    'discharge_date', 'diagnosis_code', 'procedure_code',
    'secondary_diagnoses', 'discharge_summary', 'drg_code', 'laterality',
    'consent_status', 'consent_date', 'consent_scope',
    'preauth_reference', 'preauth_valid_until',
    'triage_level', 'total_cost_aed',
]


SYNONYMS = {
    'emirates_id': [
        'emiratesid', 'emirates', 'eid', 'nationalid', 'nationalidentifier',
        'patientid', 'patientidentifier', 'patientmrn', 'mrn', 'prn',
        'prnidentifier', 'identifier', 'id', 'uid', 'patientuid',
        'uniqueidentifier', 'primaryidentifier', 'abha', 'abhanumber',
        'aadhaar', 'aadhaarnumber', 'nhsnumber', 'nhs',
    ],
    'given_name': [
        'givenname', 'firstname', 'forename', 'given', 'first', 'namefirst',
        'patientfirstname', 'patientgivenname', 'firstnm',
    ],
    'family_name': [
        'familyname', 'lastname', 'surname', 'family', 'last', 'namelast',
        'patientlastname', 'patientfamilyname', 'lastnm',
    ],
    'date_of_birth': [
        'dateofbirth', 'dob', 'birthdate', 'birthday', 'datebirth',
        'patientdob', 'birthdt', 'dateofbirthpatient',
    ],
    'gender': ['sex', 'patientgender', 'administrativesex', 'sexassigned'],
    'nationality': ['country', 'countryoforigin', 'citizenship'],
    'source_facility': [
        'facility', 'hospital', 'sourcefacility', 'facilityname',
        'hospitalname', 'sourcehospital', 'providerfacility',
    ],
    'registration_date': ['registrationdate', 'regdate', 'regdt', 'registeredon'],
    'canonical_id': ['canonicalid', 'recordid', 'recordidentifier', 'sourcerecordid'],
    'episode_id': ['episodeid', 'encounterid', 'visitid', 'visitnumber', 'encounternumber'],
    'encounter_type': ['encountertype', 'visittype', 'admissiontype', 'inpatientflag', 'patienttype'],
    'admission_date': ['admissiondate', 'admitdate', 'admittedon', 'dateofadmission'],
    'discharge_date': ['dischargedate', 'dischargedon', 'dateofdischarge'],
    'diagnosis_code': ['diagnosiscode', 'icd', 'icdcode', 'icd10', 'diagnosis', 'primarydiagnosis', 'dxcode'],
    'procedure_code': ['procedurecode', 'cpt', 'cptcode', 'proc', 'proccode', 'primaryprocedure'],
    'secondary_diagnoses': ['secondarydiagnoses', 'secondarydiagnosis', 'secondarydx'],
    'discharge_summary': ['dischargesummary', 'dischargeletter', 'summaryofdischarge'],
    'drg_code': ['drg', 'drgcode', 'irdrg', 'irdrgcode'],
    'laterality': ['laterality', 'side', 'bodyside'],
    'consent_status': ['consentstatus', 'consent', 'consentstate'],
    'consent_date': ['consentdate', 'dateofconsent'],
    'consent_scope': ['consentscope', 'consenttype'],
    'preauth_reference': ['preauthreference', 'preauth', 'preauthnumber', 'panumber'],
    'preauth_valid_until': ['preauthvaliduntil', 'paexpirydate', 'preauthexpiry', 'paexpiry'],
    'triage_level': ['triagelevel', 'triage', 'acuity', 'acuitylevel'],
    'total_cost_aed': ['totalcostaed', 'totalcost', 'amount', 'billedamount', 'claimamount'],
}


def _normalize(name):
    if name is None:
        return ''
    s = str(name).strip().lower()
    s = re.sub(r'[\s_\-\.\/]+', '', s)
    return s


def _content_hint(values):
    clean = [str(v).strip() for v in values if v is not None and str(v).strip() != '']
    if not clean:
        return None, 0.0
    sample = clean[:200]
    n = len(sample)

    def frac(pred):
        return sum(1 for v in sample if pred(v)) / n

    if frac(lambda v: re.match(r'^784\d{12}$', re.sub(r'[\s\-]', '', v))) > 0.8:
        return 'emirates_id', 0.95
    if frac(lambda v: re.match(r'^\d{12}$', re.sub(r'[\s\-]', '', v))) > 0.9:
        return 'emirates_id', 0.7
    if frac(lambda v: re.match(r'^\d{10}$', re.sub(r'[\s\-]', '', v))) > 0.9:
        return 'emirates_id', 0.5

    if frac(lambda v: re.match(r'^\d{4}-\d{2}-\d{2}', v)) > 0.85:
        years = []
        for v in sample:
            try:
                years.append(int(v[:4]))
            except (ValueError, TypeError):
                continue
        if years:
            min_y = min(years)
            if min_y < 1950:
                return 'date_of_birth', 0.9
            if min_y >= 2020:
                return 'admission_date', 0.6
        return None, 0.0

    if frac(lambda v: v.upper() in ('M', 'F', 'O', 'U', 'MALE', 'FEMALE')) > 0.85:
        return 'gender', 0.95

    return None, 0.0


def _fuzzy_match(normalized_name):
    best_field = None
    best_score = 0.0
    for field, synonyms in SYNONYMS.items():
        candidates = [_normalize(field)] + synonyms
        for c in candidates:
            score = SequenceMatcher(None, normalized_name, c).ratio()
            if score > best_score:
                best_score = score
                best_field = field
    if best_score >= 0.80:
        return best_field, best_score
    return None, 0.0


def map_columns(df, content_inference=True):
    mapping = {}
    inferred = []
    used_canonical = set()

    canonical_norms = {f: _normalize(f) for f in CANONICAL_FIELDS}

    for col in df.columns:
        norm = _normalize(col)
        matched = False
        for field, cn in canonical_norms.items():
            if cn == norm and field not in used_canonical:
                mapping[col] = field
                used_canonical.add(field)
                matched = True
                break
        if matched:
            continue
        for field, syns in SYNONYMS.items():
            if field in used_canonical:
                continue
            if norm in syns:
                mapping[col] = field
                used_canonical.add(field)
                matched = True
                break

    for col in df.columns:
        if col in mapping:
            continue
        norm = _normalize(col)
        field, score = _fuzzy_match(norm)
        if field and field not in used_canonical:
            mapping[col] = field
            used_canonical.add(field)

    if content_inference:
        for col in df.columns:
            if col in mapping:
                continue
            sample = df[col].dropna().astype(str).head(200).tolist()
            field, conf = _content_hint(sample)
            if field and field not in used_canonical:
                mapping[col] = field
                used_canonical.add(field)
                inferred.append({'column': col, 'field': field, 'confidence': conf})

    unresolved = [c for c in df.columns if c not in mapping]
    return mapping, unresolved, inferred
